"""Talking to the mouse over hidraw (I/O). No external dependencies.

Finds EVERY configuration interface present (the 2.4G dongle `FA07` and/or the
mouse itself `FA08`) and sends the command to all of them — whichever one is in
the active mode will take it. Commands are repeated a few times to beat the
wireless mouse's sleep.
"""
import os
import glob
import time
import select
import fcntl

from .protocol import (build_color, build_breathing, build_cycle, build_off,
                       build_commit, build_read, build_dpi_table_bytes,
                       build_dpi_effect, byte_to_dpi, dpi_to_byte,
                       SPEED_BREATHING, SPEED_CYCLE, DPI_ADDR, DPI_STAGES,
                       DPI_EFFECT_ADDR, build_buttons, build_media,
                       BUTTON_ADDR, BUTTON_COUNT, BTN_EXTENDED)
from . import state

EFFECT_NAMES = {0x00: "Cycle", 0x01: "Breathing", 0x02: "Steady", 0x04: "Off"}
LED_ADDR = 0xA0

VID = 0x25A7
PIDS = [0xFA07, 0xFA08]        # FA07 = 2.4G receiver ; FA08 = mouse (cable/BT)
TARGET_INTERFACE = 1

RETRIES = 4                    # the first command sometimes only wakes the mouse
RETRY_DELAY = 0.02             # seconds between repeats


class DeviceNotFound(Exception):
    """No reachable configuration interface accepted the command."""


def _IOC(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (typ << 8) | nr


def _HIDIOCSFEATURE(size):
    return _IOC(1 | 2, ord('H'), 0x06, size)     # _IOC_WRITE|_IOC_READ


def find_devices():
    """List the configuration interfaces present: [(dev_path, pid), ...]."""
    found = []
    for pid in PIDS:
        for node in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
            name = os.path.basename(node)
            try:
                uevent = open(os.path.join(node, 'device', 'uevent')).read().upper()
            except OSError:
                continue
            if f"{VID:08X}" not in uevent or f"{pid:08X}" not in uevent:
                continue
            path = os.path.realpath(os.path.join(node, 'device'))
            iface = None
            for _ in range(6):
                candidate = os.path.join(path, 'bInterfaceNumber')
                if os.path.exists(candidate):
                    try:
                        iface = int(open(candidate).read().strip(), 16)
                    except ValueError:
                        iface = None
                    break
                path = os.path.dirname(path)
            if iface == TARGET_INTERFACE:
                found.append((f"/dev/{name}", pid))
    return found


def _send_feature(dev_path, data):
    fd = os.open(dev_path, os.O_RDWR)
    try:
        fcntl.ioctl(fd, _HIDIOCSFEATURE(len(data)), bytearray(data))
    finally:
        os.close(fd)


def _apply(dev_path, packets):
    """Send every packet (with repeats) and close with ONE commit, as the app does."""
    for packet in packets:
        for _ in range(RETRIES):
            _send_feature(dev_path, packet)
            time.sleep(RETRY_DELAY)
    _send_feature(dev_path, build_commit())


def _mode_label(pid):
    return "2.4G" if pid == 0xFA07 else "cable"


def send_packets(packets):
    """Send `packets` to every interface present, with one commit at the end.

    Returns the routes that accepted it (e.g. ['2.4G', 'cable']). Raises
    DeviceNotFound when none did.
    """
    devices = find_devices()
    if not devices:
        raise DeviceNotFound(
            "mouse not found — check the dongle/cable, the udev rule (0666) "
            "and whether a VM has grabbed the device")
    accepted = []
    for dev, pid in devices:
        try:
            _apply(dev, packets)
            accepted.append(_mode_label(pid))
        except OSError:
            pass
    if not accepted:
        raise DeviceNotFound("no interface accepted the command")
    return accepted


def send_packet(packet):
    """Send a single packet (shortcut for send_packets)."""
    return send_packets([packet])


def send_color(r, g, b, brightness=0xFF):
    routes = send_packet(build_color(r, g, b, brightness=brightness))
    state.save({"effect": "Steady", "rgb": [r, g, b], "brightness": brightness})
    return routes


def send_breathing(r, g, b, brightness=0xFF, speed=SPEED_BREATHING):
    routes = send_packet(build_breathing(r, g, b, brightness=brightness, speed=speed))
    state.save({"effect": "Breathing", "rgb": [r, g, b],
                "brightness": brightness, "speed": speed})
    return routes


def send_cycle(r, g, b, brightness=0xFF, speed=SPEED_CYCLE):
    routes = send_packet(build_cycle(r, g, b, brightness=brightness, speed=speed))
    state.save({"effect": "Cycle", "rgb": [r, g, b],
                "brightness": brightness, "speed": speed})
    return routes


def send_off():
    routes = send_packet(build_off())
    saved = state.load()
    saved["effect"] = "Off"
    state.save(saved)
    return routes


# --- Reading the real hardware state ----------------------------------------
def _read_from(dev_path, addr, length, timeout):
    """Try to read `addr` through one interface. Returns the report 09 or None."""
    fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
    try:
        for _ in range(RETRIES):        # repeat: the first one often just wakes it
            fcntl.ioctl(fd, _HIDIOCSFEATURE(17), bytearray(build_read(addr, length)))
            time.sleep(RETRY_DELAY)
        end = time.monotonic() + timeout
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return None
            if not select.select([fd], [], [], remaining)[0]:
                return None
            try:
                data = os.read(fd, 64)
            except (BlockingIOError, OSError):
                continue
            # check BOTH address bytes: matching only the low one would let a
            # reply from page 0 pass as a reply from another page
            if (len(data) >= 12 and data[0] == 0x09 and data[1] == 0x08
                    and data[3] == ((addr >> 8) & 0xFF)
                    and data[4] == (addr & 0xFF)):
                return data
    finally:
        os.close(fd)


def read_register(addr, length=8, timeout=0.6):
    """Send the read request and capture the reply (interrupt IN, Report ID 09).

    Returns the report bytes, or None when no interface answered.

    Tries EVERY interface present: with the dongle and the cable connected at
    the same time it is the mouse node (FA08) that answers, not necessarily the
    first in the list — pinning `devices[0]` made reads fail silently.
    """
    devices = find_devices()
    if not devices:
        raise DeviceNotFound("mouse not found")
    for dev, _ in devices:
        try:
            reply = _read_from(dev, addr, length, timeout)
        except OSError:
            continue
        if reply:
            return reply
    return None


def read_dpi_bytes():
    """Read the RAW bytes of the five DPI stages. Returns [b1..b5] or None.

    Three reads in the same shapes the app uses to write: 0x0C (LEN 8, stages
    1-2), 0x14 (LEN 8, stages 3-4) and 0x1C (LEN 4, stage 5).

    It returns BYTES rather than DPI on purpose: changing one stage means
    rewriting the other four EXACTLY as they were, and byte -> DPI -> byte is
    not the identity above 0xBD.
    """
    out = []
    for addr, length in ((DPI_ADDR, 8), (DPI_ADDR + 8, 8), (DPI_ADDR + 16, 4)):
        reply = read_register(addr, length)
        if not reply or len(reply) < 6 + length:
            return None
        data = reply[6:6 + length]
        out += [data[i] for i in range(0, length, 4)]
    return out


def read_dpi_table():
    """Read the five DPI stages from the hardware, in DPI. Returns a list or None."""
    raw = read_dpi_bytes()
    return None if raw is None else [byte_to_dpi(b) for b in raw]


def send_dpi_bytes(values):
    """Write the five stages from the raw register bytes."""
    routes = send_packets(build_dpi_table_bytes(values))
    state.save({**state.load(), "dpi_stages": [byte_to_dpi(b) for b in values]})
    return routes


def send_dpi_table(stages):
    """Write all five stages at once, from values in DPI."""
    return send_dpi_bytes([dpi_to_byte(d) for d in stages])


def send_dpi(stage, dpi):
    """Change ONE stage (1 to 5), preserving the others byte for byte.

    The protocol writes the whole table, so the current one is read first. If
    that read fails we abort: rewriting the other four stages with a guessed
    value is exactly what the project's rule forbids.

    Returns (routes, table_in_dpi) — the RESULTING table, already quantised by
    the hardware step, not what was asked for.
    """
    if not 1 <= stage <= DPI_STAGES:
        raise ValueError(f"stage must be between 1 and {DPI_STAGES}")
    raw = read_dpi_bytes()
    if raw is None:
        raise DeviceNotFound(
            "could not read the current DPI table — without it the other "
            "stages would be rewritten with a guess. Check the dongle and "
            "try again.")
    raw[stage - 1] = dpi_to_byte(dpi)
    routes = send_dpi_bytes(raw)
    return routes, [byte_to_dpi(b) for b in raw]


def send_dpi_all(dpi):
    """Apply the SAME DPI to all five stages — the mouse ends up with one DPI.

    With every stage equal, the mouse's DPI button still cycles but no longer
    changes the sensitivity. Returns (routes, resulting_dpi).
    """
    byte = dpi_to_byte(dpi)
    return send_dpi_bytes([byte] * DPI_STAGES), byte_to_dpi(byte)


def read_buttons():
    """Read the 16 button records. Returns [(TYPE, P1, P2), ...] or None.

    It hands back the raw bytes so that changing one button can rewrite the
    other fifteen exactly as they were — including action types we cannot
    interpret yet.
    """
    out = []
    for i in range(0, BUTTON_COUNT, 2):
        reply = read_register(BUTTON_ADDR + 4 * i, 8)
        if not reply or len(reply) < 14:
            return None
        data = reply[6:14]
        out.append(tuple(data[0:3]))
        out.append(tuple(data[4:7]))
    return out


def send_buttons(actions):
    """Write the whole button table (16 actions)."""
    return send_packets(build_buttons(actions))


def _current_button_table():
    current = read_buttons()
    if current is None:
        raise DeviceNotFound(
            "could not read the button table — without it the other buttons "
            "would be rewritten with a guess. Check the dongle and try again.")
    return current


def send_button(index, action):
    """Change ONE button (index 0-15), preserving the others byte for byte."""
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"button index must be between 0 and {BUTTON_COUNT - 1}")
    table = _current_button_table()
    table[index] = tuple(action)
    return send_buttons(table), table


def send_media(index, usage):
    """Assign a multimedia key to button `index`.

    Writes the extended slot first and only then the button table, in the same
    order the official app uses.
    """
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"button index must be between 0 and {BUTTON_COUNT - 1}")
    table = _current_button_table()
    table[index] = BTN_EXTENDED
    routes = send_packets([build_media(index, usage)] + build_buttons(table))
    return routes, table


def read_dpi_effect():
    """Read the DPI Effect group. Returns (on, (byte_0x4E, byte_0x50)) or None."""
    reply = read_register(DPI_EFFECT_ADDR, 6)
    if not reply or len(reply) < 12:
        return None
    data = reply[6:12]                  # 0x4C ck | 0x4E ck | 0x50 ck
    return bool(data[0]), (data[2], data[4])


def send_dpi_effect(on):
    """Turn the DPI stage indicator LED on (Steady) or off.

    When turning it on, the still-undecoded 0x4E/0x50 fields are read first and
    handed back untouched instead of being overwritten with captured values.
    """
    if on:
        current = read_dpi_effect()
        if current is None:
            raise DeviceNotFound(
                "could not read the DPI Effect state — without it the "
                "0x4E/0x50 fields, which are still undecoded, would be "
                "overwritten. Check the dongle and try again.")
        packet = build_dpi_effect(True, tail=current[1])
    else:
        packet = build_dpi_effect(False)
    routes = send_packets([packet])
    state.save({**state.load(), "dpi_effect": bool(on)})
    return routes


def read_led_state():
    """Read the LED state straight from the mouse.

    Returns a dict in the same shape as the persisted state, or None when the
    read fails.
    """
    try:
        reply = read_register(LED_ADDR, 8)
    except (DeviceNotFound, OSError):
        return None
    if not reply or len(reply) < 12:
        return None
    effect = EFFECT_NAMES.get(reply[6], "Steady")
    return {"effect": effect, "rgb": [reply[7], reply[8], reply[9]],
            "speed": reply[10], "brightness": reply[11]}

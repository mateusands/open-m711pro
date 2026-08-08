"""Redragon M711 Pro protocol — packet construction (pure logic, no I/O).

See the Protocol section of the README. Every function here is testable by
byte-matching against real USB captures (tests/test_protocol.py).
"""

# The byte sum settles at 0x55 (mod 256). This holds for the OUTER checksum (the
# 17-byte packet) and for every memory RECORD, whatever its length.
CHECKSUM_TARGET = 0x55

LED_ADDR = 0xA0           # LED register
# EFFECT byte (data[0]) — decoded from USB captures.
# The official app names the effects Steady, Respiration, Neon, Streaming and
# OFF; 0x00 is most likely "Streaming" but that mapping is not confirmed yet.
EFFECT_CYCLE = 0x00       # running / rainbow cycle
EFFECT_BREATHING = 0x01   # breathing (pulses the colour)
EFFECT_STEADY = 0x02      # static colour
EFFECT_OFF = 0x04         # off
DEFAULT_SPEED = 0x96      # data[4] — effect speed (lower = faster)
SPEED_BREATHING = 0xBE    # observed default speed for breathing
SPEED_CYCLE = 0x13        # observed default speed for the cycle
BRIGHTNESS_MAX = 0xFF     # data[5] — 100%; below that it is the direct % (50% = 0x32)

# Backwards-compatible aliases
MODE_ON = EFFECT_STEADY
MODE_OFF = EFFECT_OFF


def checksum(data):
    """The byte that settles the sum of `data` at CHECKSUM_TARGET (mod 256)."""
    return (CHECKSUM_TARGET - sum(data)) & 0xFF


def record(values):
    """A memory record: the data followed by the checksum that settles it at 0x55.

    The checksum rule applies per record, not only to the packet — verified
    against a full hardware dump.
    """
    values = [v & 0xFF for v in values]
    return values + [checksum(values)]


def build_write(addr, data):
    """A 17-byte write packet (opcode 0x07) with a 16-bit address.

    Layout: 08 07 00 <ADDR_HI> <ADDR_LO> <LEN> <data...> <padding> <cksum>
    """
    data = [b & 0xFF for b in data]
    payload = ([0x08, 0x07, 0x00, (addr >> 8) & 0xFF, addr & 0xFF, len(data)]
               + data)
    payload += [0x00] * (16 - len(payload))
    return bytes(payload + [checksum(payload)])


def build_led(effect, r, g, b, speed=DEFAULT_SPEED, brightness=BRIGHTNESS_MAX):
    """Packet for the 0xA0 register (17 bytes).

    Layout: 08 07 00 00 A0 07 | EFFECT R G B SPEED BRIGHTNESS <inner> | 00 00 00 <cksum>
    <inner> is the record checksum over the 7 data bytes.
    """
    data = [effect, r & 0xFF, g & 0xFF, b & 0xFF, speed & 0xFF, brightness & 0xFF]
    return build_write(LED_ADDR, record(data))


def build_color(r, g, b, brightness=BRIGHTNESS_MAX):
    """Solid colour command (LED on), with optional brightness (0x00-0xFF)."""
    return build_led(EFFECT_STEADY, r, g, b, brightness=brightness)


def build_breathing(r, g, b, brightness=BRIGHTNESS_MAX, speed=SPEED_BREATHING):
    """Breathing effect (pulses the chosen colour)."""
    return build_led(EFFECT_BREATHING, r, g, b, speed=speed, brightness=brightness)


def build_cycle(r, g, b, brightness=BRIGHTNESS_MAX, speed=SPEED_CYCLE):
    """Running / rainbow cycle effect."""
    return build_led(EFFECT_CYCLE, r, g, b, speed=speed, brightness=brightness)


def build_off():
    """Turn the LED off (the colour is irrelevant once it is dark)."""
    return build_led(EFFECT_OFF, 0, 0, 0)


def build_commit():
    """Apply/save command (opcode 0x04), observed after every write burst."""
    payload = [0x08, 0x04] + [0x00] * 14
    return bytes(payload + [checksum(payload)])


def build_read(addr, length=8):
    """READ request (Report ID 08, opcode 08): asks for `length` bytes at `addr`.

    The reply comes back over interrupt IN as Report ID 09, same layout.

    The address is 16-bit — the main configuration lives at 0x0000-0x00A8, but
    the official app scans as far as 0x1981.
    """
    payload = ([0x08, 0x08, 0x00, (addr >> 8) & 0xFF, addr & 0xFF, length & 0xFF]
               + [0x00] * 10)
    return bytes(payload + [checksum(payload)])


# --- DPI (register 0x000C) --------------------------------------------------
DPI_ADDR = 0x000C
DPI_STAGES = 5            # the app writes exactly five stages
DPI_MIN = 100             # range offered by the app's slider
DPI_MAX = 16000
DPI_BYTE_MAX = 0xBD       # firmware ceiling (~15833 DPI); the app labels it 16000
DPI_STEP = 250 / 3        # ~83.33 DPI per register unit


def dpi_to_byte(dpi):
    """DPI -> register byte. Step of ~83.33 DPI: n = round(DPI * 3 / 250) - 1.

    Validated against six values read off the official app (700, 1000, 2000,
    4000, 8000, 10000) and cross-checked against the m913-ctl code table. The
    result is clamped to the range the firmware is known to hold.
    """
    dpi = max(DPI_MIN, min(DPI_MAX, int(dpi)))
    n = (dpi * 3 + 125) // 250 - 1        # round to the nearest step
    return max(0x00, min(DPI_BYTE_MAX, n))


def byte_to_dpi(n):
    """Register byte -> DPI (inverse of dpi_to_byte, without the clamp)."""
    return round((n + 1) * 250 / 3)


def build_dpi_table_bytes(values):
    """The THREE DPI table packets, from the raw register bytes.

    Each entry takes 4 bytes (`X Y 00 <cksum>`); X and Y are the axes, kept
    equal by the official app. We only emit the packet shapes seen in captures:
    0x0C with LEN 8, 0x14 with LEN 8 and 0x1C with LEN 4. Writing a single
    stage on its own has never been observed, so it is not offered.

    This is the preferred entry point when preserving stages that must not
    change: byte -> DPI -> byte is NOT the identity above 0xBD, so rebuilding
    the table from DPI values would silently lower any such stage.
    """
    if len(values) != DPI_STAGES:
        raise ValueError(f"the table needs {DPI_STAGES} stages, got {len(values)}")
    e = [record([v & 0xFF] * 2 + [0x00]) for v in values]
    return [build_write(DPI_ADDR, e[0] + e[1]),
            build_write(DPI_ADDR + 8, e[2] + e[3]),
            build_write(DPI_ADDR + 16, e[4])]


def build_dpi_table(stages):
    """Like build_dpi_table_bytes, but taking the five values in DPI."""
    return build_dpi_table_bytes([dpi_to_byte(d) for d in stages])


# --- Buttons (registers 0x0060-0x009F) --------------------------------------
# Sixteen 4-byte records: TYPE, P1, P2, record checksum. They are written as
# eight LEN 8 packets (two buttons each), exactly as the official app does.
#
# The action type table was decoded by applying a profile with known actions
# through the official app and reading memory before and after. The 16-entry
# layout and the extended slot address come from m913-ctl
# (github.com/Qehbr/m913-ctl, GPL-3.0), which mapped the same Compx chip on the
# Redragon M913 — both were verified against this mouse before being used.
BUTTON_ADDR = 0x0060
BUTTON_COUNT = 16
BUTTONS_PER_PACKET = 2

BTN_NONE = (0x00, 0x00, 0x00)      # no action / disabled
BTN_EXTENDED = (0x05, 0x00, 0x00)  # the action lives in the extended slot

MOUSE_LEFT = 0x01
MOUSE_RIGHT = 0x02
MOUSE_MIDDLE = 0x04
MOUSE_BACK = 0x08
MOUSE_FORWARD = 0x10


def btn_mouse(mask):
    """A plain mouse button. `mask` is one of the MOUSE_* constants."""
    return (0x01, mask & 0xFF, 0x00)


def btn_dpi_up():
    return (0x02, 0x02, 0x00)


def btn_dpi_down():
    return (0x02, 0x03, 0x00)


def btn_dpi_cycle():
    return (0x02, 0x01, 0x00)


def btn_fire(speed=0x3A, clicks=3):
    """Repeated click. `speed` 3-255 (lower = faster), `clicks` 0-3.

    The app's "Three click" is this same type with speed 0x32 and 3 clicks.
    """
    return (0x04, speed & 0xFF, clicks & 0xFF)


def btn_three_click():
    return btn_fire(speed=0x32, clicks=3)


def btn_rgb_toggle():
    """Toggle the LED on/off.

    NOTE: m913-ctl assigns 0x07 to "polling switch" and 0x08 to "led toggle" —
    the opposite of this. We follow what was measured on this mouse: assigning
    "RGB ON/OFF" through the official app left the register at 0x07. The
    disagreement is recorded in the README and still needs a tie-breaker.
    """
    return (0x07, 0x00, 0x00)


def btn_polling_switch():
    """Cycle the USB polling rate. See the caveat on btn_rgb_toggle()."""
    return (0x08, 0x00, 0x00)


def build_buttons(actions):
    """The EIGHT packets that write the whole button table.

    `actions` is 16 (TYPE, P1, P2) tuples, one per button index. The protocol
    writes the entire table, so changing one button means passing the other
    fifteen through untouched (see device.send_button).
    """
    if len(actions) != BUTTON_COUNT:
        raise ValueError(f"the table needs {BUTTON_COUNT} actions, "
                         f"got {len(actions)}")
    packets = []
    for i in range(0, BUTTON_COUNT, BUTTONS_PER_PACKET):
        data = []
        for action in actions[i:i + BUTTONS_PER_PACKET]:
            data += record(list(action))
        packets.append(build_write(BUTTON_ADDR + 4 * i, data))
    return packets


# --- Extended slot: multimedia and keyboard ---------------------------------
# Actions that do not fit the 3 bytes of a basic record live in a 32-byte slot.
# The button record holds BTN_EXTENDED and the slot holds the press and release
# events.
EXT_SLOT_BASE = 0x0100
EXT_SLOT_STRIDE = 0x20
EVENT_MEDIA_DOWN = 0x82        # press, HID Consumer Page
EVENT_MEDIA_UP = 0x42          # release

# HID Consumer Page usages. The first four were confirmed on this mouse; the
# rest come from the m913-ctl table and have not been tested here.
MEDIA_PLAY_PAUSE = 0x00CD      # confirmed
MEDIA_NEXT = 0x00B5            # confirmed
MEDIA_PREVIOUS = 0x00B6        # confirmed
MEDIA_MUTE = 0x00E2            # confirmed
MEDIA_STOP = 0x00B7
MEDIA_VOL_UP = 0x00E9
MEDIA_VOL_DOWN = 0x00EA


def ext_slot_addr(index):
    """Address of the extended slot belonging to button `index`."""
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"button index outside 0..{BUTTON_COUNT - 1}")
    return EXT_SLOT_BASE + EXT_SLOT_STRIDE * index


def build_media(index, usage):
    """Write a multimedia key into the extended slot of button `index`.

    `usage` is the 16-bit HID Consumer Page code (the MEDIA_* constants). The
    record stores the press and the release event with the same code.

    For the button to fire, its basic record must be BTN_EXTENDED.
    """
    lo, hi = usage & 0xFF, (usage >> 8) & 0xFF
    data = record([0x02, EVENT_MEDIA_DOWN, lo, hi, EVENT_MEDIA_UP, lo, hi])
    return build_write(ext_slot_addr(index), data)


# --- DPI Effect (register 0x004C) -------------------------------------------
DPI_EFFECT_ADDR = 0x004C
DPI_EFFECT_STEADY = 0x01
DPI_EFFECT_OFF = 0x00
# 0x4E and 0x50 complete the effect group. Their meaning is still unknown; these
# are the captured values, used only as a last resort. The normal path is to
# read the current ones from the hardware and hand them back untouched (see
# device.send_dpi_effect).
DPI_EFFECT_TAIL = (0x01, 0x03)


def build_dpi_effect(on, tail=DPI_EFFECT_TAIL):
    """Turn the "DPI Effect" on (Steady) or off — the LED that shows the DPI stage.

    When on, the app writes three 2-byte records (0x4C, 0x4E, 0x50); when off it
    writes only 0x4C. We reproduce both captured shapes.

    `tail` holds the values for 0x4E and 0x50. Pass the ones read from the
    hardware so undecoded fields are not overwritten.
    """
    if not on:
        return build_write(DPI_EFFECT_ADDR, record([DPI_EFFECT_OFF]))
    data = record([DPI_EFFECT_STEADY])
    for value in tail:
        data += record([value])
    return build_write(DPI_EFFECT_ADDR, data)

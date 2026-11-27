"""Redragon M711 Pro protocol — packet construction (pure logic, no I/O).

See the Protocol section of the README. Every function here is testable by
byte-matching against real USB captures (tests/test_protocol.py).
"""

# The byte sum settles at 0x55 (mod 256). This holds for the OUTER checksum (the
# 17-byte packet) and for every memory RECORD, whatever its length.
CHECKSUM_TARGET = 0x55

LED_ADDR = 0xA0           # LED register
# EFFECT byte (data[0]) — decoded from USB captures.
# The official app names its five effects Steady, Respiration, Neon, Streaming
# and OFF. Selecting "Streaming" in the app leaves 0x00 in this register, so the
# names below are the app's own; Neon is 0x03 by elimination and is the one
# value we have never written.
EFFECT_STREAMING = 0x00   # running / rainbow cycle ("Streaming" in the app)
EFFECT_NEON = 0x03        # not implemented yet — never written or read
EFFECT_CYCLE = EFFECT_STREAMING          # kept: the name used before
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


# A packet is 17 bytes: six of header, one of checksum, so at most ten of data.
MAX_DATA = 10


def build_write(addr, data):
    """A 17-byte write packet (opcode 0x07) with a 16-bit address.

    Layout: 08 07 00 <ADDR_HI> <ADDR_LO> <LEN> <data...> <padding> <cksum>

    Raises when the data cannot fit. Without this guard an over-long record
    silently produced a packet longer than the HID report, which the device
    would never have accepted — see build_events, which splits instead.
    """
    if len(data) > MAX_DATA:
        raise ValueError(f"a packet holds at most {MAX_DATA} data bytes, "
                         f"got {len(data)} — split the record across packets")
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


# --- USB polling rate (register 0x0000) -------------------------------------
# A 2-byte record: <code> <record checksum>, LEN 2.
#
# ORIGIN OF THE CODES: they were first decoded by the m913-ctl project
# (github.com/Qehbr/m913-ctl, GPL-3.0) from THEIR USB captures of the same Compx
# chip. They have since been verified on this hardware: all four were written,
# read back and restored, and with the register at 0x01 the actual report rate
# measured ~1002 Hz on the mouse's interrupt endpoint — an independent
# confirmation that 0x01 really is 1000 Hz.
POLLING_ADDR = 0x0000
POLLING_RATES = {1000: 0x01, 500: 0x02, 250: 0x04, 125: 0x08}


def build_polling(hz):
    """Packet setting the USB polling rate. `hz` is one of the POLLING_RATES keys."""
    if hz not in POLLING_RATES:
        supported = ", ".join(str(v) for v in sorted(POLLING_RATES, reverse=True))
        raise ValueError(f"unsupported polling rate {hz} Hz — use one of: {supported}")
    return build_write(POLLING_ADDR, record([POLLING_RATES[hz]]))


def polling_from_byte(code):
    """Register byte -> polling rate in Hz, or None when the code is unknown."""
    for hz, value in POLLING_RATES.items():
        if value == (code & 0xFF):
            return hz
    return None


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


DPI_LABEL_STEP = 100      # the official app labels DPI in hundreds
DPI_LABEL_MAX = 16000     # what the app calls the firmware ceiling (Cfg.ini)


def dpi_label(n):
    """The DPI the official app would show for register byte `n`, or None.

    The register step (~83.33) is smaller than 100, so each multiple of 100
    lands on its own byte and the app's label can be recovered from the byte
    alone: it is the multiple of 100 that encodes to `n`. Reproduces all six
    labels read off the app (700 for 0x07 although the step decodes to 667)
    and the "16000" the app's Cfg.ini gives the ceiling byte 0xBD.

    Display only — nothing here changes a byte on the wire.
    """
    if n == DPI_BYTE_MAX:
        return DPI_LABEL_MAX
    real = (n + 1) * 250 / 3
    lower = int(real // DPI_LABEL_STEP) * DPI_LABEL_STEP
    for candidate in (lower, lower + DPI_LABEL_STEP):
        if DPI_MIN <= candidate <= DPI_MAX and dpi_to_byte(candidate) == n:
            return candidate
    return None


def dpi_display(n):
    """The number to show for byte `n`: the app's label, else the real value.

    Either way dpi_to_byte(dpi_display(n)) == n, so a value typed back from the
    screen writes the same byte.
    """
    label = dpi_label(n)
    return byte_to_dpi(n) if label is None else label


def dpi_text(n):
    """"700 DPI (≈667 real)" — the label, plus the real value when it differs."""
    shown, real = dpi_display(n), byte_to_dpi(n)
    return f"{shown} DPI" if shown == real else f"{shown} DPI (≈{real} real)"


def axis_pair(entry):
    """The two axis values of a table entry: a single value (X = Y) or (x, y).

    The official app keeps the axes equal and exposes an "XY Independent"
    toggle; the record format holds them separately either way, so both forms
    are accepted and the single value stays the captured behaviour.
    """
    if isinstance(entry, (tuple, list)):
        if len(entry) != 2:
            raise ValueError("an axis entry is one value or an (x, y) pair, "
                             f"got {len(entry)} values")
        return entry[0], entry[1]
    return entry, entry


def build_dpi_table_bytes(values):
    """The THREE DPI table packets, from the raw register bytes.

    Each entry takes 4 bytes (`X Y 00 <cksum>`); X and Y are the axes, kept
    equal by the official app. A stage is therefore either one byte (X = Y) or
    an (x_byte, y_byte) pair. We only emit the packet shapes seen in captures:
    0x0C with LEN 8, 0x14 with LEN 8 and 0x1C with LEN 4. Writing a single
    stage on its own has never been observed, so it is not offered.

    This is the preferred entry point when preserving stages that must not
    change: byte -> DPI -> byte is NOT the identity above 0xBD, so rebuilding
    the table from DPI values would silently lower any such stage.
    """
    if len(values) != DPI_STAGES:
        raise ValueError(f"the table needs {DPI_STAGES} stages, got {len(values)}")
    e = []
    for value in values:
        x, y = axis_pair(value)
        e.append(record([x & 0xFF, y & 0xFF, 0x00]))
    return [build_write(DPI_ADDR, e[0] + e[1]),
            build_write(DPI_ADDR + 8, e[2] + e[3]),
            build_write(DPI_ADDR + 16, e[4])]


def build_dpi_table(stages):
    """Like build_dpi_table_bytes, but taking the five values in DPI.

    A stage is a DPI number (both axes) or an (x_dpi, y_dpi) pair.
    """
    return build_dpi_table_bytes(
        [tuple(dpi_to_byte(v) for v in axis_pair(s)) for s in stages])


# --- Per-stage DPI colour (register 0x002C) ---------------------------------
# The LED colour the mouse shows for each DPI stage. Structurally the twin of
# build_dpi_table_bytes: five 4-byte records written as the same three captured
# shapes (LEN 8, LEN 8, LEN 4) at base+0, base+8 and base+16. Only the base
# address and the meaning of the three data bytes differ (`R G B` here,
# `X Y 00` there).
DPI_COLOR_ADDR = 0x002C


def build_dpi_colors(colors):
    """The THREE packets that write the per-stage DPI LED colours.

    `colors` is five (r, g, b) tuples, one per DPI stage. Each becomes a 4-byte
    record `R G B <record checksum>`. As with the DPI table, the register is
    written whole, so changing one stage means passing the other four through
    untouched (see device.send_dpi_color).
    """
    if len(colors) != DPI_STAGES:
        raise ValueError(f"the table needs {DPI_STAGES} colours, "
                         f"got {len(colors)}")
    e = [record([r, g, b]) for r, g, b in colors]
    return [build_write(DPI_COLOR_ADDR, e[0] + e[1]),
            build_write(DPI_COLOR_ADDR + 8, e[2] + e[3]),
            build_write(DPI_COLOR_ADDR + 16, e[4])]


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
# Restore factory settings. The mouse ships it at table index 6, which no
# physical button fires. Found 2026-11-27 by copying it to button 8 and
# pressing once: DPI (-> 1000/2000/4000/8000/16000), LED (-> Streaming, red),
# buttons and the DPI Effect group were rewritten to the factory defaults and
# the extended slots erased. Named so it can be recognised when read back;
# deliberately never offered as an action — one press wipes the configuration.
BTN_FACTORY_RESET = (0x09, 0x00, 0x00)

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

    Confirmed by a single-variable experiment: with the official app, button 2
    was set to "RGB ON/OFF" and nothing else, and its record became 0x08. An
    earlier multi-change experiment had suggested 0x07, but that run changed
    seven buttons at once and its button-to-index attribution turned out to be
    unreliable. m913-ctl had 0x08 for this all along.
    """
    return (0x08, 0x00, 0x00)


def btn_polling_switch():
    """Cycle the USB polling rate, one step per press, going UP and wrapping:
    125 -> 250 -> 500 -> 1000 -> 125 Hz.

    Confirmed on this hardware (2026-11-27): with only button 8 (index 9) set
    to 0x07, counted presses moved register 0x0000 from 500 to 1000 (01), then
    to 125 (08), then to 250 (04). The firmware writes the new rate to the
    register itself, so read_polling reflects it.
    """
    return (0x07, 0x00, 0x00)


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
# The slot holds an EVENT LIST, not a fixed pair:
#
#     <event count> [ <type> <code lo> <code hi> ] * count <record checksum>
#
# Decoded on this mouse: assigning Ctrl+C through the official app produced a
# four-event record (modifier down, key down, modifier up, key up), which is
# what proved that the first byte counts events rather than naming a type.
# The codes are standard HID usages — the same Ctrl+C record carries 0x01 (the
# left-control modifier bit) and 0x06 (the keyboard usage for "c").
EXT_SLOT_BASE = 0x0100
EXT_SLOT_STRIDE = 0x20
EVENT_MEDIA_DOWN = 0x82        # press, HID Consumer Page (16-bit code)
EVENT_MEDIA_UP = 0x42          # release
EVENT_KEY_DOWN = 0x81          # press, HID Keyboard Page
EVENT_KEY_UP = 0x41            # release
EVENT_MOD_DOWN = 0x80          # press, modifier bitmask
EVENT_MOD_UP = 0x40            # release

# HID modifier bits, as carried by the 0x80/0x40 events.
MOD_CTRL_L = 0x01
MOD_SHIFT_L = 0x02
MOD_ALT_L = 0x04
MOD_WIN_L = 0x08
MOD_CTRL_R = 0x10
MOD_SHIFT_R = 0x20
MOD_ALT_R = 0x40

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


def build_events(index, events):
    """The packets writing an event list into button `index`'s extended slot.

    `events` is a list of (type, code) pairs; `code` may be 16-bit (the
    multimedia usages are). The record is the event count followed by three
    bytes per event, closed by the usual checksum.

    Returns a LIST because the record outgrows a single packet: two events fit
    in one, but a modifier combination is four events (14 bytes) and needs two,
    continuing at the next ten-byte boundary. That is how the record is laid out
    in memory — reading slot 0x0260 back gives the two halves contiguously.
    """
    data = [len(events)]
    for event_type, code in events:
        data += [event_type, code & 0xFF, (code >> 8) & 0xFF]
    data = record(data)
    base = ext_slot_addr(index)
    return [build_write(base + off, data[off:off + MAX_DATA])
            for off in range(0, len(data), MAX_DATA)]


def parse_events(data):
    """Decode an extended-slot record back into [(type, code), ...].

    The inverse of build_events. Returns None for anything that is not a
    well-formed record — an erased slot (all 0xFF, as a factory reset leaves
    it), a bad checksum, or too few bytes — so a caller never shows a guess.
    """
    data = bytes(data)
    if not data:
        return None
    count = data[0]
    size = 1 + 3 * count + 1
    if count == 0 or count == 0xFF or len(data) < size:
        return None
    if checksum(data[:size - 1]) != data[size - 1]:
        return None
    return [(data[1 + 3 * i], data[2 + 3 * i] | (data[3 + 3 * i] << 8))
            for i in range(count)]


def ext_action(events):
    """Classify an event list as one of the shapes this project builds.

    ("media", usage), ("key", usage) or ("combo", modifiers, usage) — exactly
    the records build_media / build_key / build_combo write. Anything else (a
    macro, an unknown layout) is None: shown as unknown, never rewritten.
    """
    if not events:
        return None
    if len(events) == 2:
        (t1, c1), (t2, c2) = events
        if (t1, t2) == (EVENT_MEDIA_DOWN, EVENT_MEDIA_UP) and c1 == c2:
            return ("media", c1)
        if (t1, t2) == (EVENT_KEY_DOWN, EVENT_KEY_UP) and c1 == c2:
            return ("key", c1)
    if len(events) == 4:
        (t1, m1), (t2, k1), (t3, m2), (t4, k2) = events
        if ((t1, t2, t3, t4) == (EVENT_MOD_DOWN, EVENT_KEY_DOWN,
                                 EVENT_MOD_UP, EVENT_KEY_UP)
                and m1 == m2 and k1 == k2):
            return ("combo", m1, k1)
    return None


def build_media(index, usage):
    """Write a multimedia key into the extended slot of button `index`.

    `usage` is the 16-bit HID Consumer Page code (the MEDIA_* constants). The
    record stores the press and the release event with the same code.

    For the button to fire, its basic record must be BTN_EXTENDED.
    """
    return build_events(index, [(EVENT_MEDIA_DOWN, usage),
                                (EVENT_MEDIA_UP, usage)])


def build_key(index, usage):
    """Write a keyboard key into the extended slot of button `index`.

    `usage` is a HID Keyboard Page code (see m711pro/data/hid_keys.py) — a
    single byte, so the high byte the multimedia record uses for the 16-bit
    consumer usage stays zero here.

    Verified on this hardware: assigning a single key to button 2 through the
    official app produced `02 81 1f 00 41 1f 00 53` in slot 0x0120 — the same
    shape this builds.
    """
    return build_events(index, [(EVENT_KEY_DOWN, usage),
                                (EVENT_KEY_UP, usage)])


def build_combo(index, modifiers, usage):
    """Write a modifier + key combination (e.g. Ctrl+C) into button `index`.

    Modifiers travel as their own events, which is why a combo is four events
    and not two. Verified byte for byte against the Ctrl+C record the official
    app wrote to this mouse:
        04 | 80 01 00 | 81 06 00 | 40 01 00 | 41 06 00 | c1
    """
    return build_events(index, [(EVENT_MOD_DOWN, modifiers),
                                (EVENT_KEY_DOWN, usage),
                                (EVENT_MOD_UP, modifiers),
                                (EVENT_KEY_UP, usage)])


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

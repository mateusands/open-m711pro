"""HID Keyboard Page usages, by name (for the CLI's `key:` prefix).

These are the standard codes from the USB HID Usage Tables, Keyboard/Keypad
Page (0x07) — they are not specific to this mouse. What IS specific, and still
unverified here, is how the firmware carries them: see protocol.build_key().

Only the keys that can be typed as a plain name are listed; modifiers, combos
and macros are not mapped yet.
"""

KEYS = {}

# a-z -> 0x04-0x1D
KEYS.update({chr(ord('a') + i): 0x04 + i for i in range(26)})

# 1-9 -> 0x1E-0x26 ; 0 -> 0x27 (zero sits AFTER nine on this page)
KEYS.update({str(n): 0x1E + n - 1 for n in range(1, 10)})
KEYS['0'] = 0x27

# f1-f12 -> 0x3A-0x45
KEYS.update({f"f{n}": 0x3A + n - 1 for n in range(1, 13)})

KEYS.update({
    'enter': 0x28,
    'esc': 0x29,
    'backspace': 0x2A,
    'tab': 0x2B,
    'space': 0x2C,
})


# HID modifier bits, as the extended slot's 0x80/0x40 events carry them.
# Confirmed on this hardware: the Ctrl+C record the official app wrote holds
# 0x01 for the left control key.
MODIFIERS = {
    'ctrl': 0x01, 'shift': 0x02, 'alt': 0x04, 'win': 0x08,
    'ctrl_r': 0x10, 'shift_r': 0x20, 'alt_r': 0x40,
}

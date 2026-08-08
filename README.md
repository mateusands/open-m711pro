# open-m711pro

An open-source driver and configuration tool for the **Redragon M711 Pro**
gaming mouse on Linux, written in pure Python.

The vendor only ships a Windows application. This project reimplements its USB
protocol, reverse-engineered by capturing the official software's traffic with
`usbmon` + Wireshark and verifying every byte against real hardware.

> Not affiliated with or endorsed by Redragon. Use at your own risk.

## Device

| Role | VID:PID | USB description |
|------|---------|-----------------|
| 2.4G receiver (dongle) | `25A7:FA07` | 2.4G Wireless Receiver |
| Mouse (radio or cable) | `25A7:FA08` | 2.4G Dual Mode Mouse |

`25A7` is **Compx**, a common OEM for wireless gaming mice. The same chip and
protocol family are used by the Redragon M913 Impact Elite.

## What works

- **LED** — solid colour, brightness, breathing, cycle, off, effect speed
- **DPI** — all five stages, independent X/Y in the wire format, single-DPI mode
- **DPI Effect** — the LED that indicates the current DPI stage
- **Buttons** — remap all 16 slots: mouse buttons, DPI up/down/cycle, fire key,
  three-click, RGB toggle, polling switch, disable
- **Multimedia keys** — play/pause, next, previous, mute, stop, volume
- **Reading the real state** back from the mouse, not just what this app wrote

Not mapped yet: macros and keyboard combos, and a second LED zone at `0x0054`.
The polling rate register is identified but not yet verified on this hardware.

## Requirements

- Linux, Python 3.8+
- The core is **pure stdlib**. The Qt interface needs `PySide6`; without it the
  app falls back to a tkinter UI.

Grant access to the device with a udev rule:

```
# /etc/udev/rules.d/99-m711pro.rules
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="25a7", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Usage

Graphical interface:

```bash
python3 main.py
```

Command line:

```bash
python3 main.py FF0000         # red (hex)
python3 main.py 0 255 0        # green (R G B)
python3 main.py blue           # colour by name
python3 main.py off            # turn the LED off

python3 main.py dpi            # show the five stages read from the mouse
python3 main.py dpi 1600       # single DPI: apply it to all five stages
python3 main.py dpi 3 4000     # stage 3 = 4000 DPI
python3 main.py dpi-effect on  # DPI stage indicator LED

python3 main.py buttons        # list the 16 button slots
python3 main.py button 1 middle
python3 main.py button 9 media:mute
```

> DPI is stored as a single byte with a step of ~83, so the value shown is what
> the mouse actually holds: asking for 1600 gives 1583. The official app hides
> this by displaying the number you typed. 1000, 2000, 4000 and 8000 are exact.

## Project layout

```
main.py                  entry point (GUI without args, CLI with args)
m711pro/
├── core/
│   ├── protocol.py      packet builders + checksums — PURE LOGIC, no I/O
│   ├── device.py        hidraw I/O (find_devices, send_*, read_*)
│   └── state.py         local persistence of the last applied state
├── cli/commands.py      command-line interface
├── ui/
│   ├── qt.py            PySide6 interface
│   ├── tk.py            tkinter fallback
│   └── theme.py         palette and visual constants
└── data/colors.py       colour names and palette
tools/                   read-only memory dumper, test runner
tests/                   byte-match tests against real captures
```

Layer rules: `core/protocol.py` is pure logic and is what the byte-match tests
exercise; `core/device.py` is the only module that touches the hardware; the CLI
and the UIs never build packets themselves.

## Protocol

Configuration commands are **HID Feature Reports** on interface 1
(`bmRequestType 0x21`, `bRequest 0x09`, `wValue 0x0308`, 17 bytes), sent through
`ioctl(HIDIOCSFEATURE)` on the matching `/dev/hidraw` node.

```
08 07 00 <ADDR_HI> <ADDR_LO> <LEN> <data...> <padding> <CHECKSUM>
│  │  │  └────────┬────────┘  │
│  │  │           │           └── number of data bytes
│  │  │           └── 16-bit address in the mouse's config memory
│  │  └── always 00
│  └── opcode: 0x07 write · 0x04 commit · 0x08 read
└── Report ID (0x08)
```

**Checksum.** The byte sum settles at `0x55` (mod 256). This holds for the
17-byte packet *and* for every memory record independently:

```python
checksum = (0x55 - sum(previous_bytes)) & 0xFF
```

**Reading.** A read request is `08 08 00 <hi> <lo> <len>`; the reply arrives over
interrupt IN as Report ID `09` with the same layout.

### Register map

| Address | Contents |
|---------|----------|
| `0x0000` | USB polling rate: `01` 1000 Hz, `02` 500, `04` 250, `08` 125 (unverified here) |
| `0x0002` | number of enabled DPI stages (5) |
| `0x000C`–`0x001F` | DPI table: 5 stages × 4 bytes (`X Y 00 ck`) |
| `0x002C`–`0x003F` | per-stage LED colour: 5 × 4 bytes (`R G B ck`) |
| `0x004C` | DPI Effect: `01` steady, `00` off |
| `0x0060`–`0x009F` | button table: 16 records × 4 bytes (`TYPE P1 P2 ck`) |
| `0x0054`–`0x005F` | second LED zone (logo?) — not decoded |
| `0x00A0` | LED: `EFFECT R G B SPEED BRIGHTNESS ck` |
| `0x0100 + 0x20 × n` | extended slot for button *n* (multimedia, keyboard) |

### DPI encoding

```python
byte = round(dpi * 3 / 250) - 1      # ~83.33 DPI per step
dpi  = (byte + 1) * 250 / 3
```

Validated against six values read off the official app and cross-checked with
the m913-ctl code table. The firmware ceiling is `0xBD` (~15833 DPI), which the
official app labels "16000".

### Button action types

| Type | Action | P1 | P2 |
|------|--------|----|----|
| `0x00` | disabled | — | — |
| `0x01` | mouse button | bitmask | — |
| `0x02` | DPI: `01` cycle, `02` up, `03` down | variant | — |
| `0x04` | repeated click (fire key / three-click) | speed | clicks |
| `0x05` | action lives in the extended slot | — | — |
| `0x07` | RGB toggle | — | — |
| `0x08` | polling rate switch | — | — |

A multimedia key is stored in the extended slot as
`02 82 <usage LE16> 42 <usage LE16> <ck>`, where `0x82`/`0x42` are the press and
release events and the usage is a HID Consumer Page code.

## Development

```bash
python3 -m pytest              # byte-match tests
python3 tools/run_tests.py     # same tests without pytest
python3 tools/dump_config.py   # read-only dump of the config memory
```

Every packet builder has a byte-match test against a real capture. That is the
project's core rule: **no byte is ever sent to the hardware unless it has been
validated against a real capture or read back from the device.** A wrong packet
can leave the mouse in an odd state, and the `ioctl` succeeds either way.

## Credits

The reverse engineering here is our own, done by capturing the official
software's USB traffic. Two findings were cross-checked against, and corrected
by, prior work on the **same Compx chip** (identical USB IDs, `25a7:fa07`/`fa08`)
in the Redragon M913:

- [**m913-ctl**](https://github.com/Qehbr/m913-ctl) (GPL-3.0) — the 16-entry
  button table layout (we had read only 8) and the extended slot address
  `0x0100 + 0x20 × index`.
- [**mouse_m908**](https://github.com/dokutan/mouse_m908) (GPL-3.0) — the
  upstream protocol work that m913-ctl builds on.

Our DPI formula was independently validated against their code table. Where our
hardware disagrees with them, we follow our own measurements and say so in the
code — notably the `0x07`/`0x08` pair (RGB toggle vs polling switch) and the LED
mode bytes, which genuinely differ between the M913 and the M711 Pro.

## License

[GPL-3.0](LICENSE).

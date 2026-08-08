# Contributing to open-m711pro

Thanks for looking. This project talks to real hardware over a protocol nobody
published, so the conventions below are less about style and more about not
bricking someone's mouse.

## The golden rule

**Never send the hardware a byte you have not validated against a real capture
or read back from the device.** An invented packet — wrong checksum, guessed
address — can leave the mouse in a strange state, and the `ioctl` reports
success either way. Before any write, ask: does the byte-match test pass?

Corollaries:

- Only emit packet *shapes* that have been observed. If the official app always
  writes a register with `LEN 8`, do not invent a `LEN 4` variant.
- A command that changes device state needs a known way back, and that path
  must be documented.
- When a function rewrites a whole table (DPI stages, buttons), read the current
  one first and preserve every entry you are not changing — byte for byte,
  not via a lossy round-trip.
- A finding backed by a single sample is a hypothesis, not a fact. Mark it as
  such and say what is missing.

## Layers

```
core/protocol.py   pure logic: builds packets, computes checksums. No I/O.
core/device.py     the only module that touches hidraw.
cli/, ui/          never build packets and never talk to hidraw directly.
```

Checksums always go through the central function; never hardcode the byte.

## Tests

Test-driven development is required for protocol logic:

1. Write the test first and show it failing.
2. Every packet builder gets a **byte-match test** against a known real capture.
   That is the proof the packet is right by construction.
3. Implement the minimum that turns it green.

```bash
python3 -m pytest              # official runner
python3 tools/run_tests.py     # fallback when pytest is not installed
```

A green test suite proves the packet is correct. It does **not** prove the mouse
obeyed. If you did not test on hardware, say so in the pull request.

## Language

Code, comments, documentation and commit messages are in **English**.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): description in the imperative`.

| Type | Use |
|------|-----|
| `feat` | new capability (a command, a mapped register) |
| `fix` | bug fix |
| `refactor` | restructuring with no behaviour change |
| `test` | tests |
| `docs` | documentation |
| `chore` | repository infrastructure |
| `ci` | automation |

Common scopes: `protocol`, `device`, `cli`, `ui`, `dpi`, `led`, `buttons`.

Work on a branch, never commit straight to `main`, and keep pull requests small
and focused — one responsibility each.

## Pull requests

Describe *what changed*, *how to test it* (command plus evidence), and the
*proof*: the byte-match, and the result on real hardware when applicable.

USB captures (`.pcap`, `.pcapng`) are never committed; they are gitignored.

## Mapping something new

The loop that produced everything here:

1. Run the official Windows app in a VM with the dongle passed through, and
   capture the host side with `usbmon` + `dumpcap`.
2. Change **one** setting at a time, with pauses, so each action becomes an
   isolated block in the traffic.
3. Diff neighbouring blocks. The byte that changes is the register.
4. Cross-check by reading the device back with `tools/dump_config.py`, which is
   read-only and often faster than parsing a capture.
5. Only then write the builder and its byte-match test.

Note that read replies do not show up in tshark's normal fields; you have to
parse the `-x` hex dump at offset `0x40`.

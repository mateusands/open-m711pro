#!/usr/bin/env python3
"""Dump the mouse configuration memory — READ ONLY.

Sweeps the address space with the already validated read request
(`protocol.build_read`, opcode 0x08) and prints whatever the mouse answers.
No WRITE byte is ever sent: opcode 0x07 (write) and 0x04 (commit) are not used
here, so the dump cannot change hardware state.

Addresses are 16-bit and given in hex (without 0x): the main configuration lives
at 0x0000-0x00A8, but the official app scans as far as 0x1981.

Usage:
    python3 tools/dump_config.py                    # sweep 0x0000..0x00F8
    python3 tools/dump_config.py > /tmp/before.txt
    python3 tools/dump_config.py --addr 0C          # read a single address
    python3 tools/dump_config.py --start 0100 --end 01F8   # page 1

Discovery workflow: change one setting, dump again, and diff the two files.
That is how the DPI encoding was mapped without touching a packet capture.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m711pro.core import device  # noqa: E402


def dump(addr, length=8):
    """Return (data_bytes, raw_report), or (None, None) when nothing answered."""
    try:
        reply = device.read_register(addr, length)
    except (device.DeviceNotFound, OSError) as exc:
        raise SystemExit(f"Error: {exc}")
    if not reply:
        return None, None
    return reply[6:6 + length], reply


def fmt(data):
    return ' '.join(f"{b:02x}" for b in data)


def main(argv):
    start, end, step, length = 0x0000, 0x00F8, 0x08, 0x08
    only = None
    width = 2               # hex digits in the address label
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--addr':
            only = int(argv[i + 1], 16); i += 2
        elif arg == '--start':
            start = int(argv[i + 1], 16); i += 2
        elif arg == '--end':
            end = int(argv[i + 1], 16); i += 2
        elif arg == '--step':
            step = int(argv[i + 1], 0); i += 2
        elif arg == '--len':
            length = int(argv[i + 1], 0); i += 2
        else:
            raise SystemExit(__doc__)

    addrs = [only] if only is not None else range(start, end + 1, step)
    if max(addrs) > 0xFF:
        width = 4
    if not device.find_devices():
        raise SystemExit(
            "mouse not found — is the dongle on the host (not in a VM)? "
            "check the udev rule and that the mouse is in 2.4G mode.")

    quiet = 0
    for addr in addrs:
        data, _ = dump(addr, length)
        if data is None:
            print(f"{addr:0{width}X}: <no answer>")
            quiet += 1
            continue
        print(f"{addr:0{width}X}: {fmt(data)}")
    if quiet:
        print(f"# {quiet} address(es) did not answer", file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1:])

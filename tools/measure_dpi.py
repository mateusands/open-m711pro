#!/usr/bin/env python3
"""Measure the mouse's REAL DPI with a ruler — read-only, sends nothing.

The register holds ~83.33 DPI steps, so the byte the official app writes for
"700" decodes to 667 by our formula. Whether the sensor really runs at 667 or
at 700 can only be settled physically: count the movement the mouse reports
over a known distance.

    python3 tools/measure_dpi.py            # 10 cm, horizontal
    python3 tools/measure_dpi.py --cm 20

Put a ruler on the desk, press Enter, slide the mouse in a straight line along
it for the given distance, press Enter again. Repeat a few times; the median
is printed. The counts are read straight from the kernel's evdev node, before
any desktop acceleration, so they are the sensor's own counts.

Needs read access to /dev/input/event* (run with sudo, or be in the `input`
group). Nothing is ever written to the mouse; the DPI table is only READ, to
show which stage the measurement matches.
"""
import glob
import os
import select
import statistics
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m711pro.core import device, protocol  # noqa: E402

EVENT = struct.Struct("llHHi")      # struct input_event on 64-bit Linux
EV_REL, REL_X, REL_Y = 0x02, 0x00, 0x01
CM_PER_INCH = 2.54


def cpi(counts, distance_cm):
    """Counts over a distance -> counts per inch (what "DPI" really means)."""
    return abs(counts) / (distance_cm / CM_PER_INCH)


def find_event_nodes(vid=device.VID):
    """evdev nodes of the mouse that report relative motion."""
    nodes = []
    for path in sorted(glob.glob("/sys/class/input/event*")):
        try:
            with open(os.path.join(path, "device", "id", "vendor")) as h:
                vendor = int(h.read(), 16)
            with open(os.path.join(path, "device", "capabilities", "rel")) as h:
                rel = int(h.read().split()[-1], 16)
        except (OSError, ValueError):
            continue
        if vendor == vid and rel & (1 << REL_X):
            nodes.append("/dev/input/" + os.path.basename(path))
    return nodes


def drain(fds):
    """Discard motion queued while not measuring (e.g. carrying the mouse back
    to the start of the ruler), so it does not leak into the next run."""
    for fd in fds:
        while select.select([fd], [], [], 0)[0]:
            try:
                if not os.read(fd, EVENT.size * 64):
                    break
            except BlockingIOError:
                break


def sum_motion(fds, stop_fd):
    """Accumulate REL_X/REL_Y from `fds` until a line arrives on `stop_fd`."""
    x = y = 0
    while True:
        ready, _, _ = select.select(fds + [stop_fd], [], [])
        if stop_fd in ready:
            os.read(stop_fd, 1024)
            return x, y
        for fd in ready:
            data = os.read(fd, EVENT.size * 64)
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype == EV_REL and code == REL_X:
                    x += value
                elif etype == EV_REL and code == REL_Y:
                    y += value


def main(argv):
    distance = 10.0
    if argv[:1] == ["--cm"] and len(argv) == 2:
        distance = float(argv[1])
    elif argv:
        raise SystemExit(__doc__)

    nodes = find_event_nodes()
    if not nodes:
        raise SystemExit("no evdev node of the mouse found — is it connected?")
    try:
        fds = [os.open(n, os.O_RDONLY | os.O_NONBLOCK) for n in nodes]
    except PermissionError:
        raise SystemExit(f"cannot read {', '.join(nodes)} — run with sudo, or "
                         "add yourself to the 'input' group")

    stdin = sys.stdin.fileno()
    results = []
    print(f"Slide the mouse {distance:g} cm along a ruler, in a straight line.")
    print("Enter to start a run, Enter to stop it; Ctrl+D or 'q' to finish.\n")
    while True:
        line = sys.stdin.readline()
        if not line or line.strip().lower() == "q":
            break
        drain(fds)
        print("  measuring... (Enter when you reach the mark)")
        x, y = sum_motion(fds, stdin)
        counts = max(abs(x), abs(y))          # whichever axis you moved along
        value = cpi(counts, distance)
        results.append(value)
        print(f"  {counts} counts -> {value:.0f} DPI   (Enter for another run, q to end)")

    if not results:
        return
    median = statistics.median(results)
    print(f"\nmedian of {len(results)} run(s): {median:.0f} DPI")
    try:
        table = device.read_dpi_bytes()
    except device.DeviceNotFound:
        table = None
    if table:
        print("stages in the mouse (label / real by our formula):")
        for i, b in enumerate(table, 1):
            print(f"  stage {i}: {protocol.dpi_text(b)}")


if __name__ == "__main__":
    main(sys.argv[1:])

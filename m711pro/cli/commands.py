"""open-m711pro command-line interface.

Usage:
    python3 main.py FF0000         # red (hex)
    python3 main.py 0 255 0        # green (R G B)
    python3 main.py blue           # colour by name
    python3 main.py off            # turn the LED off

    python3 main.py dpi            # show the five stages read from the mouse
    python3 main.py dpi 1600       # single DPI: apply it to all five stages
    python3 main.py dpi 3 4000     # stage 3 = 4000 DPI
    python3 main.py dpi-effect on  # DPI stage indicator LED (on/off)

    python3 main.py polling        # show the USB polling rate
    python3 main.py polling 500    # set it to 500 Hz

    python3 main.py buttons        # list the 16 slots and their mouse buttons
    python3 main.py button 2 middle      # TABLE index 2 = mouse button 3
    python3 main.py button 9 media:mute  # index 9 = mouse button 8
    python3 main.py button 9 key:a

    python3 main.py setup          # install the udev rule and the menu entry
    python3 main.py setup --uninstall
"""
import os
import sys

from ..core import device
from ..core import protocol
from ..data.colors import NAMED
from ..data.hid_keys import KEYS, MODIFIERS

def _prog():
    """How the user actually invoked us, so the help text matches.

    Installed the entry point is `open-m711pro`; from a checkout it is
    `python3 main.py`. Printing the wrong one sends people down a dead end.
    """
    name = os.path.basename(sys.argv[0] or "")
    if name == "main.py":
        return "python3 main.py"                 # running from a checkout
    if name.startswith("open-m711pro"):
        return name                              # installed entry point
    # Anything else — `python -m`, a test runner, an embedding host — has an
    # argv[0] that would only mislead. Fall back to the canonical command.
    return "open-m711pro"


PROG = _prog()
USAGE = __doc__.replace("python3 main.py", PROG)

OFF_WORDS = {'off', 'desligar', 'desliga', 'apagar'}
ON_WORDS = {'on', 'ligar', 'liga', 'ligado'}


def parse_action(argv):
    """Return ('off', None) or ('color', (r, g, b))."""
    if len(argv) == 1:
        arg = argv[0].lower()
        if arg in OFF_WORDS:
            return 'off', None
        if arg in NAMED:
            return 'color', NAMED[arg]
        hexcode = arg.lstrip('#')
        if len(hexcode) == 6:
            try:
                return 'color', (int(hexcode[0:2], 16), int(hexcode[2:4], 16),
                                 int(hexcode[4:6], 16))
            except ValueError:
                pass          # six characters, but not hex — fall through to usage
    if len(argv) == 3:
        return 'color', tuple(max(0, min(255, int(x))) for x in argv)
    raise SystemExit(USAGE)


DPI_USAGE = ("Usage: " + PROG + " dpi                  # show the stages\n"
             "       " + PROG + " dpi <value>         # single DPI (all five stages)\n"
             "       " + PROG + " dpi <stage> <value> # change one stage")


def _describe(dpi):
    """A DPI decoded from the mouse, shown the way the official app shows it.

    byte -> DPI -> byte is the identity only up to the ceiling 0xBD; a byte
    above it (never written by the app — e.g. an erased 0xFF) would otherwise
    be relabelled "16000". Those keep their raw decoded value.
    """
    b = protocol.dpi_to_byte(dpi)
    if protocol.byte_to_dpi(b) != dpi:
        return f"{dpi} DPI (outside the known range)"
    return protocol.dpi_text(b)


def _cmd_dpi(argv):
    """`dpi` shows; `dpi <value>` unifies; `dpi <stage> <value>` changes one."""
    if not argv:
        table = device.read_dpi_table()
        if table is None:
            raise SystemExit("Error: could not read the DPI from the mouse — "
                             "is the dongle plugged in and the device free?")
        for i, dpi in enumerate(table, 1):
            print(f"  stage {i}: {_describe(dpi)}")
        if len(set(table)) == 1:
            print("  (all five equal: the mouse's DPI button changes nothing)")
        return
    if len(argv) > 2:
        raise SystemExit(DPI_USAGE)
    try:
        numbers = [int(a) for a in argv]
    except ValueError:
        raise SystemExit(f"Error: the values must be numbers.\n{DPI_USAGE}")

    if len(numbers) == 1:                      # a single DPI across all stages
        requested = numbers[0]
        routes, actual = device.send_dpi_all(requested)
        byte = protocol.dpi_to_byte(actual)
        print(f"DPI = {protocol.dpi_text(byte)} on all five stages "
              f"(via {', '.join(routes)})")
        if protocol.dpi_display(byte) != requested:
            print(f"  (you asked for {requested}; the hardware step is ~83 DPI)")
        return

    stage, requested = numbers
    routes, table = device.send_dpi(stage, requested)
    byte = protocol.dpi_to_byte(table[stage - 1])
    print(f"Stage {stage} = {protocol.dpi_text(byte)} (via {', '.join(routes)})")
    if protocol.dpi_display(byte) != requested:
        print(f"  (you asked for {requested}; the hardware step is ~83 DPI)")
    print("  table: " + " . ".join(_describe(d) for d in table))


def _cmd_dpi_effect(argv):
    if len(argv) != 1 or argv[0].lower() not in ON_WORDS | OFF_WORDS:
        raise SystemExit("Usage: " + PROG + " dpi-effect on|off")
    on = argv[0].lower() in ON_WORDS
    routes = device.send_dpi_effect(on)
    print(f"DPI Effect {'on' if on else 'off'} (via {', '.join(routes)})")


POLLING_USAGE = ("Usage: " + PROG + " polling          # show the current rate\n"
                 "       " + PROG + " polling <hz>    # "
                 + " | ".join(str(hz) for hz in
                              sorted(protocol.POLLING_RATES, reverse=True)))


def _cmd_polling(argv):
    """`polling` shows the rate; `polling <hz>` sets it."""
    if not argv:
        hz, raw = device.read_polling()
        if raw is None:
            raise SystemExit("Error: could not read the polling rate from the "
                             "mouse — is the dongle plugged in and the device "
                             "free?")
        if hz is None:
            raise SystemExit(f"Error: the mouse answered with an unknown "
                             f"polling code {raw:#04x}. Only 01/02/04/08 are "
                             f"known; please report this.")
        print(f"USB polling: {hz} Hz")
        return
    if len(argv) != 1:
        raise SystemExit(POLLING_USAGE)
    try:
        hz = int(argv[0])
    except ValueError:
        raise SystemExit(f"Error: the rate must be a number.\n{POLLING_USAGE}")
    routes = device.send_polling(hz)
    print(f"USB polling = {hz} Hz (via {', '.join(routes)})")


ACTIONS = {
    'left': lambda: protocol.btn_mouse(protocol.MOUSE_LEFT),
    'right': lambda: protocol.btn_mouse(protocol.MOUSE_RIGHT),
    'middle': lambda: protocol.btn_mouse(protocol.MOUSE_MIDDLE),
    'back': lambda: protocol.btn_mouse(protocol.MOUSE_BACK),
    'forward': lambda: protocol.btn_mouse(protocol.MOUSE_FORWARD),
    'dpi+': protocol.btn_dpi_up,
    'dpi-': protocol.btn_dpi_down,
    'dpi-cycle': protocol.btn_dpi_cycle,
    'fire': protocol.btn_fire,
    'three-click': protocol.btn_three_click,
    'rgb': protocol.btn_rgb_toggle,
    'polling': protocol.btn_polling_switch,
    'none': lambda: protocol.BTN_NONE,
}
MEDIA = {
    'play': protocol.MEDIA_PLAY_PAUSE, 'next': protocol.MEDIA_NEXT,
    'previous': protocol.MEDIA_PREVIOUS, 'mute': protocol.MEDIA_MUTE,
    'stop': protocol.MEDIA_STOP, 'vol+': protocol.MEDIA_VOL_UP,
    'vol-': protocol.MEDIA_VOL_DOWN,
}
ACTION_NAMES = {
    protocol.BTN_NONE: 'none', protocol.BTN_EXTENDED: 'multimedia/keyboard',
    (0x01, 0x01, 0x00): 'left', (0x01, 0x02, 0x00): 'right',
    (0x01, 0x04, 0x00): 'middle', (0x01, 0x08, 0x00): 'back',
    (0x01, 0x10, 0x00): 'forward', (0x02, 0x02, 0x00): 'dpi+',
    (0x02, 0x03, 0x00): 'dpi-', (0x02, 0x01, 0x00): 'dpi-cycle',
    (0x08, 0x00, 0x00): 'rgb', (0x07, 0x00, 0x00): 'polling',
    protocol.BTN_FACTORY_RESET: 'factory reset (not assignable)',
}
BUTTON_USAGE = ("Usage: " + PROG + " buttons               # list the 16 buttons\n"
                "       " + PROG + " button <0-15> <action>  # TABLE index, "
                "see `buttons`\n"
                f"actions: {' '.join(sorted(ACTIONS))}\n"
                f"media:   {' '.join('media:' + m for m in sorted(MEDIA))}\n"
                "keys:    key:<name>       a-z 0-9 f1-f12 enter esc "
                "backspace tab space\n"
                f"combos:  combo:ctrl+c     modifiers: {' '.join(sorted(MODIFIERS))}")


def _cmd_buttons(argv):
    if argv:
        raise SystemExit(BUTTON_USAGE)
    table = device.read_buttons()
    if table is None:
        raise SystemExit("Error: could not read the buttons from the mouse.")
    for i, action in enumerate(table):
        name = ACTION_NAMES.get(action)
        if action[0] == 0x04:
            name = f"fire (speed {action[1]}, {action[2]} clicks)"
        extra = (f"  slot 0x{protocol.ext_slot_addr(i):04X}"
                 if action == protocol.BTN_EXTENDED else "")
        number = protocol.BUTTON_NUMBERS.get(i)
        where = f"  (mouse button {number})" if number else ""
        print(f"  {i:2d}: {action[0]:02x} {action[1]:02x} {action[2]:02x}  "
              f"{name or '?'}{extra}{where}")


def _cmd_button(argv):
    if len(argv) != 2:
        raise SystemExit(BUTTON_USAGE)
    try:
        index = int(argv[0])
    except ValueError:
        raise SystemExit(f"Error: the index must be a number.\n{BUTTON_USAGE}")
    name = argv[1].lower()
    if name.startswith('media:'):
        key = name.split(':', 1)[1]
        if key not in MEDIA:
            raise SystemExit(f"Error: unknown media key '{key}'.\n{BUTTON_USAGE}")
        routes, _ = device.send_media(index, MEDIA[key])
        print(f"Button {index} = media '{key}' (via {', '.join(routes)})")
        return
    if name.startswith('key:'):
        key = name.split(':', 1)[1]
        if key not in KEYS:
            raise SystemExit(f"Error: unknown key '{key}'.\n{BUTTON_USAGE}")
        routes, _ = device.send_key(index, KEYS[key])
        print(f"Button {index} = key '{key}' (via {', '.join(routes)})")
        return
    if name.startswith('combo:'):
        parts = name.split(':', 1)[1].split('+')
        key = parts[-1]
        if key not in KEYS:
            raise SystemExit(f"Error: unknown key '{key}'.\n{BUTTON_USAGE}")
        mods = 0
        for m in parts[:-1]:
            if m not in MODIFIERS:
                raise SystemExit(f"Error: unknown modifier '{m}' — use "
                                 f"{', '.join(sorted(MODIFIERS))}.\n{BUTTON_USAGE}")
            mods |= MODIFIERS[m]
        if not mods:
            raise SystemExit(f"Error: a combo needs a modifier, e.g. combo:ctrl+c."
                             f"\n{BUTTON_USAGE}")
        routes, _ = device.send_combo(index, mods, KEYS[key])
        print(f"Button {index} = {name.split(':', 1)[1]} (via {', '.join(routes)})")
        return
    if name not in ACTIONS:
        raise SystemExit(f"Error: unknown action '{name}'.\n{BUTTON_USAGE}")
    routes, _ = device.send_button(index, ACTIONS[name]())
    print(f"Button {index} = {name} (via {', '.join(routes)})")


def _cmd_setup(args):
    """Install (or remove) the udev rule and the menu entry.

    Lives in the CLI so pip and release installs, which do not carry
    packaging/install.sh, can still grant themselves access to the mouse.
    """
    import subprocess
    from .. import system
    try:
        if not args:
            return system.setup()
        if args == ['--uninstall']:
            return system.uninstall()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Error: '{' '.join(exc.cmd)}' failed "
                         f"(exit {exc.returncode})")
    except FileNotFoundError as exc:
        raise SystemExit(f"Error: {exc.filename} not found — install the "
                         "udev rule by hand, see the README")
    except system.RunAsUser as exc:
        raise SystemExit(f"Error: {exc}")
    raise SystemExit(f"Usage: {PROG} setup [--uninstall]")


COMMANDS = {
    'setup': _cmd_setup,
    'dpi': _cmd_dpi,
    'dpi-effect': _cmd_dpi_effect, 'dpieffect': _cmd_dpi_effect,
    'buttons': _cmd_buttons,
    'button': _cmd_button,
    'polling': _cmd_polling,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit(USAGE)
    command = COMMANDS.get(argv[0].lower())
    if command:
        try:
            return command(argv[1:])
        except (device.DeviceNotFound, ValueError) as exc:
            raise SystemExit(f"Error: {exc}")
    action, color = parse_action(argv)
    try:
        if action == 'off':
            routes = device.send_off()
            print(f"LED off (via {', '.join(routes)})")
        else:
            r, g, b = color
            routes = device.send_color(r, g, b)
            print(f"Colour #{r:02X}{g:02X}{b:02X} sent (via {', '.join(routes)})")
    except device.DeviceNotFound as exc:
        raise SystemExit(f"Error: {exc}")

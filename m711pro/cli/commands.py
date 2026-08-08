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

    python3 main.py buttons        # list the 16 buttons
    python3 main.py button 1 middle
    python3 main.py button 9 media:mute
"""
import sys

from ..core import device
from ..core import protocol
from ..data.colors import NAMED

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
            return 'color', (int(hexcode[0:2], 16), int(hexcode[2:4], 16),
                             int(hexcode[4:6], 16))
    if len(argv) == 3:
        return 'color', tuple(max(0, min(255, int(x))) for x in argv)
    raise SystemExit(__doc__)


DPI_USAGE = ("Usage: main.py dpi                  # show the stages\n"
             "       main.py dpi <value>         # single DPI (all five stages)\n"
             "       main.py dpi <stage> <value> # change one stage")


def _cmd_dpi(argv):
    """`dpi` shows; `dpi <value>` unifies; `dpi <stage> <value>` changes one."""
    if not argv:
        table = device.read_dpi_table()
        if table is None:
            raise SystemExit("Error: could not read the DPI from the mouse — "
                             "is the dongle plugged in and the device free?")
        for i, dpi in enumerate(table, 1):
            print(f"  stage {i}: {dpi} DPI")
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
        print(f"DPI = {actual} on all five stages (via {', '.join(routes)})")
        if actual != requested:
            print(f"  (you asked for {requested}; the hardware step is ~83 DPI)")
        return

    stage, requested = numbers
    routes, table = device.send_dpi(stage, requested)
    actual = table[stage - 1]
    print(f"Stage {stage} = {actual} DPI (via {', '.join(routes)})")
    if actual != requested:
        print(f"  (you asked for {requested}; the hardware step is ~83 DPI)")
    print("  table: " + " . ".join(str(d) for d in table))


def _cmd_dpi_effect(argv):
    if len(argv) != 1 or argv[0].lower() not in ON_WORDS | OFF_WORDS:
        raise SystemExit("Usage: main.py dpi-effect on|off")
    on = argv[0].lower() in ON_WORDS
    routes = device.send_dpi_effect(on)
    print(f"DPI Effect {'on' if on else 'off'} (via {', '.join(routes)})")


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
    (0x07, 0x00, 0x00): 'rgb', (0x08, 0x00, 0x00): 'polling',
}
BUTTON_USAGE = ("Usage: main.py buttons               # list the 16 buttons\n"
                "       main.py button <0-15> <action>\n"
                f"actions: {' '.join(sorted(ACTIONS))}\n"
                f"media:   {' '.join('media:' + m for m in sorted(MEDIA))}")


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
        print(f"  {i:2d}: {action[0]:02x} {action[1]:02x} {action[2]:02x}  "
              f"{name or '?'}{extra}")


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
    if name not in ACTIONS:
        raise SystemExit(f"Error: unknown action '{name}'.\n{BUTTON_USAGE}")
    routes, _ = device.send_button(index, ACTIONS[name]())
    print(f"Button {index} = {name} (via {', '.join(routes)})")


COMMANDS = {
    'dpi': _cmd_dpi,
    'dpi-effect': _cmd_dpi_effect, 'dpieffect': _cmd_dpi_effect,
    'buttons': _cmd_buttons,
    'button': _cmd_button,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit(__doc__)
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

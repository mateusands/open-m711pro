"""Interface de linha de comando do open-m711pro.

Uso:
    python3 main.py FF0000     # vermelho (hex)
    python3 main.py 0 255 0    # verde (R G B)
    python3 main.py azul       # cor por nome
    python3 main.py off        # desliga o LED
"""
import sys

from .core import device
from .colors import NAMED

OFF_WORDS = {'off', 'desligar', 'desliga', 'apagar'}


def parse_action(argv):
    """Retorna ('off', None) ou ('color', (r, g, b))."""
    if len(argv) == 1:
        a = argv[0].lower()
        if a in OFF_WORDS:
            return 'off', None
        if a in NAMED:
            return 'color', NAMED[a]
        h = a.lstrip('#')
        if len(h) == 6:
            return 'color', (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if len(argv) == 3:
        return 'color', tuple(max(0, min(255, int(x))) for x in argv)
    raise SystemExit(__doc__)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit(__doc__)
    action, color = parse_action(argv)
    try:
        if action == 'off':
            vias = device.send_off()
            print(f"LED desligado (via {', '.join(vias)})")
        else:
            r, g, b = color
            vias = device.send_color(r, g, b)
            print(f"Cor #{r:02X}{g:02X}{b:02X} enviada (via {', '.join(vias)})")
    except device.DeviceNotFound as e:
        raise SystemExit(f"Erro: {e}")

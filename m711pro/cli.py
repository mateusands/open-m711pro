"""Interface de linha de comando do open-m711pro.

Uso:
    python3 main.py FF0000        # vermelho (hex)
    python3 main.py 0 255 0       # verde (R G B)
    python3 main.py azul          # cor por nome
    python3 main.py off           # desliga o LED

    python3 main.py dpi           # mostra os 5 estágios lidos do mouse
    python3 main.py dpi 1600      # um DPI só: aplica aos 5 estágios
    python3 main.py dpi 3 4000    # estágio 3 = 4000 DPI
    python3 main.py dpi-effect on # LED indicador de nível de DPI (on/off)
"""
import sys

from .core import device
from .colors import NAMED

OFF_WORDS = {'off', 'desligar', 'desliga', 'apagar'}
ON_WORDS = {'on', 'ligar', 'liga', 'ligado'}


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


USO_DPI = ("Uso: main.py dpi                    # mostra os estágios\n"
           "     main.py dpi <valor>           # um DPI só (aplica aos 5)\n"
           "     main.py dpi <estágio> <valor> # muda um estágio")


def _cmd_dpi(argv):
    """`dpi` mostra; `dpi <valor>` unifica; `dpi <estágio> <valor>` muda um."""
    if not argv:
        tabela = device.read_dpi_table()
        if tabela is None:
            raise SystemExit("Erro: não consegui ler o DPI do mouse — dongle "
                             "plugado? mouse fora da VM?")
        for i, dpi in enumerate(tabela, 1):
            print(f"  estágio {i}: {dpi} DPI")
        if len(set(tabela)) == 1:
            print("  (os 5 iguais: o botão de DPI do mouse não muda nada)")
        return
    if len(argv) > 2:
        raise SystemExit(USO_DPI)
    try:
        nums = [int(a) for a in argv]
    except ValueError:
        raise SystemExit(f"Erro: os valores têm que ser números.\n{USO_DPI}")

    if len(nums) == 1:                      # um DPI só, nos 5 estágios
        pedido = nums[0]
        vias, real = device.send_dpi_all(pedido)
        print(f"DPI = {real} nos 5 estágios (via {', '.join(vias)})")
        if real != pedido:
            print(f"  (você pediu {pedido}; o passo do hardware é de ~83 DPI)")
        return

    stage, pedido = nums
    vias, nova = device.send_dpi(stage, pedido)
    real = nova[stage - 1]
    print(f"Estágio {stage} = {real} DPI (via {', '.join(vias)})")
    if real != pedido:
        print(f"  (você pediu {pedido}; o passo do hardware é de ~83 DPI)")
    print("  tabela: " + " · ".join(str(d) for d in nova))


def _cmd_dpi_effect(argv):
    if len(argv) != 1 or argv[0].lower() not in ON_WORDS | OFF_WORDS:
        raise SystemExit("Uso: main.py dpi-effect on|off")
    on = argv[0].lower() in ON_WORDS
    vias = device.send_dpi_effect(on)
    print(f"DPI Effect {'ligado' if on else 'desligado'} (via {', '.join(vias)})")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit(__doc__)
    if argv[0].lower() == 'dpi':
        try:
            return _cmd_dpi(argv[1:])
        except device.DeviceNotFound as e:
            raise SystemExit(f"Erro: {e}")
        except ValueError as e:
            raise SystemExit(f"Erro: {e}")
    if argv[0].lower() in ('dpi-effect', 'dpieffect'):
        try:
            return _cmd_dpi_effect(argv[1:])
        except device.DeviceNotFound as e:
            raise SystemExit(f"Erro: {e}")
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

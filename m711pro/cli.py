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

    python3 main.py botoes        # lista os 16 botões
    python3 main.py botao 1 meio  # botão 1 vira clique do meio
    python3 main.py botao 9 midia:mudo
"""
import sys

from .core import device
from .core import protocol
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


ACOES = {
    'esquerdo': lambda: protocol.btn_mouse(protocol.MOUSE_LEFT),
    'direito': lambda: protocol.btn_mouse(protocol.MOUSE_RIGHT),
    'meio': lambda: protocol.btn_mouse(protocol.MOUSE_MIDDLE),
    'voltar': lambda: protocol.btn_mouse(protocol.MOUSE_BACK),
    'avancar': lambda: protocol.btn_mouse(protocol.MOUSE_FORWARD),
    'dpi+': protocol.btn_dpi_up,
    'dpi-': protocol.btn_dpi_down,
    'dpi-ciclo': protocol.btn_dpi_cycle,
    'tiro': protocol.btn_fire,
    'triplo': protocol.btn_three_click,
    'rgb': protocol.btn_rgb_toggle,
    'polling': protocol.btn_polling_switch,
    'nenhuma': lambda: protocol.BTN_NONE,
}
MIDIAS = {
    'play': protocol.MEDIA_PLAY_PAUSE, 'proxima': protocol.MEDIA_NEXT,
    'anterior': protocol.MEDIA_PREVIOUS, 'mudo': protocol.MEDIA_MUTE,
    'parar': protocol.MEDIA_STOP, 'vol+': protocol.MEDIA_VOL_UP,
    'vol-': protocol.MEDIA_VOL_DOWN,
}
NOMES_ACAO = {
    protocol.BTN_NONE: 'nenhuma', protocol.BTN_EXTENDED: 'multimídia/teclado',
    (0x01, 0x01, 0x00): 'esquerdo', (0x01, 0x02, 0x00): 'direito',
    (0x01, 0x04, 0x00): 'meio', (0x01, 0x08, 0x00): 'voltar',
    (0x01, 0x10, 0x00): 'avancar', (0x02, 0x02, 0x00): 'dpi+',
    (0x02, 0x03, 0x00): 'dpi-', (0x02, 0x01, 0x00): 'dpi-ciclo',
    (0x07, 0x00, 0x00): 'rgb', (0x08, 0x00, 0x00): 'polling',
}
USO_BOTAO = ("Uso: main.py botoes                  # lista os 16 botões\n"
             "     main.py botao <0-15> <ação>\n"
             f"ações: {' '.join(sorted(ACOES))}\n"
             f"mídia: {' '.join('midia:' + m for m in sorted(MIDIAS))}")


def _cmd_botoes(argv):
    if argv:
        raise SystemExit(USO_BOTAO)
    tabela = device.read_buttons()
    if tabela is None:
        raise SystemExit("Erro: não consegui ler os botões do mouse.")
    for i, a in enumerate(tabela):
        nome = NOMES_ACAO.get(a)
        if a[0] == 0x04:
            nome = f"tiro (velocidade {a[1]}, {a[2]} cliques)"
        extra = f"  slot 0x{protocol.ext_slot_addr(i):04X}" if a == protocol.BTN_EXTENDED else ""
        print(f"  {i:2d}: {a[0]:02x} {a[1]:02x} {a[2]:02x}  {nome or '?'}{extra}")


def _cmd_botao(argv):
    if len(argv) != 2:
        raise SystemExit(USO_BOTAO)
    try:
        idx = int(argv[0])
    except ValueError:
        raise SystemExit(f"Erro: o índice tem que ser um número.\n{USO_BOTAO}")
    nome = argv[1].lower()
    if nome.startswith('midia:'):
        chave = nome.split(':', 1)[1]
        if chave not in MIDIAS:
            raise SystemExit(f"Erro: mídia '{chave}' desconhecida.\n{USO_BOTAO}")
        vias, _ = device.send_media(idx, MIDIAS[chave])
        print(f"Botão {idx} = mídia '{chave}' (via {', '.join(vias)})")
        return
    if nome not in ACOES:
        raise SystemExit(f"Erro: ação '{nome}' desconhecida.\n{USO_BOTAO}")
    vias, _ = device.send_button(idx, ACOES[nome]())
    print(f"Botão {idx} = {nome} (via {', '.join(vias)})")


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
    cmd = {'botoes': _cmd_botoes, 'botões': _cmd_botoes,
           'botao': _cmd_botao, 'botão': _cmd_botao}.get(argv[0].lower())
    if cmd:
        try:
            return cmd(argv[1:])
        except (device.DeviceNotFound, ValueError) as e:
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

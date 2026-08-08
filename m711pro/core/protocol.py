"""Protocolo do Redragon M711 Pro — construção de pacotes (lógica pura, sem I/O).

Ver docs/PROTOCOL.md. Toda função aqui é testável por byte-match contra capturas
reais (tests/test_protocol.py).
"""

# A soma dos bytes fecha em 0x55 (mod 256) — vale para o checksum EXTERNO (pacote
# de 17 bytes) e para o INTERNO (7 bytes de dados do registrador 0xA0).
CHECKSUM_TARGET = 0x55

LED_ADDR = 0xA0          # registrador do LED
# Byte de EFEITO (data[0]) — decodificado por captura (docs/PROTOCOL.md):
EFFECT_CICLO = 0x00      # "LED correndo" / ciclo (arco-íris)
EFFECT_RESPIRACAO = 0x01  # respiração (pulsa a cor)
EFFECT_FIXO = 0x02       # cor estática
EFFECT_OFF = 0x04        # desligado
DEFAULT_SPEED = 0x96     # data[4] — velocidade do efeito (menor = mais rápido)
SPEED_RESPIRACAO = 0xBE  # velocidade padrão da respiração (observada)
SPEED_CICLO = 0x13       # velocidade padrão do ciclo (observada)
BRIGHTNESS_MAX = 0xFF    # data[5] — 100%; abaixo é a % direta (50% = 0x32)

# Aliases retrocompatíveis
MODE_ON = EFFECT_FIXO
MODE_OFF = EFFECT_OFF


def checksum(data):
    """Byte que fecha a soma de `data` em CHECKSUM_TARGET (mod 256)."""
    return (CHECKSUM_TARGET - sum(data)) & 0xFF


def record(values):
    """Registro da memória: os dados seguidos do checksum que os fecha em 0x55.

    A regra do checksum vale por registro, não só no pacote — confirmado contra
    um dump completo do hardware (ver docs/PROTOCOL.md).
    """
    values = [v & 0xFF for v in values]
    return values + [checksum(values)]


def build_write(addr, data):
    """Pacote de escrita (opcode 0x07) de 17 bytes, com endereço de 16 bits.

    Layout: 08 07 00 <ADDR_HI> <ADDR_LO> <LEN> <dados...> <padding> <cksum>
    """
    data = [b & 0xFF for b in data]
    payload = ([0x08, 0x07, 0x00, (addr >> 8) & 0xFF, addr & 0xFF, len(data)]
               + data)
    payload += [0x00] * (16 - len(payload))
    return bytes(payload + [checksum(payload)])


def build_led(effect, r, g, b, speed=DEFAULT_SPEED, brightness=BRIGHTNESS_MAX):
    """Pacote do registrador 0xA0 (17 bytes).

    Layout: 08 07 00 00 A0 07 | EFEITO R G B VELOCIDADE BRILHO <inner> | 00 00 00 <cksum>
    <inner> é um checksum interno dos 7 bytes de dados.
    """
    data = [effect, r & 0xFF, g & 0xFF, b & 0xFF, speed & 0xFF, brightness & 0xFF]
    return build_write(LED_ADDR, record(data))


def build_color(r, g, b, brightness=BRIGHTNESS_MAX):
    """Comando de cor sólida (LED ligado), com brilho opcional (0x00–0xFF)."""
    return build_led(EFFECT_FIXO, r, g, b, brightness=brightness)


def build_breathing(r, g, b, brightness=BRIGHTNESS_MAX, speed=SPEED_RESPIRACAO):
    """Efeito respiração (pulsa a cor escolhida)."""
    return build_led(EFFECT_RESPIRACAO, r, g, b, speed=speed, brightness=brightness)


def build_cycle(r, g, b, brightness=BRIGHTNESS_MAX, speed=SPEED_CICLO):
    """Efeito ciclo / "LED correndo" (arco-íris)."""
    return build_led(EFFECT_CICLO, r, g, b, speed=speed, brightness=brightness)


def build_off():
    """Comando de desligar o LED (a cor é irrelevante com o LED apagado)."""
    return build_led(EFFECT_OFF, 0, 0, 0)


def build_commit():
    """Comando de aplicar/salvar (opcode 0x04) observado após as escritas."""
    payload = [0x08, 0x04] + [0x00] * 14
    return bytes(payload + [checksum(payload)])


def build_read(addr, length=8):
    """Requisição de LEITURA (Report ID 08, opcode 08): pede `length` bytes em
    `addr`. A resposta volta por interrupt IN como Report ID 09, mesmo layout.

    O endereço é de 16 bits — a config principal vive em 0x0000–0x00A8, mas o
    app oficial varre até 0x1981 (ver docs/PROTOCOL.md).
    """
    payload = ([0x08, 0x08, 0x00, (addr >> 8) & 0xFF, addr & 0xFF, length & 0xFF]
               + [0x00] * 10)
    return bytes(payload + [checksum(payload)])


# --- DPI (registrador 0x000C) -----------------------------------------------
DPI_ADDR = 0x000C
DPI_STAGES = 5            # o app escreve exatamente 5 estágios
DPI_MIN = 100             # faixa oferecida pelo slider do app
DPI_MAX = 16000
DPI_BYTE_MAX = 0xBD       # maior valor já observado no firmware (~15833 DPI)
DPI_STEP = 250 / 3        # ~83,33 DPI por unidade do registrador


def dpi_to_byte(dpi):
    """DPI -> byte do registrador. Passo de ~83,33 DPI: n = round(DPI*3/250) - 1.

    Validado contra 6 valores lidos na tela do app oficial (700, 1000, 2000,
    4000, 8000, 10000). O resultado é limitado à faixa observada no hardware.
    """
    dpi = max(DPI_MIN, min(DPI_MAX, int(dpi)))
    n = (dpi * 3 + 125) // 250 - 1        # arredonda para o passo mais próximo
    return max(0x00, min(DPI_BYTE_MAX, n))


def byte_to_dpi(n):
    """Byte do registrador -> DPI (inversa de dpi_to_byte, sem o clamp)."""
    return round((n + 1) * 250 / 3)


def build_dpi_table_bytes(values):
    """Os TRÊS pacotes da tabela de DPI a partir dos BYTES crus do registrador.

    Cada entrada ocupa 4 bytes (`X Y 00 <cksum>`); X e Y são os eixos, aqui
    sempre iguais. Só emitimos as formas que aparecem em captura — 0x0C com
    LEN 8, 0x14 com LEN 8 e 0x1C com LEN 4. Escrever um estágio isolado nunca
    foi observado e por isso não é oferecido.

    Esta é a forma preferida quando se preserva estágios que não vão mudar: o
    caminho byte -> DPI -> byte NÃO é identidade acima de 0xBD, então
    reconstruir a partir do DPI rebaixaria silenciosamente esses estágios.
    """
    if len(values) != DPI_STAGES:
        raise ValueError(f"a tabela precisa de {DPI_STAGES} estágios, "
                         f"recebi {len(values)}")
    e = [record([v & 0xFF] * 2 + [0x00]) for v in values]
    return [build_write(DPI_ADDR, e[0] + e[1]),
            build_write(DPI_ADDR + 8, e[2] + e[3]),
            build_write(DPI_ADDR + 16, e[4])]


def build_dpi_table(stages):
    """Como build_dpi_table_bytes, mas recebendo os 5 valores em DPI."""
    return build_dpi_table_bytes([dpi_to_byte(d) for d in stages])


# --- Botões (registradores 0x0060–0x009F) -----------------------------------
# 16 registros de 4 bytes: TIPO, P1, P2, checksum do registro. São escritos em
# oito pacotes de LEN 8 (dois botões por pacote), como o app oficial faz.
#
# A tabela de tipos foi decodificada aplicando um perfil com ações conhecidas e
# lendo a memória antes e depois. O layout de 16 entradas e o endereço do slot
# estendido vieram do m913-ctl (github.com/Qehbr/m913-ctl, GPL-3.0), que mapeou
# o mesmo chip Compx no Redragon M913 — e foram conferidos contra este mouse.
BUTTON_ADDR = 0x0060
BUTTON_COUNT = 16
BUTTONS_PER_PACKET = 2

BTN_NONE = (0x00, 0x00, 0x00)      # sem ação / desabilitado
BTN_EXTENDED = (0x05, 0x00, 0x00)  # a ação vive no slot estendido (ver build_media)

MOUSE_LEFT = 0x01
MOUSE_RIGHT = 0x02
MOUSE_MIDDLE = 0x04
MOUSE_BACK = 0x08
MOUSE_FORWARD = 0x10


def btn_mouse(mask):
    """Botão de mouse comum. `mask` é um dos MOUSE_*."""
    return (0x01, mask & 0xFF, 0x00)


def btn_dpi_up():
    return (0x02, 0x02, 0x00)


def btn_dpi_down():
    return (0x02, 0x03, 0x00)


def btn_dpi_cycle():
    return (0x02, 0x01, 0x00)


def btn_fire(speed=0x3A, clicks=3):
    """Disparo repetido. `speed` 3–255 (menor = mais rápido), `clicks` 0–3.

    "Three click" do app é este mesmo tipo com velocidade 0x32 e 3 cliques.
    """
    return (0x04, speed & 0xFF, clicks & 0xFF)


def btn_three_click():
    return btn_fire(speed=0x32, clicks=3)


def btn_rgb_toggle():
    """Liga/desliga o LED.

    ⚠️ O m913-ctl atribui `0x07` ao "polling switch" e `0x08` ao "led toggle" —
    o inverso disto. Aqui seguimos o que foi medido neste mouse: atribuindo
    "RGB ON/OFF" pelo app oficial, o registrador virou `07`. Ver PROTOCOL.md.
    """
    return (0x07, 0x00, 0x00)


def btn_polling_switch():
    """Alterna a taxa de relatório. Ver a ressalva em btn_rgb_toggle()."""
    return (0x08, 0x00, 0x00)


def build_buttons(actions):
    """Os OITO pacotes que escrevem a tabela de botões inteira.

    `actions` são 16 tuplas (TIPO, P1, P2) — uma por índice de botão. O
    protocolo escreve a tabela toda, então quem muda um botão precisa passar os
    outros quinze como estão (ver device.send_button).
    """
    if len(actions) != BUTTON_COUNT:
        raise ValueError(f"a tabela precisa de {BUTTON_COUNT} ações, "
                         f"recebi {len(actions)}")
    pkts = []
    for i in range(0, BUTTON_COUNT, BUTTONS_PER_PACKET):
        dados = []
        for a in actions[i:i + BUTTONS_PER_PACKET]:
            dados += record(list(a))
        pkts.append(build_write(BUTTON_ADDR + 4 * i, dados))
    return pkts


# --- Slot estendido: multimídia e teclado -----------------------------------
# Ações que não cabem nos 3 bytes do registro básico ficam num slot de 32 bytes.
# O botão guarda BTN_EXTENDED e o slot guarda o evento de apertar e o de soltar.
EXT_SLOT_BASE = 0x0100
EXT_SLOT_STRIDE = 0x20
EVENT_MEDIA_DOWN = 0x82        # apertar, página HID Consumer
EVENT_MEDIA_UP = 0x42          # soltar

# Usages da HID Consumer Page. Os quatro primeiros foram confirmados neste
# mouse; os demais vêm da tabela do m913-ctl.
MEDIA_PLAY_PAUSE = 0x00CD      # ✅ confirmado
MEDIA_NEXT = 0x00B5            # ✅ confirmado
MEDIA_PREVIOUS = 0x00B6        # ✅ confirmado
MEDIA_MUTE = 0x00E2            # ✅ confirmado
MEDIA_STOP = 0x00B7
MEDIA_VOL_UP = 0x00E9
MEDIA_VOL_DOWN = 0x00EA


def ext_slot_addr(index):
    """Endereço do slot estendido do botão `index`."""
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"índice de botão fora de 0..{BUTTON_COUNT - 1}")
    return EXT_SLOT_BASE + EXT_SLOT_STRIDE * index


def build_media(index, usage):
    """Grava uma tecla de multimídia no slot estendido do botão `index`.

    `usage` é o código de 16 bits da HID Consumer Page (MEDIA_*). O registro
    guarda o evento de apertar e o de soltar com o mesmo código.

    Para o botão funcionar, o registro básico dele tem que ser BTN_EXTENDED.
    """
    lo, hi = usage & 0xFF, (usage >> 8) & 0xFF
    data = record([0x02, EVENT_MEDIA_DOWN, lo, hi, EVENT_MEDIA_UP, lo, hi])
    return build_write(ext_slot_addr(index), data)


# --- Efeito de DPI (registrador 0x004C) -------------------------------------
DPI_EFFECT_ADDR = 0x004C
DPI_EFFECT_STEADY = 0x01
DPI_EFFECT_OFF = 0x00
# 0x4E e 0x50 completam o grupo do efeito. O significado ainda é 🚧 — estes são
# os valores da captura, usados só como último recurso; o caminho normal é ler
# os atuais do hardware e devolvê-los intactos (device.send_dpi_effect).
DPI_EFFECT_TAIL = (0x01, 0x03)


def build_dpi_effect(on, tail=DPI_EFFECT_TAIL):
    """Liga (Steady) ou desliga o "DPI Effect" — o LED que indica o nível de DPI.

    Ligado, o app escreve três registros de 2 bytes (0x4C, 0x4E, 0x50);
    desligado, escreve só o 0x4C. Reproduzimos as duas formas capturadas.

    `tail` são os valores de 0x4E e 0x50. Passe os lidos do hardware para não
    sobrescrever campos que ainda não decodificamos.
    """
    if not on:
        return build_write(DPI_EFFECT_ADDR, record([DPI_EFFECT_OFF]))
    data = record([DPI_EFFECT_STEADY])
    for v in tail:
        data += record([v])
    return build_write(DPI_EFFECT_ADDR, data)

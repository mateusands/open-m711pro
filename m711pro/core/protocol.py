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

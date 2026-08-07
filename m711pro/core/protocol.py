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


def build_led(effect, r, g, b, speed=DEFAULT_SPEED, brightness=BRIGHTNESS_MAX):
    """Pacote do registrador 0xA0 (17 bytes).

    Layout: 08 07 00 00 A0 07 | EFEITO R G B VELOCIDADE BRILHO <inner> | 00 00 00 <cksum>
    <inner> é um checksum interno dos 7 bytes de dados.
    """
    data = [effect, r & 0xFF, g & 0xFF, b & 0xFF, speed & 0xFF, brightness & 0xFF]
    inner = checksum(data)
    payload = [0x08, 0x07, 0x00, 0x00, LED_ADDR, 0x07] + data + [inner, 0x00, 0x00, 0x00]
    return bytes(payload + [checksum(payload)])


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
    """
    payload = [0x08, 0x08, 0x00, 0x00, addr & 0xFF, length & 0xFF] + [0x00] * 10
    return bytes(payload + [checksum(payload)])

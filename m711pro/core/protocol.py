"""Protocolo do Redragon M711 Pro — construção de pacotes (lógica pura, sem I/O).

Ver docs/PROTOCOL.md. Toda função aqui é testável por byte-match contra capturas
reais (tests/test_protocol.py).
"""

# A soma dos bytes fecha em 0x55 (mod 256) — vale para o checksum EXTERNO (pacote
# de 17 bytes) e para o INTERNO (7 bytes de dados do registrador 0xA0).
CHECKSUM_TARGET = 0x55

LED_ADDR = 0xA0      # registrador do LED (modo + RGB + brilho)
MODE_ON = 0x02       # LED ligado (cor estática)
MODE_OFF = 0x04      # LED desligado


def checksum(data):
    """Byte que fecha a soma de `data` em CHECKSUM_TARGET (mod 256)."""
    return (CHECKSUM_TARGET - sum(data)) & 0xFF


def build_led(mode, r, g, b):
    """Pacote do registrador 0xA0 (17 bytes).

    Layout: 08 07 00 00 A0 07 | mode R G B 96 FF <inner> | 00 00 00 <cksum>
    <inner> é um checksum interno dos 7 bytes de dados (explica o BF/BD).
    """
    data6 = [mode, r & 0xFF, g & 0xFF, b & 0xFF, 0x96, 0xFF]
    inner = checksum(data6)
    payload = [0x08, 0x07, 0x00, 0x00, LED_ADDR, 0x07] + data6 + [inner, 0x00, 0x00, 0x00]
    return bytes(payload + [checksum(payload)])


def build_color(r, g, b):
    """Comando de cor sólida (LED ligado)."""
    return build_led(MODE_ON, r, g, b)


def build_off():
    """Comando de desligar o LED (a cor é irrelevante com o LED apagado)."""
    return build_led(MODE_OFF, 0, 0, 0)


def build_commit():
    """Comando de aplicar/salvar (opcode 0x04) observado após as escritas."""
    payload = [0x08, 0x04] + [0x00] * 14
    return bytes(payload + [checksum(payload)])

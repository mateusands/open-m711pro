"""Byte-match: os pacotes gerados têm que bater com as capturas reais do
software oficial (ver docs/PROTOCOL.md). É a prova de que o protocolo está certo.
"""
from m711pro.core import protocol as p


def test_vermelho_bate_com_captura():
    assert p.build_color(255, 0, 0).hex() == "08070000a00702ff000096ffbf0000004a"


def test_verde_bate_com_captura():
    assert p.build_color(0, 255, 0).hex() == "08070000a0070200ff0096ffbf0000004a"


def test_off_bate_com_captura():
    # captura do OFF com a cor vermelha ainda no registrador
    assert p.build_led(p.MODE_OFF, 255, 0, 0).hex() == "08070000a00704ff000096ffbd0000004a"


def test_commit_bate_com_captura():
    assert p.build_commit().hex() == "0804000000000000000000000000000049"


def test_checksum_externo_fecha_em_0x55():
    pkt = p.build_color(18, 52, 86)      # cor arbitrária
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


def test_checksum_interno_fecha_em_0x55():
    pkt = p.build_color(255, 128, 0)     # cor mista
    dados = pkt[6:13]                    # 7 bytes de dados do registrador 0xA0
    assert sum(dados) % 256 == p.CHECKSUM_TARGET


def test_pacote_tem_17_bytes():
    assert len(p.build_color(1, 2, 3)) == 17
    assert len(p.build_off()) == 17
    assert len(p.build_commit()) == 17

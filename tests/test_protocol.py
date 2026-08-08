"""Byte-match: os pacotes gerados têm que bater com as capturas reais do
software oficial (ver docs/PROTOCOL.md). É a prova de que o protocolo está certo.
"""
from m711pro.core import protocol as p


def test_vermelho_bate_com_captura():
    assert p.build_color(255, 0, 0).hex() == "08070000a00702ff000096ffbf0000004a"


def test_verde_bate_com_captura():
    assert p.build_color(0, 255, 0).hex() == "08070000a0070200ff0096ffbf0000004a"


def test_brilho_50_bate_com_captura():
    # capturado no mapeamento: verde a 50% de brilho -> byte 0x32
    assert p.build_color(0, 255, 0, brightness=0x32).hex() == "08070000a0070200ff0096328c0000004a"


def test_respiracao_bate_com_captura():
    # capturado: respiração em vermelho, velocidade 0xBE
    assert p.build_breathing(255, 0, 0).hex() == "08070000a00701ff0000beff980000004a"


def test_ciclo_bate_com_captura():
    # capturado: ciclo ("LED correndo") em vermelho, velocidade 0x13
    assert p.build_cycle(255, 0, 0).hex() == "08070000a00700ff000013ff440000004a"


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


# --- DPI (registrador 0x000C) -----------------------------------------------
# Contrato: a codificação é DPI = (n+1) * 250/3 (passo ~83,33 DPI), confirmada
# com 6 valores lidos na tela do app oficial e cruzados com a captura. O valor
# 10000 -> 0x77 foi o experimento que desempatou a fórmula concorrente.
# Ver docs/PROTOCOL.md, seção "Registrador de DPI".

PARES_DPI = [(700, 0x07), (1000, 0x0B), (2000, 0x17),
             (4000, 0x2F), (8000, 0x5F), (10000, 0x77)]


def test_dpi_para_byte_bate_com_os_valores_do_app():
    for dpi, byte in PARES_DPI:
        assert p.dpi_to_byte(dpi) == byte, f"{dpi} DPI deveria virar {byte:#04x}"


def test_byte_para_dpi_faz_o_caminho_de_volta():
    for dpi, byte in PARES_DPI:
        assert round(p.byte_to_dpi(byte) / 100) * 100 == round(dpi / 100) * 100


def test_dpi_clampa_na_faixa_do_app():
    assert p.dpi_to_byte(10) == 0x00        # abaixo do mínimo
    assert p.dpi_to_byte(99999) == 0xBD     # satura no que o firmware segura


def test_tabela_dpi_bate_com_captura():
    # captura: tabela de fábrica 700 / 2000 / 4000 / 8000 / 16000, escrita em
    # três pacotes (0x0C LEN 8, 0x14 LEN 8, 0x1C LEN 4)
    pkts = p.build_dpi_table([700, 2000, 4000, 8000, 16000])
    assert [x.hex() for x in pkts] == [
        "080700000c080707004717170027000088",
        "0807000014082f2f00f75f5f0097000080",
        "080700001c04bdbd00db000000000000d1",
    ]


def test_tabela_dpi_com_estagio_1_em_10000_bate_com_captura():
    # captura do experimento decisivo: estágio 1 subido para 10000 DPI
    pkts = p.build_dpi_table([10000, 2000, 4000, 8000, 16000])
    assert pkts[0].hex() == "080700000c087777006717170027000088"


def test_tabela_dpi_com_estagio_1_em_1000_bate_com_captura():
    pkts = p.build_dpi_table([1000, 2000, 4000, 8000, 16000])
    assert pkts[0].hex() == "080700000c080b0b003f17170027000088"


def test_tabela_dpi_por_bytes_bate_com_captura():
    # mesma tabela de fábrica, agora a partir dos bytes crus do registrador
    pkts = p.build_dpi_table_bytes([0x07, 0x17, 0x2F, 0x5F, 0xBD])
    assert [x.hex() for x in pkts] == [
        "080700000c080707004717170027000088",
        "0807000014082f2f00f75f5f0097000080",
        "080700001c04bdbd00db000000000000d1",
    ]


def test_byte_do_dpi_sobrevive_ao_ciclo_de_leitura_e_escrita():
    # send_dpi lê os 5 estágios e reescreve todos: se byte -> DPI -> byte não
    # fosse identidade, mudar UM estágio alteraria os outros em silêncio.
    for n in range(p.DPI_BYTE_MAX + 1):
        assert p.dpi_to_byte(p.byte_to_dpi(n)) == n, f"byte {n:#04x} não volta"


def test_um_dpi_so_deixa_os_cinco_estagios_iguais():
    # modo "um DPI só": todos os estágios recebem o mesmo byte, então o botão
    # de DPI do mouse cicla sem mudar a sensibilidade
    b = p.dpi_to_byte(1600)
    pkts = p.build_dpi_table_bytes([b] * p.DPI_STAGES)
    assert pkts[0][6:14] == pkts[0][6:10] * 2           # estágios 1 e 2 iguais
    assert pkts[1][6:14] == pkts[0][6:10] * 2           # estágios 3 e 4 iguais
    assert pkts[2][6:10] == pkts[0][6:10]               # estágio 5 igual
    assert all(sum(x) % 256 == p.CHECKSUM_TARGET for x in pkts)


def test_tabela_dpi_exige_cinco_estagios():
    try:
        p.build_dpi_table([700, 2000])
    except ValueError:
        return
    raise AssertionError("build_dpi_table deveria recusar uma tabela incompleta")


# --- DPI Effect (registrador 0x004C) ----------------------------------------
def test_dpi_effect_ligado_bate_com_captura():
    assert p.build_dpi_effect(True).hex() == "080700004c0601540154035200000000f5"


def test_dpi_effect_desligado_bate_com_captura():
    assert p.build_dpi_effect(False).hex() == "080700004c0200550000000000000000a3"


def test_dpi_effect_preserva_os_campos_nao_decodificados():
    # 0x4E e 0x50 ainda são 🚧: quem liga o efeito passa os valores lidos do
    # hardware, e eles têm que aparecer no pacote com o checksum de cada um.
    pkt = p.build_dpi_effect(True, tail=(0x02, 0x07))
    assert pkt[6:12] == bytes([0x01, 0x54, 0x02, 0x53, 0x07, 0x4E])
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


# --- Botões (0x0060-0x009F) -------------------------------------------------
# Contrato: 16 registros de 4 bytes (TIPO P1 P2 cksum), escritos em oito pacotes
# de LEN 8 (dois botões por pacote). Os oito pacotes abaixo são a captura do app
# oficial gravando a configuração de fábrica deste mouse.
# Ver docs/PROTOCOL.md, seção "Botões".

TABELA_PADRAO = (
    [p.btn_mouse(p.MOUSE_LEFT), p.btn_mouse(p.MOUSE_RIGHT),
     p.btn_mouse(p.MOUSE_MIDDLE), p.btn_mouse(p.MOUSE_BACK),
     p.btn_mouse(p.MOUSE_FORWARD), p.BTN_NONE, (0x09, 0x00, 0x00),
     p.BTN_NONE, p.BTN_NONE, p.BTN_EXTENDED, p.BTN_EXTENDED, p.BTN_EXTENDED]
    + [p.BTN_NONE] * 4)


def test_tabela_de_botoes_bate_com_captura():
    assert [x.hex() for x in p.build_buttons(TABELA_PADRAO)] == [
        "0807000060080101005301020052000034",
        "080700006808010400500108004c00002c",
        "0807000070080110004400000055000024",
        "0807000078080900004c0000005500001c",
        "0807000080080000005505000050000014",
        "080700008808050000500500005000000c",
        "0807000090080000005500000055000004",
        "08070000980800000055000000550000fc",
    ]


def test_acoes_batem_com_o_hardware():
    # lidos do mouse depois de atribuir cada ação pelo app oficial
    assert p.btn_fire(0x28, 3) == (0x04, 0x28, 0x03)
    assert p.btn_three_click() == (0x04, 0x32, 0x03)
    assert p.btn_rgb_toggle() == (0x07, 0x00, 0x00)
    assert p.btn_polling_switch() == (0x08, 0x00, 0x00)
    assert p.btn_dpi_up() == (0x02, 0x02, 0x00)
    assert p.BTN_NONE == (0x00, 0x00, 0x00)
    assert p.BTN_EXTENDED == (0x05, 0x00, 0x00)


def test_bitmask_dos_botoes_de_mouse():
    assert p.btn_mouse(p.MOUSE_LEFT) == (0x01, 0x01, 0x00)
    assert p.btn_mouse(p.MOUSE_FORWARD) == (0x01, 0x10, 0x00)


def test_cada_registro_de_botao_fecha_em_0x55():
    for pkt in p.build_buttons([p.btn_fire(0x3A, 2)] * p.BUTTON_COUNT):
        for i in range(6, 6 + pkt[5], 4):
            assert sum(pkt[i:i+4]) % 256 == p.CHECKSUM_TARGET


def test_build_buttons_exige_dezesseis_acoes():
    try:
        p.build_buttons(TABELA_PADRAO[:8])
    except ValueError:
        return
    raise AssertionError("build_buttons deveria recusar uma tabela incompleta")


# --- Slot estendido (multimídia) --------------------------------------------
def test_endereco_do_slot_estendido():
    # slot = 0x0100 + 0x20 * indice — os três do nosso mouse
    assert p.ext_slot_addr(9) == 0x0220
    assert p.ext_slot_addr(10) == 0x0240
    assert p.ext_slot_addr(11) == 0x0260


def test_multimidia_bate_com_captura():
    assert p.build_media(9, p.MEDIA_PREVIOUS).hex() == \
        "0807000220080282b60042b600230000c7"
    assert p.build_media(10, p.MEDIA_PLAY_PAUSE).hex() == \
        "0807000240080282cd0042cd00f50000a7"
    assert p.build_media(11, p.MEDIA_NEXT).hex() == \
        "0807000260080282b50042b50025000087"


def test_multimidia_mute_bate_com_o_hardware():
    # lido do mouse depois de atribuir "Mute" pelo app oficial
    assert p.build_media(9, p.MEDIA_MUTE)[6:14].hex() == "0282e20042e200cb"


def test_multimidia_aceita_usage_de_16_bits():
    # "Home page" é o usage 0x0223 da HID Consumer Page — dois bytes, LE
    pkt = p.build_media(9, 0x0223)
    assert pkt[6:14].hex() == "0282230242230245"
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


# --- Leitura com endereço de 16 bits ----------------------------------------
def test_read_usa_endereco_de_16_bits():
    # captura: o app varre a página 0x0100 com LEN 0x0a
    assert p.build_read(0x0100, 0x0A).hex() == "08080001000a000000000000000000003a"


def test_read_do_led_continua_igual():
    # regressão: o LED está na página zero e não pode mudar um byte
    assert p.build_read(0xA0, 8).hex() == "08080000a008000000000000000000009d"

"""Byte-match: the generated packets must equal the real captures taken from the
official software (see the Protocol section of the README). This is the proof
that the protocol is right by construction.
"""
from m711pro.core import protocol as p


def test_red_matches_capture():
    assert p.build_color(255, 0, 0).hex() == "08070000a00702ff000096ffbf0000004a"


def test_green_matches_capture():
    assert p.build_color(0, 255, 0).hex() == "08070000a0070200ff0096ffbf0000004a"


def test_brightness_50_matches_capture():
    # captured during mapping: green at 50% brightness -> byte 0x32
    assert p.build_color(0, 255, 0, brightness=0x32).hex() == "08070000a0070200ff0096328c0000004a"


def test_breathing_matches_capture():
    # captured: breathing in red, speed 0xBE
    assert p.build_breathing(255, 0, 0).hex() == "08070000a00701ff0000beff980000004a"


def test_cycle_matches_capture():
    # captured: running cycle in red, speed 0x13
    assert p.build_cycle(255, 0, 0).hex() == "08070000a00700ff000013ff440000004a"


def test_off_matches_capture():
    # capture of OFF with red still sitting in the register
    assert p.build_led(p.MODE_OFF, 255, 0, 0).hex() == "08070000a00704ff000096ffbd0000004a"


def test_commit_matches_capture():
    assert p.build_commit().hex() == "0804000000000000000000000000000049"


def test_outer_checksum_settles_at_0x55():
    pkt = p.build_color(18, 52, 86)      # arbitrary colour
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


def test_record_checksum_settles_at_0x55():
    pkt = p.build_color(255, 128, 0)     # mixed colour
    data = pkt[6:13]                     # the seven data bytes of register 0xA0
    assert sum(data) % 256 == p.CHECKSUM_TARGET


def test_packet_is_17_bytes():
    assert len(p.build_color(1, 2, 3)) == 17
    assert len(p.build_off()) == 17
    assert len(p.build_commit()) == 17


# --- DPI (register 0x000C) -----------------------------------------------
# Contract: the encoding is DPI = (n+1) * 250/3 (~83.33 DPI per step), confirmed
# against six values read off the official app and cross-checked with captures.
# The 10000 -> 0x77 sample was the experiment that broke the tie with the rival
# formula. See the Protocol section of the README.

DPI_PAIRS = [(700, 0x07), (1000, 0x0B), (2000, 0x17),
             (4000, 0x2F), (8000, 0x5F), (10000, 0x77)]


def test_dpi_to_byte_matches_the_app_values():
    for dpi, byte in DPI_PAIRS:
        assert p.dpi_to_byte(dpi) == byte, f"{dpi} DPI should encode to {byte:#04x}"


def test_byte_to_dpi_round_trips():
    for dpi, byte in DPI_PAIRS:
        assert round(p.byte_to_dpi(byte) / 100) * 100 == round(dpi / 100) * 100


def test_dpi_clamps_to_the_app_range():
    assert p.dpi_to_byte(10) == 0x00        # below the minimum
    assert p.dpi_to_byte(99999) == 0xBD     # saturates at the firmware ceiling


def test_dpi_table_matches_capture():
    # capture: factory table 700 / 2000 / 4000 / 8000 / 16000, written as three
    # packets (0x0C LEN 8, 0x14 LEN 8, 0x1C LEN 4)
    pkts = p.build_dpi_table([700, 2000, 4000, 8000, 16000])
    assert [x.hex() for x in pkts] == [
        "080700000c080707004717170027000088",
        "0807000014082f2f00f75f5f0097000080",
        "080700001c04bdbd00db000000000000d1",
    ]


def test_dpi_table_with_stage_1_at_10000_matches_capture():
    # capture of the decisive experiment: stage 1 raised to 10000 DPI
    pkts = p.build_dpi_table([10000, 2000, 4000, 8000, 16000])
    assert pkts[0].hex() == "080700000c087777006717170027000088"


def test_dpi_table_with_stage_1_at_1000_matches_capture():
    pkts = p.build_dpi_table([1000, 2000, 4000, 8000, 16000])
    assert pkts[0].hex() == "080700000c080b0b003f17170027000088"


def test_dpi_table_from_bytes_matches_capture():
    # the same factory table, now from the raw register bytes
    pkts = p.build_dpi_table_bytes([0x07, 0x17, 0x2F, 0x5F, 0xBD])
    assert [x.hex() for x in pkts] == [
        "080700000c080707004717170027000088",
        "0807000014082f2f00f75f5f0097000080",
        "080700001c04bdbd00db000000000000d1",
    ]


def test_dpi_byte_survives_the_read_write_cycle():
    # send_dpi reads all five stages and rewrites them all: if byte -> DPI -> byte
    # were not the identity, changing ONE stage would silently alter the others.
    for n in range(p.DPI_BYTE_MAX + 1):
        assert p.dpi_to_byte(p.byte_to_dpi(n)) == n, f"byte {n:#04x} does not round-trip"


def test_single_dpi_leaves_all_five_stages_equal():
    # "single DPI" mode: every stage gets the same byte, so the mouse's DPI
    # button cycles without changing the sensitivity
    b = p.dpi_to_byte(1600)
    pkts = p.build_dpi_table_bytes([b] * p.DPI_STAGES)
    assert pkts[0][6:14] == pkts[0][6:10] * 2           # stages 1 and 2 equal
    assert pkts[1][6:14] == pkts[0][6:10] * 2           # stages 3 and 4 equal
    assert pkts[2][6:10] == pkts[0][6:10]               # stage 5 equal
    assert all(sum(x) % 256 == p.CHECKSUM_TARGET for x in pkts)


def test_dpi_table_requires_five_stages():
    try:
        p.build_dpi_table([700, 2000])
    except ValueError:
        return
    raise AssertionError("build_dpi_table should reject an incomplete table")


# --- DPI Effect (register 0x004C) ----------------------------------------
def test_dpi_effect_on_matches_capture():
    assert p.build_dpi_effect(True).hex() == "080700004c0601540154035200000000f5"


def test_dpi_effect_off_matches_capture():
    assert p.build_dpi_effect(False).hex() == "080700004c0200550000000000000000a3"


def test_dpi_effect_preserves_undecoded_fields():
    # 0x4E and 0x50 are still undecoded: turning the effect on passes the values
    # read from the hardware, and each must appear with its own checksum.
    pkt = p.build_dpi_effect(True, tail=(0x02, 0x07))
    assert pkt[6:12] == bytes([0x01, 0x54, 0x02, 0x53, 0x07, 0x4E])
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


# --- Buttons (0x0060-0x009F) -------------------------------------------------
# Contract: sixteen 4-byte records (TYPE P1 P2 cksum), written as eight LEN 8
# packets (two buttons each). The eight packets below are the capture of the
# official app writing this mouse's factory configuration.
# See the Protocol section of the README.

DEFAULT_TABLE = (
    [p.btn_mouse(p.MOUSE_LEFT), p.btn_mouse(p.MOUSE_RIGHT),
     p.btn_mouse(p.MOUSE_MIDDLE), p.btn_mouse(p.MOUSE_BACK),
     p.btn_mouse(p.MOUSE_FORWARD), p.BTN_NONE, (0x09, 0x00, 0x00),
     p.BTN_NONE, p.BTN_NONE, p.BTN_EXTENDED, p.BTN_EXTENDED, p.BTN_EXTENDED]
    + [p.BTN_NONE] * 4)


def test_button_table_matches_capture():
    assert [x.hex() for x in p.build_buttons(DEFAULT_TABLE)] == [
        "0807000060080101005301020052000034",
        "080700006808010400500108004c00002c",
        "0807000070080110004400000055000024",
        "0807000078080900004c0000005500001c",
        "0807000080080000005505000050000014",
        "080700008808050000500500005000000c",
        "0807000090080000005500000055000004",
        "08070000980800000055000000550000fc",
    ]


def test_actions_match_the_hardware():
    # read from the mouse after assigning each action through the official app
    assert p.btn_fire(0x28, 3) == (0x04, 0x28, 0x03)
    assert p.btn_three_click() == (0x04, 0x32, 0x03)
    # single-variable experiment: button 2 set to "RGB ON/OFF" alone -> 0x08
    assert p.btn_rgb_toggle() == (0x08, 0x00, 0x00)
    assert p.btn_polling_switch() == (0x07, 0x00, 0x00)
    assert p.btn_dpi_up() == (0x02, 0x02, 0x00)
    assert p.BTN_NONE == (0x00, 0x00, 0x00)
    assert p.BTN_EXTENDED == (0x05, 0x00, 0x00)


def test_mouse_button_bitmasks():
    assert p.btn_mouse(p.MOUSE_LEFT) == (0x01, 0x01, 0x00)
    assert p.btn_mouse(p.MOUSE_FORWARD) == (0x01, 0x10, 0x00)


def test_every_button_record_settles_at_0x55():
    for pkt in p.build_buttons([p.btn_fire(0x3A, 2)] * p.BUTTON_COUNT):
        for i in range(6, 6 + pkt[5], 4):
            assert sum(pkt[i:i+4]) % 256 == p.CHECKSUM_TARGET


def test_build_buttons_requires_sixteen_actions():
    try:
        p.build_buttons(DEFAULT_TABLE[:8])
    except ValueError:
        return
    raise AssertionError("build_buttons should reject an incomplete table")


# --- Extended slot (multimedia) --------------------------------------------
def test_extended_slot_address():
    # slot = 0x0100 + 0x20 * index — the three used on our mouse
    assert p.ext_slot_addr(9) == 0x0220
    assert p.ext_slot_addr(10) == 0x0240
    assert p.ext_slot_addr(11) == 0x0260


def test_multimedia_matches_capture():
    assert p.build_media(9, p.MEDIA_PREVIOUS)[0].hex() == \
        "0807000220080282b60042b600230000c7"
    assert p.build_media(10, p.MEDIA_PLAY_PAUSE)[0].hex() == \
        "0807000240080282cd0042cd00f50000a7"
    assert p.build_media(11, p.MEDIA_NEXT)[0].hex() == \
        "0807000260080282b50042b50025000087"


def test_multimedia_mute_matches_the_hardware():
    # read from the mouse after assigning "Mute" through the official app
    assert p.build_media(9, p.MEDIA_MUTE)[0][6:14].hex() == "0282e20042e200cb"


def test_multimedia_accepts_a_16_bit_usage():
    # "Home page" is HID Consumer Page usage 0x0223 — two bytes, little-endian
    pkt = p.build_media(9, 0x0223)[0]
    assert pkt[6:14].hex() == "0282230242230245"
    assert sum(pkt) % 256 == p.CHECKSUM_TARGET


# --- Reading with a 16-bit address ----------------------------------------
def test_read_uses_a_16_bit_address():
    # capture: the app scans page 0x0100 with LEN 0x0a
    assert p.build_read(0x0100, 0x0A).hex() == "08080001000a000000000000000000003a"


def test_reading_the_led_is_unchanged():
    # regression: the LED lives on page zero and must not change by a byte
    assert p.build_read(0xA0, 8).hex() == "08080000a008000000000000000000009d"


# --- Per-stage DPI colours (register 0x002C) --------------------------------
# The mouse shows a colour per DPI stage. Same shape as the DPI table: five
# 4-byte records in three captured packets (LEN 8 / 8 / 4).

FACTORY_COLORS = [(255, 0, 0), (0, 0, 255), (0, 255, 0), (255, 255, 0), (255, 128, 0)]


def test_dpi_colors_match_capture():
    assert [x.hex() for x in p.build_dpi_colors(FACTORY_COLORS)] == [
        "080700002c08ff0000560000ff56000068",
        "08070000340800ff0056ffff0057000060",
        "080700003c04ff8000d6000000000000b1",
    ]


def test_every_dpi_color_record_settles_at_0x55():
    for pkt in p.build_dpi_colors(FACTORY_COLORS):
        assert sum(pkt) % 256 == p.CHECKSUM_TARGET
        for i in range(6, 6 + pkt[5], 4):
            assert sum(pkt[i:i + 4]) % 256 == p.CHECKSUM_TARGET


def test_dpi_colors_requires_five_stages():
    for wrong in ([(0, 0, 0)] * 4, [(0, 0, 0)] * 6):
        try:
            p.build_dpi_colors(wrong)
        except ValueError:
            continue
        raise AssertionError("build_dpi_colors should reject a wrong-sized table")


# --- Independent X/Y axes ---------------------------------------------------
def test_dpi_table_bytes_accepts_an_independent_xy_stage():
    # a stage given as a pair writes different axis bytes, with a valid record
    pkts = p.build_dpi_table_bytes([(0x07, 0x17), 0x17, 0x2F, 0x5F, 0xBD])
    assert pkts[0][6:10].hex() == "07170037"
    assert sum(pkts[0][6:10]) % 256 == p.CHECKSUM_TARGET
    assert pkts[0][10:14].hex() == "17170027"        # neighbour untouched


def test_dpi_table_accepts_an_independent_xy_stage_in_dpi():
    pkts = p.build_dpi_table([(700, 2000), 2000, 4000, 8000, 16000])
    assert pkts[0][6:8] == bytes([p.dpi_to_byte(700), p.dpi_to_byte(2000)])


def test_int_and_equal_tuple_produce_identical_packets():
    single = p.build_dpi_table_bytes([0x07, 0x17, 0x2F, 0x5F, 0xBD])
    paired = p.build_dpi_table_bytes([(0x07, 0x07), (0x17, 0x17), (0x2F, 0x2F),
                                      (0x5F, 0x5F), (0xBD, 0xBD)])
    assert single == paired


# --- Extended slot: the general event list ----------------------------------
# Decoded on this mouse. The first data byte is the EVENT COUNT, not a type,
# and every event is <type> <code lo> <code hi>. Both records below were read
# back from the hardware after assigning them through the official app.

def test_keyboard_key_matches_the_hardware():
    # button 2 given a single key: slot 0x0120 held this
    pkts = p.build_key(1, 0x1F)
    assert len(pkts) == 1
    assert pkts[0][6:14].hex() == "02811f00411f0053"


def test_modifier_combo_matches_the_hardware():
    # Button 7 given Ctrl+C. The record is 14 bytes, which does NOT fit one
    # packet, so it goes out as two — and reassembling them must reproduce the
    # exact bytes read back from slot 0x0260.
    pkts = p.build_combo(11, p.MOD_CTRL_L, 0x06)
    assert len(pkts) == 2
    assert all(len(x) == 17 for x in pkts)
    assert (pkts[0][3] << 8 | pkts[0][4]) == 0x0260
    assert (pkts[1][3] << 8 | pkts[1][4]) == 0x026A     # continues ten bytes on
    rebuilt = pkts[0][6:6 + pkts[0][5]] + pkts[1][6:6 + pkts[1][5]]
    assert rebuilt.hex() == "0480010081060040010041060 0c1".replace(" ", "")
    assert all(sum(x) % 256 == p.CHECKSUM_TARGET for x in pkts)


def test_event_count_is_the_first_data_byte():
    assert p.build_key(0, 0x04)[0][6] == 2              # press + release
    assert p.build_media(0, p.MEDIA_MUTE)[0][6] == 2
    assert p.build_combo(0, p.MOD_CTRL_L, 0x06)[0][6] == 4


def test_a_packet_never_exceeds_17_bytes():
    # the guard that would have caught the oversized combo packet
    for n in range(1, 7):
        for pkt in p.build_events(0, [(p.EVENT_KEY_DOWN, 0x04)] * n):
            assert len(pkt) == 17, f"{n} events produced a {len(pkt)}-byte packet"


def test_build_write_rejects_data_that_cannot_fit():
    try:
        p.build_write(0x0100, [0] * (p.MAX_DATA + 1))
    except ValueError:
        return
    raise AssertionError("build_write should refuse more data than a packet holds")


# --- DPI labels: show what the official app shows ---------------------------
# The register holds ~83.33 DPI steps, so the byte the app writes for "700"
# decodes to 667. Showing 667 is honest but reads as a bug to everyone who
# typed 700 (an owner reported exactly that). Because the step is smaller than
# 100, every multiple of 100 lands on its own byte, so the app's label can be
# recovered from the byte alone — WITHOUT changing a single byte on the wire.
#
# Origin: the six (label, byte) pairs read off the official app during the
# DPI captures, plus 0xBD = "16000" from the app's own Cfg.ini.
APP_LABELS = {0x07: 700, 0x0B: 1000, 0x17: 2000, 0x2F: 4000, 0x5F: 8000,
              0x77: 10000, 0xBD: 16000}


def test_dpi_label_reproduces_every_label_the_official_app_showed():
    for byte, label in APP_LABELS.items():
        assert p.dpi_label(byte) == label, hex(byte)


def test_dpi_display_round_trips_to_the_same_byte_for_every_byte():
    # the safety property: typing back what is shown must write the same byte
    for byte in range(p.DPI_BYTE_MAX + 1):
        assert p.dpi_to_byte(p.dpi_display(byte)) == byte, hex(byte)


def test_every_multiple_of_100_comes_back_as_typed():
    # up to 15700: 15800 and 16000 both saturate at the ceiling byte 0xBD,
    # which the app calls 16000 (next test)
    for dpi in range(p.DPI_MIN, 15800, 100):
        assert p.dpi_display(p.dpi_to_byte(dpi)) == dpi, dpi


def test_the_ceiling_shows_as_16000_whichever_value_reached_it():
    assert p.dpi_display(p.dpi_to_byte(15800)) == 16000
    assert p.dpi_display(p.dpi_to_byte(16000)) == 16000


def test_a_byte_with_no_round_label_shows_the_real_value():
    # 0x08 sits between 700 (0x07) and 800 (0x09): no app label lands on it
    assert p.dpi_label(0x08) is None
    assert p.dpi_display(0x08) == p.byte_to_dpi(0x08) == 750


def test_dpi_text_mentions_the_real_value_only_when_it_differs():
    assert p.dpi_text(0x07) == "700 DPI (≈667 real)"
    assert p.dpi_text(0x0B) == "1000 DPI"
    assert p.dpi_text(0x08) == "750 DPI"

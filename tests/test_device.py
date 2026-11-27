"""Device layer tests — the LOGIC, never the hardware.

`core/device.py` is the only module that touches hidraw, so testing it means
proving what it *decides*, not what the wire does. Every test here replaces the
module's own functions (`read_register`, `send_packets`, `find_devices`) with
fakes, captures the packets that WOULD have been sent and asserts on them. The
two hidraw primitives are replaced by tripwires: if a test ever reaches them the
test fails instead of talking to a real mouse.

The invariant that matters most: whenever a command rewrites a whole table (DPI
stages, buttons), the entries it was not asked to change must come back out byte
for byte — including bytes this code cannot interpret or round-trip.
"""
import contextlib

from m711pro.core import device, protocol, state


# --- Fakes ------------------------------------------------------------------
def read_reply(addr, data):
    """A Report ID 09 read reply, in the shape device.read_register returns."""
    header = [0x09, 0x08, 0x00, (addr >> 8) & 0xFF, addr & 0xFF, len(data)]
    return bytes(header + list(data))


class FakeDevice:
    """Stands in for the hidraw layer: answers reads, records writes."""

    def __init__(self, registers=None, routes=("2.4G",)):
        self.registers = dict(registers or {})   # addr -> record bytes
        self.routes = list(routes)
        self.sent = []                           # packets that would have gone out
        self.reads = []                          # (addr, length) asked for

    def read_register(self, addr, length=8, timeout=0.6):
        self.reads.append((addr, length))
        data = self.registers.get(addr)
        return None if data is None else read_reply(addr, data)

    def send_packets(self, packets):
        self.sent.extend(bytes(packet) for packet in packets)
        return list(self.routes)

    def find_devices(self):
        raise AssertionError("a test tried to enumerate real hardware")

    # -- reading back what was captured --
    def addresses(self):
        return [(packet[3] << 8) | packet[4] for packet in self.sent]

    def payloads(self):
        return [packet[6:6 + packet[5]] for packet in self.sent]


def _tripwire(*args, **kwargs):
    raise AssertionError("a test tried to open /dev/hidraw")


@contextlib.contextmanager
def stubbed(fake):
    """Swap the I/O layer for `fake` and always put the originals back."""
    originals = {name: getattr(device, name) for name in
                 ("read_register", "send_packets", "find_devices",
                  "_send_feature", "_read_from")}
    saved_state = (state.load, state.save)
    device.read_register = fake.read_register
    device.send_packets = fake.send_packets
    device.find_devices = fake.find_devices
    device._send_feature = _tripwire
    device._read_from = _tripwire
    state.load = lambda: {}
    state.save = lambda _state: None
    try:
        yield fake
    finally:
        for name, original in originals.items():
            setattr(device, name, original)
        state.load, state.save = saved_state


# --- Register fixtures ------------------------------------------------------
def dpi_registers(raw):
    """The three read replies holding a DPI table of five raw register bytes."""
    entries = [protocol.record([b, b, 0x00]) for b in raw]
    return {protocol.DPI_ADDR: entries[0] + entries[1],
            protocol.DPI_ADDR + 8: entries[2] + entries[3],
            protocol.DPI_ADDR + 16: entries[4]}


def button_registers(table):
    """The eight read replies holding a 16-entry button table."""
    return {protocol.BUTTON_ADDR + 4 * i:
            protocol.record(list(table[i])) + protocol.record(list(table[i + 1]))
            for i in range(0, protocol.BUTTON_COUNT, 2)}


def sent_dpi_bytes(fake):
    """The five stage bytes carried by the DPI packets that were sent."""
    out = []
    for data in fake.payloads():
        out += [data[i] for i in range(0, len(data), 4)]
    return out


def sent_button_table(fake, skip=0):
    """The 16 (TYPE, P1, P2) records carried by the button packets that were sent."""
    out = []
    for data in fake.payloads()[skip:]:
        out.append(tuple(data[0:3]))
        out.append(tuple(data[4:7]))
    return out


# A table whose stage 2 sits ABOVE the firmware ceiling 0xBD, so byte -> DPI ->
# byte would silently lower it (0xC8 -> 16750 DPI -> clamped back to 0xBD).
TABLE_WITH_UNREACHABLE_BYTE = [0x0B, 0xC8, 0x2F, 0x5F, 0xBD]

# A plausible button table holding one action type the code cannot interpret.
UNKNOWN_ACTION = (0x09, 0x00, 0x00)
BUTTON_TABLE = [
    protocol.btn_mouse(protocol.MOUSE_LEFT),
    protocol.btn_mouse(protocol.MOUSE_RIGHT),
    protocol.btn_mouse(protocol.MOUSE_MIDDLE),
    protocol.btn_dpi_cycle(),
    protocol.btn_mouse(protocol.MOUSE_BACK),
    protocol.btn_mouse(protocol.MOUSE_FORWARD),
    UNKNOWN_ACTION,
    protocol.btn_fire(speed=0x3A, clicks=3),
    protocol.BTN_EXTENDED,
    protocol.BTN_NONE,
] + [protocol.BTN_NONE] * 6


# --- DPI --------------------------------------------------------------------
def test_send_dpi_preserves_the_other_stages_byte_for_byte():
    """The heart of the contract: only the asked-for stage may change."""
    fake = FakeDevice(dpi_registers(TABLE_WITH_UNREACHABLE_BYTE))
    with stubbed(fake):
        routes, table = device.send_dpi(1, 4000)

    expected = list(TABLE_WITH_UNREACHABLE_BYTE)
    expected[0] = protocol.dpi_to_byte(4000)
    assert sent_dpi_bytes(fake) == expected
    assert routes == ["2.4G"]
    assert table == [protocol.byte_to_dpi(b) for b in expected]


def test_send_dpi_keeps_a_byte_that_cannot_round_trip():
    """0xC8 is above the 0xBD ceiling: a DPI round-trip would lower it."""
    assert protocol.dpi_to_byte(protocol.byte_to_dpi(0xC8)) != 0xC8

    fake = FakeDevice(dpi_registers(TABLE_WITH_UNREACHABLE_BYTE))
    with stubbed(fake):
        device.send_dpi(5, 1600)

    assert sent_dpi_bytes(fake)[1] == 0xC8


def test_send_dpi_writes_the_three_captured_packet_shapes():
    fake = FakeDevice(dpi_registers(TABLE_WITH_UNREACHABLE_BYTE))
    with stubbed(fake):
        device.send_dpi(3, 800)

    assert fake.addresses() == [protocol.DPI_ADDR, protocol.DPI_ADDR + 8,
                                protocol.DPI_ADDR + 16]
    assert [len(data) for data in fake.payloads()] == [8, 8, 4]


def test_send_dpi_aborts_when_the_table_cannot_be_read():
    """No read, no write: guessing the other four stages is forbidden."""
    fake = FakeDevice(registers={})           # nothing answers
    with stubbed(fake):
        try:
            device.send_dpi(2, 1600)
        except device.DeviceNotFound:
            pass
        else:
            raise AssertionError("expected DeviceNotFound")

    assert fake.sent == []


def test_send_dpi_aborts_when_only_part_of_the_table_answers():
    registers = dpi_registers(TABLE_WITH_UNREACHABLE_BYTE)
    del registers[protocol.DPI_ADDR + 16]     # the last stage stays silent
    fake = FakeDevice(registers)
    with stubbed(fake):
        try:
            device.send_dpi(1, 1600)
        except device.DeviceNotFound:
            pass
        else:
            raise AssertionError("expected DeviceNotFound")

    assert fake.sent == []


def test_send_dpi_rejects_a_stage_outside_1_to_5():
    fake = FakeDevice(dpi_registers(TABLE_WITH_UNREACHABLE_BYTE))
    with stubbed(fake):
        for stage in (0, -1, 6, 99):
            try:
                device.send_dpi(stage, 1600)
            except ValueError:
                continue
            raise AssertionError(f"stage {stage} should have been rejected")

    assert fake.reads == [] and fake.sent == []


def test_send_dpi_all_writes_the_same_byte_five_times():
    fake = FakeDevice()
    with stubbed(fake):
        routes, actual = device.send_dpi_all(1600)

    byte = protocol.dpi_to_byte(1600)
    assert sent_dpi_bytes(fake) == [byte] * protocol.DPI_STAGES
    assert (routes, actual) == (["2.4G"], protocol.byte_to_dpi(byte))
    assert fake.reads == []                   # nothing to preserve, nothing to read


def test_read_dpi_table_decodes_the_five_stages():
    fake = FakeDevice(dpi_registers([0x0B, 0x17, 0x2F, 0x5F, 0xBD]))
    with stubbed(fake):
        table = device.read_dpi_table()

    assert table == [protocol.byte_to_dpi(b)
                     for b in (0x0B, 0x17, 0x2F, 0x5F, 0xBD)]


def test_read_dpi_table_returns_none_when_nothing_answers():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        assert device.read_dpi_table() is None


# --- Buttons ----------------------------------------------------------------
def test_send_button_preserves_the_other_fifteen():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        routes, table = device.send_button(4, protocol.btn_dpi_up())

    expected = list(BUTTON_TABLE)
    expected[4] = protocol.btn_dpi_up()
    assert sent_button_table(fake) == expected
    assert table == expected
    assert routes == ["2.4G"]


def test_send_button_preserves_an_action_type_it_cannot_interpret():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        device.send_button(0, protocol.BTN_NONE)

    assert sent_button_table(fake)[6] == UNKNOWN_ACTION


def test_send_button_writes_the_eight_captured_packets():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        device.send_button(15, protocol.btn_rgb_toggle())

    assert fake.addresses() == [protocol.BUTTON_ADDR + 4 * i
                                for i in range(0, protocol.BUTTON_COUNT, 2)]
    assert sent_button_table(fake)[15] == protocol.btn_rgb_toggle()


def test_send_button_aborts_when_the_table_cannot_be_read():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        try:
            device.send_button(1, protocol.BTN_NONE)
        except device.DeviceNotFound:
            pass
        else:
            raise AssertionError("expected DeviceNotFound")

    assert fake.sent == []


def test_send_button_rejects_an_index_outside_0_to_15():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        for index in (-1, 16, 99):
            try:
                device.send_button(index, protocol.BTN_NONE)
            except ValueError:
                continue
            raise AssertionError(f"index {index} should have been rejected")

    assert fake.reads == [] and fake.sent == []


def test_read_buttons_returns_none_when_nothing_answers():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        assert device.read_buttons() is None


# --- Multimedia / keyboard (extended slot) ----------------------------------
def test_send_media_preserves_the_other_fifteen_buttons():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        routes, table = device.send_media(9, protocol.MEDIA_MUTE)

    expected = list(BUTTON_TABLE)
    expected[9] = protocol.BTN_EXTENDED
    assert sent_button_table(fake, skip=1) == expected
    assert sent_button_table(fake, skip=1)[6] == UNKNOWN_ACTION
    assert table == expected
    assert routes == ["2.4G"]


def test_send_media_writes_the_extended_slot_before_the_button_table():
    """The order the official app uses: slot first, then the table."""
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        device.send_media(9, protocol.MEDIA_MUTE)

    assert fake.addresses()[0] == protocol.ext_slot_addr(9)
    assert fake.addresses()[1:] == [protocol.BUTTON_ADDR + 4 * i
                                    for i in range(0, protocol.BUTTON_COUNT, 2)]
    assert [fake.sent[0]] == protocol.build_media(9, protocol.MEDIA_MUTE)


def test_send_key_writes_the_extended_slot_before_the_button_table():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        device.send_key(2, 0x04)              # 'a'

    assert fake.addresses()[0] == protocol.ext_slot_addr(2)
    assert sent_button_table(fake, skip=1)[2] == protocol.BTN_EXTENDED
    assert sent_button_table(fake, skip=1)[6] == UNKNOWN_ACTION


def test_send_media_rejects_an_index_outside_0_to_15():
    fake = FakeDevice(button_registers(BUTTON_TABLE))
    with stubbed(fake):
        for index in (-1, 16):
            try:
                device.send_media(index, protocol.MEDIA_MUTE)
            except ValueError:
                continue
            raise AssertionError(f"index {index} should have been rejected")

    assert fake.reads == [] and fake.sent == []


# --- DPI Effect -------------------------------------------------------------
def dpi_effect_registers(on, tail):
    data = protocol.record([0x01 if on else 0x00])
    for value in tail:
        data += protocol.record([value])
    return {protocol.DPI_EFFECT_ADDR: data}


def test_send_dpi_effect_on_hands_back_the_undecoded_tail_untouched():
    """0x4E/0x50 are unknown fields: they are read, not invented."""
    tail = (0x07, 0x09)                       # deliberately != DPI_EFFECT_TAIL
    assert tail != protocol.DPI_EFFECT_TAIL
    fake = FakeDevice(dpi_effect_registers(False, tail))
    with stubbed(fake):
        device.send_dpi_effect(True)

    assert fake.reads == [(protocol.DPI_EFFECT_ADDR, 6)]
    assert fake.sent == [protocol.build_dpi_effect(True, tail=tail)]
    assert fake.sent != [protocol.build_dpi_effect(True)]   # not the defaults


def test_send_dpi_effect_on_aborts_when_the_state_cannot_be_read():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        try:
            device.send_dpi_effect(True)
        except device.DeviceNotFound:
            pass
        else:
            raise AssertionError("expected DeviceNotFound")

    assert fake.sent == []


def test_send_dpi_effect_off_needs_no_read():
    """Turning it off writes only 0x4C, so there is nothing to preserve."""
    fake = FakeDevice(registers={})
    with stubbed(fake):
        routes = device.send_dpi_effect(False)

    assert fake.reads == []
    assert fake.sent == [protocol.build_dpi_effect(False)]
    assert routes == ["2.4G"]


def test_read_dpi_effect_reports_the_flag_and_the_tail():
    fake = FakeDevice(dpi_effect_registers(True, (0x01, 0x03)))
    with stubbed(fake):
        assert device.read_dpi_effect() == (True, (0x01, 0x03))


# --- Polling ----------------------------------------------------------------
def test_read_polling_decodes_a_known_code():
    fake = FakeDevice({protocol.POLLING_ADDR: protocol.record([0x02])})
    with stubbed(fake):
        assert device.read_polling() == (500, 0x02)


def test_read_polling_returns_none_and_the_raw_byte_for_an_unknown_code():
    """Guessing a rate from an unknown byte would be inventing a reading."""
    fake = FakeDevice({protocol.POLLING_ADDR: protocol.record([0x33])})
    with stubbed(fake):
        assert device.read_polling() == (None, 0x33)


def test_read_polling_returns_none_none_when_nothing_answers():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        assert device.read_polling() == (None, None)


def test_send_polling_writes_the_rate_packet():
    fake = FakeDevice()
    with stubbed(fake):
        routes = device.send_polling(250)

    assert fake.sent == [protocol.build_polling(250)]
    assert routes == ["2.4G"]


# --- LED --------------------------------------------------------------------
def test_read_led_state_decodes_the_register():
    data = protocol.record([protocol.EFFECT_BREATHING, 0x11, 0x22, 0x33,
                            0xBE, 0xFF])
    fake = FakeDevice({device.LED_ADDR: data})
    with stubbed(fake):
        assert device.read_led_state() == {"effect": "Breathing",
                                           "rgb": [0x11, 0x22, 0x33],
                                           "speed": 0xBE, "brightness": 0xFF}


def test_read_led_state_returns_none_when_nothing_answers():
    fake = FakeDevice(registers={})
    with stubbed(fake):
        assert device.read_led_state() is None


def test_send_color_sends_the_led_packet_and_reports_the_routes():
    fake = FakeDevice(routes=("2.4G", "cable"))
    with stubbed(fake):
        routes = device.send_color(255, 0, 0)

    assert fake.sent == [protocol.build_color(255, 0, 0)]
    assert routes == ["2.4G", "cable"]


def test_send_off_sends_the_off_packet():
    fake = FakeDevice()
    with stubbed(fake):
        device.send_off()

    assert fake.sent == [protocol.build_off()]


# --- The stubbing itself ----------------------------------------------------
def test_stubbing_restores_the_originals():
    """A leaked stub would let a later test reach the real hardware."""
    originals = (device.read_register, device.send_packets,
                 device.find_devices, state.save)
    with stubbed(FakeDevice()):
        assert device.read_register is not originals[0]
    assert (device.read_register, device.send_packets,
            device.find_devices, state.save) == originals


# --- Effect names: one source of truth --------------------------------------
def test_every_colour_effect_has_a_sender():
    """A name with no sender makes the UI silently send nothing.

    That is exactly what happened once: the interface offered "Steady" while the
    dispatch table still keyed on the old Portuguese name, so picking an effect
    did nothing at all. Keeping the names and the senders in one module means a
    rename cannot reintroduce it — and this test proves they line up.
    """
    for name in device.COLOR_EFFECTS:
        assert device.sender_for(name) is not None, f"{name} has no sender"


def test_colour_effect_names_are_the_ones_read_back():
    # sender_for must accept exactly what read_led_state reports
    reported = set(device.EFFECT_NAMES.values())
    assert set(device.COLOR_EFFECTS) <= reported
    assert device.sender_for("Off") is None          # Off has its own path


# --- Permission denied: the most common first-run failure -------------------
# Without the udev rule the hidraw node exists but is root-only. find_devices
# still lists it (it only reads sysfs), and opening it raises PermissionError.
# That used to be swallowed as a generic OSError, so a missing rule read as
# "no interface accepted the command" or "did the mouse answer?" — a message
# that sends people looking at the dongle instead of at the fix.
def _denied(*args, **kwargs):
    raise PermissionError(13, "Permission denied", "/dev/hidraw9")


@contextlib.contextmanager
def denied_node():
    originals = {name: getattr(device, name) for name in
                 ("find_devices", "_send_feature", "_read_from", "_last_reader")}
    device.find_devices = lambda: [("/dev/hidraw9", 0xFA07)]
    device._send_feature = _denied
    device._read_from = _denied
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(device, name, original)


def test_send_packets_reports_a_permission_problem_as_such():
    with denied_node():
        try:
            device.send_packets([protocol.build_off()])
        except device.NoPermission as exc:
            message = str(exc)
        else:
            raise AssertionError("a denied node must raise NoPermission")
    assert "/dev/hidraw9" in message
    assert "open-m711pro setup" in message    # works from pip and releases
    assert "install.sh" in message            # and the checkout path


def test_read_register_reports_a_permission_problem_as_such():
    with denied_node():
        try:
            device.read_register(protocol.LED_ADDR, 8)
        except device.NoPermission:
            pass
        else:
            raise AssertionError("a denied node must raise NoPermission")


def test_no_permission_is_still_a_device_not_found():
    # every interface already catches DeviceNotFound and shows its message
    assert issubclass(device.NoPermission, device.DeviceNotFound)


def test_the_not_found_message_does_not_recommend_mode_0666():
    # the shipped rule uses TAG+="uaccess"; 0666 is what it argues against
    original = device.find_devices
    device.find_devices = lambda: []
    try:
        device.send_packets([protocol.build_off()])
    except device.DeviceNotFound as exc:
        assert "0666" not in str(exc)
    finally:
        device.find_devices = original


def test_read_ext_slot_reads_twenty_bytes_and_classifies():
    ctrl_c = list(bytes.fromhex("04 80 01 00 81 06 00 40 01 00 41 06 00 c1"))
    base = protocol.ext_slot_addr(10)
    fake = FakeDevice({base: ctrl_c[:10], base + 10: ctrl_c[10:] + [0xff] * 6})
    with stubbed(fake):
        assert device.read_ext_slot(10) == ("combo", 0x01, 0x06)
    assert fake.reads == [(base, 10), (base + 10, 10)]


def test_read_ext_slot_returns_none_for_an_erased_slot():
    base = protocol.ext_slot_addr(9)
    fake = FakeDevice({base: [0xff] * 10, base + 10: [0xff] * 10})
    with stubbed(fake):
        assert device.read_ext_slot(9) is None

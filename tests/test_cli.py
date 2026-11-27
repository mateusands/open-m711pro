"""CLI tests — argument parsing and error paths, with the device layer stubbed.

Nothing here touches hardware: every function of `core/device.py` that could
reach hidraw is replaced, by default, with a tripwire that fails the test. A
test only opens the door it needs, so "the CLI rejected this before any I/O"
is proved rather than assumed.
"""
import io
import contextlib

from m711pro.cli import commands
from m711pro.core import device, protocol, state


# --- Harness ----------------------------------------------------------------
def _tripwire(*args, **kwargs):
    raise AssertionError("the CLI reached the device layer when it should not")


HARDWARE = ("find_devices", "send_packets", "read_register",
            "_send_feature", "_read_from")


@contextlib.contextmanager
def stubbed(**overrides):
    """Stub the device layer; anything not overridden becomes a tripwire.

    The originals are always restored, so one test cannot leak a stub into the
    next one.
    """
    patches = dict.fromkeys(HARDWARE, _tripwire)
    patches.update(overrides)
    originals = {name: getattr(device, name) for name in patches}
    saved_state = (state.load, state.save)
    for name, value in patches.items():
        setattr(device, name, value)
    state.load = lambda: {}
    state.save = lambda _state: None
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(device, name, value)
        state.load, state.save = saved_state


class Recorder:
    """A stand-in device function: records its arguments, returns `result`."""

    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        return self.result


class Raiser:
    """A stand-in device function that fails the way the hardware layer does."""

    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *args, **kwargs):
        raise self.exc


def run(argv):
    """Run the CLI. Returns (stdout, exit message) — the message is None on success."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            commands.main(argv)
    except SystemExit as exc:
        return out.getvalue(), str(exc)
    return out.getvalue(), None


# --- parse_action -----------------------------------------------------------
def test_parse_action_reads_a_hex_colour():
    assert commands.parse_action(["FF0000"]) == ("color", (255, 0, 0))
    assert commands.parse_action(["#00ff00"]) == ("color", (0, 255, 0))


def test_parse_action_reads_an_r_g_b_triplet():
    assert commands.parse_action(["0", "255", "0"]) == ("color", (0, 255, 0))


def test_parse_action_clamps_the_triplet_to_a_byte():
    assert commands.parse_action(["-5", "300", "10"]) == ("color", (0, 255, 10))


def test_parse_action_reads_a_named_colour():
    assert commands.parse_action(["blue"]) == ("color", (0, 0, 255))
    assert commands.parse_action(["AZUL"]) == ("color", (0, 0, 255))


def test_parse_action_reads_every_off_word():
    for word in commands.OFF_WORDS:
        assert commands.parse_action([word]) == ("off", None)
        assert commands.parse_action([word.upper()]) == ("off", None)


def test_parse_action_rejects_something_that_is_not_a_colour():
    try:
        commands.parse_action(["notacolour"])
    except SystemExit:
        return
    raise AssertionError("expected SystemExit with the usage text")


# --- Error paths: the device must never be reached --------------------------
def test_unknown_button_action_is_rejected_before_any_io():
    send_button = Recorder()
    with stubbed(send_button=send_button, read_buttons=Recorder()):
        out, message = run(["button", "1", "bogus"])

    assert message.startswith("Error: unknown action 'bogus'")
    assert send_button.calls == [] and out == ""


def test_unknown_media_key_is_rejected_before_any_io():
    send_media = Recorder()
    with stubbed(send_media=send_media):
        _, message = run(["button", "1", "media:bogus"])

    assert message.startswith("Error: unknown media key 'bogus'")
    assert send_media.calls == []


def test_unknown_key_name_is_rejected_before_any_io():
    send_key = Recorder()
    with stubbed(send_key=send_key):
        _, message = run(["button", "1", "key:notakey"])

    assert message.startswith("Error: unknown key 'notakey'")
    assert send_key.calls == []


def test_a_non_numeric_button_index_is_rejected_before_any_io():
    send_button = Recorder()
    with stubbed(send_button=send_button):
        _, message = run(["button", "x", "middle"])

    assert message.startswith("Error: the index must be a number")
    assert send_button.calls == []


def test_a_non_numeric_dpi_is_rejected_before_any_io():
    send_dpi_all = Recorder()
    with stubbed(send_dpi_all=send_dpi_all, send_dpi=Recorder()):
        _, message = run(["dpi", "abc"])

    assert message.startswith("Error: the values must be numbers")
    assert send_dpi_all.calls == []


def test_an_unsupported_polling_rate_is_rejected_before_any_io():
    """device.send_polling is the REAL one here: protocol validates the rate."""
    sent = Recorder(result=["cable"])
    with stubbed(send_packets=sent):
        _, message = run(["polling", "333"])

    assert message.startswith("Error: unsupported polling rate 333 Hz")
    assert sent.calls == []


def test_a_supported_polling_rate_reaches_the_wire():
    sent = Recorder(result=["cable"])
    with stubbed(send_packets=sent):
        out, message = run(["polling", "250"])

    assert message is None
    assert sent.calls == [([protocol.build_polling(250)],)]
    assert "250 Hz" in out


def test_too_many_dpi_arguments_show_the_usage():
    with stubbed(send_dpi=Recorder(), send_dpi_all=Recorder()):
        _, message = run(["dpi", "1", "2", "3"])

    assert message.startswith("Usage: " + commands.PROG + " dpi")


def test_no_arguments_shows_the_usage():
    with stubbed():
        _, message = run([])

    # USAGE is the docstring with the program name substituted for however the
    # tool was actually invoked, so the help never points at a command the user
    # does not have.
    assert message == commands.USAGE
    assert commands.PROG in message


# --- dpi: the three forms dispatch to three different calls -----------------
def test_dpi_without_arguments_shows_the_table():
    read_dpi_table = Recorder(result=[800, 1600, 3200, 6400, 16000])
    with stubbed(read_dpi_table=read_dpi_table,
                 send_dpi=_tripwire, send_dpi_all=_tripwire):
        out, message = run(["dpi"])

    assert message is None
    assert read_dpi_table.calls == [()]
    assert "stage 1: 800 DPI" in out and "stage 5: 16000 DPI" in out


def test_dpi_with_one_value_unifies_every_stage():
    send_dpi_all = Recorder(result=(["cable"], 1583))
    with stubbed(send_dpi_all=send_dpi_all, send_dpi=_tripwire,
                 read_dpi_table=_tripwire):
        out, message = run(["dpi", "1600"])

    assert message is None
    assert send_dpi_all.calls == [(1600,)]
    # shown as the official app shows it, with the real value still disclosed
    assert "1600 DPI (≈1583 real)" in out and "all five stages" in out
    assert "you asked for" not in out           # 1600 is what they get on screen


def test_dpi_off_the_hundreds_says_what_it_became():
    send_dpi_all = Recorder(result=(["cable"], 1667))
    with stubbed(send_dpi_all=send_dpi_all, send_dpi=_tripwire,
                 read_dpi_table=_tripwire):
        out, _ = run(["dpi", "1650"])

    assert "1700 DPI" in out and "you asked for 1650" in out


def test_dpi_with_stage_and_value_changes_one_stage():
    send_dpi = Recorder(result=(["cable"], [800, 1600, 4000, 6400, 16000]))
    with stubbed(send_dpi=send_dpi, send_dpi_all=_tripwire,
                 read_dpi_table=_tripwire):
        out, message = run(["dpi", "3", "4000"])

    assert message is None
    assert send_dpi.calls == [(3, 4000)]
    assert "Stage 3 = 4000 DPI" in out


def test_dpi_reports_all_five_stages_being_equal():
    with stubbed(read_dpi_table=Recorder(result=[1600] * 5)):
        out, _ = run(["dpi"])

    assert "all five equal" in out


def test_dpi_read_failure_is_reported_not_guessed():
    with stubbed(read_dpi_table=Recorder(result=None)):
        _, message = run(["dpi"])

    assert message.startswith("Error: could not read the DPI")


def test_dpi_device_not_found_becomes_an_error_message():
    failing = Raiser(device.DeviceNotFound("could not read the current DPI table"))
    with stubbed(send_dpi=failing):
        _, message = run(["dpi", "2", "1600"])

    assert message.startswith("Error: could not read the current DPI table")


# --- polling ----------------------------------------------------------------
def test_polling_without_arguments_shows_the_rate():
    with stubbed(read_polling=Recorder(result=(1000, 0x01))):
        out, message = run(["polling"])

    assert message is None and "USB polling: 1000 Hz" in out


def test_polling_reports_an_unknown_code_instead_of_guessing():
    with stubbed(read_polling=Recorder(result=(None, 0x33))):
        _, message = run(["polling"])

    assert message.startswith("Error: the mouse answered with an unknown")
    assert "0x33" in message


def test_polling_reports_a_silent_device():
    with stubbed(read_polling=Recorder(result=(None, None))):
        _, message = run(["polling"])

    assert message.startswith("Error: could not read the polling rate")


# --- buttons ----------------------------------------------------------------
def test_button_by_name_sends_the_matching_action():
    send_button = Recorder(result=(["cable"], []))
    with stubbed(send_button=send_button):
        out, message = run(["button", "1", "middle"])

    assert message is None
    assert send_button.calls == [(1, protocol.btn_mouse(protocol.MOUSE_MIDDLE))]
    assert "Button 1 = middle" in out


def test_button_with_a_media_prefix_uses_the_media_path():
    send_media = Recorder(result=(["cable"], []))
    with stubbed(send_media=send_media, send_button=_tripwire):
        out, message = run(["button", "9", "media:mute"])

    assert message is None
    assert send_media.calls == [(9, protocol.MEDIA_MUTE)]
    assert "media 'mute'" in out


def test_button_with_a_key_prefix_uses_the_keyboard_path():
    send_key = Recorder(result=(["cable"], []))
    with stubbed(send_key=send_key, send_button=_tripwire, send_media=_tripwire):
        out, message = run(["button", "9", "key:a"])

    assert message is None
    assert send_key.calls == [(9, 0x04)]


def test_buttons_lists_the_sixteen_slots():
    table = [protocol.btn_mouse(protocol.MOUSE_LEFT)] * 15 + [protocol.BTN_EXTENDED]
    with stubbed(read_buttons=Recorder(result=table)):
        out, message = run(["buttons"])

    assert message is None
    assert len(out.strip().splitlines()) == protocol.BUTTON_COUNT
    assert f"slot 0x{protocol.ext_slot_addr(15):04X}" in out


def test_buttons_read_failure_is_reported():
    with stubbed(read_buttons=Recorder(result=None)):
        _, message = run(["buttons"])

    assert message.startswith("Error: could not read the buttons")


# --- dpi-effect and the colour path -----------------------------------------
def test_dpi_effect_on_and_off():
    send_dpi_effect = Recorder(result=["cable"])
    with stubbed(send_dpi_effect=send_dpi_effect):
        run(["dpi-effect", "on"])
        run(["dpi-effect", "off"])

    assert send_dpi_effect.calls == [(True,), (False,)]


def test_dpi_effect_needs_on_or_off():
    send_dpi_effect = Recorder()
    with stubbed(send_dpi_effect=send_dpi_effect):
        _, message = run(["dpi-effect", "maybe"])

    assert message.startswith("Usage: " + commands.PROG + " dpi-effect")
    assert send_dpi_effect.calls == []


def test_a_colour_argument_reaches_send_color():
    send_color = Recorder(result=["cable"])
    with stubbed(send_color=send_color, send_off=_tripwire):
        out, message = run(["FF8000"])

    assert message is None
    assert send_color.calls == [(255, 128, 0)]
    assert "#FF8000" in out


def test_off_reaches_send_off():
    send_off = Recorder(result=["cable"])
    with stubbed(send_off=send_off, send_color=_tripwire):
        out, message = run(["off"])

    assert message is None and send_off.calls == [()]
    assert "LED off" in out


def test_a_missing_mouse_becomes_an_error_message():
    with stubbed(send_color=Raiser(device.DeviceNotFound("mouse not found"))):
        _, message = run(["red"])

    assert message == "Error: mouse not found"


# --- The stubbing itself ----------------------------------------------------
def test_stubbing_restores_the_originals():
    originals = (device.send_packets, device.find_devices, device.send_color,
                 state.save)
    with stubbed(send_color=Recorder()):
        assert device.send_color is not originals[2]
    assert (device.send_packets, device.find_devices, device.send_color,
            state.save) == originals


# --- setup: the udev rule and menu entry, for pip and release installs ------
def test_setup_dispatches_to_the_system_module():
    from m711pro import system
    calls = []
    original = system.setup
    system.setup = lambda **kw: calls.append("setup")
    try:
        with stubbed():                      # setup must not touch the mouse
            commands.main(["setup"])
    finally:
        system.setup = original
    assert calls == ["setup"]


def test_setup_uninstall_dispatches_to_uninstall():
    from m711pro import system
    calls = []
    original = system.uninstall
    system.uninstall = lambda **kw: calls.append("uninstall")
    try:
        with stubbed():
            commands.main(["setup", "--uninstall"])
    finally:
        system.uninstall = original
    assert calls == ["uninstall"]


def test_setup_is_in_the_usage_text():
    assert " setup" in commands.USAGE


def test_dpi_above_the_ceiling_is_not_relabelled_16000():
    # an erased byte (0xFF) decodes to 21333; it must not pass for "16000"
    raw = protocol.byte_to_dpi(0xFF)
    with stubbed(read_dpi_table=Recorder(result=[raw] + [1000] * 4)):
        out, _ = run(["dpi"])
    assert f"stage 1: {raw} DPI (outside the known range)" in out
    assert "stage 2: 1000 DPI" in out


def test_buttons_names_the_factory_reset_and_does_not_offer_it():
    table = [protocol.BTN_NONE] * 16
    table[6] = protocol.BTN_FACTORY_RESET
    with stubbed(read_buttons=Recorder(result=table)):
        out, _ = run(["buttons"])
    assert "factory reset" in out
    assert "factory-reset" not in commands.ACTIONS and "reset" not in commands.ACTIONS

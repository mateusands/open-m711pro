"""Smoke tests for the Qt interface, with the hardware stubbed out.

These exist because of a specific class of bug that shipped twice: a rename or a
refactor touched two classes that happened to share a line, and the interface
broke in a way no protocol test could see. Once it was the effect dispatch
keyed on stale names, so choosing an effect sent nothing at all; once it was
`self.rows` becoming a dict in one page while the other still kept a list, which
crashed the DPI tab the moment it opened.

Nothing here talks to a mouse: the device layer is replaced wholesale, and the
functions that would reach /dev/hidraw raise if anything calls them.

They skip themselves when PySide6 is absent, so the dependency-free CI run —
which is what proves the core needs nothing — still passes.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:                                  # pragma: no cover
    HAVE_QT = False

from m711pro.core import device, protocol, state

_app = None


def _qt():
    """One QApplication for the whole module; Qt allows no more."""
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    from m711pro.ui import i18n
    i18n.set_language("en", persist=False)     # assertions are in English
    return _app


BUTTON_TABLE = (
    [protocol.btn_mouse(protocol.MOUSE_LEFT), protocol.btn_mouse(protocol.MOUSE_RIGHT),
     protocol.btn_mouse(protocol.MOUSE_MIDDLE), protocol.btn_mouse(protocol.MOUSE_BACK),
     protocol.btn_mouse(protocol.MOUSE_FORWARD), protocol.BTN_NONE,
     (0x09, 0x00, 0x00), protocol.BTN_NONE, protocol.BTN_NONE,
     protocol.BTN_EXTENDED, protocol.BTN_EXTENDED, protocol.BTN_EXTENDED]
    + [protocol.BTN_NONE] * 4)


class _Stub:
    """Stands in for the whole device layer and records what was sent."""

    def __init__(self):
        self.sent = []

    def install(self):
        self._saved = {name: getattr(device, name) for name in (
            "find_devices", "send_packets", "read_register", "read_buttons",
            "read_dpi_axes", "read_dpi_bytes", "read_dpi_colors",
            "read_dpi_effect", "read_polling", "read_led_state", "read_ext_slot",
            "send_color", "send_breathing", "send_cycle", "send_off",
            "_send_feature", "_read_from")}

        def tripwire(*_a, **_k):
            raise AssertionError("a UI test tried to reach the hardware")

        device.find_devices = lambda: [("/dev/null", 0xFA07)]
        device._send_feature = tripwire
        device._read_from = tripwire
        device.send_packets = lambda pkts: self.sent.extend(pkts) or ["2.4G"]
        device.read_register = lambda addr, length=8, timeout=0.6: None
        device.read_buttons = lambda: [tuple(a) for a in BUTTON_TABLE]
        device.read_dpi_axes = lambda: [(0x07, 0x07)] * protocol.DPI_STAGES
        device.read_dpi_bytes = lambda: [0x07] * protocol.DPI_STAGES
        device.read_dpi_colors = lambda: [(255, 0, 0)] * protocol.DPI_STAGES
        device.read_dpi_effect = lambda: (True, (0x01, 0x03))
        device.read_polling = lambda: (1000, 0x01)
        self.ext = {}                       # index -> what read_ext_slot returns
        device.read_ext_slot = lambda index: self.ext.get(index)
        device.read_led_state = lambda: {"effect": "Steady", "rgb": [0, 0, 255],
                                         "speed": 0x96, "brightness": 0xFF}
        for name in ("send_color", "send_breathing", "send_cycle"):
            setattr(device, name, self._recorder(name))
        device.send_off = self._recorder("send_off")
        # The pages persist choices (DPI mode, language, last effect). Without
        # this the suite wrote into the developer's real state.json.
        self._saved_state = (state.load, state.save)
        self.state = {}
        state.load = lambda: dict(self.state)
        state.save = lambda new: self.state.update(new) or None

    def _recorder(self, name):
        def call(*args, **kwargs):
            self.sent.append((name, args, kwargs))
            return ["2.4G"]
        call.__name__ = name          # so device.sender_for() still reads right
        return call

    def restore(self):
        for name, original in self._saved.items():
            setattr(device, name, original)
        state.load, state.save = self._saved_state


def _window():
    from m711pro.ui import qt
    _qt()
    window = qt.MainWindow()
    window.show()
    _qt().processEvents()
    return qt, window


def test_every_page_opens():
    """The DPI tab once crashed on open; nothing in the suite noticed."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        for index in range(len(window.nav_btns)):
            window._go(index)
            _qt().processEvents()
    finally:
        stub.restore()


def test_choosing_an_effect_actually_sends_something():
    """The dispatch was once keyed on stale names and silently sent nothing."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        for effect in device.COLOR_EFFECTS:
            # Qt emits nothing when the text does not change, and the window
            # opens on one of these — so step away first, then back.
            window.lighting.effect.setCurrentText("Off")
            _qt().processEvents()
            stub.sent.clear()
            window.lighting.effect.setCurrentText(effect)
            _qt().processEvents()
            assert stub.sent, f"choosing {effect!r} sent nothing"
            # Checked against a map written out here rather than derived from
            # device.sender_for — deriving it from the code under test would
            # have passed happily while the dispatch was broken.
            expected = {"Steady": "send_color",
                        "Breathing": "send_breathing",
                        "Cycle": "send_cycle"}[effect]
            sent_names = [entry[0] for entry in stub.sent if isinstance(entry, tuple)]
            assert expected in sent_names, f"{effect!r} called {sent_names}"
    finally:
        stub.restore()


def test_the_buttons_page_offers_only_real_buttons():
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        qt, window = _window()
        window._go(2)
        _qt().processEvents()
        shown = set(window.buttons.rows)
        assert shown == {index for _, (_, index, _r) in
                         qt.MouseDiagram.BUTTONS.items()}
        assert len(shown) == 8
    finally:
        stub.restore()


def test_an_uninterpretable_action_is_shown_but_never_selectable():
    """Index 6 holds 09 00 00 from the factory and must survive untouched."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        qt, window = _window()
        window._go(2)
        _qt().processEvents()
        # index 6 is not one of the eight, so it is not even offered — the
        # guarantee is that it stays in the table, which send_button enforces.
        assert 6 not in window.buttons.rows
        assert window.buttons._table[6] == (0x09, 0x00, 0x00)
    finally:
        stub.restore()


def test_a_dpi_row_shows_the_app_label_and_the_real_value():
    """Byte 0x07 is what the official app writes for "700": show 700, not 667.

    An owner reported "I set 700 and it does not stay 700" — the byte was
    right, only the number on screen differed from the official app's.
    """
    if not HAVE_QT:
        return
    _qt()
    from m711pro.ui.qt import DpiRow
    row = DpiRow("")
    row.set_byte(0x07)
    assert row.spin.value() == 700
    assert row.real.text() == "≈667 real"
    row.set_byte(0x0B)                         # 1000 is exact: no note
    assert row.spin.value() == 1000 and row.real.text() == ""
    # typing the shown value back must keep the same byte
    row.spin.setValue(700); row._from_spin()
    assert row.byte() == 0x07


# --- Usability review (2026-11-27) ------------------------------------------
def _wheel(widget):
    """Send one wheel notch to `widget`, the way scrolling the page over it does."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    centre = QPointF(widget.width() / 2, widget.height() / 2)
    event = QWheelEvent(centre, widget.mapToGlobal(centre), QPoint(0, 0),
                        QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_the_dpi_field_holds_only_the_number():
    """With " DPI" inside the editable text the cursor landed after the unit,
    so deleting the number meant deleting the unit first."""
    if not HAVE_QT:
        return
    _qt()
    from m711pro.ui.qt import DpiRow
    row = DpiRow("")
    assert row.spin.suffix() == "" and row.spin.prefix() == ""
    assert row.spin_y.suffix() == "" and row.spin_y.prefix() == ""


def test_scrolling_over_a_control_never_reaches_the_mouse():
    """Scrolling the page with the pointer over a combo used to change it — and
    on the buttons page a changed combo is a write to the mouse."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._go(2)
        row = next(iter(window.buttons.rows.values()))
        before = row.action.currentIndex()
        stub.sent.clear()
        _wheel(row.action)
        _qt().processEvents()
        assert row.action.currentIndex() == before
        window._go(1)
        slider = window.dpi.single.slider
        before = slider.value()
        _wheel(slider)
        assert slider.value() == before
        assert stub.sent == []
    finally:
        stub.restore()


def test_moving_the_dpi_slider_without_dragging_still_sends():
    """A click on the groove or an arrow key moved the value but never sent it,
    leaving the screen showing a DPI the mouse did not have."""
    if not HAVE_QT:
        return
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractSlider
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._go(1)
        window.dpi.mode.setCurrentIndex(0)           # single DPI
        stub.sent.clear()
        window.dpi.single.slider.triggerAction(QAbstractSlider.SliderSingleStepAdd)
        QTest.qWait(700)
        assert stub.sent, "a keyboard/groove move must reach the mouse"
        expected = protocol.build_dpi_table_bytes([0x08] * protocol.DPI_STAGES)
        assert [bytes(p) for p in stub.sent] == [bytes(p) for p in expected]
    finally:
        stub.restore()


def test_dpi_presets_send_their_value():
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._go(1)
        window.dpi.mode.setCurrentIndex(0)
        stub.sent.clear()
        window.dpi.presets[1600].click()
        b = protocol.dpi_to_byte(1600)
        expected = protocol.build_dpi_table_bytes([b] * protocol.DPI_STAGES)
        assert [bytes(p) for p in stub.sent] == [bytes(p) for p in expected]
        assert window.dpi.single.spin.value() == 1600
    finally:
        stub.restore()


def test_button_rows_do_not_show_table_indices():
    """The register index (10, 11, 9 for buttons 6-8) is an implementation
    detail; next to the button number it only confused."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        texts = [row.name.text() for row in window.buttons.rows.values()]
        assert not any(t.lstrip().startswith(("10", "11", "9 ")) for t in texts)
        widths = {row.name.minimumWidth() for row in window.buttons.rows.values()}
        assert len(widths) == 1                     # the combos line up
    finally:
        stub.restore()


def test_opening_the_app_sends_nothing():
    """Loading a page sets sliders programmatically; that must never be taken
    for a user move and written to the mouse."""
    if not HAVE_QT:
        return
    from PySide6.QtTest import QTest
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        for index in range(len(window.nav_btns)):
            window._go(index)
        QTest.qWait(700)                        # past any debounce
        assert stub.sent == []
    finally:
        stub.restore()


# --- Language ----------------------------------------------------------------
def test_switching_to_portuguese_relabels_and_sends_nothing():
    if not HAVE_QT:
        return
    from PySide6.QtTest import QTest
    from m711pro.ui import i18n
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._set_language("pt", persist=False)
        _qt().processEvents(); QTest.qWait(500)
        assert [b.text() for b in window.nav_btns] == \
            ["Iluminação", "Sensibilidade (DPI)", "Botões"]
        assert stub.sent == []                     # a relabel is not a write
    finally:
        i18n.set_language("en", persist=False)
        stub.restore()


def test_a_translated_effect_still_sends_the_right_command():
    """The combo paints "Respiração" but must still dispatch "Breathing"."""
    if not HAVE_QT:
        return
    from m711pro.ui import i18n
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._set_language("pt", persist=False)
        combo = window.lighting.effect
        combo.setCurrentIndex(combo.findData("Off")); _qt().processEvents()
        stub.sent.clear()
        combo.setCurrentIndex(combo.findData("Breathing")); _qt().processEvents()
        assert combo.currentText() == "Respiração"
        assert stub.sent and stub.sent[-1][0] == "send_breathing"
    finally:
        i18n.set_language("en", persist=False)
        stub.restore()



def test_the_ui_suite_never_touches_the_real_state_file():
    """The suite once rewrote the developer's ~/.config state.json."""
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        _, window = _window()
        window._go(1)
        window.dpi.mode.setCurrentIndex(1)       # persists "dpi_mode"
        assert stub.state.get("dpi_mode") == "stages"
    finally:
        stub.restore()


def test_qt_dialogs_follow_the_interface_language():
    if not HAVE_QT:
        return
    from m711pro.ui import i18n, qt
    from PySide6.QtCore import QCoreApplication
    app = _qt()
    try:
        i18n.set_language("pt", persist=False)
        qt._install_qt_translator(app)
        if qt._qt_translator is None:            # no qtbase_pt_BR on this box
            return
        assert QCoreApplication.translate("QColorDialog", "&Basic colors") != "&Basic colors"
    finally:
        i18n.set_language("en", persist=False)
        qt._install_qt_translator(app)
    assert qt._qt_translator is None


def test_a_factory_reset_button_is_named_but_not_selectable():
    if not HAVE_QT:
        return
    _qt()
    from m711pro.ui.qt import ButtonRow, BUTTON_ACTIONS
    row = ButtonRow(9)
    row.set_action(protocol.BTN_FACTORY_RESET)
    assert "Factory reset" in row.action.currentText()
    assert row.current_action() is None                  # never sent back
    assert protocol.BTN_FACTORY_RESET not in [a for _, a in BUTTON_ACTIONS]



# --- Keyboard keys and combinations on the buttons page -----------------------
def _buttons_window(stub):
    _, window = _window()
    window._go(2)
    _qt().processEvents()
    return window.buttons


def test_a_button_holding_a_combo_shows_it():
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    stub.ext = {9: ("media", protocol.MEDIA_PREVIOUS), 10: ("combo", 0x01, 0x06),
                11: ("key", 0x04)}
    try:
        page = _buttons_window(stub)
        combo_row, key_row = page.rows[10], page.rows[11]
        assert combo_row.current_kind() == "combo"
        assert combo_row.mods.currentData() == 0x01 and combo_row.key.currentData() == 0x06
        assert combo_row.key.isVisibleTo(page) and not combo_row.media.isVisibleTo(page)
        assert key_row.current_kind() == "key" and key_row.key.currentData() == 0x04
        assert not key_row.mods.isVisibleTo(page)
    finally:
        stub.restore()


def test_choosing_a_keyboard_key_writes_the_key_record():
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    try:
        page = _buttons_window(stub)
        row = page.rows[9]
        stub.sent.clear()
        row.action.setCurrentIndex(row.action.findText("Keyboard key"))
        _qt().processEvents()
        sent = [bytes(pk) for pk in stub.sent if not isinstance(pk, tuple)]
        expected = [bytes(pk) for pk in protocol.build_key(9, row.key.currentData())]
        assert sent[:len(expected)] == expected
    finally:
        stub.restore()


def test_changing_the_modifier_rewrites_the_combo():
    if not HAVE_QT:
        return
    stub = _Stub(); stub.install()
    stub.ext = {10: ("combo", 0x01, 0x06)}
    try:
        page = _buttons_window(stub)
        row = page.rows[10]
        stub.sent.clear()
        row.mods.setCurrentIndex(row.mods.findData(0x01 | 0x02))      # Ctrl+Shift
        _qt().processEvents()
        sent = [bytes(pk) for pk in stub.sent if not isinstance(pk, tuple)]
        expected = [bytes(pk) for pk in protocol.build_combo(10, 0x03, 0x06)]
        assert sent[:len(expected)] == expected
    finally:
        stub.restore()


def test_the_diagram_and_the_protocol_agree_on_button_numbers():
    if not HAVE_QT:
        return
    from m711pro.ui.qt import MouseDiagram
    diagram = {index: n for n, (_, index, _r) in MouseDiagram.BUTTONS.items()}
    assert diagram == protocol.BUTTON_NUMBERS

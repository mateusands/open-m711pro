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

from m711pro.core import device, protocol

_app = None


def _qt():
    """One QApplication for the whole module; Qt allows no more."""
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
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
            "read_dpi_effect", "read_polling", "read_led_state",
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
        device.read_led_state = lambda: {"effect": "Steady", "rgb": [0, 0, 255],
                                         "speed": 0x96, "brightness": 0xFF}
        for name in ("send_color", "send_breathing", "send_cycle"):
            setattr(device, name, self._recorder(name))
        device.send_off = self._recorder("send_off")

    def _recorder(self, name):
        def call(*args, **kwargs):
            self.sent.append((name, args, kwargs))
            return ["2.4G"]
        call.__name__ = name          # so device.sender_for() still reads right
        return call

    def restore(self):
        for name, original in self._saved.items():
            setattr(device, name, original)


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

"""open-m711pro graphical interface, built on PySide6 (Qt).

Inspired by Logitech G HUB and Piper (libratbag): a sidebar, an anti-aliased HSV
colour wheel drawn with QPainter, the lighting effects, and the Sensitivity (DPI)
section, which reads and writes the five stages straight on the mouse.

The core (m711pro.core) stays pure stdlib; only this GUI uses Qt.
"""
import math
import colorsys

from PySide6.QtCore import (Qt, Signal, QRectF, QPointF, QTimer, QTranslator,
                            QLibraryInfo)
from PySide6.QtGui import QPainter, QColor, QConicalGradient, QRadialGradient, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QComboBox, QSlider, QPushButton, QFrame, QStackedWidget, QColorDialog,
    QSpinBox, QScrollArea, QCheckBox, QAbstractSpinBox, QStyle, QStyleOptionButton,
)

from ..core import device, state, protocol
from ..data.hid_keys import KEYS
from .i18n import tr, tr_error, LANGUAGES, language, set_language

ACCENT = "#19b8c8"
BORDER_COLOR = "#2a2e38"
PANEL_COLOR = "#171a21"

QSS = f"""
* {{ font-family: "Segoe UI", "Noto Sans", sans-serif; }}
QMainWindow, QWidget#page {{ background: #12141a; }}
QWidget#sidebar {{ background: #0b0d11; }}
QLabel {{ color: #e8eaed; }}
QLabel#muted {{ color: #8b9098; font-size: 11px; }}
QLabel#title {{ font-size: 20px; font-weight: 700; }}
QLabel#brand {{ font-size: 15px; font-weight: 700; color: #e8eaed; }}
QPushButton#nav {{
    color: #8b9098; background: transparent; border: none; text-align: left;
    padding: 11px 18px; font-size: 13px; border-left: 3px solid transparent;
}}
QPushButton#nav:hover {{ background: #171a21; color: #e8eaed; }}
QPushButton#nav:checked {{
    color: {ACCENT}; background: #171a21; border-left: 3px solid {ACCENT};
}}
QComboBox {{
    background: #20242e; color: #e8eaed; border: 1px solid #2a2e38;
    border-radius: 6px; padding: 6px 10px; min-width: 180px;
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox:hover {{ border: 1px solid #3a3f4a; }}
QComboBox QAbstractItemView {{
    background: #20242e; color: #e8eaed; selection-background-color: {ACCENT};
}}
QPushButton#action {{
    background: #20242e; color: #e8eaed; border: 1px solid #2a2e38;
    border-radius: 6px; padding: 8px 14px;
}}
QPushButton#action:hover {{ background: #2a2f3a; }}
QSlider::groove:horizontal {{ height: 6px; background: #20242e; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 16px; margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSpinBox {{
    background: #20242e; color: #e8eaed; border: 1px solid #2a2e38;
    border-radius: 6px; padding: 6px 10px; min-width: 64px; font-size: 13px;
}}
QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox#media {{ min-width: 120px; }}
QComboBox#buttonAction {{ min-width: 140px; }}
QComboBox#mods {{ min-width: 84px; }}
QComboBox#key {{ min-width: 64px; }}
QComboBox:disabled {{ color: #5a5f68; border: 1px solid #23262e; }}
QScrollArea#rows, QWidget#rowsBody {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2a2e38; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a3f4a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QWidget[focused="true"] {{ background: #171a21; border-radius: 6px; }}
QPushButton#swatch {{ border: 1px solid #2a2e38; border-radius: 4px; }}
QPushButton#preset {{
    background: #20242e; color: #c9ccd1; border: 1px solid #2a2e38;
    border-radius: 13px; padding: 4px 12px; font-size: 12px;
}}
QPushButton#preset:hover {{ border: 1px solid {ACCENT}; color: #e8eaed; }}
QPushButton#preset:disabled {{ color: #5a5f68; }}
QLabel#unit {{ color: #8b9098; font-size: 12px; }}
QPushButton#lang {{
    background: transparent; color: #8b9098; border: 1px solid #2a2e38;
    border-radius: 11px; padding: 3px 10px; font-size: 11px;
}}
QPushButton#lang:hover {{ color: #e8eaed; }}
QPushButton#lang:checked {{ color: {ACCENT}; border: 1px solid {ACCENT}; }}
QCheckBox {{ color: #e8eaed; spacing: 8px; }}
QCheckBox:disabled {{ color: #5a5f68; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid #3a3f4a; border-radius: 4px;
    background: #20242e;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QLabel#statusbar {{ background: #191c24; color: #8b9098; padding: 7px 12px; }}
"""


# ---------------------------------------------------------------------------
# Combo helpers, shared by every page that mirrors a value read from the mouse.
# A value we cannot interpret is displayed honestly and never becomes something
# the user can send back.
def _combo_trim(combo, base):
    """Drop the temporary "cannot be built" entry, if there is one."""
    while combo.count() > base:
        combo.removeItem(combo.count() - 1)


def _combo_pick(combo, base, index):
    combo.blockSignals(True)
    _combo_trim(combo, base)
    combo.setCurrentIndex(index)
    combo.blockSignals(False)


def _combo_pick_raw(combo, base, text):
    """Show `text` as the current entry, un-selectable from the list."""
    combo.blockSignals(True)
    _combo_trim(combo, base)
    combo.addItem(text)
    item = combo.model().item(base)
    if item is not None:
        item.setEnabled(False)
    combo.setCurrentIndex(base)
    combo.blockSignals(False)


# ---------------------------------------------------------------------------
# Controls that ignore the mouse wheel. Qt changes a combo or slider when the
# page is scrolled with the pointer over it, and on these pages a changed
# control is a WRITE to the mouse — so the wheel is handed back to the page,
# which scrolls instead.
class Combo(QComboBox):
    def wheelEvent(self, e):
        e.ignore()

    def paintEvent(self, e):
        # the stylesheet hides Qt's arrow (it rendered as a dark block); draw
        # a plain chevron instead
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#8b9098" if self.isEnabled() else "#4a4f58"), 1.6))
        x, y = self.width() - 18, self.height() / 2
        p.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        p.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))
        p.end()


class Slider(QSlider):
    """A horizontal slider that ignores the wheel and reports *settled* moves.

    `settled` fires when the handle is released, and — after a short pause —
    when the value moved without a drag (a click on the groove, the arrow
    keys). Committing only on release left those moves on screen but never
    sent, so the page showed a value the mouse did not have.
    """
    settled = Signal()
    DEBOUNCE_MS = 350

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self.settled)
        # actionTriggered fires for USER actions only (keys, groove clicks) —
        # never for setValue/setRange, so loading a page cannot send anything.
        self.actionTriggered.connect(self._acted)
        self.sliderReleased.connect(self._released)

    def _acted(self, action):
        if action != QSlider.SliderMove:       # a drag ends in sliderReleased
            self._timer.start()

    def _released(self):
        self._timer.stop()
        self.settled.emit()

    def wheelEvent(self, e):
        e.ignore()


class CheckBox(QCheckBox):
    """A checkbox whose ticked state shows a check mark, not only a colour."""

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.isChecked():
            return
        opt = QStyleOptionButton(); self.initStyleOption(opt)
        box = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, opt, self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#0b0d11" if self.isEnabled() else "#3a3e47"), 2.2)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        x, y, w, h = box.x(), box.y(), box.width(), box.height()
        p.drawLine(QPointF(x + w * 0.24, y + h * 0.52), QPointF(x + w * 0.43, y + h * 0.72))
        p.drawLine(QPointF(x + w * 0.43, y + h * 0.72), QPointF(x + w * 0.78, y + h * 0.30))
        p.end()


# ---------------------------------------------------------------------------
class ColorWheel(QWidget):
    previewed = Signal(int, int, int)
    committed = Signal(int, int, int)

    def __init__(self, diameter=240, parent=None):
        super().__init__(parent)
        self.d = diameter
        self.setFixedSize(diameter, diameter)
        self.hue, self.sat, self.value = 0.5, 1.0, 1.0
        self._drag = False

    def _geom(self):
        m = 8
        return self.d / 2, (self.d - 2 * m) / 2, m

    def set_value(self, v):
        self.value = v
        self.update()

    def set_hs(self, hue, sat):
        self.hue, self.sat = hue, sat
        self.update()

    def rgb(self):
        # "full" colour (value=1.0); brightness is a separate byte in the protocol.
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, 1.0)
        return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))

    def paintEvent(self, _ev):
        cx, r, m = self._geom()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(m, m, self.d - 2 * m, self.d - 2 * m)

        cg = QConicalGradient(cx, cx, 0)
        for i in range(25):
            cg.setColorAt(i / 24, QColor.fromHsvF(i / 24, 1.0, 1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg)); p.drawEllipse(rect)

        rg = QRadialGradient(cx, cx, r)
        rg.setColorAt(0.0, QColor(255, 255, 255, 255))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(rg)); p.drawEllipse(rect)

        if self.value < 1.0:
            p.setBrush(QColor(0, 0, 0, int((1 - self.value) * 255)))
            p.drawEllipse(rect)

        ang = self.hue * 2 * math.pi
        mx, my = cx + math.cos(ang) * self.sat * r, cx - math.sin(ang) * self.sat * r
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#000000"), 3)); p.drawEllipse(QPointF(mx, my), 7, 7)
        p.setPen(QPen(QColor("#ffffff"), 2)); p.drawEllipse(QPointF(mx, my), 7, 7)
        p.end()

    def _from_pos(self, pos):
        cx, r, _ = self._geom()
        dx, dy = pos.x() - cx, pos.y() - cx
        self.hue = (math.degrees(math.atan2(-dy, dx)) % 360) / 360.0
        self.sat = min(math.hypot(dx, dy) / r, 1.0)
        self.update()

    def mousePressEvent(self, e):
        self._drag = True; self._from_pos(e.position()); self.previewed.emit(*self.rgb())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._from_pos(e.position()); self.previewed.emit(*self.rgb())

    def mouseReleaseEvent(self, e):
        self._drag = False; self._from_pos(e.position()); self.committed.emit(*self.rgb())


# ---------------------------------------------------------------------------
# Names come from the core so the two can never drift apart.
COLOR_EFFECTS = set(device.COLOR_EFFECTS)
EFFECTS = list(device.COLOR_EFFECTS) + [device.EFFECT_NAMES[protocol.EFFECT_OFF]]
PRESETS = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0),
           (0, 255, 255), (0, 0, 255), (180, 0, 255), (255, 255, 255)]


class LightingPage(QWidget):
    status = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        root = QVBoxLayout(self); root.setContentsMargins(26, 22, 26, 22); root.setSpacing(14)

        t = QLabel(tr("LIGHTING")); t.setObjectName("title"); root.addWidget(t)

        er = QHBoxLayout()
        lbl = QLabel(tr("EFFECT")); lbl.setObjectName("muted"); er.addWidget(lbl)
        # The item DATA is the effect key the device layer dispatches on; only
        # the painted text is translated.
        self.effect = Combo()
        for key in EFFECTS:
            self.effect.addItem(tr(key), key)
        self.effect.currentIndexChanged.connect(
            lambda _i: self._on_effect(self._effect_key()))
        er.addWidget(self.effect); er.addStretch(); root.addLayout(er)

        body = QHBoxLayout(); body.setSpacing(24)
        self.wheel = ColorWheel(240)
        self.wheel.previewed.connect(self._preview)
        self.wheel.committed.connect(self._commit)
        body.addWidget(self.wheel)

        right = QVBoxLayout(); right.setSpacing(10)
        self.preview = QFrame(); self.preview.setFixedSize(64, 64)
        self._set_preview_bg(0, 0, 0)
        right.addWidget(self.preview)
        self.readout = QLabel("—"); self.readout.setStyleSheet("font-weight:600;")
        right.addWidget(self.readout)

        bl = QLabel(tr("BRIGHTNESS")); bl.setObjectName("muted"); right.addWidget(bl)
        self.bright = Slider(); self.bright.setRange(15, 100)
        self.bright.setValue(100); self.bright.setFixedWidth(180)
        self.bright.valueChanged.connect(self._on_bright)
        self.bright.settled.connect(self._commit_current)
        right.addWidget(self.bright)

        # Speed — only shown for animated effects
        self.speed_label = QLabel(tr("SPEED (Slow -> Fast)"))
        self.speed_label.setObjectName("muted"); right.addWidget(self.speed_label)
        self.speed = Slider(); self.speed.setRange(0, 100)
        self.speed.setValue(50); self.speed.setFixedWidth(180)
        self.speed.settled.connect(self._commit_current)
        right.addWidget(self.speed)

        pr = QGridLayout(); pr.setSpacing(4)
        for i, (r, g, b) in enumerate(PRESETS):
            sw = QPushButton(); sw.setFixedSize(24, 24); sw.setCursor(Qt.PointingHandCursor)
            sw.setStyleSheet(f"background:{self._hex(r,g,b)}; border:1px solid #2a2e38; border-radius:4px;")
            sw.clicked.connect(lambda _=False, c=(r, g, b): self._commit_rgb(*c))
            pr.addWidget(sw, 0, i)
        right.addLayout(pr)

        custom = QPushButton(tr("Custom colour…")); custom.setObjectName("action")
        custom.clicked.connect(self._pick_custom); right.addWidget(custom)
        right.addStretch()
        body.addLayout(right); body.addStretch()
        # Colour controls container — hidden when the effect uses no colour.
        self.color_area = QWidget(); self.color_area.setLayout(body)
        root.addWidget(self.color_area)

        # Notice shown in its place when there is no colour to pick.
        self.no_color = QLabel("")
        self.no_color.setObjectName("muted"); self.no_color.setWordWrap(True)
        self.no_color.hide()
        root.addWidget(self.no_color)
        root.addStretch()

        self._apply_saved_state()

    # -- helpers
    @staticmethod
    def _hex(r, g, b):
        return f"#{r:02x}{g:02x}{b:02x}"

    def _set_preview_bg(self, r, g, b):
        self.preview.setStyleSheet(
            f"background:{self._hex(r,g,b)}; border:1px solid #2a2e38; border-radius:6px;")

    def _bright_pct(self):
        return self.bright.value()               # 0–100

    def _bright_byte(self):
        pct = self._bright_pct()                 # 100% = 0xFF; abaixo = a % direta
        return 0xFF if pct >= 100 else pct

    def _refresh(self, r, g, b):
        pct = self._bright_pct()                 # the preview shows the colour with brightness applied
        self._set_preview_bg(r * pct // 100, g * pct // 100, b * pct // 100)
        self.readout.setText(f"#{r:02X}{g:02X}{b:02X}   RGB({r}, {g}, {b})   {pct}%")

    def _preview(self, r, g, b):
        self._refresh(r, g, b)

    def _effect_key(self):
        return self.effect.currentData()

    def _send_fn(self):
        return device.sender_for(self._effect_key())

    def _speed_byte(self):
        # slider 0% (slow) -> 100% (fast); a lower byte is faster (0xF0..0x08)
        pct = self.speed.value()
        return int(round(0xF0 - pct / 100 * (0xF0 - 0x08)))

    def _commit(self, r, g, b):
        eff = self._effect_key()
        fn = self._send_fn()
        if fn is None:
            return
        self._refresh(r, g, b)
        bb = self._bright_byte()
        if eff in ("Breathing", "Cycle"):
            sp = self._speed_byte()
            call = lambda: fn(r, g, b, brightness=bb, speed=sp)
        else:
            call = lambda: fn(r, g, b, brightness=bb)
        self._send(call, tr("{effect} {colour} ({pct}%)", effect=tr(eff),
                              colour=f"#{r:02X}{g:02X}{b:02X}",
                              pct=self._bright_pct()))

    def _commit_rgb(self, r, g, b):
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self.wheel.set_hs(h, s)                  # presets keep the slider brightness
        self._commit(r, g, b)

    def _commit_current(self):
        if self._send_fn() is None:
            return
        self._commit(*self.wheel.rgb())

    def _on_bright(self, _val):
        self.wheel.set_value(self._bright_pct() / 100.0)   # escurece a roda (visual)
        self._refresh(*self.wheel.rgb())

    def _speed_visible(self, eff):
        show = eff in ("Breathing", "Cycle")   # speed only applies to animated effects
        self.speed_label.setVisible(show)
        self.speed.setVisible(show)

    def _on_effect(self, eff):
        has_color = eff in COLOR_EFFECTS     # Steady/Breathing/Cycle use a colour
        self.color_area.setVisible(has_color)
        self.no_color.setVisible(not has_color)
        self._speed_visible(eff)
        if eff == "Off":
            self.no_color.setText(tr("Lighting is off."))
            self._send(device.send_off, tr("LED off"))
        elif has_color:
            self.no_color.setText("")
            self._commit_current()
        else:
            self.no_color.setText(f"'{eff}' is not implemented yet — the LED was left untouched.")
            self.status.emit(f"'{eff}' is not implemented yet.", False)

    def _pick_custom(self):
        c = QColorDialog.getColor(parent=self, title=tr("Pick a colour"))
        if c.isValid():
            self._commit_rgb(c.red(), c.green(), c.blue())

    def _apply_saved_state(self):
        """Reflect the CURRENT state — read from the hardware, falling back to the
        locally persisted state. Nothing is sent back to the mouse."""
        st = device.read_led_state() or state.load()
        rgb = st.get("rgb")
        if rgb and len(rgb) == 3:
            h, s, _ = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
            self.wheel.set_hs(h, s)
        bb = st.get("brightness", 0xFF)
        pct = 100 if bb >= 0xFF else int(bb)
        self.bright.blockSignals(True)
        self.bright.setValue(pct)
        self.bright.blockSignals(False)
        self.wheel.set_value(pct / 100.0)
        self._refresh(*self.wheel.rgb())
        sp = st.get("speed")
        if sp is not None:
            spct = max(0, min(100, round((0xF0 - sp) / (0xF0 - 0x08) * 100)))
            self.speed.blockSignals(True)
            self.speed.setValue(spct)
            self.speed.blockSignals(False)
        eff = st.get("effect", "Steady")
        if eff not in EFFECTS:
            eff = "Steady"
        self.effect.blockSignals(True)          # reflect without triggering a send
        self.effect.setCurrentIndex(self.effect.findData(eff))
        self.effect.blockSignals(False)
        has_color = eff in COLOR_EFFECTS
        self.color_area.setVisible(has_color)
        self.no_color.setVisible(not has_color)
        self._speed_visible(eff)
        if not has_color:
            self.no_color.setText(tr("Lighting is off.") if eff == "Off"
                                  else f"'{eff}' is not implemented yet.")

    def _send(self, fn, ok):
        try:
            vias = fn()
            self.status.emit(tr("{what} — via {routes}", what=ok,
                                routes=", ".join(vias)), False)
        except device.DeviceNotFound as exc:
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)


class DpiSpinBox(QSpinBox):
    """A DPI field whose arrows move ONE hardware step (~83 DPI).

    Stepping byte by byte, every value shown is one the mouse can hold. Values
    are shown as the official app labels them (700, not the 667 the step
    decodes to); the row's note carries the real value.
    """
    def __init__(self):
        super().__init__()
        # Only the number is editable: the unit lives in a label beside it.
        # With " DPI" as a suffix the cursor landed after the unit and clearing
        # the field meant fighting it.
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setRange(protocol.DPI_MIN, protocol.DPI_MAX)
        self.setFixedWidth(84)

    def stepBy(self, steps):
        b = protocol.dpi_to_byte(self.value()) + steps
        b = max(0, min(protocol.DPI_BYTE_MAX, b))
        self.setValue(protocol.dpi_display(b))

    def focusInEvent(self, e):
        super().focusInEvent(e)
        QTimer.singleShot(0, self.selectAll)     # click, type, Enter

    def wheelEvent(self, e):
        e.ignore()


class DpiRow(QWidget):
    """A slider plus a typed field for one DPI value.

    The slider moves in REGISTER units (each step is a real mouse step, ~83
    DPI); the field accepts a typed DPI and, once confirmed, echoes back the
    value the hardware will actually store.
    """
    edited = Signal()          # the user confirmed a value -> safe to send
    color_clicked = Signal()   # the stage swatch was clicked

    def __init__(self, label, with_color=False):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        if label:
            lb = QLabel(label); lb.setObjectName("muted"); lb.setMinimumWidth(58)
            lay.addWidget(lb)

        # Per-stage LED colour: the mouse shows it to indicate the active stage.
        self.color = None
        if with_color:
            self.color = QPushButton()
            self.color.setObjectName("swatch")
            self.color.setFixedSize(22, 22)
            self.color.setToolTip(tr("Stage colour — the LED shows it when this "
                                     "stage is active"))
            self.color.clicked.connect(self.color_clicked)
            lay.addWidget(self.color)

        self.slider = Slider()
        self.slider.setRange(0, protocol.DPI_BYTE_MAX)
        self.spin = DpiSpinBox()
        unit = QLabel("DPI"); unit.setObjectName("unit")
        # Y axis, hidden unless the user asks for independent axes.
        self.y_label = QLabel("Y"); self.y_label.setObjectName("unit")
        self.spin_y = DpiSpinBox()
        self.y_label.setVisible(False); self.spin_y.setVisible(False)
        self.spin_y.editingFinished.connect(self.edited)
        # The real value, when the app-style label rounds it (700 -> ≈667).
        self.real = QLabel(""); self.real.setObjectName("muted")
        self.real.setFixedWidth(76)
        lay.addWidget(self.slider, 1); lay.addWidget(self.spin)
        lay.addWidget(unit); lay.addWidget(self.real)
        lay.addWidget(self.y_label); lay.addWidget(self.spin_y)

        self.slider.valueChanged.connect(self._show_byte)
        self.slider.settled.connect(self.edited)
        self.spin.editingFinished.connect(self._from_spin)
        self.setEnabled(False)

    def _from_spin(self):
        b = protocol.dpi_to_byte(self.spin.value())
        self._set_slider(b)
        self._show_byte(b)                          # echo the quantised value
        if not self.spin_y.isVisible():
            self._set_spin_y(protocol.dpi_display(b))
        self.edited.emit()

    def _show_byte(self, b):
        self._set_spin(protocol.dpi_display(b))
        real = protocol.byte_to_dpi(b)
        self.real.setText("" if real == protocol.dpi_display(b)
                          else tr("≈{real} real", real=real))
        self.real.setToolTip("" if not self.real.text() else
                             tr("The mouse stores DPI in steps of ~83; this is the "
                                "value it really holds. The official app shows the "
                                "rounded number."))

    def _set_spin(self, dpi):
        self.spin.blockSignals(True)
        self.spin.setValue(dpi)
        self.spin.blockSignals(False)

    def _set_slider(self, b):
        self.slider.blockSignals(True)
        self.slider.setValue(b)
        self.slider.blockSignals(False)

    def _set_spin_y(self, dpi):
        self.spin_y.blockSignals(True)
        self.spin_y.setValue(dpi)
        self.spin_y.blockSignals(False)

    def set_byte(self, b, y=None):
        """Show a stage. `y` is the Y-axis byte when it differs from X."""
        self._set_slider(b)
        self._show_byte(b)
        self._set_spin_y(protocol.dpi_display(b if y is None else y))

    def byte(self):
        return self.slider.value()

    def axes(self):
        """(x, y) register bytes — equal unless the Y field is showing."""
        x = self.slider.value()
        if not self.spin_y.isVisible():
            return x, x
        return x, protocol.dpi_to_byte(self.spin_y.value())

    def show_y(self, flag):
        self.y_label.setVisible(flag)
        self.spin_y.setVisible(flag)

    def set_color(self, rgb):
        if self.color is None:
            return
        self.color.setStyleSheet(
            f"background:#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X};"
            "border:1px solid #2a2e38; border-radius:4px;")


class DpiPage(QWidget):
    """DPI page wired to the hardware (registers 0x000C, 0x004C and 0x0000).

    Two modes, chosen by the user and persisted in state.json:
    - "Single DPI": the typed value goes to all five stages, so the mouse's DPI
      button cycles without changing the sensitivity.
    - "5 stages": edit each stage separately.

    It also carries the DPI stage indicator (0x004C) and the USB polling rate
    (0x0000), both read back from the mouse before their control comes alive.
    """
    status = Signal(str, bool)
    MODES = [("single", "Single DPI"), ("stages", "5 stages")]

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._loaded = False
        self._raw = [0] * protocol.DPI_STAGES   # bytes read, preserved untouched
        self._axes = [(0, 0)] * protocol.DPI_STAGES
        self._colors = [(0, 0, 0)] * protocol.DPI_STAGES
        # last rate READ BACK from the mouse (None = a code we cannot decode) and
        # the register byte behind it (None = nothing answered)
        self._polling_hz = None
        self._polling_raw = None
        self._polling_rates = sorted(protocol.POLLING_RATES, reverse=True)
        root = QVBoxLayout(self); root.setContentsMargins(26, 22, 26, 22); root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel(tr("SENSITIVITY (DPI)")); t.setObjectName("title")
        head.addWidget(t); head.addStretch()
        btn = QPushButton(tr("Read from mouse")); btn.setObjectName("action")
        btn.clicked.connect(self._reload); head.addWidget(btn)
        root.addLayout(head)

        mr = QHBoxLayout()
        mr.addWidget(self._muted(tr("MODE"))); mr.addSpacing(8)
        self.mode = Combo()
        for _, rotulo in self.MODES:
            self.mode.addItem(tr(rotulo))
        saved = state.load().get("dpi_mode", "single")
        self.mode.setCurrentIndex(
            next((i for i, (k, _) in enumerate(self.MODES) if k == saved), 0))
        self.mode.currentIndexChanged.connect(self._on_mode)
        mr.addWidget(self.mode); mr.addStretch()
        root.addLayout(mr)

        # --- "single DPI" mode ---
        self.single_box = QWidget()
        sb = QVBoxLayout(self.single_box); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(6)
        self.single = DpiRow("")
        self.single.edited.connect(self._commit_single)
        sb.addWidget(self.single)
        # Quick picks: the slider is linear up to ~16000, so the values people
        # actually use sit in its first fifth and are fiddly to hit.
        pr = QHBoxLayout(); pr.setSpacing(6)
        self.presets = {}
        for dpi in (400, 800, 1600, 3200, 6400):
            chip = QPushButton(str(dpi)); chip.setObjectName("preset")
            chip.setCursor(Qt.PointingHandCursor); chip.setEnabled(False)
            chip.clicked.connect(lambda _=False, v=dpi: self._preset(v))
            pr.addWidget(chip); self.presets[dpi] = chip
        pr.addStretch(); sb.addLayout(pr)
        self.single_note = QLabel(""); self.single_note.setObjectName("muted")
        self.single_note.setWordWrap(True); sb.addWidget(self.single_note)
        root.addWidget(self.single_box)

        # --- "5 stages" mode ---
        self.stages_box = QWidget()
        gb = QVBoxLayout(self.stages_box); gb.setContentsMargins(0, 0, 0, 0); gb.setSpacing(7)
        self.rows = []
        for i in range(protocol.DPI_STAGES):
            row = DpiRow(f"  {i + 1}", with_color=True)
            row.edited.connect(lambda k=i: self._commit_stage(k))
            row.color_clicked.connect(lambda k=i: self._pick_color(k))
            gb.addWidget(row); self.rows.append(row)
        self.xy = QPushButton(tr("Independent X / Y axes"))
        self.xy.setObjectName("action"); self.xy.setCheckable(True)
        self.xy.setEnabled(False)
        self.xy.toggled.connect(self._show_xy)
        xr = QHBoxLayout(); xr.addWidget(self.xy); xr.addStretch()
        gb.addLayout(xr)
        root.addWidget(self.stages_box)

        hint = QLabel(tr(
            "Type a value and press Enter, drag the slider, or pick a preset. "
            "The mouse works in steps of ~{step} DPI: values are "
            "shown the way the official app shows them, with the real one beside "
            "them when it differs (700 is really ≈667).",
            step=f"{protocol.DPI_STEP:.0f}"))
        hint.setObjectName("muted"); hint.setWordWrap(True); root.addWidget(hint)

        root.addSpacing(6)
        root.addWidget(self._muted(tr("DPI STAGE INDICATOR")))
        self.effect_btn = CheckBox(tr("Light the LED in the active stage's colour "
                                       "(DPI Effect)"))
        self.effect_btn.setEnabled(False)
        self.effect_btn.clicked.connect(self._toggle_effect)
        root.addWidget(self.effect_btn)
        root.addSpacing(6)

        # --- USB polling rate (register 0x0000) ---
        # The choices come from protocol.POLLING_RATES so the page cannot drift
        # from the rates the protocol can actually build.
        pol = QHBoxLayout()
        pol.addWidget(self._muted(tr("POLLING RATE (Hz)"))); pol.addSpacing(8)
        self.polling = Combo()
        for hz in self._polling_rates:
            self.polling.addItem(f"{hz} Hz")
        self.polling.setEnabled(False)          # only a successful read wakes it
        self.polling.currentIndexChanged.connect(self._on_polling)
        pol.addWidget(self.polling); pol.addStretch()
        root.addLayout(pol)
        root.addStretch()
        self._show_mode()

    # -- mode ---------------------------------------------------------------
    def _mode_key(self):
        return self.MODES[self.mode.currentIndex()][0]

    def _on_mode(self, _idx):
        state.save({**state.load(), "dpi_mode": self._mode_key()})
        self._show_mode()

    def _show_mode(self):
        single = self._mode_key() == "single"
        self.single_box.setVisible(single)
        self.stages_box.setVisible(not single)
        self._update_single_note()

    def _update_single_note(self):
        if self._mode_key() != "single" or not self._loaded:
            return
        if len(set(self._raw)) > 1:
            current = " · ".join(str(protocol.dpi_display(b)) for b in self._raw)
            self.single_note.setText(tr(
                "The five stages still differ ({current}). Confirm a value above to "
                "make them all equal.", current=current))
        else:
            self.single_note.setText(tr(
                "All five stages are equal — the mouse's DPI button cycles without "
                "changing the sensitivity."))

    # -- loading (only the first time the page is shown: the read is slow) --
    def ensure_loaded(self):
        if not self._loaded:
            self._reload()

    def _reload(self):
        try:
            axes = device.read_dpi_axes()
            raw = None if axes is None else [x for x, _ in axes]
            colors = device.read_dpi_colors()
            eff = device.read_dpi_effect()
            hz, code = device.read_polling()
        except device.DeviceNotFound as exc:
            self._enable(False); self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        if raw is None:
            self._enable(False)
            self.status.emit(tr("Could not read the DPI — did the mouse answer?"), True)
            return
        self._raw = list(raw)
        self._axes = list(axes)
        if colors:
            self._colors = list(colors)
        for row, (x, y), color in zip(self.rows, self._axes, self._colors):
            row.set_byte(x, y)
            row.set_color(color)
        self.single.set_byte(raw[0])
        self._enable(True)
        # Show the Y fields when the mouse already holds different axes.
        self.xy.setChecked(any(x != y for x, y in self._axes))
        if eff is not None:
            self._show_effect(eff[0])
        self._show_polling(hz, code)
        self._loaded = True
        self._update_single_note()
        if code is None:
            self.status.emit(tr("DPI read from the mouse — the polling rate did "
                                "not answer."), True)
        else:
            self.status.emit(tr("DPI read from the mouse."), False)

    def _enable(self, flag):
        for row in self.rows:            # DpiPage keeps a list, one per stage
            row.setEnabled(flag)
        self.xy.setEnabled(flag)
        self.single.setEnabled(flag)
        self.effect_btn.setEnabled(flag)
        for chip in self.presets.values():
            chip.setEnabled(flag)
        if not flag:
            self.polling.setEnabled(False)   # only its own read wakes it again

    def _show_effect(self, on):
        self.effect_btn.setChecked(on)

    def _show_polling(self, hz, code):
        """Make the combo reflect the rate we believe the register holds.

        A code we cannot decode is shown as its raw byte and cannot be selected
        — the value is never silently rewritten into one we do understand.
        """
        self._polling_hz, self._polling_raw = hz, code
        self.polling.setEnabled(code is not None)
        base = len(self._polling_rates)
        if hz in self._polling_rates:
            _combo_pick(self.polling, base, self._polling_rates.index(hz))
        else:
            _combo_pick_raw(self.polling, base, "no answer" if code is None
                            else f"unknown (0x{code:02x})")

    # -- per-stage colour and independent axes --------------------------------
    def _show_xy(self, flag):
        """Reveal the Y field on every stage row.

        Toggling writes nothing by itself — the mouse keeps whatever it holds
        until a stage is actually edited. From then on the rule follows the
        toggle: with it off the axes are linked, so editing a stage sets Y = X;
        with it on each axis carries its own value. Rewriting the table the
        moment the toggle moves would be a write nobody asked for.
        """
        for row in self.rows:
            row.show_y(flag)

    def _pick_color(self, k):
        """Pick the LED colour the mouse shows while stage `k` is active."""
        chosen = QColorDialog.getColor(QColor(*self._colors[k]), self,
                                       tr("Stage {n} colour", n=k + 1))
        if not chosen.isValid():
            return
        rgb = (chosen.red(), chosen.green(), chosen.blue())
        try:
            _, colors = device.send_dpi_color(k + 1, rgb)
        except (device.DeviceNotFound, ValueError) as exc:
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        self._colors = [tuple(c) for c in colors]
        self.rows[k].set_color(rgb)
        self.status.emit(tr("Stage {n} colour = {colour}", n=k + 1,
                            colour=f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"), False)

    # -- sending --------------------------------------------------------------
    def _send(self, entries, msg):
        """Write the table, adopting the new bytes only if the send succeeded.

        `entries` may hold a single byte per stage or an (x, y) pair; the
        protocol layer normalises both.
        """
        try:
            vias = device.send_dpi_bytes(entries)
        except device.DeviceNotFound as exc:
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        self._axes = [protocol.axis_pair(e) for e in entries]
        self._raw = [x for x, _ in self._axes]
        self._update_single_note()
        self.status.emit(tr("{what} — via {routes}", what=msg,
                            routes=", ".join(vias)), False)

    def _preset(self, dpi):
        self.single.set_byte(protocol.dpi_to_byte(dpi))
        self._commit_single()

    def _commit_single(self):
        b = self.single.byte()
        self._send([b] * protocol.DPI_STAGES,
                   tr("DPI = {dpi} on all five stages", dpi=protocol.dpi_text(b)))

    def _commit_stage(self, k):
        # start from the bytes we READ, not from the sliders: a stage the slider
        # cannot represent then stays exactly as it was
        entries = list(self._axes)
        entries[k] = self.rows[k].axes()
        x, y = entries[k]
        label = (tr("Stage {n} = {dpi}", n=k + 1, dpi=protocol.dpi_text(x))
                 if x == y else
                 tr("Stage {n} = X {x} / Y {y}", n=k + 1,
                    x=protocol.dpi_text(x), y=protocol.dpi_text(y)))
        self._send(entries, label)

    def _toggle_effect(self):
        on = self.effect_btn.isChecked()
        try:
            vias = device.send_dpi_effect(on)
            self._show_effect(on)
            self.status.emit(tr("{what} — via {routes}",
                                what=tr("DPI Effect on" if on else "DPI Effect off"),
                                routes=", ".join(vias)), False)
        except device.DeviceNotFound as exc:
            self.effect_btn.setChecked(not on)      # desfaz o toggle visual
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)

    def _on_polling(self, index):
        if index >= len(self._polling_rates):    # the raw entry — never sent
            return
        hz = self._polling_rates[index]
        try:
            routes = device.send_polling(hz)
        except (device.DeviceNotFound, ValueError) as exc:
            # undo the visual change: back to the last rate we actually read
            self._show_polling(self._polling_hz, self._polling_raw)
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        # adopt the new rate; this also drops the raw entry, if there was one
        self._show_polling(hz, protocol.POLLING_RATES[hz])
        self.status.emit(tr("{what} — via {routes}",
                            what=tr("Polling rate = {hz} Hz", hz=hz),
                            routes=", ".join(routes)), False)

    @staticmethod
    def _muted(text):
        lb = QLabel(text); lb.setObjectName("muted"); return lb


# ---------------------------------------------------------------------------
# Actions offered by the combo. Only actions we can BUILD are listed here; an
# action read from the mouse that is not on this list is shown as-is and cannot
# be re-selected (see ButtonRow.set_action).
BUTTON_ACTIONS = [
    ("Left click", protocol.btn_mouse(protocol.MOUSE_LEFT)),
    ("Right click", protocol.btn_mouse(protocol.MOUSE_RIGHT)),
    ("Middle click", protocol.btn_mouse(protocol.MOUSE_MIDDLE)),
    ("Back", protocol.btn_mouse(protocol.MOUSE_BACK)),
    ("Forward", protocol.btn_mouse(protocol.MOUSE_FORWARD)),
    ("DPI up", protocol.btn_dpi_up()),
    ("DPI down", protocol.btn_dpi_down()),
    ("DPI cycle", protocol.btn_dpi_cycle()),
    ("Three click", protocol.btn_three_click()),
    ("Fire key", protocol.btn_fire()),
    ("RGB on/off", protocol.btn_rgb_toggle()),
    ("Polling rate switch", protocol.btn_polling_switch()),
    ("Multimedia key", protocol.BTN_EXTENDED),
    ("Keyboard key", protocol.BTN_EXTENDED),
    ("Key combination", protocol.BTN_EXTENDED),
    ("Disabled", protocol.BTN_NONE),
]

# The three entries above share BTN_EXTENDED: the basic record only says "the
# action lives in the extended slot"; the slot's event list says which kind.
EXT_KINDS = {"Multimedia key": "media", "Keyboard key": "key",
             "Key combination": "combo"}

# Keyboard keys offered in the UI, in the HID table's order (a-z, 1-0, F1-F12,
# then the named keys). The usages are the ones the CLI's key: prefix uses.
KEY_CHOICES = [(name.upper() if len(name) == 1 or name[1:].isdigit()
                else name.capitalize(), code)
               for name, code in KEYS.items()]

# Modifier sets for a combination: the HID modifier bits carried by the
# 0x80/0x40 events (Ctrl+C was verified byte for byte with 0x01).
MOD_CHOICES = [("Ctrl", 0x01), ("Shift", 0x02), ("Alt", 0x04), ("Win", 0x08),
               ("Ctrl+Shift", 0x03), ("Ctrl+Alt", 0x05), ("Alt+Shift", 0x06)]

MEDIA_KEYS = [
    ("Play / pause", protocol.MEDIA_PLAY_PAUSE),
    ("Next track", protocol.MEDIA_NEXT),
    ("Previous track", protocol.MEDIA_PREVIOUS),
    ("Mute", protocol.MEDIA_MUTE),
    ("Stop", protocol.MEDIA_STOP),
    ("Volume up", protocol.MEDIA_VOL_UP),
    ("Volume down", protocol.MEDIA_VOL_DOWN),
]




class MouseDiagram(QWidget):
    """A top-down schematic of the mouse with the eight buttons numbered.

    Drawn rather than shipped as an image: the official app's render is the
    vendor's artwork and cannot go into a GPL repository. The button POSITIONS
    are facts about the hardware, so the layout matches what the app shows.

    Numbers are the ones the official app uses. The table index behind each one
    is not the same number — buttons 6, 7 and 8 live at indices 10, 11 and 9 —
    so the mapping lives here in one place.
    """
    selected = Signal(int)             # emits the TABLE INDEX, not the label

    # label on the mouse -> (position in a 0..1 box, table index, what it is)
    BUTTONS = {
        1: ((0.30, 0.20), 0, "left click"),
        2: ((0.70, 0.20), 1, "right click"),
        3: ((0.50, 0.17), 2, "wheel"),
        4: ((0.13, 0.45), 3, "side"),
        5: ((0.13, 0.34), 4, "side"),
        6: ((0.50, 0.38), 10, "top"),
        7: ((0.50, 0.48), 11, "top"),
        8: ((0.50, 0.58), 9, "top"),
    }
    R = 11                             # badge radius

    def __init__(self):
        super().__init__()
        self.setMinimumSize(190, 250)
        self.setCursor(Qt.PointingHandCursor)
        self._active = None            # highlighted table index

    def set_active(self, index):
        self._active = index
        self.update()

    def _centre(self, label):
        (fx, fy), _, _ = self.BUTTONS[label]
        w, h = self.width(), self.height()
        return QPointF(fx * w, fy * h)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # body: a rounded shell, narrower at the front
        body = QRectF(w * 0.18, h * 0.06, w * 0.64, h * 0.84)
        p.setPen(QPen(QColor(BORDER_COLOR), 2))
        p.setBrush(QBrush(QColor(PANEL_COLOR)))
        p.drawRoundedRect(body, w * 0.30, h * 0.22)

        # the split between the two main buttons, and the wheel slot
        p.setPen(QPen(QColor(BORDER_COLOR), 1))
        p.drawLine(QPointF(w * 0.5, h * 0.08), QPointF(w * 0.5, h * 0.30))
        wheel = QRectF(w * 0.46, h * 0.11, w * 0.08, h * 0.10)
        p.setBrush(QBrush(QColor(BORDER_COLOR)))
        p.drawRoundedRect(wheel, 3, 3)

        # side buttons sit on a small tab
        p.setBrush(QBrush(QColor(PANEL_COLOR)))
        p.drawRoundedRect(QRectF(w * 0.06, h * 0.28, w * 0.14, h * 0.23), 4, 4)

        for label in self.BUTTONS:
            centre = self._centre(label)
            active = self.BUTTONS[label][1] == self._active
            p.setBrush(QBrush(QColor(ACCENT if active else "#20242e")))
            p.setPen(QPen(QColor(ACCENT if active else BORDER_COLOR), 2))
            p.drawEllipse(centre, self.R, self.R)
            p.setPen(QPen(QColor("#0b0d11" if active else "#e8eaed")))
            p.drawText(QRectF(centre.x() - self.R, centre.y() - self.R,
                              self.R * 2, self.R * 2),
                       Qt.AlignCenter, str(label))
        p.end()

    def mousePressEvent(self, e):
        for label, (_, index, _role) in self.BUTTONS.items():
            if (e.position() - self._centre(label)).manhattanLength() <= self.R * 2:
                self.selected.emit(index)
                return


# Derived from the diagram so the two can never disagree about which slot is
# which button — the numbers on the mouse are not the table indices.
PHYSICAL_BUTTONS = {
    index: f"button {label} ({role})"
    for label, (_, index, role) in MouseDiagram.BUTTONS.items()
}


def _pick_data(combo, base, value, raw_text):
    """Select the entry whose data is `value`, or show `raw_text` unselectable."""
    for i in range(base):
        if combo.itemData(i) == value:
            _combo_pick(combo, base, i)
            return
    _combo_pick_raw(combo, base, raw_text)


class ButtonRow(QWidget):
    """One slot of the button table: a label, an action combo and, when the
    action lives in an extended slot, the fields that say what it sends — a
    multimedia key, a keyboard key, or a modifier plus a key."""
    action_edited = Signal(int)     # emits the slot index
    ext_edited = Signal(int)        # the multimedia/key/modifier field changed

    def __init__(self, index):
        super().__init__()
        self.index = index
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)

        # The number printed on the mouse, never the table index behind it
        # (buttons 6-8 live at 10, 11 and 9 — an implementation detail).
        label = next((n for n, (_, i, _r) in MouseDiagram.BUTTONS.items()
                      if i == index), None)
        role = MouseDiagram.BUTTONS[label][2] if label else "unused"
        self.name = QLabel(f"{tr('Button {n}', n=label)}  "
                           f"<span style='color:#8b9098'>{tr(role)}</span>"
                           if label else f"Slot {index}  (unused)")
        self.name.setFixedWidth(132)
        self.name.setMinimumWidth(132)
        lay.addWidget(self.name)

        self.action = Combo(); self.action.setObjectName("buttonAction")
        for text, _ in BUTTON_ACTIONS:
            self.action.addItem(tr(text))
        self.action.currentIndexChanged.connect(
            lambda _idx: self.action_edited.emit(self.index))
        lay.addWidget(self.action, 1)

        def field(choices, name):
            combo = Combo(); combo.setObjectName(name)
            for text, value in choices:
                combo.addItem(tr(text), value)
            combo.currentIndexChanged.connect(
                lambda _idx: self.ext_edited.emit(self.index))
            combo.hide()
            return combo

        self.media = field(MEDIA_KEYS, "media")
        self.mods = field(MOD_CHOICES, "mods")
        self.key = field(KEY_CHOICES, "key")
        lay.addWidget(self.media, 1); lay.addWidget(self.mods); lay.addWidget(self.key)

        self.setEnabled(False)

    # -- state --------------------------------------------------------------
    def set_action(self, action, ext=None):
        """Show `action`; for BTN_EXTENDED, `ext` is what read_ext_slot found."""
        action = tuple(action)
        if action == protocol.BTN_FACTORY_RESET:
            # recognised, shown by name, and like any raw entry never sent back
            _combo_pick_raw(self.action, len(BUTTON_ACTIONS),
                            tr("Factory reset (not assignable here)"))
            self.show_ext(None)
            return
        if action == protocol.BTN_EXTENDED:
            kind = ext[0] if ext else "media"     # erased/unknown: say so there
            label = next(t for t, k in EXT_KINDS.items() if k == kind)
            _combo_pick(self.action, len(BUTTON_ACTIONS),
                        [t for t, _ in BUTTON_ACTIONS].index(label))
            self._set_ext(ext)
            self.show_ext(kind)
            return
        for i, (_, known) in enumerate(BUTTON_ACTIONS):
            if known == action:
                _combo_pick(self.action, len(BUTTON_ACTIONS), i)
                self.show_ext(None)
                return
        _combo_pick_raw(self.action, len(BUTTON_ACTIONS),
                        tr("unknown ({raw})",
                           raw="{:02x} {:02x} {:02x}".format(*action)))
        self.show_ext(None)

    def _set_ext(self, ext):
        if not ext:
            _combo_pick_raw(self.media, len(MEDIA_KEYS), tr("unknown slot"))
            return
        kind, *values = ext
        unknown = lambda v: tr("unknown (usage {usage})", usage=f"{v:04x}")
        if kind == "media":
            _pick_data(self.media, len(MEDIA_KEYS), values[0], unknown(values[0]))
        elif kind == "key":
            _pick_data(self.key, len(KEY_CHOICES), values[0], unknown(values[0]))
        else:
            _pick_data(self.mods, len(MOD_CHOICES), values[0], unknown(values[0]))
            _pick_data(self.key, len(KEY_CHOICES), values[1], unknown(values[1]))

    def current_action(self):
        """The action tuple to send, or None when the entry is a raw byte dump."""
        i = self.action.currentIndex()
        return BUTTON_ACTIONS[i][1] if i < len(BUTTON_ACTIONS) else None

    def current_kind(self):
        """"media", "key" or "combo" for an extended action, else None."""
        i = self.action.currentIndex()
        return EXT_KINDS.get(BUTTON_ACTIONS[i][0]) if i < len(BUTTON_ACTIONS) else None

    def ensure_ext_choice(self):
        """An explicit pick of an extended kind needs a value to send: replace a
        raw "unknown" entry by the first real choice."""
        kind = self.current_kind()
        fields = {"media": [(self.media, MEDIA_KEYS)],
                  "key": [(self.key, KEY_CHOICES)],
                  "combo": [(self.mods, MOD_CHOICES), (self.key, KEY_CHOICES)]}
        for combo, choices in fields.get(kind, []):
            if combo.currentIndex() >= len(choices):
                _combo_pick(combo, len(choices), 0)

    def current_ext(self):
        """What to write into the slot, or None when any field is a raw entry."""
        kind = self.current_kind()
        if kind == "media":
            usage = self.media.currentData()
            return None if usage is None else ("media", usage)
        if kind == "key":
            usage = self.key.currentData()
            return None if usage is None else ("key", usage)
        if kind == "combo":
            mods, usage = self.mods.currentData(), self.key.currentData()
            return None if mods is None or usage is None else ("combo", mods, usage)
        return None

    def ext_text(self):
        kind = self.current_kind()
        if kind == "media":
            return self.media.currentText()
        if kind == "key":
            return self.key.currentText()
        return f"{self.mods.currentText()}+{self.key.currentText()}"

    def show_ext(self, kind):
        self.media.setVisible(kind == "media")
        self.mods.setVisible(kind == "combo")
        self.key.setVisible(kind in ("key", "combo"))


class ButtonsPage(QWidget):
    """Button page wired to the hardware (table at 0x0060, extended slots at 0x0100).

    The table is written whole on every change, so the fifteen buttons we are
    not touching must go back exactly as they were: `device.send_button` re-reads
    the table before writing, and this page never turns a byte it cannot
    interpret into one it can (an unrecognised action stays un-selectable).
    """
    status = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._loaded = False
        self._table = [protocol.BTN_NONE] * protocol.BUTTON_COUNT
        self._ext = {}                   # index -> what read_ext_slot decoded
        root = QVBoxLayout(self); root.setContentsMargins(22, 22, 22, 22); root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel(tr("BUTTONS")); t.setObjectName("title")
        head.addWidget(t); head.addStretch()
        btn = QPushButton(tr("Read from mouse")); btn.setObjectName("action")
        btn.clicked.connect(self._reload); head.addWidget(btn)
        root.addLayout(head)

        note = QLabel(tr(
            "Click a number on the mouse to jump to its row. These are the eight "
            "buttons the mouse actually has, numbered the way the official app "
            "numbers them. The register table has sixteen slots, but the other "
            "eight fire nothing on this model — they are preserved untouched on "
            "every write and simply not offered here."))
        note.setObjectName("muted"); note.setWordWrap(True); root.addWidget(note)

        body = QWidget(); body.setObjectName("rowsBody")
        rows = QVBoxLayout(body); rows.setContentsMargins(0, 0, 8, 0); rows.setSpacing(6)
        # Only the slots a physical button fires, laid out in the order the
        # mouse numbers them. The table has 16 slots and the other eight are
        # dead on this model — showing them as "Disabled" invited people to
        # configure buttons that do not exist. They are still preserved on
        # every write; they just are not offered.
        self.rows = {}
        for label in sorted(MouseDiagram.BUTTONS):
            index = MouseDiagram.BUTTONS[label][1]
            row = ButtonRow(index)
            row.action_edited.connect(self._on_action)
            row.ext_edited.connect(self._send_ext)
            rows.addWidget(row); self.rows[index] = row
        rows.addStretch()

        area = QScrollArea(); area.setObjectName("rows")
        area.setWidgetResizable(True); area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(body)

        # The diagram sits beside the rows: clicking a numbered button scrolls to
        # and highlights its row, which is the whole point — the table index is
        # not the number printed on the mouse.
        self.diagram = MouseDiagram()
        self.diagram.selected.connect(self._focus_index)
        side = QVBoxLayout(); side.addWidget(self.diagram); side.addStretch()
        split = QHBoxLayout(); split.setSpacing(16)
        split.addLayout(side); split.addWidget(area, 1)
        root.addLayout(split, 1)
        self._area = area

        hint = QLabel(tr(
            "An action this app cannot build is shown as its raw bytes and cannot "
            "be selected — the byte is preserved instead of being guessed at."))
        hint.setObjectName("muted"); hint.setWordWrap(True); root.addWidget(hint)

    @staticmethod
    def _number(index):
        """The number printed on the mouse for table `index`."""
        return next((n for n, (_, i, _r) in MouseDiagram.BUTTONS.items()
                     if i == index), index)

    def _focus_index(self, index):
        """Scroll to the row a diagram badge points at and highlight both."""
        self.diagram.set_active(index)
        row = self.rows[index]
        self._area.ensureWidgetVisible(row)
        for i, other in self.rows.items():
            other.setProperty("focused", i == index)
            other.style().unpolish(other); other.style().polish(other)

    # -- loading (only the first time the page is shown: the read is slow) --
    def ensure_loaded(self):
        if not self._loaded:
            self._reload()

    def _reload(self):
        try:
            table = device.read_buttons()
        except device.DeviceNotFound as exc:
            self._enable(False); self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        if table is None:
            self._enable(False)
            self.status.emit(tr("Could not read the buttons — did the mouse answer?"), True)
            return
        self._table = [tuple(a) for a in table]
        self._ext = {}
        for i, action in enumerate(self._table):
            if i not in self.rows:          # a slot no button fires; kept, not shown
                continue
            if action == protocol.BTN_EXTENDED:
                self._ext[i] = self._read_ext(i)
            self._show(i)
        self._enable(True)
        self._loaded = True
        self.status.emit(tr("Buttons read from the mouse."), False)

    @staticmethod
    def _read_ext(index):
        """What the extended slot holds, decoded — or None (erased, a macro, or
        a layout we do not build), which the row then shows as unknown."""
        try:
            return device.read_ext_slot(index)
        except (device.DeviceNotFound, OSError):
            return None

    def _show(self, index):
        """Make row `index` reflect the state we believe the hardware holds."""
        self.rows[index].set_action(self._table[index], self._ext.get(index))

    def _enable(self, flag):
        for row in self.rows.values():
            row.setEnabled(flag)

    # -- sending ------------------------------------------------------------
    def _on_action(self, index):
        row = self.rows[index]
        action = row.current_action()
        if action is None:                       # a raw byte entry — never sent
            return
        if action == protocol.BTN_EXTENDED:
            row.show_ext(row.current_kind())
            row.ensure_ext_choice()              # an explicit choice needs a value
            self._send_ext(index)
            return
        label = row.action.currentText()
        try:
            routes, table = device.send_button(index, action)
        except (device.DeviceNotFound, ValueError) as exc:
            self._show(index)                    # undo the visual change
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        self._table = [tuple(a) for a in table]
        self._ext.pop(index, None)
        row.show_ext(None)
        self.status.emit(tr("{what} — via {routes}",
                            what=tr("Button {n} = {action}", n=self._number(index),
                                    action=label),
                            routes=", ".join(routes)), False)

    def _send_ext(self, index):
        """Write the extended slot (and the table) for button `index`."""
        row = self.rows[index]
        ext = row.current_ext()
        if ext is None:                          # a raw entry — never sent
            return
        kind = ext[0]
        senders = {"media": device.send_media, "key": device.send_key,
                   "combo": device.send_combo}
        try:
            routes, table = senders[kind](index, *ext[1:])
        except (device.DeviceNotFound, ValueError) as exc:
            self._show(index)                    # undo the visual change
            self.status.emit(tr("Error: {error}", error=tr_error(exc)), True)
            return
        self._table = [tuple(a) for a in table]
        self._ext[index] = ext
        n = self._number(index)
        what = {"media": tr("Button {n} = media '{key}'", n=n, key=row.ext_text()),
                "key": tr("Button {n} = key '{key}'", n=n, key=row.ext_text()),
                "combo": tr("Button {n} = {combo}", n=n, combo=row.ext_text())}[kind]
        self.status.emit(tr("{what} — via {routes}", what=what,
                            routes=", ".join(routes)), False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("open-m711pro — Redragon M711 Pro")
        self.resize(940, 660)      # 620 keeps most of the 16 button rows on screen
        self._build(0)

    def _build(self, page):
        """(Re)build every page in the current language, showing `page`.

        Building only READS the mouse (each page reflects the hardware); a
        rebuild for a language switch can therefore never write anything.
        """
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(0)

        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(180)
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(0, 18, 0, 14); sl.setSpacing(0)
        brand = QLabel("M711 PRO"); brand.setObjectName("brand")
        brand.setContentsMargins(18, 0, 0, 0)
        sub = QLabel("open-m711pro"); sub.setObjectName("muted")
        sub.setContentsMargins(18, 0, 0, 0)
        sl.addWidget(brand); sl.addWidget(sub); sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.lighting = LightingPage(); self.lighting.status.connect(self._status)
        self.stack.addWidget(self.lighting)
        self.dpi = DpiPage(); self.dpi.status.connect(self._status)
        self.stack.addWidget(self.dpi)
        self.buttons = ButtonsPage(); self.buttons.status.connect(self._status)
        self.stack.addWidget(self.buttons)

        self.nav_btns = []
        for i, name in enumerate(["Lighting", "Sensitivity (DPI)", "Buttons"]):
            b = QPushButton(tr(name)); b.setObjectName("nav"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._go(idx))
            sl.addWidget(b); self.nav_btns.append(b)
        sl.addStretch()

        # Language switch, bottom-left: one chip per language.
        lang = QHBoxLayout(); lang.setContentsMargins(18, 0, 18, 0); lang.setSpacing(6)
        self.lang_btns = {}
        for code, label in LANGUAGES.items():
            chip = QPushButton(label); chip.setObjectName("lang")
            chip.setCheckable(True); chip.setChecked(code == language())
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip(tr("Language"))
            chip.clicked.connect(lambda _=False, c=code: self._set_language(c))
            lang.addWidget(chip); self.lang_btns[code] = chip
        lang.addStretch()
        sl.addLayout(lang)

        top.addWidget(sidebar); top.addWidget(self.stack, 1)
        outer.addLayout(top, 1)

        self.status = QLabel(tr("Ready.")); self.status.setObjectName("statusbar")
        outer.addWidget(self.status)

        self._go(page)

    def _set_language(self, code, persist=True):
        if code == language():
            self.lang_btns[code].setChecked(True)
            return
        set_language(code, persist=persist)
        _install_qt_translator(QApplication.instance())
        self._build(self.stack.currentIndex())

    def _go(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)
        current = self.stack.currentWidget()
        if current is self.dpi:
            self.dpi.ensure_loaded()      # the read is slow; only when the tab opens
        elif current is self.buttons:
            self.buttons.ensure_loaded()

    def _status(self, msg, is_error):
        color = "#ff6b6b" if is_error else "#8b9098"
        self.status.setStyleSheet(f"background:#191c24; color:{color}; padding:7px 12px;")
        self.status.setText(msg)


_qt_translator = None


def _install_qt_translator(app):
    """Qt's own dialogs (the colour picker) in the interface language.

    Qt ships its translations; without loading them the picker stayed in
    English inside a Portuguese interface. A missing file just leaves English.
    """
    global _qt_translator
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if language() != "pt":
        return
    translator = QTranslator(app)
    if translator.load("qtbase_pt_BR",
                       QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
        _qt_translator = translator


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    _install_qt_translator(app)
    win = MainWindow(); win.show()
    app.exec()

"""Interface gráfica do open-m711pro em PySide6 (Qt).

Inspirada no Logitech G HUB e no Piper (libratbag): barra lateral, roda de cores
HSV desenhada com QPainter (anti-aliased), efeitos de iluminação e uma seção de
Sensibilidade (DPI) já montada (protocolo a mapear).

O núcleo (m711pro.core) continua stdlib puro; só esta GUI usa Qt.
"""
import math
import colorsys

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QConicalGradient, QRadialGradient, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QComboBox, QSlider, QPushButton, QFrame, QStackedWidget, QColorDialog,
)

from .core import device, state

ACCENT = "#19b8c8"

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
QLabel#statusbar {{ background: #191c24; color: #8b9098; padding: 7px 12px; }}
QFrame#chip {{ background: #171a21; border-radius: 6px; }}
QFrame#chipActive {{ background: #20242e; border: 1px solid {ACCENT}; border-radius: 6px; }}
"""


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
        # cor "cheia" (value=1.0); o brilho é um byte separado no protocolo.
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
EFEITOS = ["Fixo", "Respiração", "Ciclo", "Desligado",
           "Visualizador de áudio (em breve)"]
COLOR_EFFECTS = {"Fixo", "Respiração", "Ciclo"}   # efeitos que usam a cor escolhida
PRESETS = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0),
           (0, 255, 255), (0, 0, 255), (180, 0, 255), (255, 255, 255)]
DPI_STAGES = [800, 1600, 2400, 3200]
POLLING = [1000, 500, 250, 125]


class LightingPage(QWidget):
    status = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        root = QVBoxLayout(self); root.setContentsMargins(26, 22, 26, 22); root.setSpacing(14)

        t = QLabel("ILUMINAÇÃO"); t.setObjectName("title"); root.addWidget(t)

        er = QHBoxLayout()
        lbl = QLabel("EFEITO"); lbl.setObjectName("muted"); er.addWidget(lbl)
        self.effect = QComboBox(); self.effect.addItems(EFEITOS)
        self.effect.currentTextChanged.connect(self._on_effect)
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

        bl = QLabel("BRILHO"); bl.setObjectName("muted"); right.addWidget(bl)
        self.bright = QSlider(Qt.Horizontal); self.bright.setRange(15, 100)
        self.bright.setValue(100); self.bright.setFixedWidth(180)
        self.bright.valueChanged.connect(self._on_bright)
        self.bright.sliderReleased.connect(self._commit_current)
        right.addWidget(self.bright)

        # Velocidade — só aparece nos efeitos animados
        self.speed_label = QLabel("VELOCIDADE (Lenta → Rápida)")
        self.speed_label.setObjectName("muted"); right.addWidget(self.speed_label)
        self.speed = QSlider(Qt.Horizontal); self.speed.setRange(0, 100)
        self.speed.setValue(50); self.speed.setFixedWidth(180)
        self.speed.sliderReleased.connect(self._commit_current)
        right.addWidget(self.speed)

        pr = QGridLayout(); pr.setSpacing(4)
        for i, (r, g, b) in enumerate(PRESETS):
            sw = QPushButton(); sw.setFixedSize(24, 24); sw.setCursor(Qt.PointingHandCursor)
            sw.setStyleSheet(f"background:{self._hex(r,g,b)}; border:1px solid #2a2e38; border-radius:4px;")
            sw.clicked.connect(lambda _=False, c=(r, g, b): self._commit_rgb(*c))
            pr.addWidget(sw, 0, i)
        right.addLayout(pr)

        custom = QPushButton("Cor personalizada…"); custom.setObjectName("action")
        custom.clicked.connect(self._pick_custom); right.addWidget(custom)
        right.addStretch()
        body.addLayout(right); body.addStretch()
        # Container dos controles de cor — some quando o efeito não usa cor.
        self.color_area = QWidget(); self.color_area.setLayout(body)
        root.addWidget(self.color_area)

        # Aviso mostrado no lugar quando não há cor a escolher.
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
        pct = self._bright_pct()                 # preview mostra a cor já com o brilho
        self._set_preview_bg(r * pct // 100, g * pct // 100, b * pct // 100)
        self.readout.setText(f"#{r:02X}{g:02X}{b:02X}   RGB({r}, {g}, {b})   {pct}%")

    def _preview(self, r, g, b):
        self._refresh(r, g, b)

    def _send_fn(self):
        return {"Fixo": device.send_color,
                "Respiração": device.send_breathing,
                "Ciclo": device.send_cycle}.get(self.effect.currentText())

    def _speed_byte(self):
        # slider 0%(lenta) → 100%(rápida); byte menor = mais rápido (0xF0..0x08)
        pct = self.speed.value()
        return int(round(0xF0 - pct / 100 * (0xF0 - 0x08)))

    def _commit(self, r, g, b):
        eff = self.effect.currentText()
        fn = self._send_fn()
        if fn is None:
            return
        self._refresh(r, g, b)
        bb = self._bright_byte()
        if eff in ("Respiração", "Ciclo"):
            sp = self._speed_byte()
            call = lambda: fn(r, g, b, brightness=bb, speed=sp)
        else:
            call = lambda: fn(r, g, b, brightness=bb)
        self._send(call, f"{eff} #{r:02X}{g:02X}{b:02X} ({self._bright_pct()}%)")

    def _commit_rgb(self, r, g, b):
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self.wheel.set_hs(h, s)                  # presets mantêm o brilho do slider
        self._commit(r, g, b)

    def _commit_current(self):
        if self._send_fn() is None:
            return
        self._commit(*self.wheel.rgb())

    def _on_bright(self, _val):
        self.wheel.set_value(self._bright_pct() / 100.0)   # escurece a roda (visual)
        self._refresh(*self.wheel.rgb())

    def _speed_visible(self, eff):
        show = eff in ("Respiração", "Ciclo")   # velocidade só nos animados
        self.speed_label.setVisible(show)
        self.speed.setVisible(show)

    def _on_effect(self, eff):
        has_color = eff in COLOR_EFFECTS     # Fixo/Respiração/Ciclo usam cor
        self.color_area.setVisible(has_color)
        self.no_color.setVisible(not has_color)
        self._speed_visible(eff)
        if eff == "Desligado":
            self.no_color.setText("Iluminação desligada.")
            self._send(device.send_off, "LED desligado")
        elif has_color:
            self.no_color.setText("")
            self._commit_current()
        else:
            self.no_color.setText(f"'{eff}' ainda não implementado — o LED não foi alterado.")
            self.status.emit(f"'{eff}' ainda não implementado.", False)

    def _pick_custom(self):
        c = QColorDialog.getColor(parent=self, title="Escolha uma cor")
        if c.isValid():
            self._commit_rgb(c.red(), c.green(), c.blue())

    def _apply_saved_state(self):
        """Reflete o estado ATUAL — lê do hardware (nível 2); se falhar, usa a
        persistência local (nível 1). Não reenvia nada ao mouse."""
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
        eff = st.get("effect", "Fixo")
        if eff not in EFEITOS:
            eff = "Fixo"
        self.effect.blockSignals(True)          # refletir sem disparar envio
        self.effect.setCurrentText(eff)
        self.effect.blockSignals(False)
        has_color = eff in COLOR_EFFECTS
        self.color_area.setVisible(has_color)
        self.no_color.setVisible(not has_color)
        self._speed_visible(eff)
        if not has_color:
            self.no_color.setText("Iluminação desligada." if eff == "Desligado"
                                  else f"'{eff}' ainda não implementado.")

    def _send(self, fn, ok):
        try:
            vias = fn()
            self.status.emit(f"{ok} — via {', '.join(vias)}", False)
        except device.DeviceNotFound as e:
            self.status.emit(f"Erro: {e}", True)


class DpiPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        root = QVBoxLayout(self); root.setContentsMargins(26, 22, 26, 22); root.setSpacing(12)
        t = QLabel("SENSIBILIDADE (DPI)"); t.setObjectName("title"); root.addWidget(t)
        info = QLabel("🚧 Ainda não mapeado — interface pronta, protocolo em breve "
                      "(mapear com a skill captura).")
        info.setStyleSheet(f"color:{ACCENT};"); info.setWordWrap(True); root.addWidget(info)

        root.addWidget(self._muted("VELOCIDADES DE DPI"))
        chips = QHBoxLayout(); chips.setSpacing(6)
        for dpi in DPI_STAGES:
            chips.addWidget(self._chip(str(dpi), dpi == 2400))
        chips.addStretch(); root.addLayout(chips)

        sl = QSlider(Qt.Horizontal); sl.setRange(200, 12000); sl.setValue(2400)
        sl.setEnabled(False); root.addWidget(sl)

        root.addWidget(self._muted("TAXA DE RELATÓRIO (Hz)"))
        pol = QHBoxLayout(); pol.setSpacing(6)
        for hz in POLLING:
            pol.addWidget(self._chip(str(hz), hz == 1000))
        pol.addStretch(); root.addLayout(pol)
        root.addStretch()

    @staticmethod
    def _muted(text):
        lb = QLabel(text); lb.setObjectName("muted"); return lb

    @staticmethod
    def _chip(text, active):
        f = QFrame(); f.setObjectName("chipActive" if active else "chip")
        lay = QVBoxLayout(f); lay.setContentsMargins(16, 9, 16, 9)
        lb = QLabel(text); lb.setStyleSheet(
            f"color:{ACCENT if active else '#3a3e47'}; font-weight:{'700' if active else '400'};")
        lay.addWidget(lb); return f


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("open-m711pro — Redragon M711 Pro")
        self.resize(760, 500)

        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(0)

        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(180)
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(0, 18, 0, 0); sl.setSpacing(0)
        brand = QLabel("  M711 PRO"); brand.setObjectName("brand")
        sub = QLabel("  open-m711pro"); sub.setObjectName("muted")
        sl.addWidget(brand); sl.addWidget(sub); sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.lighting = LightingPage(); self.lighting.status.connect(self._status)
        self.stack.addWidget(self.lighting)
        self.stack.addWidget(DpiPage())

        self.nav_btns = []
        for i, name in enumerate(["Iluminação", "Sensibilidade (DPI)"]):
            b = QPushButton(name); b.setObjectName("nav"); b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self._go(idx))
            sl.addWidget(b); self.nav_btns.append(b)
        sl.addStretch()

        top.addWidget(sidebar); top.addWidget(self.stack, 1)
        outer.addLayout(top, 1)

        self.status = QLabel("Pronto."); self.status.setObjectName("statusbar")
        outer.addWidget(self.status)

        self._go(0)

    def _go(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)

    def _status(self, msg, is_error):
        color = "#ff6b6b" if is_error else "#8b9098"
        self.status.setStyleSheet(f"background:#191c24; color:{color}; padding:7px 12px;")
        self.status.setText(msg)


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    win = MainWindow(); win.show()
    app.exec()

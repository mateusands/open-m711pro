"""open-m711pro graphical interface (tkinter, no external dependencies).

Inspired by Logitech G HUB: a sidebar, an HSV colour wheel and the lighting
effects. This is the fallback used when PySide6 is not installed; the Qt
interface (m711pro.ui.qt) is the full one.
"""
import math
import colorsys
import tkinter as tk
from tkinter import ttk, colorchooser

from ..core import device
from . import theme as T


def _hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _rgb_of(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------------------
# Roda de cores HSV (Canvas + PhotoImage), renderizada uma vez.
# ---------------------------------------------------------------------------
class ColorWheel(tk.Canvas):
    def __init__(self, master, size=T.WHEEL_SIZE, on_preview=None, on_commit=None):
        super().__init__(master, width=size, height=size, bg=T.PANEL,
                         highlightthickness=0)
        self.size = size
        self.cx = self.cy = size // 2
        self.r = size // 2 - 3
        self.on_preview = on_preview
        self.on_commit = on_commit
        self._img = tk.PhotoImage(width=size, height=size)
        self.create_image(0, 0, anchor="nw", image=self._img)
        self._marker = self.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        self._render()
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _render(self):
        bg = _rgb_of(T.PANEL)
        r_in = self.r - 1.0
        rows = []
        for y in range(self.size):
            dy = y - self.cy + 0.5
            row = []
            for x in range(self.size):
                dx = x - self.cx + 0.5
                dist = math.hypot(dx, dy)
                if dist > self.r + 0.5:
                    row.append(T.PANEL)
                    continue
                hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
                sat = min(dist / self.r, 1.0)
                cr, cg, cb = colorsys.hsv_to_rgb(hue, sat, 1.0)
                cr, cg, cb = cr * 255, cg * 255, cb * 255
                if dist > r_in:                 # anti-aliasing da borda
                    a = max(0.0, min(1.0, self.r + 0.5 - dist))
                    cr = cr * a + bg[0] * (1 - a)
                    cg = cg * a + bg[1] * (1 - a)
                    cb = cb * a + bg[2] * (1 - a)
                row.append(_hex(cr, cg, cb))
            rows.append("{" + " ".join(row) + "}")
        self._img.put(" ".join(rows))

    def _hs_at(self, ex, ey):
        dx, dy = ex - self.cx, ey - self.cy
        dist = math.hypot(dx, dy)
        if dist > self.r:                       # prende na borda
            ang = math.atan2(dy, dx)
            dx, dy = math.cos(ang) * self.r, math.sin(ang) * self.r
            dist = self.r
        hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
        sat = min(dist / self.r, 1.0)
        self.coords(self._marker, self.cx + dx - 6, self.cy + dy - 6,
                    self.cx + dx + 6, self.cy + dy + 6)
        return hue, sat

    def set_marker_hs(self, hue, sat):
        dx = math.cos(hue * 2 * math.pi) * sat * self.r
        dy = math.sin(hue * 2 * math.pi) * sat * self.r
        self.coords(self._marker, self.cx + dx - 6, self.cy + dy - 6,
                    self.cx + dx + 6, self.cy + dy + 6)

    def _drag(self, e):
        hue, sat = self._hs_at(e.x, e.y)
        if self.on_preview:
            self.on_preview(hue, sat)

    def _release(self, e):
        hue, sat = self._hs_at(e.x, e.y)
        if self.on_commit:
            self.on_commit(hue, sat)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
EFFECTS = ["Steady", "Off", "Cycle (coming soon)", "Breathing (coming soon)",
           "Audio visualiser (coming soon)"]
DPI_STAGES = [800, 1600, 2400, 3200]   # placeholder for the informational panel
POLLING = [1000, 500, 250, 125]


class App:
    def __init__(self, root):
        self.root = root
        self.hue = 0.5
        self.sat = 1.0
        self.brightness = 1.0
        root.title("open-m711pro — Redragon M711 Pro")
        root.configure(bg=T.BG)
        root.geometry("720x470")
        root.minsize(680, 440)
        self._init_style()
        self._build()
        self.show("light")

    def _init_style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TCombobox", fieldbackground=T.PANEL_HI, background=T.PANEL_HI,
                    foreground=T.FG, arrowcolor=T.FG, bordercolor=T.BORDER)
        s.configure("Accent.Horizontal.TScale", background=T.PANEL)

    # ---- layout ------------------------------------------------------------
    def _build(self):
        # Barra de status PRIMEIRO (reserva a faixa inferior de largura total,
        # otherwise the sidebar/content squeeze it and the text gets clipped).
        self.status = tk.Label(self.root, text="Ready.", bg=T.PANEL, fg=T.MUTED,
                               anchor="w", padx=12, pady=7)
        self.status.pack(side="bottom", fill="x")

        self.sidebar = tk.Frame(self.root, bg=T.SIDEBAR, width=170)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="M711 PRO", bg=T.SIDEBAR, fg=T.FG,
                 font=(T.FONT, 14, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(self.sidebar, text="open-m711pro", bg=T.SIDEBAR, fg=T.MUTED,
                 font=(T.FONT, 8)).pack(anchor="w", padx=18, pady=(0, 18))

        self.nav = {}
        self._nav_item("light", "  Lighting")
        self._nav_item("dpi", "  Sensitivity (DPI)")

        self.content = tk.Frame(self.root, bg=T.BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages = {"light": self._page_light(), "dpi": self._page_dpi()}

    def _nav_item(self, key, label):
        b = tk.Label(self.sidebar, text=label, bg=T.SIDEBAR, fg=T.MUTED,
                     anchor="w", padx=18, pady=11, cursor="hand2",
                     font=(T.FONT, 11))
        b.pack(fill="x")
        b.bind("<Button-1>", lambda e, k=key: self.show(k))
        self.nav[key] = b

    def show(self, key):
        for k, page in self.pages.items():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True, padx=22, pady=18)
        for k, b in self.nav.items():
            active = (k == key)
            b.config(fg=T.ACCENT if active else T.MUTED,
                     bg=T.PANEL_HI if active else T.SIDEBAR)

    # ---- page: Lighting ------------------------------------------------
    def _page_light(self):
        p = tk.Frame(self.content, bg=T.BG)
        tk.Label(p, text="LIGHTING", bg=T.BG, fg=T.FG,
                 font=(T.FONT, 16, "bold")).pack(anchor="w")

        # efeito
        row = tk.Frame(p, bg=T.BG); row.pack(anchor="w", pady=(14, 8))
        tk.Label(row, text="EFEITO", bg=T.BG, fg=T.MUTED,
                 font=(T.FONT, 9)).pack(side="left")
        self.effect = ttk.Combobox(row, values=EFFECTS, state="readonly", width=28)
        self.effect.set("Steady")
        self.effect.pack(side="left", padx=10)
        self.effect.bind("<<ComboboxSelected>>", self._on_effect)

        self.body = tk.Frame(p, bg=T.BG); self.body.pack(anchor="w", fill="x", pady=6)

        # roda de cores
        self.wheel = ColorWheel(self.body, on_preview=self._preview_hs,
                                on_commit=self._commit_hs)
        self.wheel.pack(side="left")

        # controls on the right
        right = tk.Frame(self.body, bg=T.BG); right.pack(side="left", padx=20, anchor="n")

        self.preview = tk.Frame(right, width=54, height=54, bg="#000000",
                                highlightthickness=1, highlightbackground=T.BORDER)
        self.preview.pack(anchor="w")
        self.preview.pack_propagate(False)
        self.readout = tk.Label(right, text="—", bg=T.BG, fg=T.FG,
                                font=(T.FONT, 11, "bold"))
        self.readout.pack(anchor="w", pady=8)

        tk.Label(right, text="BRILHO", bg=T.BG, fg=T.MUTED,
                 font=(T.FONT, 9)).pack(anchor="w")
        self.bright = ttk.Scale(right, from_=0.15, to=1.0, value=1.0, length=150,
                                command=self._on_bright)
        self.bright.pack(anchor="w")
        self.bright.bind("<ButtonRelease-1>", lambda e: self._commit_current())

        # quick presets
        presets = tk.Frame(right, bg=T.BG); presets.pack(anchor="w", pady=12)
        for (r, g, b) in [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0),
                          (0, 255, 255), (0, 0, 255), (180, 0, 255), (255, 255, 255)]:
            sw = tk.Frame(presets, width=22, height=22, bg=_hex(r, g, b),
                          highlightthickness=1, highlightbackground=T.BORDER,
                          cursor="hand2")
            sw.pack(side="left", padx=2)
            sw.pack_propagate(False)
            sw.bind("<Button-1>", lambda e, c=(r, g, b): self._commit_rgb(c))

        ttk.Button(right, text="Cor personalizada…",
                   command=self._pick_custom).pack(anchor="w", pady=(4, 0))
        return p

    # ---- page: Sensitivity (DPI) — informational only ------------------------------
    def _page_dpi(self):
        p = tk.Frame(self.content, bg=T.BG)
        tk.Label(p, text="SENSITIVITY (DPI)", bg=T.BG, fg=T.FG,
                 font=(T.FONT, 16, "bold")).pack(anchor="w")
        tk.Label(p, text="Configure DPI from the Qt interface or the command line; "
                 "this fallback UI only covers lighting.", bg=T.BG, fg=T.ACCENT,
                 wraplength=440, justify="left").pack(anchor="w", pady=(6, 16))

        tk.Label(p, text="VELOCIDADES DE DPI", bg=T.BG, fg=T.MUTED,
                 font=(T.FONT, 9)).pack(anchor="w")
        chips = tk.Frame(p, bg=T.BG); chips.pack(anchor="w", pady=8)
        for i, dpi in enumerate(DPI_STAGES):
            active = (dpi == 2400)
            tk.Label(chips, text=str(dpi), bg=T.PANEL_HI if active else T.PANEL,
                     fg=T.ACCENT if active else T.DISABLED, padx=14, pady=8,
                     font=(T.FONT, 11, "bold" if active else "normal")).pack(
                     side="left", padx=3)

        tk.Scale(p, from_=200, to=12000, orient="horizontal", length=420,
                 bg=T.BG, fg=T.DISABLED, troughcolor=T.PANEL, highlightthickness=0,
                 state="disabled").pack(anchor="w", pady=14)

        tk.Label(p, text="POLLING RATE (Hz)", bg=T.BG, fg=T.MUTED,
                 font=(T.FONT, 9)).pack(anchor="w")
        pol = tk.Frame(p, bg=T.BG); pol.pack(anchor="w", pady=8)
        for hz in POLLING:
            active = (hz == 1000)
            tk.Label(pol, text=str(hz), bg=T.PANEL_HI if active else T.PANEL,
                     fg=T.ACCENT if active else T.DISABLED, padx=12, pady=6).pack(
                     side="left", padx=3)
        return p

    # ---- colour logic -----------------------------------------------------
    def _rgb_from_state(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.brightness)
        return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))

    def _refresh_preview(self):
        r, g, b = self._rgb_from_state()
        self.preview.config(bg=_hex(r, g, b))
        self.readout.config(text=f"#{r:02X}{g:02X}{b:02X}   RGB({r}, {g}, {b})")

    def _preview_hs(self, hue, sat):
        self.hue, self.sat = hue, sat
        self._refresh_preview()

    def _commit_hs(self, hue, sat):
        self.hue, self.sat = hue, sat
        self._commit_current()

    def _commit_rgb(self, rgb):
        r, g, b = rgb
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self.hue, self.sat, self.brightness = h, s, v
        self.bright.set(max(v, 0.15))
        self.wheel.set_marker_hs(h, s)
        self._commit_current()

    def _on_bright(self, val):
        self.brightness = float(val)
        self._refresh_preview()

    def _on_effect(self, _e=None):
        eff = self.effect.get()
        steady = (eff == "Steady")
        if steady:
            self.body.pack(anchor="w", fill="x", pady=6)   # show the palette
        else:
            self.body.pack_forget()                        # hide unless the effect is Steady
        if eff == "Off":
            self._send(device.send_off, "LED off")
        elif steady:
            self._commit_current()
        else:
            self.status.config(text=f"'{eff}' is not implemented yet.", fg=T.ACCENT)

    def _commit_current(self):
        if self.effect.get() != "Steady":
            return
        r, g, b = self._rgb_from_state()
        self._refresh_preview()
        self._send(lambda: device.send_color(r, g, b),
                   f"Cor #{r:02X}{g:02X}{b:02X}")

    def _pick_custom(self):
        rgb, _ = colorchooser.askcolor(title="Escolha uma cor")
        if rgb:
            self._commit_rgb((int(rgb[0]), int(rgb[1]), int(rgb[2])))

    def _send(self, fn, ok_msg):
        try:
            vias = fn()
            self.status.config(text=f"{ok_msg} — via {', '.join(vias)}", fg=T.MUTED)
        except device.DeviceNotFound as exc:
            self.status.config(text=f"Error: {exc}", fg=T.DANGER)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

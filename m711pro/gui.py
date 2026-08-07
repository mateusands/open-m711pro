"""Interface gráfica do open-m711pro (tkinter, sem dependências externas).

Estilo editor de imagem: paleta de swatches, seletor de cor HSV (colorchooser),
cores recentes, preview com HEX/RGB e botão de desligar. Clicar aplica ao vivo.
"""
import tkinter as tk
from tkinter import ttk, colorchooser

from .core import device
from . import colors

BG = "#1e1e1e"
FG = "#e0e0e0"
MUTED = "#9a9a9a"
CARD = "#2a2a2a"
SWATCH = 24          # tamanho de cada swatch (px)
RECENT_MAX = 12


def _hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


class App:
    def __init__(self, root):
        self.root = root
        self.recent = []
        root.title("open-m711pro — Controle de LED (M711 Pro)")
        root.configure(bg=BG)
        root.resizable(False, False)
        self._build()

    # ---- construção da UI --------------------------------------------------
    def _build(self):
        pad = dict(padx=14, pady=6)

        # Preview + info
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", **pad)
        self.preview = tk.Frame(header, width=64, height=64, bg="#000000",
                                highlightthickness=1, highlightbackground="#444")
        self.preview.pack(side="left")
        self.preview.pack_propagate(False)
        self.info = tk.Label(header, text="Escolha uma cor", bg=BG, fg=FG,
                             font=("TkDefaultFont", 12, "bold"), anchor="w")
        self.info.pack(side="left", padx=12)

        # Paleta
        tk.Label(self.root, text="Paleta", bg=BG, fg=MUTED, anchor="w").pack(
            fill="x", padx=14)
        pal = tk.Frame(self.root, bg=BG)
        pal.pack(**pad)
        for row in colors.palette():
            rf = tk.Frame(pal, bg=BG)
            rf.pack()
            for (r, g, b) in row:
                self._swatch(rf, r, g, b)

        # Recentes
        tk.Label(self.root, text="Recentes", bg=BG, fg=MUTED, anchor="w").pack(
            fill="x", padx=14)
        self.recent_frame = tk.Frame(self.root, bg=BG, height=SWATCH + 4)
        self.recent_frame.pack(fill="x", padx=13, pady=(0, 6))
        self.recent_frame.pack_propagate(False)

        # Ações
        actions = tk.Frame(self.root, bg=BG)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Cor personalizada…",
                   command=self.pick_custom).pack(side="left")
        ttk.Button(actions, text="Desligar LED",
                   command=self.off).pack(side="left", padx=8)

        # Status
        self.status = tk.Label(self.root, text="Pronto.", bg=CARD, fg=MUTED,
                               anchor="w", padx=10, pady=5)
        self.status.pack(fill="x", side="bottom")

    def _swatch(self, parent, r, g, b, size=SWATCH):
        f = tk.Frame(parent, width=size, height=size, bg=_hex(r, g, b),
                     highlightthickness=1, highlightbackground="#333", cursor="hand2")
        f.pack(side="left", padx=1, pady=1)
        f.pack_propagate(False)
        f.bind("<Button-1>", lambda e, c=(r, g, b): self.set_color(*c))

    # ---- ações -------------------------------------------------------------
    def set_color(self, r, g, b):
        try:
            vias = device.send_color(r, g, b)
        except device.DeviceNotFound as e:
            self.status.config(text=f"Erro: {e}", fg="#ff6b6b")
            return
        self._update_preview(r, g, b, f"enviada via {', '.join(vias)}")
        self._add_recent(r, g, b)

    def off(self):
        try:
            vias = device.send_off()
        except device.DeviceNotFound as e:
            self.status.config(text=f"Erro: {e}", fg="#ff6b6b")
            return
        self._update_preview(0, 0, 0, f"LED desligado (via {', '.join(vias)})")

    def pick_custom(self):
        rgb, _ = colorchooser.askcolor(title="Escolha uma cor")
        if rgb:
            self.set_color(int(rgb[0]), int(rgb[1]), int(rgb[2]))

    # ---- helpers -----------------------------------------------------------
    def _update_preview(self, r, g, b, msg):
        self.preview.config(bg=_hex(r, g, b))
        self.info.config(text=f"#{r:02X}{g:02X}{b:02X}   RGB({r}, {g}, {b})")
        self.status.config(text=msg, fg=MUTED)

    def _add_recent(self, r, g, b):
        c = (r, g, b)
        if c in self.recent:
            self.recent.remove(c)
        self.recent.insert(0, c)
        self.recent = self.recent[:RECENT_MAX]
        for w in self.recent_frame.winfo_children():
            w.destroy()
        for (rr, gg, bb) in self.recent:
            self._swatch(self.recent_frame, rr, gg, bb)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()

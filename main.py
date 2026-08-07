#!/usr/bin/env python3
"""Ponto de entrada do open-m711pro.

  python3 main.py            → abre a interface gráfica (Qt; cai no tkinter se
                               o PySide6 não estiver instalado)
  python3 main.py <cor>      → modo linha de comando (ex.: azul, FF0000, off)
"""
import sys


def _run_gui():
    try:
        from m711pro.gui import main as gui_main      # PySide6 (Qt)
    except ImportError:
        from m711pro.gui_tk import main as gui_main    # fallback stdlib (tkinter)
    gui_main()


def main():
    if len(sys.argv) > 1:
        from m711pro.cli import main as cli_main
        cli_main()
    else:
        _run_gui()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Ponto de entrada do open-m711pro.

  python3 main.py            → abre a interface gráfica
  python3 main.py <cor>      → modo linha de comando (ex.: azul, FF0000, off)
"""
import sys


def main():
    if len(sys.argv) > 1:
        from m711pro.cli import main as cli_main
        cli_main()
    else:
        from m711pro.gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()

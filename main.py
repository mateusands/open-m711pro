#!/usr/bin/env python3
"""open-m711pro entry point.

  python3 main.py            -> graphical interface (Qt; falls back to tkinter
                                when PySide6 is not installed)
  python3 main.py <args>     -> command line (e.g. blue, FF0000, off, dpi 1600)
"""
import sys


def _run_gui():
    try:
        from m711pro.ui.qt import main as gui_main      # PySide6 (Qt)
    except ImportError:
        from m711pro.ui.tk import main as gui_main      # stdlib fallback
    gui_main()


def main():
    if len(sys.argv) > 1:
        from m711pro.cli import main as cli_main
        cli_main()
    else:
        _run_gui()


if __name__ == "__main__":
    main()

"""Module entry point: ``python3 -m m711pro``.

Mirrors the behaviour of ``main.py`` at the repository root:

  python3 -m m711pro          -> graphical interface (Qt; falls back to tkinter
                                 when PySide6 is not installed)
  python3 -m m711pro <args>   -> command line (e.g. blue, FF0000, off, dpi 1600)

It also hosts the installed entry points declared in ``pyproject.toml``:

  open-m711pro-gui  -> :func:`gui`
  open-m711pro      -> ``m711pro.cli:main`` (declared directly, no wrapper)
"""
import sys


def gui(argv=None):
    """Open the graphical interface.

    Prefers the Qt (PySide6) interface and falls back to the stdlib tkinter one
    when PySide6 is not installed, so the core stays dependency-free.
    """
    try:
        from .ui.qt import main as gui_main       # PySide6 (Qt)
    except ImportError:
        from .ui.tk import main as gui_main       # stdlib fallback
    return gui_main()


def main(argv=None):
    """Dispatch: no arguments opens the GUI, arguments go to the CLI."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args:
        from .cli import main as cli_main
        return cli_main(args)
    return gui()


if __name__ == "__main__":
    sys.exit(main())

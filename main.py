#!/usr/bin/env python3
"""open-m711pro entry point (running from a source checkout).

  python3 main.py            -> graphical interface
  python3 main.py <args>     -> command line (e.g. blue, FF0000, off, dpi 1600)

The dispatch itself lives in m711pro/__main__.py so that this script, the
`python3 -m m711pro` form and the installed console entry point all behave
identically.
"""
import sys

from m711pro.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

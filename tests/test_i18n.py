"""Interface language — the translation table and how the language is chosen.

No Qt needed: the table is plain data. What matters most is that a
translation never changes behaviour (placeholders intact, keys reachable) and
that the language follows the user's choice, then the system locale.
"""
import os
import re
import string

from m711pro.core import device, state
from m711pro.ui import i18n


def _fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_translation_keeps_its_placeholders():
    # a dropped {n} would raise KeyError mid-click; an extra one, too
    for english, portuguese in i18n.PT.items():
        assert _fields(english) == _fields(portuguese), english


def test_every_string_the_interface_asks_for_is_translated():
    # scan the UI source for tr("...") literals: each must have a PT entry
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "m711pro", "ui", "qt.py")) as handle:
        source = handle.read()
    asked = set()
    for match in re.finditer(r'tr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', source):
        asked.add("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))))
    missing = sorted(a for a in asked if a not in i18n.PT)
    assert not missing, missing


def test_tr_formats_after_translating():
    i18n.set_language("pt", persist=False)
    try:
        assert i18n.tr("Stage {n} = {dpi}", n=2, dpi="700 DPI") == "Estágio 2 = 700 DPI"
        assert i18n.tr("never translated") == "never translated"
    finally:
        i18n.set_language("en", persist=False)
    assert i18n.tr("Stage {n} = {dpi}", n=2, dpi="700 DPI") == "Stage 2 = 700 DPI"


def test_the_language_follows_the_saved_choice_then_the_locale():
    saved = (state.load, os.environ.get("LANG"), os.environ.get("LC_ALL"),
             os.environ.get("LC_MESSAGES"), i18n._current)
    try:
        os.environ.pop("LC_ALL", None); os.environ.pop("LC_MESSAGES", None)
        state.load = lambda: {}
        os.environ["LANG"] = "pt_BR.UTF-8"; i18n._current = None
        assert i18n.language() == "pt"
        os.environ["LANG"] = "en_US.UTF-8"; i18n._current = None
        assert i18n.language() == "en"
        state.load = lambda: {"language": "pt"}; i18n._current = None
        assert i18n.language() == "pt"            # the explicit choice wins
    finally:
        state.load = saved[0]
        for var, value in zip(("LANG", "LC_ALL", "LC_MESSAGES"), saved[1:4]):
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value
        i18n._current = saved[4]


def test_first_run_errors_are_translated():
    i18n.set_language("pt", persist=False)
    try:
        locked = device._no_permission(["/dev/hidraw3"])
        assert "/dev/hidraw3" in i18n.tr_error(locked)
        assert "permissão" in i18n.tr_error(locked)
        assert i18n.tr_error(device.DeviceNotFound("mouse not found — x")) \
            .startswith("mouse não encontrado")
        assert i18n.tr_error(ValueError("something else")) == "something else"
    finally:
        i18n.set_language("en", persist=False)

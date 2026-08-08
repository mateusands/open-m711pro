"""Persistence of the last state this app applied.

Stores what THIS app set last (effect + colour) so it can reopen reflecting the
real state when it was the last thing to touch the mouse. Reading the state
straight from the hardware is implemented in device.read_led_state().
"""
import os
import json


def _path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "open-m711pro", "state.json")


def load():
    """Return the saved state as a dict (empty on missing file or error)."""
    try:
        with open(_path()) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save(state):
    """Persist `state` (a dict). Silent on write errors."""
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            json.dump(state, handle)
    except OSError:
        pass

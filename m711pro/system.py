"""System integration: the udev rule and the application menu entry.

`open-m711pro setup` makes a pip or release install usable on its own. The
udev rule and the menu entry ship inside the package (m711pro/data/), so this
works without a checkout; packaging/install.sh reads the same two files.

Nothing here talks to the mouse. The only step that needs root is copying the
udev rule into /etc, and that one goes through sudo explicitly so the user sees
the password prompt for what it is.
"""
import os
import shutil
import subprocess
import sys
import tempfile

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# Must sort before 73-seat-late.rules, where systemd applies the uaccess ACL:
# shipped as 99-m711pro.rules the tag arrived too late and did nothing.
RULE_NAME = "70-m711pro.rules"
PREVIOUS_RULE = "/etc/udev/rules.d/99-m711pro.rules"   # our own, v0.1.x
DESKTOP_NAME = "open-m711pro.desktop"
RULE_DEST = "/etc/udev/rules.d/" + RULE_NAME
GUI_COMMAND = "open-m711pro-gui"

# The first README (v0, in Portuguese) told people to create this file with
# this single line. It makes every Compx hidraw node world-writable, and its
# name differs from ours, so installing the uaccess rule alone left it active.
LEGACY_RULE = "/etc/udev/rules.d/99-redragon-m711.rules"
LEGACY_LINE = 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="25a7", MODE="0666"'


def legacy_rule(path=LEGACY_RULE):
    """None when absent; "ours" when it is exactly the line we told people to
    write (safe to remove); "modified" when someone edited it (left alone)."""
    try:
        with open(path) as handle:
            lines = [l.strip() for l in handle.read().splitlines() if l.strip()]
    except FileNotFoundError:
        return None
    except OSError:
        return "modified"                      # unreadable: never touch it
    return "ours" if lines == [LEGACY_LINE] else "modified"


class RunAsUser(Exception):
    """setup was started through sudo; it must run as the desktop user."""


def _read(name):
    with open(os.path.join(DATA_DIR, name)) as handle:
        return handle.read()


def udev_rule():
    """The udev rule text, as shipped in the package."""
    return _read(RULE_NAME)


def launcher(which=shutil.which, exists=os.path.exists):
    """The argv the menu entry should run, as a list.

    The installed GUI command when it exists; otherwise main.py of the checkout
    this module lives in, run by the current interpreter — the README's
    per-distribution steps clone the repository and never run pip, so the
    installed command is often absent. Both paths are absolute: a desktop
    session's PATH frequently lacks ~/.local/bin.
    """
    installed = which(GUI_COMMAND)
    if installed:
        return [installed]
    # pipx and venv installs put it beside the interpreter, often off the PATH
    beside = os.path.join(os.path.dirname(sys.executable), GUI_COMMAND)
    if exists(beside):
        return [beside]
    checkout_main = os.path.join(os.path.dirname(os.path.dirname(DATA_DIR)),
                                 "main.py")
    if exists(checkout_main):
        return [sys.executable, checkout_main]
    return [sys.executable, "-m", "m711pro"]


def _desktop_quote(arg):
    # freedesktop Exec quoting: double quotes, with " ` $ \ escaped inside
    if arg and not any(c in arg for c in ' \t"\'\\`$;&|<>()*?#~'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def desktop_entry(argv):
    """The .desktop file text, with Exec pointing at `argv`."""
    exec_line = "Exec=" + " ".join(_desktop_quote(a) for a in argv)
    return "".join(exec_line + "\n" if line.startswith("Exec=") else line
                   for line in _read(DESKTOP_NAME).splitlines(keepends=True))


def _data_home(data_home=None):
    return (data_home or os.environ.get("XDG_DATA_HOME")
            or os.path.expanduser("~/.local/share"))


def desktop_path(data_home=None):
    return os.path.join(_data_home(data_home), "applications", DESKTOP_NAME)


def install_desktop_entry(argv, data_home=None):
    """Write the menu entry for this user (no root needed). Returns its path."""
    path = desktop_path(data_home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(desktop_entry(argv))
    return path


def _as_root(cmd, is_root):
    return cmd if is_root else ["sudo"] + cmd


def udev_install_commands(rule_file, is_root):
    """The three commands that install the rule and make it take effect."""
    return [_as_root(["install", "-D", "-m", "0644", rule_file, RULE_DEST], is_root),
            _as_root(["udevadm", "control", "--reload-rules"], is_root),
            _as_root(["udevadm", "trigger", "--subsystem-match=hidraw"], is_root)]


def _run(cmd):
    subprocess.run(cmd, check=True)


def setup(run=_run, data_home=None, is_root=None, which=shutil.which, say=print,
          legacy_path=LEGACY_RULE, previous_path=PREVIOUS_RULE):
    """Install the udev rule (via sudo) and this user's menu entry."""
    if is_root is None:
        is_root = os.geteuid() == 0
    if is_root and os.environ.get("SUDO_USER"):
        # the menu entry would land in root's home, not the user's
        raise RunAsUser("run 'open-m711pro setup' without sudo — it asks for "
                        "sudo itself, only for the udev rule")
    say("udev rule (grants the logged-in user access to the mouse):")
    with tempfile.NamedTemporaryFile("w", suffix=".rules", delete=False) as tmp:
        tmp.write(udev_rule())
    commands = udev_install_commands(tmp.name, is_root)
    if os.path.exists(previous_path):
        say(f"replacing {previous_path}: numbered after 73-seat-late.rules, it "
            "never granted access")
        commands.insert(1, _as_root(["rm", "-f", previous_path], is_root))
    legacy = legacy_rule(legacy_path)
    if legacy == "ours":
        say(f"removing the old world-writable rule {legacy_path} (MODE 0666, "
            "from an early version of the README):")
        commands.insert(1, _as_root(["rm", "-f", legacy_path], is_root))
    elif legacy == "modified":
        say(f"warning: {legacy_path} exists and was edited, so it is left alone. "
            "If it still sets MODE=\"0666\", remove it yourself — it keeps the "
            "mouse writable by every account.")
    try:
        for cmd in commands:
            say("  $ " + " ".join(cmd))
            run(cmd)
    finally:
        os.unlink(tmp.name)
    path = install_desktop_entry(launcher(which), data_home)
    say(f"menu entry: {path}")
    say("Done. Replug the dongle so the new rule applies.")


def uninstall(run=_run, data_home=None, is_root=None, say=print):
    """Remove exactly what setup installed."""
    if is_root is None:
        is_root = os.geteuid() == 0
    for cmd in ([_as_root(["rm", "-f", RULE_DEST], is_root),
                 _as_root(["rm", "-f", PREVIOUS_RULE], is_root)]
                + udev_install_commands("", is_root)[1:]):
        say("  $ " + " ".join(cmd))
        run(cmd)
    path = desktop_path(data_home)
    if os.path.exists(path):
        os.remove(path)
        say(f"removed {path}")

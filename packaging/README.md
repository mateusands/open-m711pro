# packaging/

Everything needed to turn the repository into a normal Linux desktop
application. Nothing here talks to the mouse; it only arranges permissions and
menu integration.

| File | Purpose |
|------|---------|
| `../m711pro/data/70-m711pro.rules` | udev rule granting the logged-in user access to the mouse's `/dev/hidraw*` node (both PIDs, `25a7:fa07` and `25a7:fa08`). |
| `../m711pro/data/open-m711pro.desktop` | freedesktop entry template so the GUI shows up in the application menu. |
| `install.sh` | installs/removes the two files above, reloads udev, refreshes the desktop database. Idempotent, root-checked. |

The two data files live **inside the Python package** so that a pip or release
install carries them too: `open-m711pro setup` installs the same rule without a
checkout (asking for `sudo` only for that step) and writes a per-user menu
entry pointing at whichever launcher actually exists.

The Python package itself is installed with `pip`; `install.sh` deliberately
does not touch it.

## Install

### 1. The Python package

From a checkout of the repository:

```bash
pipx install --system-site-packages .   # uses the distribution's PySide6 (or tkinter)
pipx install '.[gui]'                   # pulls PySide6 from PyPI
```

That provides two commands:

| Command | What it does |
|---------|--------------|
| `open-m711pro` | the CLI (`open-m711pro blue`, `open-m711pro dpi 1600`, …) |
| `open-m711pro-gui` | opens the graphical interface |

`python3 -m m711pro` works too — no arguments opens the GUI, arguments go to
the CLI, same as `python3 main.py` from the source tree.

> pipx puts the commands in `~/.local/bin`. If the desktop entry shows
> up but does nothing, that directory is probably not on your session's `PATH`;
> `open-m711pro setup` writes the entry with the absolute path, which avoids it.

For development, an editable install keeps the source tree live:

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui]'
```

### 2. Device access and the menu entry

```bash
open-m711pro setup             # any install: pip, release download or checkout
sudo sh packaging/install.sh   # from a checkout, system-wide menu entry
```

Either one is enough. `install.sh` points the menu entry at this checkout's
`main.py`, so it works even if you never ran pip — keep the checkout where it
is.

Then replug the mouse (or the 2.4G dongle) so udev applies the new rule.

Running it again is safe: files that already match are left alone.

## Uninstall

```bash
open-m711pro setup --uninstall     # or: sudo sh packaging/install.sh --uninstall
pipx uninstall open-m711pro
```

## Why `uaccess` instead of `MODE="0666"`

The README's original one-liner used `MODE="0666"`, which makes the raw HID node
readable and writable by *every* account on the machine, forever. That node
carries every button and movement the mouse reports, and writing to it
reprograms the device — this project can already map a mouse button to an
arbitrary keystroke.

`TAG+="uaccess"` asks systemd-logind to grant access, via an ACL, only to the
user of the currently active local session, and to revoke it when that session
ends. Identical convenience on a desktop, much smaller blast radius. It is what
libratbag/piper, OpenRGB and solaar use.

The file must sort **before** `73-seat-late.rules`, where systemd actually
applies the ACL — hence `70-`. Versions up to 0.1.2 shipped it as
`99-m711pro.rules`, which tagged the device too late and granted nothing; both
installers remove that file.

It needs systemd-logind, which every mainstream desktop distribution has. The
rules file carries a commented-out `GROUP="plugdev", MODE="0660"` fallback for
systems without it — still narrower than `0666`.

## Manual install, without the script

```bash
sudo install -m 0644 m711pro/data/70-m711pro.rules /etc/udev/rules.d/70-m711pro.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

sudo install -m 0644 m711pro/data/open-m711pro.desktop /usr/share/applications/open-m711pro.desktop
```

For a per-user menu entry instead, drop the `.desktop` file into
`~/.local/share/applications/`. The udev rule always needs root.

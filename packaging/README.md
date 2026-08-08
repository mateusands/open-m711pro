# packaging/

Everything needed to turn the repository into a normal Linux desktop
application. Nothing here talks to the mouse; it only arranges permissions and
menu integration.

| File | Purpose |
|------|---------|
| `99-m711pro.rules` | udev rule granting the logged-in user access to the mouse's `/dev/hidraw*` node (both PIDs, `25a7:fa07` and `25a7:fa08`). |
| `open-m711pro.desktop` | freedesktop entry so the GUI shows up in the application menu. Runs `open-m711pro-gui`. |
| `install.sh` | installs/removes the two files above, reloads udev, refreshes the desktop database. Idempotent, root-checked. |

The Python package itself is installed with `pip`; `install.sh` deliberately
does not touch it.

## Install

### 1. The Python package

From a checkout of the repository:

```bash
pip install --user .          # core only, zero dependencies (tkinter UI)
pip install --user '.[gui]'   # with the Qt interface (PySide6)
```

That provides two commands:

| Command | What it does |
|---------|--------------|
| `open-m711pro` | the CLI (`open-m711pro blue`, `open-m711pro dpi 1600`, …) |
| `open-m711pro-gui` | opens the graphical interface |

`python3 -m m711pro` works too — no arguments opens the GUI, arguments go to
the CLI, same as `python3 main.py` from the source tree.

> With `--user` the commands land in `~/.local/bin`. If the desktop entry shows
> up but does nothing, that directory is probably not on your session's `PATH`;
> installing system-wide (`sudo pip install .`, or via `pipx`) avoids it.

For development, an editable install keeps the source tree live:

```bash
pip install --user -e '.[gui]'
```

### 2. Device access and the menu entry

```bash
sudo sh packaging/install.sh
```

Then replug the mouse (or the 2.4G dongle) so udev applies the new rule.

Running it again is safe: files that already match are left alone.

## Uninstall

```bash
sudo sh packaging/install.sh --uninstall
pip uninstall open-m711pro
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

It needs systemd-logind, which every mainstream desktop distribution has. The
rules file carries a commented-out `GROUP="plugdev", MODE="0660"` fallback for
systems without it — still narrower than `0666`.

## Manual install, without the script

```bash
sudo install -m 0644 packaging/99-m711pro.rules /etc/udev/rules.d/99-m711pro.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

sudo install -m 0644 packaging/open-m711pro.desktop /usr/share/applications/open-m711pro.desktop
```

For a per-user menu entry instead, drop the `.desktop` file into
`~/.local/share/applications/`. The udev rule always needs root.

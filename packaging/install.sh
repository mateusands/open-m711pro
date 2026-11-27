#!/bin/sh
#
# open-m711pro — system integration installer.
#
# Installs two files and nothing else:
#   /etc/udev/rules.d/99-m711pro.rules      device access for the logged-in user
#   /usr/share/applications/open-m711pro.desktop   application menu entry
#
# It does NOT install the Python package; use pip for that (see packaging/README.md).
#
# Usage:
#   sudo sh packaging/install.sh
#   sudo sh packaging/install.sh --uninstall
#
set -eu

UDEV_RULE_NAME="99-m711pro.rules"
DESKTOP_NAME="open-m711pro.desktop"

UDEV_RULE_DIR="/etc/udev/rules.d"
DESKTOP_DIR="/usr/share/applications"

UDEV_RULE_DEST="$UDEV_RULE_DIR/$UDEV_RULE_NAME"
DESKTOP_DEST="$DESKTOP_DIR/$DESKTOP_NAME"

# Directory holding this script, so it works from anywhere. The two files live
# inside the Python package (m711pro/data/) so pip installs carry them too.
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname -- "$SRC_DIR")
DATA_DIR="$REPO_DIR/m711pro/data"

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
open-m711pro system integration installer

  sudo sh $0              install the udev rule and the desktop entry
  sudo sh $0 --uninstall  remove exactly those two files
  sh $0 --help            this message

Files touched:
  $UDEV_RULE_DEST
  $DESKTOP_DEST
EOF
}

require_root() {
    # id -u is POSIX; 0 is root.
    if [ "$(id -u)" -ne 0 ]; then
        die "this needs root to write to /etc and /usr/share — re-run with sudo"
    fi
}

# install_file <source> <destination>
# Idempotent: identical content is left alone, and mode is always normalised.
install_file() {
    src=$1
    dest=$2
    [ -f "$src" ] || die "missing source file: $src"
    if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
        say "  unchanged  $dest"
        return 0
    fi
    if [ -f "$dest" ]; then
        say "  updating   $dest"
    else
        say "  installing $dest"
    fi
    install -D -m 0644 "$src" "$dest"
}

# remove_file <path> — removes one named file, never a directory, never a glob.
remove_file() {
    dest=$1
    if [ -f "$dest" ]; then
        say "  removing   $dest"
        rm -f "$dest"
    else
        say "  absent     $dest"
    fi
}

reload_udev() {
    if ! command -v udevadm >/dev/null 2>&1; then
        say "  udevadm not found — reload udev yourself, or replug the mouse"
        return 0
    fi
    say "  reloading udev rules"
    udevadm control --reload-rules
    say "  triggering hidraw subsystem"
    # Scoped to hidraw: no reason to re-trigger every device on the system.
    udevadm trigger --subsystem-match=hidraw
}

refresh_desktop_db() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        say "  refreshing the desktop database"
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
}

do_install() {
    require_root
    say "open-m711pro: installing system integration"

    say "udev rule:"
    install_file "$DATA_DIR/$UDEV_RULE_NAME" "$UDEV_RULE_DEST"
    reload_udev

    say "desktop entry:"
    # The entry runs main.py from this checkout, which works whether or not the
    # package was pip-installed: the README's per-distribution steps never run
    # pip, and an entry pointing at 'open-m711pro-gui' did nothing for them.
    entry=$(mktemp)
    trap 'rm -f "$entry"' EXIT
    # escape what sed's replacement treats specially (& and the | delimiter)
    repo_esc=$(printf '%s' "$REPO_DIR" | sed 's/[&|\\]/\\&/g')
    sed "s|^Exec=.*|Exec=python3 \"$repo_esc/main.py\"|" \
        "$DATA_DIR/$DESKTOP_NAME" > "$entry"
    if command -v desktop-file-validate >/dev/null 2>&1; then
        if ! desktop-file-validate "$entry"; then
            die "the .desktop file failed validation; nothing was installed"
        fi
    fi
    install_file "$entry" "$DESKTOP_DEST"
    refresh_desktop_db

    say ""
    say "Done. Replug the mouse (or the 2.4G dongle) so the new rule applies."
    say "The menu entry runs $REPO_DIR/main.py — keep this checkout where it is."
}

do_uninstall() {
    require_root
    say "open-m711pro: removing system integration"

    say "udev rule:"
    remove_file "$UDEV_RULE_DEST"
    reload_udev

    say "desktop entry:"
    remove_file "$DESKTOP_DEST"
    refresh_desktop_db

    say ""
    say "Done. The Python package is untouched; remove it with:"
    say "  pipx uninstall open-m711pro"
}

case "${1-}" in
    ""|--install)   do_install ;;
    --uninstall)    do_uninstall ;;
    -h|--help)      usage ;;
    *)              usage >&2; die "unknown option: $1" ;;
esac

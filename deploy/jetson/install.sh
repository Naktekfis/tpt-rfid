#!/usr/bin/env bash
# Bring up tpt-rfid on the Jetson Nano (JetPack 4.6.x, Ubuntu 18.04).
#
# Run from the repo checkout on the device, as the kiosk user (not root):
#   deploy/jetson/install.sh            # install
#   DRY_RUN=1 deploy/jetson/install.sh  # print commands, render files to build/
#
# Env overrides: TPT_RFID_BIND (default 127.0.0.1:5000; 0.0.0.0:5000 opens
# the admin pages to the LAN), PYTHON (default python3.8).
#
# Idempotent: safe to run again after a git pull.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="$APP_DIR/deploy/jetson"
APP_USER="$(id -un)"
BIND="${TPT_RFID_BIND:-127.0.0.1:5000}"
PYTHON="${PYTHON:-python3.8}"
DRY_RUN="${DRY_RUN:-0}"
OUT="$APP_DIR/build/jetson-dry-run"

step() { printf '\n==> %s\n' "$*"; }
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '+ %s\n' "$*"
    else
        "$@"
    fi
}

render() { # render <template> <dest>: fill @USER@ @APP_DIR@ @BIND@
    local tmp
    tmp="$(mktemp)"
    sed -e "s|@USER@|$APP_USER|g" -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@BIND@|$BIND|g" "$1" > "$tmp"
    if [ "$DRY_RUN" = 1 ]; then
        mkdir -p "$OUT"
        mv "$tmp" "$OUT/$(basename "$2")"
        printf '+ install %s -> %s (rendered: %s)\n' "$1" "$2" "$OUT/$(basename "$2")"
    else
        sudo install -m 0644 "$tmp" "$2"
        rm -f "$tmp"
    fi
}

if [ "$(id -u)" = 0 ]; then
    echo "Run as the kiosk user, not root (sudo is used where needed)." >&2
    exit 1
fi
if [ "$(uname -m)" != aarch64 ]; then
    echo "Warning: not aarch64 ($(uname -m)); this script targets the Jetson Nano." >&2
fi

step "System packages"
run sudo apt-get update
run sudo apt-get install -y "$PYTHON" "$PYTHON-venv" "$PYTHON-dev" curl unclutter

step "Python venv (.venv, $PYTHON)"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    run "$PYTHON" -m venv "$APP_DIR/.venv"
fi
# 18.04's venv pip is too old for manylinux2014 aarch64 wheels; pip 25.1+ drops 3.8.
run "$APP_DIR/.venv/bin/pip" install --upgrade "pip<25.1" wheel
run "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/requirements-cv.txt"

step "NFC reader dependencies (PN532 I2C)"
run "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements-nfc.txt"

step ".env"
if [ -f "$APP_DIR/.env" ]; then
    echo ".env exists; not touching it. Make sure it has FLASK_ENV=production,"
    echo "RFID_READER_ENABLED=true, RFID_READER_PORT=/dev/rfid-reader,"
    echo "NFC_READER_ENABLED=true, CAMERA_ENABLED=true and no postgresql DATABASE_URL."
elif [ "$DRY_RUN" = 1 ]; then
    echo "+ create .env (FLASK_ENV=production, new SECRET_KEY, reader on /dev/rfid-reader, camera on)"
else
    secret="$("$APP_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
    umask 077
    cat > "$APP_DIR/.env" <<EOF
FLASK_ENV=production
SECRET_KEY=$secret
RFID_READER_ENABLED=true
RFID_READER_PORT=/dev/rfid-reader
NFC_READER_ENABLED=true
CAMERA_ENABLED=true
CAMERA_INDEX=0
EOF
    umask 022
    echo "Created .env (mode 600). Add MAIL_* settings by hand if email is needed."
fi

step "Admin PIN"
if [ -f "$APP_DIR/.env" ] && grep -q '^ADMIN_PIN_HASH=' "$APP_DIR/.env"; then
    echo "ADMIN_PIN_HASH already set (change it with scripts/set_admin_pin.py)."
else
    echo "Using the default admin PIN 133133 (change it with scripts/set_admin_pin.py)."
fi

step "Reader and camera access (dialout/video groups, udev rule -> /dev/rfid-reader)"
# brltty claims the reader's CH340 bridge (1a86:7523) and the tty disappears.
if dpkg-query -W -f='${Status}' brltty 2>/dev/null | grep -q 'ok installed'; then
    run sudo apt-get remove -y brltty
fi
if ! id -nG "$APP_USER" | tr ' ' '\n' | grep -qx dialout; then
    run sudo usermod -aG dialout "$APP_USER"
    echo "$APP_USER joins dialout at next login (the service gets it via SupplementaryGroups)."
fi
if ! id -nG "$APP_USER" | tr ' ' '\n' | grep -qx video; then
    run sudo usermod -aG video "$APP_USER"
    echo "$APP_USER joins video (USB webcam) at next login."
fi
for access_group in i2c gpio; do
    if getent group "$access_group" >/dev/null; then
        run sudo usermod -aG "$access_group" "$APP_USER"
    else
        echo "Missing $access_group group: install Jetson I2C/GPIO access rules before enabling NFC."
    fi
done
render "$HERE/99-tpt-rfid-reader.rules" /etc/udev/rules.d/99-tpt-rfid-reader.rules
run sudo udevadm control --reload-rules
run sudo udevadm trigger --subsystem-match=tty

step "systemd: app service and daily backup"
render "$HERE/tpt-rfid.service" /etc/systemd/system/tpt-rfid.service
render "$HERE/tpt-rfid-backup.service" /etc/systemd/system/tpt-rfid-backup.service
render "$HERE/tpt-rfid-backup.timer" /etc/systemd/system/tpt-rfid-backup.timer
run sudo systemctl daemon-reload
run sudo systemctl enable tpt-rfid.service tpt-rfid-backup.timer
run sudo systemctl restart tpt-rfid.service
run sudo systemctl start tpt-rfid-backup.timer

step "Kiosk browser autostart"
autostart="$HOME/.config/autostart/tpt-rfid-kiosk.desktop"
if [ "$DRY_RUN" = 1 ]; then
    mkdir -p "$OUT"
    sed -e "s|@APP_DIR@|$APP_DIR|g" "$HERE/tpt-rfid-kiosk.desktop" > "$OUT/tpt-rfid-kiosk.desktop"
    echo "+ install kiosk autostart -> $autostart (rendered: $OUT/tpt-rfid-kiosk.desktop)"
else
    mkdir -p "$(dirname "$autostart")"
    sed -e "s|@APP_DIR@|$APP_DIR|g" "$HERE/tpt-rfid-kiosk.desktop" > "$autostart"
fi
if ! command -v chromium-browser >/dev/null && ! command -v chromium >/dev/null \
    && ! command -v firefox >/dev/null; then
    echo "Warning: no chromium-browser/chromium/firefox found; kiosk.sh needs one." >&2
fi

step "Done"
cat <<EOF
Check:
  systemctl status tpt-rfid --no-pager
  journalctl -u tpt-rfid -n 50 --no-pager
  curl -s http://${BIND/0.0.0.0/127.0.0.1}/api/rfid/status
  ls -l /dev/rfid-reader /dev/video0
  curl -s http://${BIND/0.0.0.0/127.0.0.1}/api/devices/status
Sample data (optional): .venv/bin/python seed_database.py
Log out and in again (dialout group, kiosk autostart), or reboot.
EOF

#!/usr/bin/env bash
# Open the app full-screen once the local server answers.
# Started from ~/.config/autostart/tpt-rfid-kiosk.desktop at desktop login.
set -u

URL="${TPT_RFID_URL:-http://127.0.0.1:5000}"

# Wait up to ~2 minutes for gunicorn (first boot on microSD is slow).
for _ in $(seq 1 120); do
    if curl -fs -o /dev/null "$URL"; then
        break
    fi
    sleep 1
done

# No screen blanking or power saving.
xset s off || true
xset -dpms || true
xset s noblank || true

# Hide the mouse cursor if unclutter is installed.
if command -v unclutter >/dev/null; then
    unclutter -idle 0.5 -root &
fi

for browser in chromium-browser chromium; do
    if command -v "$browser" >/dev/null; then
        exec "$browser" --kiosk --incognito --noerrdialogs --no-first-run \
            --disable-session-crashed-bubble --disable-infobars \
            --disable-translate --check-for-update-interval=31536000 "$URL"
    fi
done
if command -v firefox >/dev/null; then
    exec firefox --kiosk "$URL"
fi
echo "kiosk.sh: no chromium-browser, chromium or firefox found" >&2
exit 1

#!/usr/bin/env bash
# Development setup on a laptop: .venv, dependencies, .env.
# For the Jetson Nano use deploy/jetson/install.sh instead.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 8), "Python 3.8+ required"'

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv with $PYTHON"
    "$PYTHON" -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example (mock reader, SQLite in instance/)."
else
    echo ".env exists; left as is. Remove any postgresql DATABASE_URL to use SQLite."
fi

cat <<'MSG'

Done. Next:
  .venv/bin/python app.py              # http://localhost:5000
  .venv/bin/python seed_database.py    # optional sample data
  scripts/check.sh                     # ruff + tests
Optional extras: requirements-mqtt.txt (ESP32/MQTT), requirements-cv.txt (CV benchmark).
MSG

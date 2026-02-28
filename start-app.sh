#!/bin/bash
# TPT-RFID Quick Launcher
# For development/testing without systemd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run tpt-rfid-installer.sh first"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please run tpt-rfid-installer.sh first"
    exit 1
fi

# Activate venv
source venv/bin/activate

# Check which branch
CURRENT_BRANCH=$(git branch --show-current)

clear
echo "╔════════════════════════════════════════════════╗"
echo "║        TPT-RFID Application Launcher           ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "Branch:      $CURRENT_BRANCH"
echo "Directory:   $SCRIPT_DIR"
echo "Python:      $(which python)"
echo ""
echo "Starting Flask development server..."
echo "Press Ctrl+C to stop"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Load .env and run Flask
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=1

# Run with Flask development server (auto-reload enabled)
python app.py

# Alternative: Use gunicorn for production-like testing
# gunicorn --workers 1 --threads 2 --bind 0.0.0.0:5000 --reload app:app

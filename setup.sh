#!/bin/bash
# Quick Setup Script for RFID Workshop Tool System
# Run this after cloning the repository
#
# Prerequisites: Python 3.8+, PostgreSQL installed and running,
#                database 'tpt_rfid' and a PostgreSQL role already created.
# See README.md for full instructions.

set -e

echo "================================================"
echo " RFID Workshop Tool System - Quick Setup"
echo "================================================"
echo ""

# Check Python version
echo "[1/6] Checking Python version..."
python3 --version || { echo "ERROR: Python 3 not found. Install it first."; exit 1; }

# Create virtual environment
echo ""
echo "[2/6] Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo ""
echo "[3/6] Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "[4/6] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if not exists
echo ""
echo "[5/6] Checking .env configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from template."
    echo "  IMPORTANT: Edit .env and set DATABASE_URL with your PostgreSQL credentials."
    echo "  Example:   DATABASE_URL=postgresql://youruser:yourpassword@localhost/tpt_rfid"
else
    echo "  .env already exists, skipping."
fi

# Run database migration
echo ""
echo "[6/6] Running database migration..."
if [ -d "migrations" ]; then
    flask db upgrade
    echo "  Database tables created/updated."
else
    flask db init
    flask db migrate -m "initial"
    flask db upgrade
    echo "  Migration initialized and applied."
fi

echo ""
echo "================================================"
echo " Setup complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env and set DATABASE_URL, SECRET_KEY, ADMIN_PIN"
echo "  2. (Optional) Seed sample data:  python seed_database.py"
echo "  3. Run the application:          python app.py"
echo "  4. Open browser:                 http://localhost:5000"
echo ""
echo "For development (mock RFID), open browser console (F12) and run:"
echo "  simulateRFID('STUDENT001')   // scan student card"
echo "  simulateRFID('TOOL001')      // scan tool tag"
echo ""

#!/bin/bash
# Quick Setup Script for RFID Workshop Tool System
# Run this after cloning the repository

echo "🚀 RFID Workshop Tool System - Quick Setup"
echo "==========================================="
echo ""

# Check Python version
echo "📝 Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "🔧 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo ""
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if not exists
if [ ! -f .env ]; then
    echo ""
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your configuration!"
fi

# Check for Firebase credentials
if [ ! -f serviceAccountKey.json ]; then
    echo ""
    echo "⚠️  Firebase credentials not found!"
    echo "Please download serviceAccountKey.json from Firebase Console"
    echo "and place it in the project root directory."
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure .env with your settings"
echo "2. Add serviceAccountKey.json from Firebase Console"
echo "3. Run the application: python app.py"
echo ""
echo "For development with mock RFID:"
echo "- Visit http://localhost:5000"
echo "- Use console command: simulateRFID('UID123')"
echo "- Or visit: http://localhost:5000/debug/scan?uid=UID123"
echo ""

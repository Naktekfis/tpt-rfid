#!/bin/bash
# TPT-RFID One-Time Complete Installer
# Run once, auto-start setup
# Compatible with Raspberry Pi and standard Linux (Ubuntu/Debian)

set -e  # Exit on error

# Detect User
CURRENT_USER=$(whoami)
USER_HOME=$HOME

if [ "$CURRENT_USER" = "root" ]; then
    echo "Error: Please run this script as a normal user, not root/sudo."
    echo "Usage: ./tpt-rfid-installer.sh"
    exit 1
fi

clear
echo "╔════════════════════════════════════════════════╗"
echo "║   TPT-RFID Lab Fabrikasi ITB - AUTO INSTALLER  ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "Installing for user: $CURRENT_USER"
echo "Home directory:      $USER_HOME"
echo ""
echo "This will install everything automatically."
echo "Estimated time: 30-45 minutes"
echo ""
read -p "Press ENTER to start or Ctrl+C to cancel..."

# ===================================
# 1. SYSTEM UPDATE
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1/8: Updating system packages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo apt update
sudo apt upgrade -y

# ===================================
# 2. INSTALL DEPENDENCIES
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/8: Installing dependencies..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    postgresql \
    postgresql-contrib \
    chromium-browser \
    x11-xserver-utils \
    unclutter

# ===================================
# 3. SETUP POSTGRESQL
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/8: Setting up PostgreSQL..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Generate random password for PostgreSQL
DB_PASSWORD=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-20)

# Create database and user
sudo -u postgres psql << EOF
-- Drop if exists (untuk re-run)
DROP DATABASE IF EXISTS tpt_rfid;
DROP ROLE IF EXISTS "$CURRENT_USER";

-- Create new
CREATE ROLE "$CURRENT_USER" WITH LOGIN PASSWORD '$DB_PASSWORD';
CREATE DATABASE tpt_rfid OWNER "$CURRENT_USER";
GRANT ALL PRIVILEGES ON DATABASE tpt_rfid TO "$CURRENT_USER";
EOF

echo "✓ PostgreSQL setup complete"

# ===================================
# 4. CLONE REPOSITORY
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4/8: Cloning TPT-RFID repository..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$USER_HOME"
if [ -d "tpt-rfid" ]; then
    echo "⚠ Directory exists, pulling latest changes..."
    cd tpt-rfid
    git pull
else
    git clone https://github.com/Naktekfis/tpt-rfid.git
    cd tpt-rfid
fi

# ===================================
# 5. PYTHON ENVIRONMENT
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5/8: Setting up Python environment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove existing venv if it exists (clean slate)
if [ -d "venv" ]; then
    rm -rf venv
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ===================================
# 6. CONFIGURE ENVIRONMENT
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6/8: Configuring environment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Generate SECRET_KEY
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Generate ADMIN_PIN
ADMIN_PIN=$(python3 -c "import secrets; print(secrets.token_urlsafe(8))")

# Create .env file
cat > .env << EOF
FLASK_ENV=production
DEBUG=False
SECRET_KEY=$SECRET_KEY
DATABASE_URL=postgresql://$CURRENT_USER:$DB_PASSWORD@localhost/tpt_rfid
ADMIN_PIN=$ADMIN_PIN

# Email (optional - configure later if needed)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=
EOF

chmod 600 .env

echo "✓ Environment configured"
echo ""
echo "📝 Your credentials (SAVE THIS!):"
echo "   DATABASE_URL: postgresql://$CURRENT_USER:$DB_PASSWORD@localhost/tpt_rfid"
echo "   ADMIN_PIN: $ADMIN_PIN"
echo ""

# Save credentials to file
cat > "$USER_HOME/tpt-rfid-credentials.txt" << EOF
TPT-RFID Credentials
Generated: $(date)
User: $CURRENT_USER

Database Password: $DB_PASSWORD
Admin PIN: $ADMIN_PIN
Secret Key: $SECRET_KEY

Full Database URL:
postgresql://$CURRENT_USER:$DB_PASSWORD@localhost/tpt_rfid

Access admin panel at: http://localhost:5000/admin
EOF

chmod 600 "$USER_HOME/tpt-rfid-credentials.txt"
echo "✓ Credentials saved to $USER_HOME/tpt-rfid-credentials.txt"

# ===================================
# 7. DATABASE MIGRATION
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7/8: Initializing database..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if migrations exist
if [ ! -d "migrations" ]; then
    flask db init
    flask db migrate -m "initial migration"
fi

flask db upgrade

# Seed sample data
echo ""
read -p "Do you want to add sample data for testing? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python seed_database.py
    echo "✓ Sample data added"
fi

# ===================================
# 8. SYSTEMD SERVICE
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 8/8: Setting up auto-start service..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sudo tee /etc/systemd/system/tpt-rfid.service > /dev/null << EOF
[Unit]
Description=TPT RFID Tool Monitoring System
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=$CURRENT_USER
WorkingDirectory=$USER_HOME/tpt-rfid
Environment="PATH=$USER_HOME/tpt-rfid/venv/bin"
ExecStart=$USER_HOME/tpt-rfid/venv/bin/gunicorn \\
    --workers 1 \\
    --threads 2 \\
    --timeout 60 \\
    --bind 0.0.0.0:5000 \\
    app:app
Restart=no
# RestartSec=5  <-- Disabled to prevent auto-restart loop

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tpt-rfid
sudo systemctl start tpt-rfid

# ===================================
# 9. KIOSK MODE SETUP
# ===================================
echo ""
read -p "Setup kiosk mode (auto-open browser on boot)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Setting up kiosk mode..."
    
    # Create autostart directory
    mkdir -p "$USER_HOME/.config/autostart"
    
    # Kiosk launcher
    cat > "$USER_HOME/.config/autostart/tpt-rfid-kiosk.desktop" << EOF
[Desktop Entry]
Type=Application
Name=TPT RFID Kiosk
Exec=$USER_HOME/tpt-rfid-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF
    
    # Kiosk script
    cat > "$USER_HOME/tpt-rfid-kiosk.sh" << EOF
#!/bin/bash
# Wait for service to be ready
sleep 10

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor
unclutter -idle 0.1 &

# Launch Chromium in kiosk mode
chromium-browser \\
    --kiosk \\
    --disable-restore-session-state \\
    --disable-session-crashed-bubble \\
    --disable-infobars \\
    --noerrdialogs \\
    --no-first-run \\
    http://localhost:5000
EOF
    
    chmod +x "$USER_HOME/tpt-rfid-kiosk.sh"
    
    # Disable screen blanking in lightdm (Raspberry Pi specific)
    if [ -f /etc/lightdm/lightdm.conf ]; then
        if grep -q "Common instructions for LightDM display manager" /etc/lightdm/lightdm.conf; then
            echo "Configuring LightDM..."
             # Simplified approach: append if not exists, though sed is safer if we knew the exact structure
             # Using the user's sed command but making it safe
             sudo sed -i '/^\[Seat:\*\]/a xserver-command=X -s 0 -dpms' /etc/lightdm/lightdm.conf
        fi
    fi
    
    echo "✓ Kiosk mode configured"
fi

# ===================================
# DONE!
# ===================================
echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║          INSTALLATION COMPLETE! 🎉             ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "Service status:"
sudo systemctl status tpt-rfid --no-pager -l
echo ""
echo "═══════════════════════════════════════════════════"
echo "Next steps:"
echo "  1. Application URL: http://$(hostname -I | awk '{print $1}'):5000"
echo "  2. Credentials saved in: $USER_HOME/tpt-rfid-credentials.txt"
echo "  3. Reboot to activate kiosk mode: sudo reboot"
echo ""
echo "Commands:"
echo "  - View logs:     sudo journalctl -u tpt-rfid -f"
echo "  - Restart app:   sudo systemctl restart tpt-rfid"
echo "  - Stop app:      sudo systemctl stop tpt-rfid"
echo "═══════════════════════════════════════════════════"
echo ""
read -p "Press ENTER to finish..."

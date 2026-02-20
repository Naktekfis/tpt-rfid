#!/bin/bash
# Fix Mosquitto configuration - Remove duplicate directives

set -e

echo "Fixing Mosquitto configuration..."

# Backup original config
sudo cp /etc/mosquitto/conf.d/tpt-rfid.conf /etc/mosquitto/conf.d/tpt-rfid.conf.backup

# Create fixed config
sudo tee /etc/mosquitto/conf.d/tpt-rfid.conf > /dev/null <<'EOF'
# TPT-RFID Mosquitto Configuration
# Development environment - NO AUTHENTICATION
# WARNING: For production, enable authentication!

# MQTT over TCP (default port)
listener 1883
protocol mqtt
allow_anonymous true

# MQTT over WebSocket (for browser clients)
listener 8083
protocol websockets
allow_anonymous true

# Logging (stdout only - file logging already in main config)
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information

# Connection settings
max_connections -1
EOF

echo "Configuration fixed. Testing config..."
mosquitto -c /etc/mosquitto/mosquitto.conf -t

echo "Restarting Mosquitto service..."
sudo systemctl restart mosquitto

echo "Checking service status..."
sudo systemctl status mosquitto --no-pager

echo ""
echo "✅ Mosquitto configuration fixed and service restarted!"

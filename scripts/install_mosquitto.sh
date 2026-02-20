#!/bin/bash
################################################################################
# TPT-RFID Mosquitto MQTT Broker Installation Script
# Install and configure Mosquitto for development
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Mosquitto MQTT Broker Installation          ║${NC}"
echo -e "${CYAN}║   For TPT-RFID Development Environment        ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════╝${NC}"
echo ""

# Check if running on Ubuntu/Debian
if [ ! -f /etc/os-release ]; then
    echo -e "${RED}✗ Cannot detect OS. This script is for Ubuntu/Debian.${NC}"
    exit 1
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" ]] && [[ "$ID" != "debian" ]]; then
    echo -e "${YELLOW}⚠  Warning: This script is designed for Ubuntu/Debian.${NC}"
    echo -e "${YELLOW}   Your OS: $PRETTY_NAME${NC}"
    echo -e "${YELLOW}   Installation may not work as expected.${NC}"
    echo ""
    read -p "Continue anyway? (y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo -e "${RED}Installation cancelled${NC}"
        exit 0
    fi
fi

echo -e "${BLUE}Detected OS: ${NC}$PRETTY_NAME"
echo ""

# Check if mosquitto is already installed
if command -v mosquitto &> /dev/null; then
    MOSQUITTO_VERSION=$(mosquitto -h 2>&1 | head -1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
    echo -e "${YELLOW}⚠  Mosquitto is already installed (version $MOSQUITTO_VERSION)${NC}"
    echo ""
    read -p "Reinstall/reconfigure? (y/N): " REINSTALL
    if [[ ! "$REINSTALL" =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Skipping installation, will configure only${NC}"
        SKIP_INSTALL=true
    fi
fi

# Step 1: Update package index
if [ "$SKIP_INSTALL" != "true" ]; then
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  STEP 1: Updating Package Index${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""
    
    echo -e "${YELLOW}Running: sudo apt update${NC}"
    if sudo apt update > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Package index updated${NC}"
    else
        echo -e "${RED}✗ Failed to update package index${NC}"
        exit 1
    fi
    echo ""
    
    # Step 2: Install Mosquitto
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  STEP 2: Installing Mosquitto${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""
    
    echo -e "${YELLOW}Installing mosquitto and mosquitto-clients...${NC}"
    if sudo apt install -y mosquitto mosquitto-clients > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Mosquitto installed successfully${NC}"
    else
        echo -e "${RED}✗ Failed to install Mosquitto${NC}"
        exit 1
    fi
    echo ""
fi

# Check installation
MOSQUITTO_VERSION=$(mosquitto -h 2>&1 | head -1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
echo -e "${GREEN}Installed version: ${NC}$MOSQUITTO_VERSION"
echo ""

# Step 3: Create configuration
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 3: Configuring Mosquitto${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

CONFIG_DIR="/etc/mosquitto/conf.d"
CONFIG_FILE="$CONFIG_DIR/tpt-rfid.conf"

echo -e "${YELLOW}Creating configuration: $CONFIG_FILE${NC}"

# Create configuration file content
CONFIG_CONTENT="# TPT-RFID Mosquitto Configuration
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

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information

# Message persistence
persistence true
persistence_location /var/lib/mosquitto/

# Connection settings
max_connections -1
"

# Write configuration
echo "$CONFIG_CONTENT" | sudo tee "$CONFIG_FILE" > /dev/null

if [ -f "$CONFIG_FILE" ]; then
    echo -e "${GREEN}✓ Configuration file created${NC}"
    echo ""
    echo -e "${BLUE}Configuration details:${NC}"
    echo "  • MQTT Port: 1883 (TCP)"
    echo "  • WebSocket Port: 8083"
    echo "  • Authentication: Disabled (dev mode)"
    echo "  • Persistence: Enabled"
    echo ""
else
    echo -e "${RED}✗ Failed to create configuration file${NC}"
    exit 1
fi

# Step 4: Restart Mosquitto service
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 4: Starting Mosquitto Service${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Restarting Mosquitto service...${NC}"
if sudo systemctl restart mosquitto 2>&1; then
    echo -e "${GREEN}✓ Service restarted${NC}"
else
    echo -e "${RED}✗ Failed to restart service${NC}"
    echo -e "${YELLOW}Checking service status...${NC}"
    sudo systemctl status mosquitto --no-pager
    exit 1
fi

sleep 2

# Enable auto-start on boot
echo -e "${YELLOW}Enabling auto-start on boot...${NC}"
if sudo systemctl enable mosquitto > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Auto-start enabled${NC}"
else
    echo -e "${YELLOW}⚠  Could not enable auto-start${NC}"
fi
echo ""

# Step 5: Verify installation
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 5: Verifying Installation${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

# Check service status
echo -e "${YELLOW}Checking service status...${NC}"
if sudo systemctl is-active --quiet mosquitto; then
    echo -e "${GREEN}✓ Mosquitto service is running${NC}"
else
    echo -e "${RED}✗ Mosquitto service is not running${NC}"
    echo -e "${YELLOW}Checking logs...${NC}"
    sudo journalctl -u mosquitto -n 20 --no-pager
    exit 1
fi

# Check listening ports
echo ""
echo -e "${YELLOW}Checking listening ports...${NC}"
MQTT_PORT=$(sudo netstat -tulpn 2>/dev/null | grep mosquitto | grep ":1883" || echo "")
WS_PORT=$(sudo netstat -tulpn 2>/dev/null | grep mosquitto | grep ":8083" || echo "")

if [ -n "$MQTT_PORT" ]; then
    echo -e "${GREEN}✓ MQTT port 1883 listening${NC}"
else
    echo -e "${RED}✗ MQTT port 1883 not listening${NC}"
fi

if [ -n "$WS_PORT" ]; then
    echo -e "${GREEN}✓ WebSocket port 8083 listening${NC}"
else
    echo -e "${RED}✗ WebSocket port 8083 not listening${NC}"
fi

echo ""

# Show service info
echo -e "${BLUE}Service Information:${NC}"
sudo systemctl status mosquitto --no-pager | head -10

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Installation Complete!                        ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${GREEN}✓ Mosquitto MQTT broker installed and configured${NC}"
echo ""

echo -e "${BLUE}Connection Details:${NC}"
echo "  • MQTT Broker: localhost:1883"
echo "  • WebSocket: ws://localhost:8083"
echo "  • Authentication: None (development mode)"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Test MQTT: ${CYAN}./scripts/test_mqtt.sh${NC}"
echo "  2. View logs: ${CYAN}sudo journalctl -u mosquitto -f${NC}"
echo "  3. Stop service: ${CYAN}sudo systemctl stop mosquitto${NC}"
echo "  4. Start service: ${CYAN}sudo systemctl start mosquitto${NC}"
echo ""

echo -e "${YELLOW}⚠  Security Note:${NC}"
echo "  This is a DEVELOPMENT configuration with NO authentication."
echo "  For PRODUCTION deployment on Raspberry Pi, you MUST:"
echo "    • Enable authentication (username/password)"
echo "    • Configure firewall rules"
echo "    • Use SSL/TLS for encryption"
echo ""

echo -e "${GREEN}Installation script completed successfully!${NC}"

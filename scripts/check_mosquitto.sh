#!/bin/bash
# Restart Mosquitto and show detailed status

echo "=== Restarting Mosquitto Service ==="
sudo systemctl restart mosquitto
sleep 2

echo ""
echo "=== Service Status ==="
sudo systemctl status mosquitto --no-pager -l

echo ""
echo "=== Checking Ports ==="
ss -tlnp 2>/dev/null | grep -E ':(1883|8083)' || netstat -tlnp 2>/dev/null | grep -E ':(1883|8083)' || echo "No ports listening on 1883 or 8083"

echo ""
echo "=== Recent Logs ==="
sudo journalctl -u mosquitto -n 20 --no-pager

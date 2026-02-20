# MQTT Setup Guide - TPT-RFID System

Panduan lengkap setup Mosquitto MQTT broker untuk TPT-RFID system.

---

## Daftar Isi

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Testing](#testing)
6. [Security](#security)
7. [Troubleshooting](#troubleshooting)

---

## Overview

TPT-RFID menggunakan MQTT (Message Queuing Telemetry Transport) untuk komunikasi real-time antara ESP32 dan server Flask. Mosquitto adalah MQTT broker yang lightweight dan cocok untuk Raspberry Pi.

### Mengapa MQTT?

- **Lightweight** - Hemat bandwidth dan resource
- **Real-time** - Notifikasi instant saat RFID discan
- **Reliable** - QoS (Quality of Service) guarantee
- **Scalable** - Support multiple ESP32 clients
- **Event-driven** - Tidak perlu HTTP polling

### Architecture

```
ESP32 (Publisher)  →  Mosquitto Broker  →  Flask App (Subscriber)
                            ↓
                       Port 1883 (MQTT)
                       Port 8083 (WebSocket)
```

---

## Prerequisites

**OS yang didukung:**
- Ubuntu 20.04+
- Debian 11+
- Raspberry Pi OS (Bullseye/Bookworm)

**Requirements:**
- Root/sudo access
- Internet connection untuk download packages

---

## Installation

### Method 1: Automated Install (Recommended)

Kami menyediakan script installer otomatis:

```bash
cd /home/ahmad/tpt-rfid
sudo ./scripts/install_mosquitto.sh
```

Script akan:
1. Update apt package cache
2. Install `mosquitto` dan `mosquitto-clients`
3. Create configuration file di `/etc/mosquitto/conf.d/tpt-rfid.conf`
4. Restart Mosquitto service
5. Enable auto-start on boot
6. Verify ports listening

**Expected output:**
```
✓ Mosquitto installed successfully
✓ Configuration created
✓ Service restarted
✓ Port 1883 listening
✓ Port 8083 listening
```

### Method 2: Manual Install

Jika ingin install manual:

```bash
# 1. Update package list
sudo apt update

# 2. Install Mosquitto
sudo apt install mosquitto mosquitto-clients -y

# 3. Enable service
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# 4. Verify running
sudo systemctl status mosquitto
```

---

## Configuration

### Configuration File Location

Mosquitto main config: `/etc/mosquitto/mosquitto.conf`  
TPT-RFID custom config: `/etc/mosquitto/conf.d/tpt-rfid.conf`

### Development Configuration

File: `/etc/mosquitto/conf.d/tpt-rfid.conf`

```conf
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

# Logging (stdout only - file logging in main config)
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information

# Connection settings
max_connections -1
```

### Production Configuration (Recommended)

Untuk production, **WAJIB** enable authentication:

```conf
# TPT-RFID Mosquitto Configuration - PRODUCTION

# MQTT over TCP
listener 1883
protocol mqtt
allow_anonymous false
password_file /etc/mosquitto/passwd

# MQTT over WebSocket
listener 8083
protocol websockets
allow_anonymous false
password_file /etc/mosquitto/passwd

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice

# Security
max_connections 100
max_inflight_messages 20
max_queued_messages 100

# Persistence
persistence true
persistence_location /var/lib/mosquitto/
```

#### Create Password File

```bash
# Create password file with user
sudo mosquitto_passwd -c /etc/mosquitto/passwd tpt-rfid

# Add more users (without -c flag)
sudo mosquitto_passwd /etc/mosquitto/passwd esp32_user

# Restart Mosquitto
sudo systemctl restart mosquitto
```

#### Update .env untuk Production

```env
MQTT_ENABLED=true
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=tpt-rfid
MQTT_PASSWORD=your_secure_password
```

### Configuration Options Explained

| Option | Deskripsi | Nilai |
|--------|-----------|-------|
| `listener` | Port yang di-listen | `1883` (MQTT), `8083` (WS) |
| `protocol` | Protocol type | `mqtt` atau `websockets` |
| `allow_anonymous` | Allow tanpa auth | `true` (dev), `false` (prod) |
| `password_file` | File password users | `/etc/mosquitto/passwd` |
| `log_dest` | Destination logs | `stdout`, `file`, `syslog` |
| `persistence` | Simpan messages di disk | `true` (recommended) |
| `max_connections` | Max concurrent clients | `-1` (unlimited) atau angka |

---

## Testing

### Test 1: Service Status

```bash
# Check service running
sudo systemctl status mosquitto

# Should show:
# ● mosquitto.service - Mosquitto MQTT Broker
#      Active: active (running)
```

### Test 2: Port Listening

```bash
# Check ports
ss -tlnp | grep -E '1883|8083'

# Should show:
# LISTEN 0  100  0.0.0.0:1883  0.0.0.0:*  users:(("mosquitto",pid=...))
# LISTEN 0  4096       *:8083        *:*  users:(("mosquitto",pid=...))
```

### Test 3: Publish/Subscribe

**Terminal 1 - Subscriber:**
```bash
mosquitto_sub -h localhost -t 'test/topic' -v
```

**Terminal 2 - Publisher:**
```bash
mosquitto_pub -h localhost -t 'test/topic' -m 'Hello MQTT!'
```

Terminal 1 seharusnya menampilkan:
```
test/topic Hello MQTT!
```

### Test 4: RFID Topic Structure

Test dengan topic structure yang digunakan TPT-RFID:

```bash
# Subscribe to all topics
mosquitto_sub -h localhost -t '#' -v

# Publish RFID scan
mosquitto_pub -h localhost -t 'rfid/scan' -m '{"rfid_uid":"1234567890","reader_id":"esp32_01"}' -q 1

# Publish sensor data
mosquitto_pub -h localhost -t 'sensor/temperature' -m '{"value":25.5,"unit":"celsius"}' -q 0
```

### Test 5: Automated Test Suite

Gunakan script test kami:

```bash
cd /home/ahmad/tpt-rfid
./scripts/test_mqtt.sh
```

Script akan test:
- ✓ Service status
- ✓ Port listening (1883, 8083)
- ✓ Connection test
- ✓ Pub/sub functionality
- ✓ RFID topic structure
- ✓ WebSocket port

### Test 6: Integration with Flask App

```bash
# Terminal 1: Start Flask app with MQTT enabled
cd /home/ahmad/tpt-rfid
source venv/bin/activate
# Pastikan MQTT_ENABLED=true di .env
python app.py

# Terminal 2: Simulate ESP32 RFID scan
./scripts/test_mqtt_integration.py
```

Check Flask logs untuk:
```
MQTT client connected successfully
Subscribed to MQTT topics
MQTT RFID scan received: 1234567890 from esp32_01
Student identified: Ahmad Fauzi (NIM: 1234567890)
```

---

## Security

### Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Authentication | Disabled | **Enabled** |
| Anonymous | Allowed | **Denied** |
| Max Connections | Unlimited | Limited (100) |
| Logging | Stdout only | File + rotation |
| TLS/SSL | Not used | **Recommended** |

### Enable TLS/SSL (Advanced)

Untuk production dengan TLS encryption:

#### 1. Generate Self-Signed Certificate

```bash
# Create directory for certificates
sudo mkdir -p /etc/mosquitto/certs
cd /etc/mosquitto/certs

# Generate CA key
sudo openssl genrsa -out ca.key 2048

# Generate CA certificate
sudo openssl req -new -x509 -days 3650 -key ca.key -out ca.crt

# Generate server key
sudo openssl genrsa -out server.key 2048

# Generate server certificate request
sudo openssl req -new -key server.key -out server.csr

# Sign server certificate
sudo openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 3650

# Set permissions
sudo chown mosquitto:mosquitto /etc/mosquitto/certs/*
sudo chmod 600 /etc/mosquitto/certs/*.key
```

#### 2. Update Configuration

Edit `/etc/mosquitto/conf.d/tpt-rfid.conf`:

```conf
# MQTT with TLS
listener 8883
protocol mqtt
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
allow_anonymous false
password_file /etc/mosquitto/passwd

# WebSocket with TLS
listener 8084
protocol websockets
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
allow_anonymous false
password_file /etc/mosquitto/passwd
```

#### 3. Update .env

```env
MQTT_BROKER_PORT=8883
MQTT_USE_TLS=true
MQTT_CA_CERT=/etc/mosquitto/certs/ca.crt
```

### Firewall Configuration

Jika menggunakan `ufw`:

```bash
# Allow MQTT ports
sudo ufw allow 1883/tcp comment 'MQTT'
sudo ufw allow 8083/tcp comment 'MQTT WebSocket'

# For TLS
sudo ufw allow 8883/tcp comment 'MQTT TLS'
sudo ufw allow 8084/tcp comment 'MQTT WS TLS'

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

---

## Troubleshooting

### Service Tidak Start

**Symptom:** `systemctl status mosquitto` shows failed

**Solution:**
```bash
# Check logs
sudo journalctl -u mosquitto -n 50 --no-pager

# Common issues:
# 1. Config syntax error
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v

# 2. Permission issue
sudo chown -R mosquitto:mosquitto /var/log/mosquitto
sudo chown -R mosquitto:mosquitto /var/lib/mosquitto

# 3. Port already in use
sudo lsof -i :1883
sudo kill <PID>

# Restart
sudo systemctl restart mosquitto
```

### Connection Refused

**Symptom:** `mosquitto_sub` atau `mosquitto_pub` error "Connection refused"

**Solution:**
```bash
# 1. Check service running
sudo systemctl status mosquitto

# 2. Check port listening
ss -tlnp | grep 1883

# 3. Check firewall
sudo ufw status
sudo ufw allow 1883

# 4. Check config allows connections
cat /etc/mosquitto/conf.d/tpt-rfid.conf | grep listener
```

### Authentication Failed

**Symptom:** Error "Connection Refused: not authorized"

**Solution:**
```bash
# 1. Check password file exists
ls -la /etc/mosquitto/passwd

# 2. Recreate password
sudo mosquitto_passwd -c /etc/mosquitto/passwd username

# 3. Check config uses password file
grep password_file /etc/mosquitto/conf.d/tpt-rfid.conf

# 4. Restart service
sudo systemctl restart mosquitto
```

### High CPU Usage

**Symptom:** Mosquitto menggunakan CPU tinggi

**Solution:**
```bash
# 1. Check number of connections
mosquitto_sub -h localhost -t '$SYS/broker/clients/connected' -C 1

# 2. Limit max connections
# Edit /etc/mosquitto/conf.d/tpt-rfid.conf
max_connections 100

# 3. Check message rate
mosquitto_sub -h localhost -t '$SYS/broker/messages/received' -C 1

# 4. Enable message limits
max_inflight_messages 20
max_queued_messages 100
```

### Persistent Messages Lost

**Symptom:** Messages hilang setelah restart

**Solution:**
```bash
# 1. Check persistence enabled
grep persistence /etc/mosquitto/conf.d/tpt-rfid.conf

# 2. Check persistence location writable
ls -la /var/lib/mosquitto/
sudo chown -R mosquitto:mosquitto /var/lib/mosquitto/

# 3. Enable persistence
# Edit config:
persistence true
persistence_location /var/lib/mosquitto/

# 4. Restart
sudo systemctl restart mosquitto
```

### WebSocket Port Not Working

**Symptom:** Port 8083 tidak responding

**Solution:**
```bash
# 1. Check listener configured
grep 8083 /etc/mosquitto/conf.d/tpt-rfid.conf

# 2. Check port listening
ss -tlnp | grep 8083

# 3. Test WebSocket connection
# Install wscat
npm install -g wscat

# Test connection
wscat -c ws://localhost:8083

# 4. Check firewall
sudo ufw allow 8083
```

---

## Monitoring

### System Topics

Mosquitto menyediakan system topics untuk monitoring:

```bash
# Total clients connected
mosquitto_sub -h localhost -t '$SYS/broker/clients/connected' -C 1

# Total messages received
mosquitto_sub -h localhost -t '$SYS/broker/messages/received' -C 1

# Uptime
mosquitto_sub -h localhost -t '$SYS/broker/uptime' -C 1

# Subscribe to all system topics
mosquitto_sub -h localhost -t '$SYS/#' -v
```

### Log Monitoring

```bash
# Real-time logs
sudo journalctl -u mosquitto -f

# Last 100 lines
sudo journalctl -u mosquitto -n 100

# Logs for specific time
sudo journalctl -u mosquitto --since "1 hour ago"
```

### Performance Metrics

```bash
# Check memory usage
ps aux | grep mosquitto

# Check connections
netstat -an | grep 1883 | grep ESTABLISHED | wc -l

# Check disk usage (persistence)
du -sh /var/lib/mosquitto/
```

---

## Best Practices

1. **Gunakan authentication** - Jangan allow anonymous di production
2. **Enable persistence** - Agar messages tidak hilang saat restart
3. **Limit connections** - Set max_connections untuk prevent overload
4. **Monitor logs** - Setup log rotation dan monitoring
5. **Use QoS appropriately** - QoS 1 untuk critical messages, QoS 0 untuk sensor data
6. **Firewall rules** - Hanya allow port yang diperlukan
7. **Regular backups** - Backup `/var/lib/mosquitto/` dan config files
8. **Update regularly** - Keep Mosquitto updated untuk security patches

---

## References

- [Mosquitto Documentation](https://mosquitto.org/documentation/)
- [MQTT Protocol Specification](https://mqtt.org/)
- [Eclipse Mosquitto GitHub](https://github.com/eclipse/mosquitto)

---

**Next Steps:**
- [ESP32 Client Guide](ESP32_CLIENT_GUIDE.md) - Programming ESP32 untuk publish RFID scans
- [Deployment Guide](DEPLOYMENT.md) - Deploy ke Raspberry Pi production
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues dan solutions

# Troubleshooting Guide - TPT RFID System

Panduan lengkap troubleshooting untuk mengatasi masalah yang umum terjadi pada sistem TPT RFID.

## Daftar Isi

1. [Overview](#overview)
2. [PostgreSQL Issues](#postgresql-issues)
3. [Flask Application Issues](#flask-application-issues)
4. [MQTT & Mosquitto Issues](#mqtt--mosquitto-issues)
5. [ESP32 Client Issues](#esp32-client-issues)
6. [Hardware Issues](#hardware-issues)
7. [Network & Connectivity Issues](#network--connectivity-issues)
8. [Performance Issues](#performance-issues)
9. [Security & Authentication Issues](#security--authentication-issues)
10. [Common Error Messages](#common-error-messages)
11. [Debug Procedures](#debug-procedures)
12. [Log Analysis](#log-analysis)

---

## Overview

### Quick Diagnostic Commands

Gunakan command-command ini untuk diagnosa cepat:

```bash
# Check all service status
sudo systemctl status postgresql mosquitto tpt-rfid nginx

# Check network ports
sudo netstat -tlnp | grep -E "5432|1883|8083|5000|80|443"

# Check system resources
free -h
df -h
htop

# Check recent errors
sudo journalctl -p err -n 50

# Test web access
curl http://localhost
```

### Troubleshooting Workflow

```
1. Identify the Problem
   ├─ Which component is failing? (DB, MQTT, Flask, ESP32, Network)
   └─ What are the symptoms? (errors, slow, not responding)

2. Check Service Status
   ├─ Is the service running?
   ├─ Any error in logs?
   └─ Are dependencies running?

3. Verify Configuration
   ├─ Check .env file
   ├─ Check service configs
   └─ Check firewall rules

4. Test Connections
   ├─ Database connection
   ├─ MQTT connection
   └─ Network connectivity

5. Check Resources
   ├─ CPU usage
   ├─ Memory usage
   ├─ Disk space
   └─ Network bandwidth

6. Apply Fix
   ├─ Restart services
   ├─ Fix configuration
   └─ Update code/dependencies

7. Verify Solution
   └─ Re-test functionality
```

---

## PostgreSQL Issues

### Issue: Cannot Connect to Database

**Symptoms:**
- Flask app gagal start dengan error "could not connect to server"
- `psql` command timeout atau connection refused
- Error: `FATAL: password authentication failed`

**Diagnosis:**

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check if PostgreSQL is listening
sudo netstat -tlnp | grep 5432

# Try manual connection
psql -U tpt_rfid -d tpt_rfid_db -h localhost
```

**Solutions:**

#### Solution 1: PostgreSQL Not Running

```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Enable auto-start
sudo systemctl enable postgresql

# Check status
sudo systemctl status postgresql
```

#### Solution 2: Wrong Credentials

```bash
# Check DATABASE_URL in .env
grep DATABASE_URL /opt/tpt-rfid/.env

# Format should be:
# DATABASE_URL=postgresql://tpt_rfid:password@localhost:5432/tpt_rfid_db

# Reset password if needed
sudo -u postgres psql -c "ALTER USER tpt_rfid WITH PASSWORD 'new_password';"

# Update .env with new password
nano /opt/tpt-rfid/.env
```

#### Solution 3: Authentication Configuration Error

```bash
# Check pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Ensure this line exists:
# host    all    all    127.0.0.1/32    scram-sha-256

# Restart PostgreSQL
sudo systemctl restart postgresql
```

#### Solution 4: Database Doesn't Exist

```bash
# List databases
sudo -u postgres psql -c "\l"

# Create database if missing
sudo -u postgres psql << EOF
CREATE DATABASE tpt_rfid_db;
CREATE USER tpt_rfid WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE tpt_rfid_db TO tpt_rfid;
EOF
```

---

### Issue: Database Tables Not Found

**Symptoms:**
- Error: `relation "users" does not exist`
- Error: `no such table: transactions`
- Flask app starts tapi tidak bisa query data

**Diagnosis:**

```bash
# Check if tables exist
psql -U tpt_rfid -d tpt_rfid_db -h localhost -c "\dt"
```

**Solutions:**

#### Solution 1: Initialize Database

```bash
cd /opt/tpt-rfid
source venv/bin/activate

# Run database initialization
python3 << EOF
from app import app, db
with app.app_context():
    db.create_all()
    print("Database initialized!")
EOF

# Verify tables created
psql -U tpt_rfid -d tpt_rfid_db -h localhost -c "\dt"
```

#### Solution 2: Run Migrations (Jika pakai Flask-Migrate)

```bash
cd /opt/tpt-rfid
source venv/bin/activate

# Run migrations
flask db upgrade

# Check migration history
flask db current
```

---

### Issue: PostgreSQL Taking Too Much Memory

**Symptoms:**
- System slow/laggy
- Out of memory errors
- PostgreSQL using >50% RAM

**Diagnosis:**

```bash
# Check memory usage
free -h

# Check PostgreSQL processes
ps aux | grep postgres | head -10

# Check active connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
```

**Solutions:**

#### Solution 1: Tune PostgreSQL Configuration

```bash
sudo nano /etc/postgresql/*/main/postgresql.conf
```

For Raspberry Pi 4GB:
```conf
shared_buffers = 512MB          # Was: 1GB
effective_cache_size = 1536MB   # Was: 2GB
maintenance_work_mem = 64MB     # Was: 128MB
work_mem = 5MB                  # Was: 10MB
max_connections = 30            # Was: 50
```

```bash
sudo systemctl restart postgresql
```

#### Solution 2: Kill Idle Connections

```bash
# Find idle connections
sudo -u postgres psql << EOF
SELECT pid, usename, state, query_start 
FROM pg_stat_activity 
WHERE state = 'idle' 
AND query_start < NOW() - INTERVAL '10 minutes';
EOF

# Kill idle connections
sudo -u postgres psql << EOF
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND query_start < NOW() - INTERVAL '10 minutes';
EOF
```

---

### Issue: Database Corruption or Data Loss

**Symptoms:**
- Error: `invalid page header`
- Error: `could not read block`
- Data hilang atau tidak konsisten

**Diagnosis:**

```bash
# Check PostgreSQL logs
sudo tail -100 /var/log/postgresql/postgresql-*-main.log

# Check for corruption
sudo -u postgres psql tpt_rfid_db -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;"
```

**Solutions:**

#### Solution 1: Restore from Backup

```bash
# Stop application
sudo systemctl stop tpt-rfid

# Drop and recreate database
sudo -u postgres psql << EOF
DROP DATABASE tpt_rfid_db;
CREATE DATABASE tpt_rfid_db;
GRANT ALL PRIVILEGES ON DATABASE tpt_rfid_db TO tpt_rfid;
EOF

# Restore from backup
LATEST_BACKUP=$(ls -t /opt/backups/database/tpt_rfid_db_*.sql.gz | head -1)
echo "Restoring from: $LATEST_BACKUP"

PGPASSWORD='your_password' gunzip -c $LATEST_BACKUP | \
  psql -U tpt_rfid -h localhost -d tpt_rfid_db

# Start application
sudo systemctl start tpt-rfid
```

#### Solution 2: REINDEX Database

```bash
# Reindex all tables
sudo -u postgres psql tpt_rfid_db -c "REINDEX DATABASE tpt_rfid_db;"
```

---

## Flask Application Issues

### Issue: Flask App Won't Start

**Symptoms:**
- `systemctl status tpt-rfid` shows "failed"
- Error di journalctl
- Port 5000 tidak listening

**Diagnosis:**

```bash
# Check service status
sudo systemctl status tpt-rfid

# Check detailed logs
sudo journalctl -u tpt-rfid -n 100

# Try manual start untuk melihat error
cd /opt/tpt-rfid
source venv/bin/activate
python app.py
```

**Solutions:**

#### Solution 1: Missing Dependencies

```bash
cd /opt/tpt-rfid
source venv/bin/activate

# Reinstall all dependencies
pip install -r requirements.txt
pip install -r requirements-mqtt.txt
pip install gunicorn

# Verify
pip list | grep -E "flask|gunicorn|paho"
```

#### Solution 2: Permission Issues

```bash
# Check file ownership
ls -la /opt/tpt-rfid/

# Fix ownership jika salah
sudo chown -R pi:pi /opt/tpt-rfid

# Check log directory
sudo mkdir -p /var/log/tpt-rfid
sudo chown pi:pi /var/log/tpt-rfid
```

#### Solution 3: Port Already in Use

```bash
# Check what's using port 5000
sudo netstat -tlnp | grep 5000

# Kill process jika ada
sudo kill -9 <PID>

# Atau restart service
sudo systemctl restart tpt-rfid
```

#### Solution 4: Environment Variables Missing

```bash
# Check .env exists
ls -la /opt/tpt-rfid/.env

# Verify required vars
grep -E "SECRET_KEY|DATABASE_URL|MQTT" /opt/tpt-rfid/.env

# Copy from example jika missing
cp /opt/tpt-rfid/.env.example /opt/tpt-rfid/.env
nano /opt/tpt-rfid/.env
```

---

### Issue: Import Errors or Module Not Found

**Symptoms:**
- Error: `ModuleNotFoundError: No module named 'flask'`
- Error: `ImportError: cannot import name 'xxx'`

**Diagnosis:**

```bash
# Check Python version
python3 --version
which python3

# Check virtual environment
cd /opt/tpt-rfid
source venv/bin/activate
which python
# Should show: /opt/tpt-rfid/venv/bin/python

# Check installed packages
pip list
```

**Solutions:**

#### Solution 1: Virtual Environment Not Activated

```bash
# Activate venv
cd /opt/tpt-rfid
source venv/bin/activate

# Verify
which python
# Should be: /opt/tpt-rfid/venv/bin/python
```

#### Solution 2: Recreate Virtual Environment

```bash
cd /opt/tpt-rfid

# Remove old venv
rm -rf venv

# Create new venv
python3 -m venv venv
source venv/bin/activate

# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-mqtt.txt
pip install gunicorn

# Restart service
sudo systemctl restart tpt-rfid
```

#### Solution 3: System Python vs Venv Python

Check systemd service using correct Python:

```bash
sudo nano /etc/systemd/system/tpt-rfid.service

# Ensure ExecStart uses venv Python:
# ExecStart=/opt/tpt-rfid/venv/bin/gunicorn ...

sudo systemctl daemon-reload
sudo systemctl restart tpt-rfid
```

---

### Issue: Session Errors or Login Not Working

**Symptoms:**
- Error: `KeyError: 'user_id'`
- Login tidak persist (langsung logout lagi)
- Error: `The session is unavailable`

**Diagnosis:**

```bash
# Check SESSION_TYPE in .env
grep SESSION_TYPE /opt/tpt-rfid/.env

# Check session directory
ls -la /tmp/flask_session/
```

**Solutions:**

#### Solution 1: Session Directory Not Writable

```bash
# Create session directory
sudo mkdir -p /tmp/flask_session
sudo chown pi:pi /tmp/flask_session
sudo chmod 755 /tmp/flask_session

# Restart app
sudo systemctl restart tpt-rfid
```

#### Solution 2: SECRET_KEY Not Set or Changed

```bash
# Check SECRET_KEY
grep SECRET_KEY /opt/tpt-rfid/.env

# Generate new if missing
python3 -c "import secrets; print(secrets.token_hex(32))"

# Add to .env
nano /opt/tpt-rfid/.env
# SECRET_KEY=<generated_key>

# Restart
sudo systemctl restart tpt-rfid
```

**WARNING:** Changing SECRET_KEY akan logout semua users!

---

### Issue: Static Files Not Loading (CSS/JS)

**Symptoms:**
- Web page tampil tanpa styling
- 404 errors untuk `/static/...`
- Console errors di browser

**Diagnosis:**

```bash
# Check static directory exists
ls -la /opt/tpt-rfid/static/

# Check Nginx config
sudo nginx -t
grep static /etc/nginx/sites-available/tpt-rfid
```

**Solutions:**

#### Solution 1: Static Directory Missing

```bash
# Create static directory
mkdir -p /opt/tpt-rfid/static/{css,js,images}

# Set permissions
chown -R pi:pi /opt/tpt-rfid/static
```

#### Solution 2: Nginx Static Alias Wrong

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid

# Add/fix:
location /static {
    alias /opt/tpt-rfid/static;
    expires 30d;
}

sudo nginx -t
sudo systemctl reload nginx
```

#### Solution 3: Flask Not Serving Static in Dev Mode

```python
# In app.py, ensure:
app = Flask(__name__, static_folder='static', static_url_path='/static')
```

---

### Issue: 502 Bad Gateway (Nginx)

**Symptoms:**
- Browser shows "502 Bad Gateway"
- Nginx error log shows "connect() failed"

**Diagnosis:**

```bash
# Check if Flask app is running
sudo systemctl status tpt-rfid

# Check Flask listening on correct port
sudo netstat -tlnp | grep 5000

# Check Nginx error log
sudo tail -50 /var/log/nginx/tpt-rfid-error.log
```

**Solutions:**

#### Solution 1: Flask App Not Running

```bash
# Start Flask app
sudo systemctl start tpt-rfid

# Check status
sudo systemctl status tpt-rfid
```

#### Solution 2: Wrong Upstream in Nginx

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid

# Verify upstream block:
upstream tpt_rfid_app {
    server 127.0.0.1:5000 fail_timeout=0;
}

sudo nginx -t
sudo systemctl reload nginx
```

---

## MQTT & Mosquitto Issues

### Issue: Mosquitto Won't Start

**Symptoms:**
- `systemctl status mosquitto` shows "failed"
- Error: `Address already in use`
- Error: `Error: Unable to open config file`

**Diagnosis:**

```bash
# Check status
sudo systemctl status mosquitto

# Check logs
sudo tail -50 /var/log/mosquitto/mosquitto.log

# Try manual start
mosquitto -c /etc/mosquitto/conf.d/tpt-rfid.conf -v
```

**Solutions:**

#### Solution 1: Port Already in Use

```bash
# Check what's using port 1883
sudo netstat -tlnp | grep 1883

# Kill the process
sudo kill -9 <PID>

# Or if it's another Mosquitto instance
sudo killall mosquitto
sudo systemctl start mosquitto
```

#### Solution 2: Configuration Error

```bash
# Test config
mosquitto -c /etc/mosquitto/conf.d/tpt-rfid.conf -v

# Check config syntax
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf

# Common errors:
# - Typo in parameter name
# - Invalid value
# - Missing file (password_file, acl_file)
```

#### Solution 3: Permission Issues

```bash
# Check file permissions
ls -la /etc/mosquitto/conf.d/tpt-rfid.conf
ls -la /etc/mosquitto/passwd

# Fix ownership
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 600 /etc/mosquitto/passwd

# Fix log directory
sudo mkdir -p /var/log/mosquitto
sudo chown mosquitto:mosquitto /var/log/mosquitto

# Restart
sudo systemctl restart mosquitto
```

---

### Issue: MQTT Authentication Failed

**Symptoms:**
- ESP32 cannot connect
- Flask app error: "Connection refused: bad username or password"
- Error dalam Mosquitto log: `Bad socket read/write on client`

**Diagnosis:**

```bash
# Check password file exists
ls -la /etc/mosquitto/passwd

# Test authentication
mosquitto_pub -h localhost -p 1883 \
  -u tpt-rfid -P 'your_password' \
  -t test/topic -m "test"
```

**Solutions:**

#### Solution 1: Password File Missing or Wrong

```bash
# Recreate password file
sudo mosquitto_passwd -c /etc/mosquitto/passwd tpt-rfid
# Enter password when prompted

# Add ESP32 user
sudo mosquitto_passwd /etc/mosquitto/passwd esp32_client

# Set permissions
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 600 /etc/mosquitto/passwd

# Restart Mosquitto
sudo systemctl restart mosquitto
```

#### Solution 2: Wrong Password in Config

```bash
# Check .env
grep MQTT_PASSWORD /opt/tpt-rfid/.env

# Update jika salah
nano /opt/tpt-rfid/.env

# Restart Flask
sudo systemctl restart tpt-rfid
```

#### Solution 3: ACL Blocking Access

```bash
# Check ACL config
sudo nano /etc/mosquitto/acl.conf

# Ensure user has access to topics
# user tpt-rfid
# topic readwrite #

# Restart Mosquitto
sudo systemctl restart mosquitto
```

#### Solution 4: Anonymous Access Disabled

```bash
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf

# Ensure:
allow_anonymous false

# Jangan set ke true di production!
```

---

### Issue: MQTT Messages Not Received

**Symptoms:**
- ESP32 publish berhasil tapi Flask tidak receive
- Subscribe tidak dapat message
- WebSocket tidak update real-time

**Diagnosis:**

```bash
# Test publish/subscribe
# Terminal 1:
mosquitto_sub -h localhost -p 1883 -u tpt-rfid -P 'password' -t '#' -v

# Terminal 2:
mosquitto_pub -h localhost -p 1883 -u tpt-rfid -P 'password' -t test/topic -m "hello"

# Should see message in Terminal 1
```

**Solutions:**

#### Solution 1: Wrong Topic Names

```bash
# Check topic names match
# ESP32 publish to: rfid/scan
# Flask subscribe to: rfid/scan (case-sensitive!)

# Check Flask logs
sudo journalctl -u tpt-rfid -f | grep -i mqtt
```

#### Solution 2: QoS Mismatch

```bash
# Ensure QoS level match
# Publisher QoS >= Subscriber QoS

# In Flask (.env):
MQTT_QOS=1

# In ESP32 code:
client.publish("rfid/scan", payload, 1);  // QoS 1
```

#### Solution 3: Flask Not Subscribed

```bash
# Check Flask MQTT client logs
sudo journalctl -u tpt-rfid -n 100 | grep -i subscribe

# Should see: "Subscribed to topic: rfid/scan"
```

#### Solution 4: Mosquitto Max Connections Reached

```bash
# Check active connections
mosquitto_sub -h localhost -p 1883 -u tpt-rfid -P 'password' \
  -t '$SYS/broker/clients/connected' -C 1

# Increase max_connections if needed
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf
# max_connections 100

sudo systemctl restart mosquitto
```

---

### Issue: MQTT Broker Memory Leak

**Symptoms:**
- Mosquitto memory usage terus naik
- System slow setelah beberapa hari
- Error: `Out of memory`

**Diagnosis:**

```bash
# Check Mosquitto memory
ps aux | grep mosquitto

# Check message queue size
mosquitto_sub -h localhost -p 1883 -u tpt-rfid -P 'password' \
  -t '$SYS/broker/messages/stored' -C 1
```

**Solutions:**

#### Solution 1: Set Message Limits

```bash
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf

# Add:
max_queued_messages 1000
message_size_limit 1024  # 1KB max

sudo systemctl restart mosquitto
```

#### Solution 2: Disable Persistence (Jika tidak perlu)

```bash
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf

# Comment out atau set false:
# persistence false

sudo systemctl restart mosquitto
```

#### Solution 3: Restart Mosquitto Periodically

```bash
# Add to crontab
crontab -e
```

```cron
# Restart Mosquitto every week (Sunday 3 AM)
0 3 * * 0 sudo systemctl restart mosquitto
```

---

## ESP32 Client Issues

### Issue: ESP32 Cannot Connect to WiFi

**Symptoms:**
- ESP32 serial monitor shows "WiFi connection failed"
- LED blink pattern menunjukkan no connection
- Timeout saat connecting

**Diagnosis:**

```cpp
// Check serial monitor output
Serial.begin(115200);
WiFi.begin(ssid, password);
while (WiFi.status() != WL_CONNECTED) {
  delay(500);
  Serial.print(".");
  Serial.println(WiFi.status());  // Debug WiFi status code
}
```

**Solutions:**

#### Solution 1: Wrong SSID/Password

```cpp
// Verify credentials
const char* ssid = "Your_WiFi_SSID";          // Case sensitive!
const char* password = "Your_WiFi_Password";  // Case sensitive!

// Re-upload code dengan credentials yang benar
```

#### Solution 2: WiFi Signal Too Weak

```bash
# Check signal strength
# On ESP32 serial monitor, add:
```

```cpp
long rssi = WiFi.RSSI();
Serial.print("Signal strength (RSSI): ");
Serial.println(rssi);
// Good: > -67 dBm
// Fair: -67 to -70 dBm
// Poor: < -70 dBm
```

**Fix:** Move ESP32 closer to router atau gunakan WiFi extender.

#### Solution 3: MAC Address Filtering

```cpp
// Get ESP32 MAC address
Serial.println(WiFi.macAddress());
// Example output: AA:BB:CC:DD:EE:FF

// Add MAC ke WiFi router's whitelist
```

#### Solution 4: ESP32 Power Issues

- **Symptom:** WiFi connects lalu disconnect berulang
- **Cause:** Insufficient power supply
- **Fix:** Gunakan power supply 5V 2A minimum, bukan dari USB laptop

---

### Issue: ESP32 Connected to WiFi but Cannot Connect to MQTT

**Symptoms:**
- WiFi connected (IP address obtained)
- MQTT connection failed atau timeout
- Error: `Connection refused`

**Diagnosis:**

```cpp
// Add debug dalam setup():
Serial.print("WiFi connected, IP: ");
Serial.println(WiFi.localIP());

Serial.print("Connecting to MQTT broker: ");
Serial.println(mqtt_server);

if (!client.connect("ESP32Client", mqtt_user, mqtt_password)) {
  Serial.print("Failed, rc=");
  Serial.println(client.state());
  // rc codes:
  // -4 = MQTT_CONNECTION_TIMEOUT
  // -3 = MQTT_CONNECTION_LOST
  // -2 = MQTT_CONNECT_FAILED
  // -1 = MQTT_DISCONNECTED
  //  0 = MQTT_CONNECTED
  //  1 = MQTT_CONNECT_BAD_PROTOCOL
  //  2 = MQTT_CONNECT_BAD_CLIENT_ID
  //  4 = MQTT_CONNECT_BAD_CREDENTIALS
  //  5 = MQTT_CONNECT_UNAUTHORIZED
}
```

**Solutions:**

#### Solution 1: Wrong MQTT Server Address

```cpp
// Verify server IP
const char* mqtt_server = "192.168.1.100";  // Raspberry Pi IP

// Test connectivity dari ESP32:
// Gunakan ping dari komputer lain di network
ping 192.168.1.100
```

#### Solution 2: MQTT Port Blocked by Firewall

```bash
# Di Raspberry Pi, check firewall
sudo ufw status

# Ensure port 1883 allowed dari local network
sudo ufw allow from 192.168.1.0/24 to any port 1883 proto tcp

# Test dari komputer lain
telnet 192.168.1.100 1883
# Should connect (blank screen = success, Ctrl+] then quit)
```

#### Solution 3: Wrong MQTT Credentials

```cpp
// Verify credentials match Mosquitto password file
const char* mqtt_user = "esp32_client";
const char* mqtt_password = "your_password";

// Check di Raspberry Pi:
sudo cat /etc/mosquitto/passwd
# Should have entry for esp32_client

// Test manually
mosquitto_pub -h 192.168.1.100 -p 1883 \
  -u esp32_client -P 'your_password' \
  -t test -m "test"
```

#### Solution 4: Mosquitto Not Running

```bash
# Di Raspberry Pi
sudo systemctl status mosquitto

# Start jika stopped
sudo systemctl start mosquitto
```

---

### Issue: RFID Reader Not Detecting Cards

**Symptoms:**
- ESP32 connected tapi tidak baca RFID
- Serial monitor tidak show card UID
- No LED indication saat tap card

**Diagnosis:**

```cpp
// Add dalam loop():
if (mfrc522.PICC_IsNewCardPresent()) {
  Serial.println("Card detected!");
} else {
  Serial.println("No card detected");
  delay(1000);
}
```

**Solutions:**

#### Solution 1: Wiring Issues

Verify wiring:

```
MFRC522 → ESP32
SDA  →  GPIO 21 (atau pin lain yang di-define)
SCK  →  GPIO 18
MOSI →  GPIO 23
MISO →  GPIO 19
RST  →  GPIO 22
3.3V →  3.3V (BUKAN 5V!)
GND  →  GND
```

**Check:**
- Semua kabel tersambung kencang (tidak kendor)
- Tidak ada short circuit
- MFRC522 powered dari 3.3V, BUKAN 5V!

#### Solution 2: Wrong SPI Pins

```cpp
// Verify pin definitions
#define SS_PIN 21
#define RST_PIN 22

MFRC522 mfrc522(SS_PIN, RST_PIN);

// Pastikan match dengan physical wiring!
```

#### Solution 3: MFRC522 Module Rusak

Test dengan kode minimal:

```cpp
#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN 21
#define RST_PIN 22

MFRC522 mfrc522(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("Scan a card...");
  mfrc522.PCD_DumpVersionToSerial();  // Should show version info
}

void loop() {
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    Serial.print("UID: ");
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      Serial.print(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " ");
      Serial.print(mfrc522.uid.uidByte[i], HEX);
    }
    Serial.println();
    mfrc522.PICC_HaltA();
  }
  delay(500);
}
```

Jika `PCD_DumpVersionToSerial()` tidak show anything, module rusak atau wiring salah.

#### Solution 4: RFID Card Too Far

- **Distance:** MFRC522 max range ~3-5 cm
- **Fix:** Dekatkan card ke reader
- **Note:** Metal surface di belakang reader bisa ganggu signal

---

### Issue: ESP32 Reboots Randomly

**Symptoms:**
- ESP32 restart sendiri
- Serial monitor shows `Guru Meditation Error` atau `Brownout detector`
- Watchdog timer reset

**Diagnosis:**

```cpp
// Check reset reason
#include "esp_system.h"

void setup() {
  Serial.begin(115200);
  
  esp_reset_reason_t reason = esp_reset_reason();
  Serial.print("Reset reason: ");
  Serial.println(reason);
  // 1 = POWERON_RESET
  // 3 = SW_RESET
  // 4 = OWDT_RESET (watchdog)
  // 5 = DEEPSLEEP_RESET
  // 6 = SDIO_RESET
  // 7 = TG0WDT_SYS_RESET (watchdog)
  // 8 = TG1WDT_SYS_RESET
  // 9 = RTCWDT_SYS_RESET
  // 10 = INTRUSION_RESET
  // 11 = TGWDT_CPU_RESET
  // 12 = SW_CPU_RESET
  // 13 = RTCWDT_CPU_RESET
  // 14 = EXT_CPU_RESET
  // 15 = RTCWDT_BROWN_OUT_RESET (power issue!)
  // 16 = RTCWDT_RTC_RESET
}
```

**Solutions:**

#### Solution 1: Power Supply Insufficient (Brownout)

- **Symptom:** Reset reason = 15 (RTCWDT_BROWN_OUT_RESET)
- **Cause:** Power supply drops below ~2.7V
- **Fix:**
  - Gunakan power supply 5V 2A minimum
  - Jangan power dari USB laptop
  - Tambahkan capacitor 100µF antara VIN dan GND (untuk stabilisasi)

#### Solution 2: Watchdog Timer Reset

```cpp
// Add watchdog feed in loop()
#include "esp_task_wdt.h"

void setup() {
  // Configure watchdog (10 seconds timeout)
  esp_task_wdt_init(10, true);
  esp_task_wdt_add(NULL);
}

void loop() {
  // Feed watchdog
  esp_task_wdt_reset();
  
  // Your code...
}
```

#### Solution 3: Memory Leak atau Stack Overflow

```cpp
// Check free heap
void loop() {
  Serial.print("Free heap: ");
  Serial.println(ESP.getFreeHeap());
  
  // Should be > 50000 bytes
  // Jika terus menurun = memory leak!
  
  delay(1000);
}
```

**Fix memory leak:**
- Hindari String concatenation berlebihan (gunakan char array)
- Free allocated memory dengan `delete` atau `free()`
- Reduce buffer sizes

---

## Hardware Issues

### Issue: Raspberry Pi Won't Boot

**Symptoms:**
- Power LED nyala tapi tidak ada display
- Rainbow screen
- Red LED blink pattern
- No HDMI output

**Diagnosis:**

**LED Patterns:**
- **Solid red, no green:** No power atau power insufficient
- **Green blink 4x:** start4.elf not found (SD card issue)
- **Green blink 7x:** Kernel image not found
- **Green blink 8x:** SDRAM failure
- **Rainbow screen:** GPU firmware issue

**Solutions:**

#### Solution 1: SD Card Corrupted

```bash
# Dari komputer lain:
# 1. Backup SD card jika possible
# 2. Re-flash Raspberry Pi OS menggunakan Raspberry Pi Imager
# 3. Restore data dari backup
```

#### Solution 2: Insufficient Power Supply

- **Symptom:** Rainbow screen, random reboots
- **Cause:** Power supply < 3A untuk Pi 4B
- **Fix:** Gunakan official 5V 3A USB-C power supply

#### Solution 3: Overclocking Too Aggressive

```bash
# Mount SD card di komputer lain
# Edit /boot/config.txt
# Comment out overclock settings:
# over_voltage=0
# arm_freq=1500

# Save dan boot Pi
```

---

### Issue: Touchscreen Not Working

**Symptoms:**
- Display tampil tapi touch tidak respond
- Touch terbalik (x/y inverted)
- Multi-touch tidak work

**Diagnosis:**

```bash
# Check if touchscreen detected
ls /dev/input/event*

# Test touch events
sudo evtest /dev/input/event0
# Tap screen, should show events
```

**Solutions:**

#### Solution 1: Touchscreen Not Connected Properly

- **Check:** Ribbon cable tersambung kencang ke Pi dan screen
- **Note:** Official touchscreen pakai separate power connector

#### Solution 2: Touch Rotation Wrong

```bash
sudo nano /boot/config.txt
```

Add:
```
# Rotate touch 180 degrees
dtoverlay=rpi-ft5406,touchscreen-swapped-x-y,touchscreen-inverted-x,touchscreen-inverted-y

# Atau rotate 90 degrees
# lcd_rotate=1
```

Reboot:
```bash
sudo reboot
```

#### Solution 3: Driver Not Loaded

```bash
# Check loaded modules
lsmod | grep ft5406

# Load manually jika tidak ada
sudo modprobe rpi_ft5406

# Add to /etc/modules untuk permanent
echo "rpi_ft5406" | sudo tee -a /etc/modules
```

---

### Issue: Overheating

**Symptoms:**
- Temperature > 80°C
- Throttling (CPU frequency drop)
- System slow/laggy
- Random crashes

**Diagnosis:**

```bash
# Check current temperature
vcgencmd measure_temp

# Check throttling status
vcgencmd get_throttled
# 0x0 = OK
# 0x50000 = Throttled due to undervoltage
# 0x50005 = Throttled due to undervoltage + currently throttled
```

**Solutions:**

#### Solution 1: Add Heatsink & Fan

- **Passive:** Aluminum heatsink on CPU (~Rp 50.000)
- **Active:** 5V fan (~Rp 30.000) connected to GPIO pins
  - Pin 4 (5V) → Fan +
  - Pin 6 (GND) → Fan -

#### Solution 2: Improve Airflow

- Jangan tutup case sepenuhnya
- Posisikan Pi vertikal untuk better airflow
- Jauhkan dari sumber panas lain

#### Solution 3: Reduce Load

```bash
# Disable GUI jika tidak pakai kiosk mode
sudo systemctl set-default multi-user.target
sudo reboot

# Reduce overclock (jika ada)
sudo nano /boot/config.txt
# Comment out overclock settings
```

---

## Network & Connectivity Issues

### Issue: Cannot Access Web UI from Other Devices

**Symptoms:**
- `curl http://localhost` works di Pi
- Browser dari komputer lain timeout atau connection refused
- Ping ke Pi berhasil tapi HTTP gagal

**Diagnosis:**

```bash
# Check if Nginx listening on 0.0.0.0 (all interfaces)
sudo netstat -tlnp | grep :80

# Should show: 0.0.0.0:80 (not 127.0.0.1:80)

# Check firewall
sudo ufw status | grep 80

# Test from another device
curl http://192.168.1.100
```

**Solutions:**

#### Solution 1: Nginx Not Listening on External Interface

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid

# Ensure listen directive:
listen 80;  # Not: listen 127.0.0.1:80;

sudo nginx -t
sudo systemctl reload nginx
```

#### Solution 2: Firewall Blocking HTTP

```bash
# Allow HTTP
sudo ufw allow 80/tcp

# Verify
sudo ufw status numbered
```

#### Solution 3: Wrong IP Address

```bash
# Get Pi's IP
hostname -I
ip addr show

# Update konfigurasi jika pakai static IP yang salah
sudo nano /etc/dhcpcd.conf
```

---

### Issue: SSH Connection Refused or Timeout

**Symptoms:**
- `ssh pi@192.168.1.100` timeout
- Connection refused
- Cannot remote access Pi

**Diagnosis:**

```bash
# Di Pi (via keyboard/monitor):
# Check SSH service
sudo systemctl status ssh

# Check if listening
sudo netstat -tlnp | grep :22

# From another device:
ping 192.168.1.100  # Should respond
telnet 192.168.1.100 22  # Should show SSH banner
```

**Solutions:**

#### Solution 1: SSH Service Not Running

```bash
# Start SSH
sudo systemctl start ssh
sudo systemctl enable ssh

# Verify
sudo systemctl status ssh
```

#### Solution 2: Firewall Blocking SSH

```bash
# Allow SSH (CRITICAL!)
sudo ufw allow 22/tcp

# Verify
sudo ufw status
```

#### Solution 3: Wrong IP Address

```bash
# Get correct IP
hostname -I

# Or check router DHCP leases

# Connect dengan IP yang benar
ssh pi@<correct_ip>
```

#### Solution 4: SSH Keys Mismatch

```bash
# Error: "Host key verification failed"

# On client (komputer Anda):
ssh-keygen -R 192.168.1.100

# Try connect lagi
ssh pi@192.168.1.100
```

---

### Issue: Network Drops or Unstable WiFi

**Symptoms:**
- WiFi disconnect-reconnect berulang
- Ping packet loss
- MQTT messages delayed atau hilang

**Diagnosis:**

```bash
# Check WiFi link quality
iwconfig wlan0

# Check signal strength
watch -n 1 iwconfig wlan0

# Check for errors
ifconfig wlan0
# Look for: errors, dropped, overruns
```

**Solutions:**

#### Solution 1: Disable WiFi Power Management

```bash
# Check current setting
iwconfig wlan0 | grep "Power Management"

# Disable power management
sudo iw wlan0 set power_save off

# Make permanent
sudo nano /etc/rc.local
# Add before "exit 0":
/sbin/iw wlan0 set power_save off

# Or use NetworkManager
sudo nano /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf
```

```ini
[connection]
wifi.powersave = 2
# 0 = use default, 1 = ignore, 2 = disable, 3 = enable
```

#### Solution 2: Use Ethernet Instead of WiFi

- More stable dan reliable untuk production
- Lower latency
- No interference issues

```bash
# Configure static IP for eth0
sudo nano /etc/dhcpcd.conf
```

```conf
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

#### Solution 3: Change WiFi Channel

- Router pada channel yang crowded bisa cause interference
- Gunakan WiFi analyzer app untuk find best channel
- Change router ke channel 1, 6, atau 11 (non-overlapping)

---

## Performance Issues

### Issue: Web UI Slow to Load

**Symptoms:**
- Pages take >5 seconds to load
- Timeout errors
- High CPU usage saat load page

**Diagnosis:**

```bash
# Check system resources
htop

# Check Nginx access log
tail -f /var/log/nginx/tpt-rfid-access.log

# Check Flask response time
curl -w "@-" -o /dev/null -s http://localhost << 'EOF'
    time_namelookup:  %{time_namelookup}\n
       time_connect:  %{time_connect}\n
    time_appconnect:  %{time_appconnect}\n
   time_pretransfer:  %{time_pretransfer}\n
      time_redirect:  %{time_redirect}\n
 time_starttransfer:  %{time_starttransfer}\n
                    ----------\n
         time_total:  %{time_total}\n
EOF
```

**Solutions:**

#### Solution 1: Increase Gunicorn Workers

```bash
sudo nano /etc/systemd/system/tpt-rfid.service

# Increase workers untuk Pi 4B
--workers 3 --threads 4

sudo systemctl daemon-reload
sudo systemctl restart tpt-rfid
```

#### Solution 2: Add Nginx Caching

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid
```

```nginx
# Add caching
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=tpt_cache:10m max_size=100m inactive=60m;

server {
    # ...
    location / {
        proxy_cache tpt_cache;
        proxy_cache_valid 200 1m;
        proxy_cache_bypass $http_pragma $http_authorization;
        proxy_pass http://tpt_rfid_app;
        # ...
    }
}
```

```bash
# Create cache directory
sudo mkdir -p /var/cache/nginx
sudo chown www-data:www-data /var/cache/nginx

sudo nginx -t
sudo systemctl reload nginx
```

#### Solution 3: Optimize Database Queries

```bash
# Add indexes
psql -U tpt_rfid -d tpt_rfid_db -h localhost << EOF
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
ANALYZE;
EOF
```

#### Solution 4: Use SSD Instead of SD Card

- SD card: ~20 MB/s read/write
- SSD: ~400 MB/s read/write
- Significantly faster database operations

---

### Issue: High CPU Usage

**Symptoms:**
- `htop` shows CPU 90-100%
- System laggy
- Temperature high

**Diagnosis:**

```bash
# Check top processes
htop
# Press F5 to tree view
# Press F6 to sort by CPU%

# Check which service
ps aux --sort=-%cpu | head -10

# Check for busy loops
sudo strace -p <PID> -c
```

**Solutions:**

#### Solution 1: Reduce Gunicorn Workers

```bash
# Pi 4B (4 cores) optimal: 2-3 workers
sudo nano /etc/systemd/system/tpt-rfid.service

--workers 2 --threads 4

sudo systemctl daemon-reload
sudo systemctl restart tpt-rfid
```

#### Solution 2: Optimize MQTT Message Processing

```python
# In mqtt_client.py, add throttling
import time

last_process_time = 0

def on_message(client, userdata, msg):
    global last_process_time
    current_time = time.time()
    
    # Process max 10 messages per second
    if current_time - last_process_time < 0.1:
        return
    
    last_process_time = current_time
    # Process message...
```

#### Solution 3: Disable Unnecessary Services

```bash
# List services
systemctl list-units --type=service --state=running

# Disable yang tidak perlu
sudo systemctl disable bluetooth.service
sudo systemctl stop bluetooth.service
```

---

### Issue: Database Queries Slow

**Symptoms:**
- Report generation timeout
- Transaction list loading >10 seconds
- PostgreSQL high CPU

**Diagnosis:**

```sql
-- Find slow queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
FROM pg_stat_activity 
WHERE (now() - pg_stat_activity.query_start) > interval '5 seconds'
ORDER BY duration DESC;

-- Check for missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public'
ORDER BY abs(correlation) DESC;

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Solutions:**

#### Solution 1: Add Indexes

```sql
-- Common indexes untuk TPT RFID
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_tool_id ON transactions(tool_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_date_range ON transactions(borrow_time, return_time);

-- Update statistics
ANALYZE transactions;
ANALYZE users;
ANALYZE tools;
```

#### Solution 2: Archive Old Data

```sql
-- Create archive table
CREATE TABLE transactions_archive (LIKE transactions INCLUDING ALL);

-- Move old transactions (>1 year)
INSERT INTO transactions_archive
SELECT * FROM transactions
WHERE borrow_time < NOW() - INTERVAL '1 year';

DELETE FROM transactions
WHERE borrow_time < NOW() - INTERVAL '1 year';

-- Vacuum
VACUUM FULL transactions;
```

#### Solution 3: Tune PostgreSQL for Pi

```bash
sudo nano /etc/postgresql/*/main/postgresql.conf
```

For SD card:
```conf
random_page_cost = 4.0
effective_io_concurrency = 2
```

For SSD:
```conf
random_page_cost = 1.1
effective_io_concurrency = 200
```

```bash
sudo systemctl restart postgresql
```

---

## Security & Authentication Issues

### Issue: Cannot Login (Wrong PIN)

**Symptoms:**
- Error: "Invalid PIN" atau "Access Denied"
- Sure PIN benar tapi tidak bisa login
- Tidak bisa akses halaman admin

**Diagnosis:**

```bash
# Check ADMIN_PIN in .env
grep ADMIN_PIN /opt/tpt-rfid/.env

# Check if .env is loaded
cd /opt/tpt-rfid
source venv/bin/activate
python3 -c "from config import Config; print(Config.ADMIN_PIN if hasattr(Config, 'ADMIN_PIN') else 'NOT SET')"
```

**Solutions:**

#### Solution 1: ADMIN_PIN Not Set in .env

```bash
# Add ADMIN_PIN to .env
nano /opt/tpt-rfid/.env

# Add this line:
ADMIN_PIN=your_secure_pin_here

# Restart application
sudo systemctl restart tpt-rfid
```

**SECURITY:** Jangan gunakan PIN default `133133` di production!

#### Solution 2: Wrong PIN Being Used

```bash
# Verify correct PIN
grep ADMIN_PIN /opt/tpt-rfid/.env

# Update jika salah
nano /opt/tpt-rfid/.env

# Restart app
sudo systemctl restart tpt-rfid
```

#### Solution 3: Environment File Not Loaded

```bash
# Check if .env exists and readable
ls -la /opt/tpt-rfid/.env

# Check systemd service loads .env
sudo systemctl cat tpt-rfid | grep -i env

# Verify environment in running process
sudo systemctl show tpt-rfid --property=Environment
```

---

### Issue: CSRF Token Missing or Invalid

**Symptoms:**
- Error: "The CSRF token is missing"
- Error: "The CSRF token is invalid"
- Forms tidak submit

**Diagnosis:**

```bash
# Check SECRET_KEY in .env
grep SECRET_KEY /opt/tpt-rfid/.env

# Check session working
curl -I http://localhost
# Should have Set-Cookie header
```

**Solutions:**

#### Solution 1: SECRET_KEY Missing

```bash
# Generate new secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Add to .env
nano /opt/tpt-rfid/.env
SECRET_KEY=<generated_key>

sudo systemctl restart tpt-rfid
```

#### Solution 2: Clear Browser Cookies

- Browser: Clear cookies for site
- Try incognito/private mode

---

## Common Error Messages

### `OperationalError: could not connect to server`

**Cause:** PostgreSQL not running atau wrong connection parameters

**Fix:**
```bash
sudo systemctl start postgresql
grep DATABASE_URL /opt/tpt-rfid/.env
```

---

### `ModuleNotFoundError: No module named 'flask'`

**Cause:** Virtual environment not activated atau dependencies not installed

**Fix:**
```bash
cd /opt/tpt-rfid
source venv/bin/activate
pip install -r requirements.txt
```

---

### `Address already in use`

**Cause:** Port 5000 atau 1883 sudah dipakai process lain

**Fix:**
```bash
# Find process
sudo netstat -tlnp | grep <port>

# Kill process
sudo kill -9 <PID>

# Atau restart service
sudo systemctl restart tpt-rfid
```

---

### `502 Bad Gateway`

**Cause:** Flask app not running atau Nginx cannot connect

**Fix:**
```bash
sudo systemctl status tpt-rfid
sudo systemctl start tpt-rfid
sudo systemctl reload nginx
```

---

### `Permission denied`

**Cause:** File ownership atau permissions salah

**Fix:**
```bash
# Fix ownership
sudo chown -R pi:pi /opt/tpt-rfid

# Fix permissions
chmod 600 /opt/tpt-rfid/.env
chmod 755 /opt/tpt-rfid
```

---

## Debug Procedures

### Systematic Debugging Approach

1. **Identify Component:**
   - Database issue? → Check PostgreSQL
   - Web UI issue? → Check Flask + Nginx
   - MQTT issue? → Check Mosquitto
   - ESP32 issue? → Check serial monitor

2. **Check Logs:**
   - PostgreSQL: `/var/log/postgresql/postgresql-*-main.log` (replace * with version 14 or 15)
   - Flask: `sudo journalctl -u tpt-rfid -f`
   - Mosquitto: `/var/log/mosquitto/mosquitto.log`
   - Nginx: `/var/log/nginx/tpt-rfid-error.log`
   - System: `sudo journalctl -p err -n 50`

3. **Verify Configuration:**
   - `.env` file complete?
   - Service configs correct?
   - Firewall rules OK?

4. **Test Connectivity:**
   - Can connect to database?
   - Can connect to MQTT?
   - Can access web UI?

5. **Check Resources:**
   - Disk space: `df -h`
   - Memory: `free -h`
   - CPU: `htop`

6. **Reproduce Issue:**
   - Can you reproduce consistently?
   - What triggers the issue?
   - Any pattern (time, load, specific action)?

---

## Log Analysis

### PostgreSQL Logs

```bash
# Recent errors
sudo tail -100 /var/log/postgresql/postgresql-*-main.log | grep ERROR

# Slow queries
sudo grep "duration:" /var/log/postgresql/postgresql-*-main.log | \
  awk '$13 > 1000' | tail -20

# Connection issues
sudo grep "connection" /var/log/postgresql/postgresql-*-main.log | tail -20
```

---

### Flask Application Logs

```bash
# Real-time log
sudo journalctl -u tpt-rfid -f

# Errors only
sudo journalctl -u tpt-rfid -p err -n 50

# Specific time range
sudo journalctl -u tpt-rfid --since "2024-01-15 10:00:00" --until "2024-01-15 11:00:00"

# Search for keyword
sudo journalctl -u tpt-rfid | grep -i "mqtt"

# Export to file
sudo journalctl -u tpt-rfid -n 1000 > /tmp/tpt-rfid-logs.txt
```

---

### Mosquitto Logs

```bash
# Real-time
tail -f /var/log/mosquitto/mosquitto.log

# Connection attempts
grep "New connection" /var/log/mosquitto/mosquitto.log | tail -20

# Authentication failures
grep "Bad" /var/log/mosquitto/mosquitto.log | tail -20

# Disconnections
grep "Socket error" /var/log/mosquitto/mosquitto.log | tail -20
```

---

### Nginx Logs

```bash
# Access log (successful requests)
tail -50 /var/log/nginx/tpt-rfid-access.log

# Error log
tail -50 /var/log/nginx/tpt-rfid-error.log

# 404 errors
grep "404" /var/log/nginx/tpt-rfid-access.log | tail -20

# 502 errors (backend down)
grep "502" /var/log/nginx/tpt-rfid-access.log | tail -20

# Slow requests (>5 seconds)
awk '$NF > 5' /var/log/nginx/tpt-rfid-access.log | tail -20
```

---

## Getting Help

Jika troubleshooting guide ini tidak solve masalah:

1. **Collect Information:**
   ```bash
   # Save logs
   sudo journalctl -u tpt-rfid -n 500 > logs-flask.txt
   sudo tail -200 /var/log/mosquitto/mosquitto.log > logs-mosquitto.txt
   sudo tail -200 /var/log/postgresql/postgresql-*-main.log > logs-postgres.txt
   
   # System info
   uname -a > sysinfo.txt
   free -h >> sysinfo.txt
   df -h >> sysinfo.txt
   
   # Configuration (HIDE PASSWORDS!)
   grep -v PASSWORD /opt/tpt-rfid/.env > config.txt
   ```

2. **Document Steps:**
   - Apa yang Anda lakukan sebelum error terjadi?
   - Langkah-langkah untuk reproduce issue
   - Error message lengkap

3. **Check Documentation:**
   - [MQTT_SETUP.md](MQTT_SETUP.md)
   - [ESP32_CLIENT_GUIDE.md](ESP32_CLIENT_GUIDE.md)
   - [DEPLOYMENT.md](DEPLOYMENT.md)

4. **Contact Support:**
   - Include logs dan system info
   - Jangan share passwords atau sensitive info!

---

**Last Updated:** 2024-01-15  
**Version:** 1.0  
**Author:** TPT RFID Team

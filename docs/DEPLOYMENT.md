# Deployment Guide - TPT RFID System

Panduan lengkap deployment aplikasi TPT RFID ke production environment menggunakan Raspberry Pi 4B.

## Daftar Isi

1. [Overview](#overview)
3. [Persiapan Raspberry Pi](#persiapan-raspberry-pi)
4. [PostgreSQL Production Setup](#postgresql-production-setup)
5. [Mosquitto Production Setup](#mosquitto-production-setup)
6. [Flask Application Deployment](#flask-application-deployment)
7. [Nginx Reverse Proxy](#nginx-reverse-proxy)
8. [Firewall & Security](#firewall--security)
9. [Kiosk Mode Setup](#kiosk-mode-setup)
10. [Backup & Recovery](#backup--recovery)
11. [Monitoring & Logging](#monitoring--logging)
12. [Update Procedures](#update-procedures)
13. [Performance Tuning](#performance-tuning)

---

## Overview

### Arsitektur Production

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4B                           │
│                                                              │
│  ┌────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │   Nginx    │───▶│ Gunicorn     │───▶│  PostgreSQL    │  │
│  │ (Port 80)  │    │ Flask App    │    │  (Port 5432)   │  │
│  │            │    │ (Port 5000)  │    │                │  │
│  └────────────┘    └──────────────┘    └────────────────┘  │
│        │                   │                                │
│        │                   ▼                                │
│        │           ┌──────────────┐                         │
│        │           │  Mosquitto   │                         │
│        │           │  MQTT Broker │                         │
│        │           │ (Port 1883)  │                         │
│        │           │ (Port 8083)  │                         │
│        │           └──────────────┘                         │
│        │                   ▲                                │
│        ▼                   │                                │
│  ┌────────────┐           │                                │
│  │ Touchscreen│           │                                │
│  │   Kiosk    │           │                                │
│  └────────────┘           │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
                   ┌─────────┴─────────┐
                   │                   │
               ┌───▼────┐         ┌───▼────┐
               │ ESP32  │         │ ESP32  │
               │ RFID 1 │         │ RFID 2 │
               └────────┘         └────────┘
```

### Target Environment

- **Hardware:** Raspberry Pi 4B (4GB RAM minimum)
- **OS:** Raspberry Pi OS Lite (64-bit) - Debian 12 (Bookworm)
- **Database:** PostgreSQL 14 or 15
- **MQTT Broker:** Mosquitto 2.0+
- **Web Server:** Nginx
- **App Server:** Gunicorn
- **Python:** 3.11+

---

## Persiapan Raspberry Pi

### 1. Install Raspberry Pi OS

#### Option A: Raspberry Pi Imager (Recommended)

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

2. Pilih OS:
   - **Raspberry Pi OS (64-bit) Lite** (no desktop, server only)
   - Atau **Raspberry Pi OS (64-bit)** (with desktop, jika pakai kiosk mode)

3. Advanced Settings (Ctrl+Shift+X):
   ```
   ✓ Set hostname: tpt-rfid
   ✓ Enable SSH
   ✓ Set username: pi
   ✓ Set password: [your-secure-password]
   ✓ Configure WiFi (optional)
   ✓ Set locale: Asia/Jakarta, en_US.UTF-8
   ```

4. Write ke SD card

#### Option B: Manual Setup

```bash
# After first boot, raspi-config
sudo raspi-config

# Configure:
# 1. System Options -> Hostname -> tpt-rfid
# 2. System Options -> Boot -> Console Autologin (jika kiosk mode)
# 3. Interface Options -> SSH -> Enable
# 4. Localisation -> Timezone -> Asia/Jakarta
# 5. Localisation -> Locale -> en_US.UTF-8
# 6. Performance -> GPU Memory -> 256 (jika pakai touchscreen)
# 7. Finish -> Reboot
```

### 2. Update System

```bash
# Update package list
sudo apt update

# Upgrade all packages (bisa lama, 10-30 menit)
sudo apt full-upgrade -y

# Install essential tools
sudo apt install -y \
  git curl wget vim nano \
  build-essential python3-dev \
  python3-pip python3-venv \
  libpq-dev postgresql-client \
  ufw fail2ban \
  htop iotop

# Reboot
sudo reboot
```

### 3. Configure Static IP (Production)

Edit dhcpcd config:

```bash
sudo nano /etc/dhcpcd.conf
```

Tambahkan di akhir file:

```conf
# Static IP Configuration
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8

# Atau untuk WiFi
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

**Sesuaikan IP dengan network lab Anda!**

Restart networking:

```bash
sudo systemctl restart dhcpcd
```

Verify:

```bash
ip addr show
# Should show 192.168.1.100
```

### 4. SSH Setup (Remote Access)

Jika belum enable SSH:

```bash
sudo systemctl enable ssh
sudo systemctl start ssh
```

**Security:** Disable password login, gunakan SSH key:

```bash
# Di komputer local (bukan di Pi):
ssh-keygen -t ed25519 -C "tpt-rfid-key"
ssh-copy-id pi@192.168.1.100

# Di Pi, disable password login:
sudo nano /etc/ssh/sshd_config
```

Set:
```conf
PasswordAuthentication no
PermitRootLogin no
```

Restart SSH:

```bash
sudo systemctl restart ssh
```

---

## PostgreSQL Production Setup

### 1. Install PostgreSQL

```bash
# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Verify
sudo systemctl status postgresql
psql --version
# Output: psql (PostgreSQL) 14.x or 15.x
```

### 2. Create Database & User

```bash
# Login sebagai postgres user
sudo -u postgres psql

# Di PostgreSQL prompt:
```

```sql
-- Create database
CREATE DATABASE tpt_rfid_db;

-- Create user dengan password kuat
CREATE USER tpt_rfid WITH ENCRYPTED PASSWORD 'your_secure_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE tpt_rfid_db TO tpt_rfid;

-- Connect to database
\c tpt_rfid_db

-- Grant schema privileges (PostgreSQL 14+)
GRANT ALL ON SCHEMA public TO tpt_rfid;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tpt_rfid;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tpt_rfid;

-- Exit
\q
```

### 3. Configure PostgreSQL

Edit PostgreSQL config:

```bash
sudo nano /etc/postgresql/*/main/postgresql.conf
# Note: Replace * with your version (14 or 15)
# Or use: sudo nano $(find /etc/postgresql -name postgresql.conf | head -1)
```

**Production tuning** (untuk Pi 4B 4GB RAM):

```conf
# Connection Settings
max_connections = 50                # Reduced untuk Pi
shared_buffers = 512MB              # 25% of RAM
effective_cache_size = 2GB          # 50% of RAM
maintenance_work_mem = 128MB
work_mem = 10MB

# WAL Settings (Write-Ahead Logging)
wal_buffers = 16MB
checkpoint_completion_target = 0.9
max_wal_size = 1GB
min_wal_size = 256MB

# Query Tuning
random_page_cost = 1.1              # Untuk SSD, set 1.1. Untuk SD card, biarkan 4.0
effective_io_concurrency = 200      # Untuk SSD. Untuk SD card, set 2

# Logging
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
log_timezone = 'Asia/Jakarta'
```

Edit authentication:

```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf
# Note: Replace * with your version (14 or 15)
```

Set:

```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# Local connections
local   all             postgres                                peer
local   all             all                                     peer

# IPv4 local connections
host    all             all             127.0.0.1/32            scram-sha-256

# Allow from local network (optional, untuk remote access)
# host    tpt_rfid_db     tpt_rfid        192.168.1.0/24          scram-sha-256
```

Restart PostgreSQL:

```bash
sudo systemctl restart postgresql
```

### 4. Test Connection

```bash
# Test local connection
psql -U tpt_rfid -d tpt_rfid_db -h localhost

# Should prompt for password, then connect
# \dt to list tables (empty untuk sekarang)
# \q to quit
```

### 5. Enable Auto-start

```bash
sudo systemctl enable postgresql
```

---

## Mosquitto Production Setup

### 1. Install Mosquitto

```bash
# Install
sudo apt install -y mosquitto mosquitto-clients

# Verify
mosquitto -h
# Output: mosquitto version 2.0.x
```

### 2. Create Authentication

```bash
# Create password file
sudo mosquitto_passwd -c /etc/mosquitto/passwd tpt-rfid

# Akan prompt untuk password, gunakan password yang kuat
# Example: tpt_rfid_mqtt_2024!

# Add more users jika perlu
sudo mosquitto_passwd /etc/mosquitto/passwd esp32_client
```

**Security best practice:** Gunakan password berbeda untuk setiap role:
- `tpt-rfid` - untuk Flask app (read/write semua topic)
- `esp32_client` - untuk ESP32 (read/write terbatas)

### 3. Configure Mosquitto

Create production config:

```bash
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf
```

```conf
# TPT RFID Production Configuration

# Listener - MQTT Protocol (for ESP32)
listener 1883 0.0.0.0
protocol mqtt
max_connections 100

# Listener - WebSocket Protocol (for Web UI)
listener 8083 0.0.0.0
protocol websockets

# Authentication
allow_anonymous false
password_file /etc/mosquitto/passwd

# ACL (Access Control List) - optional
# acl_file /etc/mosquitto/acl.conf

# Persistence
persistence true
persistence_location /var/lib/mosquitto/

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# Connection Settings
max_keepalive 300
keepalive_interval 60

# Message Settings
max_queued_messages 1000
message_size_limit 0
```

### 4. Create ACL (Access Control List) - Optional tapi Recommended

```bash
sudo nano /etc/mosquitto/acl.conf
```

```conf
# TPT RFID Access Control List

# Flask App - Full access
user tpt-rfid
topic readwrite #

# ESP32 Clients - Limited access
user esp32_client
topic write rfid/scan
topic write sensor/#
topic read transaction/update
topic read tool/status

# Pattern-based ACL untuk multiple ESP32
# pattern write rfid/%u/scan
# pattern write sensor/%u/#
```

Jika pakai ACL, uncomment di config:

```bash
sudo nano /etc/mosquitto/conf.d/tpt-rfid.conf
# Uncomment: acl_file /etc/mosquitto/acl.conf
```

### 5. Set Permissions

```bash
# Ensure mosquitto owns the files
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 600 /etc/mosquitto/passwd

# Ensure log directory exists
sudo mkdir -p /var/log/mosquitto
sudo chown mosquitto:mosquitto /var/log/mosquitto
```

### 6. Restart & Test

```bash
# Restart Mosquitto
sudo systemctl restart mosquitto

# Check status
sudo systemctl status mosquitto

# Test authentication
mosquitto_pub -h localhost -p 1883 \
  -u tpt-rfid -P 'your_password' \
  -t test/topic -m "Hello MQTT"

# Subscribe (di terminal lain)
mosquitto_sub -h localhost -p 1883 \
  -u tpt-rfid -P 'your_password' \
  -t test/topic

# Should receive "Hello MQTT"
```

### 7. Enable Auto-start

```bash
sudo systemctl enable mosquitto
```

---

## Flask Application Deployment

### 1. Clone Repository

```bash
# Create application directory
sudo mkdir -p /opt/tpt-rfid
sudo chown pi:pi /opt/tpt-rfid

# Clone repository
cd /opt/tpt-rfid
git clone https://github.com/YOUR_USERNAME/tpt-rfid.git .

# Atau jika sudah ada repository local, rsync dari komputer:
# rsync -avz --exclude '.git' --exclude '__pycache__' \
#   /path/to/local/tpt-rfid/ pi@192.168.1.100:/opt/tpt-rfid/
```

### 2. Create Virtual Environment

```bash
cd /opt/tpt-rfid

# Create venv
python3 -m venv venv

# Activate
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

### 3. Install Dependencies

```bash
# Install base requirements
pip install -r requirements.txt

# Install MQTT requirements (production)
pip install -r requirements-mqtt.txt

# Install Gunicorn (production server)
pip install gunicorn

# Verify installation
pip list
```

### 4. Configure Environment

Create production `.env`:

```bash
nano /opt/tpt-rfid/.env
```

**Production configuration:**

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your_very_long_random_secret_key_here_minimum_32_chars

# Database Configuration
DATABASE_URL=postgresql://tpt_rfid:your_secure_password_here@localhost:5432/tpt_rfid_db

# Admin PIN (required for login)
ADMIN_PIN=your_secure_pin_here

# MQTT Configuration
MQTT_ENABLED=true
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID=tpt-rfid-server

# MQTT Authentication (if broker requires it)
MQTT_USERNAME=tpt-rfid
MQTT_PASSWORD=tpt_rfid_mqtt_2024!

# WebSocket Configuration
WEBSOCKET_ENABLED=true
WEBSOCKET_BROKER_HOST=localhost
WEBSOCKET_BROKER_PORT=8083

# Email Configuration (optional - for notifications)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

**PENTING:** Generate secure secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Copy output ke SECRET_KEY
```

Set file permissions:

```bash
chmod 600 /opt/tpt-rfid/.env
```

### 5. Initialize Database

```bash
cd /opt/tpt-rfid
source venv/bin/activate

# Run migrations (jika pakai Flask-Migrate)
# flask db upgrade

# Atau initialize database manually
python3 << EOF
from app import app, db
with app.app_context():
    db.create_all()
    print("Database initialized successfully!")
EOF
```

Verify tables created:

```bash
psql -U tpt_rfid -d tpt_rfid_db -h localhost -c "\dt"
# Should list: students, tools, transactions
```

### 6. Configure Admin Access

Aplikasi ini menggunakan **ADMIN_PIN** untuk autentikasi (bukan username/password).

Pastikan `ADMIN_PIN` sudah di-set di file `.env`:

```bash
# Check ADMIN_PIN in .env
grep ADMIN_PIN /opt/tpt-rfid/.env

# If not set, add it
nano /opt/tpt-rfid/.env
# Add: ADMIN_PIN=your_secure_pin_here
```

**SECURITY WARNING:** 
- Jangan gunakan PIN default `133133`
- Gunakan PIN yang sulit ditebak (minimal 6 digit)
- PIN ini digunakan untuk akses halaman admin

### 7. Test Flask App

```bash
# Test run (development mode)
cd /opt/tpt-rfid
source venv/bin/activate
python app.py

# Should start on http://0.0.0.0:5000
# Press Ctrl+C to stop
```

### 8. Create Gunicorn Service

Create systemd service file:

```bash
sudo nano /etc/systemd/system/tpt-rfid.service
```

```ini
[Unit]
Description=TPT RFID Flask Application
After=network.target postgresql.service mosquitto.service
Wants=postgresql.service mosquitto.service

[Service]
Type=notify
User=pi
Group=pi
WorkingDirectory=/opt/tpt-rfid
Environment="PATH=/opt/tpt-rfid/venv/bin"
ExecStart=/opt/tpt-rfid/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile /var/log/tpt-rfid/access.log \
    --error-logfile /var/log/tpt-rfid/error.log \
    --log-level info \
    app:app

# Restart policy
Restart=always
RestartSec=10

# Security hardening
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/tpt-rfid /var/log/tpt-rfid /tmp/flask_session

[Install]
WantedBy=multi-user.target
```

**Gunicorn tuning untuk Raspberry Pi:**
- `--workers 2` - 2 worker processes (1 per CPU core untuk I/O bound app)
- `--threads 4` - 4 threads per worker (handle concurrent requests)
- `--timeout 120` - 2 minutes timeout untuk slow operations

Create log directory:

```bash
sudo mkdir -p /var/log/tpt-rfid
sudo chown pi:pi /var/log/tpt-rfid
```

Enable and start service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start
sudo systemctl enable tpt-rfid

# Start service
sudo systemctl start tpt-rfid

# Check status
sudo systemctl status tpt-rfid

# View logs
sudo journalctl -u tpt-rfid -f
```

### 9. Verify Application

```bash
# Test local access
curl http://127.0.0.1:5000

# Should return HTML response

# Check if MQTT connected
sudo journalctl -u tpt-rfid -n 50 | grep -i mqtt
# Should show "Connected to MQTT broker"
```

---

## Nginx Reverse Proxy

### 1. Install Nginx

```bash
sudo apt install -y nginx
```

### 2. Configure Nginx

Remove default config:

```bash
sudo rm /etc/nginx/sites-enabled/default
```

Create TPT RFID config:

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid
```

```nginx
# TPT RFID Nginx Configuration

upstream tpt_rfid_app {
    server 127.0.0.1:5000 fail_timeout=0;
}

server {
    listen 80;
    server_name tpt-rfid 192.168.1.100 localhost;

    # Logs
    access_log /var/log/nginx/tpt-rfid-access.log;
    error_log /var/log/nginx/tpt-rfid-error.log;

    # Max upload size (untuk upload gambar tools)
    client_max_body_size 10M;

    # Proxy settings
    location / {
        proxy_pass http://tpt_rfid_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Static files (jika ada folder static)
    location /static {
        alias /opt/tpt-rfid/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Favicon
    location /favicon.ico {
        alias /opt/tpt-rfid/static/favicon.ico;
        access_log off;
        log_not_found off;
    }

    # Health check endpoint (optional - implement if needed)
    # location /health {
    #     proxy_pass http://tpt_rfid_app/health;
    #     access_log off;
    # }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/tpt-rfid /etc/nginx/sites-enabled/
```

Test configuration:

```bash
sudo nginx -t
# Output: syntax is ok, test is successful
```

Restart Nginx:

```bash
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### 3. Test Nginx

```bash
# Test from Pi
curl http://localhost

# Test from komputer lain di network
# Browser: http://192.168.1.100
```

### 4. Optional: SSL/HTTPS Setup

Jika ada domain name atau ingin pakai self-signed certificate:

#### Option A: Self-signed Certificate (Internal Use)

```bash
# Generate certificate
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/tpt-rfid.key \
  -out /etc/nginx/ssl/tpt-rfid.crt \
  -subj "/C=ID/ST=Jakarta/L=Jakarta/O=TPT Lab/CN=tpt-rfid"

# Update Nginx config
sudo nano /etc/nginx/sites-available/tpt-rfid
```

Add SSL server block:

```nginx
server {
    listen 443 ssl http2;
    server_name tpt-rfid 192.168.1.100;

    ssl_certificate /etc/nginx/ssl/tpt-rfid.crt;
    ssl_certificate_key /etc/nginx/ssl/tpt-rfid.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # ... rest of config same as HTTP block
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name tpt-rfid 192.168.1.100;
    return 301 https://$server_name$request_uri;
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

#### Option B: Let's Encrypt (Jika Ada Domain)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Firewall & Security

### 1. Configure UFW (Uncomplicated Firewall)

```bash
# Reset UFW (jika sudah pernah dikonfigurasi)
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (CRITICAL: allow ini dulu sebelum enable!)
sudo ufw allow 22/tcp comment 'SSH'

# Allow HTTP/HTTPS (untuk web access)
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# Allow MQTT dari local network only (untuk ESP32)
sudo ufw allow from 192.168.1.0/24 to any port 1883 proto tcp comment 'MQTT'
sudo ufw allow from 192.168.1.0/24 to any port 8083 proto tcp comment 'MQTT WebSocket'

# Enable firewall
sudo ufw enable

# Verify
sudo ufw status numbered
```

Output should show:

```
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere                   # SSH
[ 2] 80/tcp                     ALLOW IN    Anywhere                   # HTTP
[ 3] 443/tcp                    ALLOW IN    Anywhere                   # HTTPS
[ 4] 1883/tcp                   ALLOW IN    192.168.1.0/24            # MQTT
[ 5] 8083/tcp                   ALLOW IN    192.168.1.0/24            # MQTT WebSocket
```

**SECURITY NOTE:** 
- PostgreSQL (5432) TIDAK exposed, hanya localhost
- MQTT hanya accept dari local network
- SSH tetap allow dari mana saja (jika butuh remote access)

### 2. Install & Configure Fail2ban

Protect SSH dari brute force:

```bash
sudo apt install -y fail2ban

# Create local config
sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
# Ban time: 1 hour
bantime = 3600
findtime = 600
maxretry = 5

# Email notifications (optional)
# destemail = your-email@example.com
# sendername = Fail2Ban-TPT-RFID
# action = %(action_mwl)s

[sshd]
enabled = true
port = 22
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/tpt-rfid-error.log
```

Start Fail2ban:

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

### 3. Disable Unused Services

```bash
# List all services
systemctl list-unit-files --type=service --state=enabled

# Disable yang tidak perlu (contoh):
# sudo systemctl disable bluetooth.service
# sudo systemctl disable avahi-daemon.service
```

### 4. Regular Security Updates

```bash
# Create update script
sudo nano /usr/local/bin/security-update.sh
```

```bash
#!/bin/bash
# TPT RFID Security Update Script

echo "=== TPT RFID Security Update ==="
echo "Started: $(date)"

# Update package list
apt update

# List upgradable packages
echo ""
echo "Available updates:"
apt list --upgradable

# Upgrade security packages only
# apt upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

echo ""
echo "Finished: $(date)"
echo "================================"
```

```bash
sudo chmod +x /usr/local/bin/security-update.sh

# Run manual
sudo /usr/local/bin/security-update.sh

# Atau schedule dengan cron (weekly)
sudo crontab -e
```

Add:
```cron
# Security updates every Sunday 3 AM
0 3 * * 0 /usr/local/bin/security-update.sh >> /var/log/security-update.log 2>&1
```

---

## Kiosk Mode Setup

Untuk setup Raspberry Pi dengan touchscreen sebagai kiosk (auto-login, full-screen browser).

**Requirements:**
- Raspberry Pi OS with Desktop (bukan Lite)
- Official 7" Touchscreen atau HDMI monitor

### 1. Install Chromium Browser

```bash
sudo apt install -y chromium-browser unclutter
```

### 2. Configure Auto-login

```bash
sudo raspi-config
# 1. System Options -> Boot -> Desktop Autologin
```

Atau manual:

```bash
sudo nano /etc/systemd/system/getty@tty1.service.d/autologin.conf
```

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
```

### 3. Create Kiosk Start Script

```bash
mkdir -p /home/pi/.config/autostart
nano /home/pi/.config/autostart/kiosk.desktop
```

```ini
[Desktop Entry]
Type=Application
Name=TPT RFID Kiosk
Exec=/home/pi/start-kiosk.sh
X-GNOME-Autostart-enabled=true
```

Create start script:

```bash
nano /home/pi/start-kiosk.sh
```

```bash
#!/bin/bash
# TPT RFID Kiosk Mode Startup Script

# Wait for network
sleep 10

# Hide cursor
unclutter -idle 0.1 &

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Start Chromium in kiosk mode
chromium-browser \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --disable-features=TranslateUI \
  --kiosk \
  --incognito \
  --app=http://localhost
```

```bash
chmod +x /home/pi/start-kiosk.sh
```

### 4. Disable On-Screen Keyboard (Optional)

Jika tidak perlu on-screen keyboard:

```bash
sudo apt remove --purge -y matchbox-keyboard
```

### 5. Configure Touchscreen Rotation (Optional)

Jika layar terbalik:

```bash
sudo nano /boot/config.txt
```

Add:
```
# Rotate display 180 degrees
display_rotate=2

# Atau rotate 90 degrees
# display_rotate=1
```

Reboot:

```bash
sudo reboot
```

### 6. Test Kiosk Mode

Setelah reboot, Chromium akan auto-start full-screen ke `http://localhost`.

**Keluar dari kiosk mode:** Alt+F4 atau Ctrl+W

### 7. Remote Desktop (Optional, untuk Troubleshooting)

Install VNC server:

```bash
sudo raspi-config
# Interface Options -> VNC -> Enable
```

Atau manual:

```bash
sudo apt install -y realvnc-vnc-server
sudo systemctl enable vncserver-x11-serviced
sudo systemctl start vncserver-x11-serviced
```

Allow VNC di firewall:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 5900 proto tcp comment 'VNC'
```

Connect dengan VNC Viewer dari komputer lain: `192.168.1.100:5900`

---

## Backup & Recovery

### 1. Database Backup

Create automated backup script:

```bash
sudo mkdir -p /opt/backups/database
sudo chown pi:pi /opt/backups/database

nano /opt/tpt-rfid/scripts/backup-database.sh
```

```bash
#!/bin/bash
# TPT RFID Database Backup Script

BACKUP_DIR="/opt/backups/database"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tpt_rfid_db_$TIMESTAMP.sql.gz"
DB_NAME="tpt_rfid_db"
DB_USER="tpt_rfid"

echo "=== Database Backup Started: $(date) ==="

# Create backup
PGPASSWORD='your_db_password' pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_FILE

if [ $? -eq 0 ]; then
    echo "Backup successful: $BACKUP_FILE"
    
    # Get file size
    SIZE=$(du -h $BACKUP_FILE | cut -f1)
    echo "Backup size: $SIZE"
    
    # Delete backups older than 30 days
    find $BACKUP_DIR -name "tpt_rfid_db_*.sql.gz" -mtime +30 -delete
    echo "Old backups cleaned (>30 days)"
else
    echo "ERROR: Backup failed!"
    exit 1
fi

echo "=== Backup Completed: $(date) ==="
```

```bash
chmod +x /opt/tpt-rfid/scripts/backup-database.sh
```

Schedule daily backup:

```bash
crontab -e
```

Add:
```cron
# Daily database backup at 2 AM
0 2 * * * /opt/tpt-rfid/scripts/backup-database.sh >> /var/log/tpt-rfid/backup.log 2>&1
```

### 2. Database Restore

```bash
# Restore dari backup
PGPASSWORD='your_db_password' gunzip -c /opt/backups/database/tpt_rfid_db_20240115_020000.sql.gz | \
  psql -U tpt_rfid -h localhost -d tpt_rfid_db
```

### 3. Application Backup

```bash
sudo mkdir -p /opt/backups/application

# Backup application code (exclude venv)
tar -czf /opt/backups/application/tpt-rfid-app-$(date +%Y%m%d).tar.gz \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  /opt/tpt-rfid

# Backup environment file (contains secrets!)
sudo cp /opt/tpt-rfid/.env /opt/backups/application/.env.backup
sudo chmod 600 /opt/backups/application/.env.backup
```

### 4. System Image Backup (Full SD Card)

**Option A: Using `dd` (dari komputer lain, bukan Pi)**

```bash
# Backup SD card ke image file (16GB card = 16GB file!)
sudo dd if=/dev/sdX of=/path/to/backup/tpt-rfid-backup.img bs=4M status=progress

# Compress
gzip /path/to/backup/tpt-rfid-backup.img

# Restore
gunzip -c tpt-rfid-backup.img.gz | sudo dd of=/dev/sdX bs=4M status=progress
```

**Option B: Using `rpi-clone` (recommended)**

```bash
# Install rpi-clone
cd /tmp
git clone https://github.com/billw2/rpi-clone.git
cd rpi-clone
sudo cp rpi-clone /usr/local/sbin

# Clone SD card ke USB drive
sudo rpi-clone sda -f
```

### 5. Remote Backup (Rsync ke NAS/Server)

```bash
# Sync ke remote server
rsync -avz --delete \
  /opt/backups/ \
  user@backup-server:/backups/tpt-rfid/

# Atau ke local NAS (mount dulu)
sudo mount -t cifs //192.168.1.200/backups /mnt/nas \
  -o username=backup,password=xxx

rsync -avz --delete /opt/backups/ /mnt/nas/tpt-rfid/
```

---

## Monitoring & Logging

### 1. System Monitoring

Install monitoring tools:

```bash
sudo apt install -y htop iotop nethogs
```

Check system resources:

```bash
# CPU, RAM, processes
htop

# Disk I/O
sudo iotop

# Network usage
sudo nethogs

# Disk usage
df -h
du -sh /opt/tpt-rfid
du -sh /var/lib/postgresql
```

### 2. Service Monitoring

Check all TPT services:

```bash
# Create monitoring script
nano /usr/local/bin/tpt-status.sh
```

```bash
#!/bin/bash
# TPT RFID Service Status Check

echo "=== TPT RFID Service Status ==="
echo ""

# PostgreSQL
echo "PostgreSQL:"
systemctl status postgresql --no-pager -l | grep -E "Active|Main PID"
echo ""

# Mosquitto
echo "Mosquitto:"
systemctl status mosquitto --no-pager -l | grep -E "Active|Main PID"
echo ""

# TPT RFID App
echo "TPT RFID App:"
systemctl status tpt-rfid --no-pager -l | grep -E "Active|Main PID"
echo ""

# Nginx
echo "Nginx:"
systemctl status nginx --no-pager -l | grep -E "Active|Main PID"
echo ""

# Network ports
echo "Listening Ports:"
sudo netstat -tlnp | grep -E "5432|1883|8083|5000|80"
echo ""

# Disk usage
echo "Disk Usage:"
df -h | grep -E "Filesystem|/$"
echo ""

# Memory
echo "Memory Usage:"
free -h
echo ""

echo "================================"
```

```bash
sudo chmod +x /usr/local/bin/tpt-status.sh

# Run
sudo /usr/local/bin/tpt-status.sh
```

### 3. Log Management

Centralize logs:

```bash
# Log locations:
# - Flask App: /var/log/tpt-rfid/app.log, error.log, access.log
# - Mosquitto: /var/log/mosquitto/mosquitto.log
# - PostgreSQL: /var/log/postgresql/postgresql-*-main.log
# - Nginx: /var/log/nginx/tpt-rfid-*.log
# - System: /var/log/syslog, /var/log/messages
```

View logs:

```bash
# Flask app logs
tail -f /var/log/tpt-rfid/app.log

# Mosquitto logs
tail -f /var/log/mosquitto/mosquitto.log

# PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log

# System logs (all TPT services)
sudo journalctl -u tpt-rfid -u mosquitto -u postgresql -u nginx -f
```

Log rotation (sudah auto-configured via logrotate):

```bash
# Check logrotate config
cat /etc/logrotate.d/nginx
cat /etc/logrotate.d/postgresql-common

# Manual rotate
sudo logrotate -f /etc/logrotate.conf
```

### 4. Health Check Endpoint (Optional)

**Note:** Aplikasi saat ini belum punya endpoint `/health`. Jika diperlukan untuk monitoring, tambahkan ke `app.py`:

```python
# Add to app.py
from datetime import datetime
from flask import jsonify

@app.route('/health')
def health_check():
    """Health check endpoint untuk monitoring"""
    try:
        # Check database connection
        db.session.execute(text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = 'error'
        logger.error(f"Health check DB error: {e}")
    
    # Check MQTT (if enabled)
    if app.config.get('MQTT_ENABLED'):
        mqtt_status = 'ok' if mqtt_client.is_connected() else 'disconnected'
    else:
        mqtt_status = 'disabled'
    
    status = {
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'database': db_status,
        'mqtt': mqtt_status,
        'timestamp': datetime.now().isoformat()
    }
    
    status_code = 200 if status['status'] == 'ok' else 503
    return jsonify(status), status_code
```

Setelah ditambahkan, uncomment di Nginx config:

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid
# Uncomment location /health block

sudo nginx -t
sudo systemctl reload nginx
```

Test health endpoint:

```bash
# Check dari command line
curl http://localhost/health

# Expected output:
# {"status":"ok","database":"ok","mqtt":"ok","timestamp":"2024-01-15T10:30:00"}
```

### 5. Alerting (Optional)

Simple email alert untuk critical errors:

```bash
# Install mail utils
sudo apt install -y mailutils

# Create alert script
nano /opt/tpt-rfid/scripts/alert-service-down.sh
```

```bash
#!/bin/bash
# Alert jika service down

SERVICE=$1
EMAIL="admin@example.com"

if ! systemctl is-active --quiet $SERVICE; then
    echo "ALERT: Service $SERVICE is DOWN on $(hostname)" | \
      mail -s "[TPT RFID] Service Down: $SERVICE" $EMAIL
fi
```

```bash
chmod +x /opt/tpt-rfid/scripts/alert-service-down.sh

# Schedule check every 5 minutes
crontab -e
```

```cron
# Service monitoring
*/5 * * * * /opt/tpt-rfid/scripts/alert-service-down.sh tpt-rfid
*/5 * * * * /opt/tpt-rfid/scripts/alert-service-down.sh mosquitto
*/5 * * * * /opt/tpt-rfid/scripts/alert-service-down.sh postgresql
```

---

## Update Procedures

### 1. Update Application Code

```bash
# Stop service
sudo systemctl stop tpt-rfid

# Backup current version
cd /opt
sudo tar -czf tpt-rfid-backup-$(date +%Y%m%d).tar.gz tpt-rfid/

# Pull updates
cd /opt/tpt-rfid
git pull origin main

# Update dependencies (jika ada perubahan)
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-mqtt.txt

# Run database migrations (jika ada)
# flask db upgrade

# Restart service
sudo systemctl start tpt-rfid

# Check status
sudo systemctl status tpt-rfid
sudo journalctl -u tpt-rfid -n 50
```

### 2. Update System Packages

```bash
# Update package list
sudo apt update

# List upgradable
apt list --upgradable

# Upgrade all (HATI-HATI di production!)
sudo apt upgrade -y

# Reboot jika kernel update
sudo reboot
```

### 3. Update PostgreSQL

```bash
# Check current version
psql --version

# Backup database BEFORE upgrade!
/opt/tpt-rfid/scripts/backup-database.sh

# Update PostgreSQL
sudo apt update
sudo apt upgrade postgresql postgresql-contrib

# Restart
sudo systemctl restart postgresql
```

### 4. Update Python Dependencies

```bash
cd /opt/tpt-rfid
source venv/bin/activate

# List outdated packages
pip list --outdated

# Update specific package
pip install --upgrade flask

# Atau update semua (TESTING dulu!)
pip install --upgrade -r requirements.txt

# Test
python -c "import flask; print(flask.__version__)"

# Restart app
sudo systemctl restart tpt-rfid
```

### 5. Rollback Procedure

Jika update bermasalah:

```bash
# Stop service
sudo systemctl stop tpt-rfid

# Restore dari backup
cd /opt
sudo rm -rf tpt-rfid
sudo tar -xzf tpt-rfid-backup-20240115.tar.gz

# Restore database (jika perlu)
# PGPASSWORD='xxx' gunzip -c /opt/backups/database/xxx.sql.gz | psql ...

# Start service
sudo systemctl start tpt-rfid
```

---

## Performance Tuning

### 1. Raspberry Pi Overclocking (Optional)

**WARNING:** Overclocking dapat menyebabkan instability dan overheat. Monitor temperature!

```bash
sudo nano /boot/config.txt
```

Add (Pi 4B):
```
# Moderate overclock
over_voltage=2
arm_freq=1750

# Atau conservative (recommended)
# over_voltage=1
# arm_freq=1650
```

Monitor temperature:

```bash
# Check current temp
vcgencmd measure_temp

# Monitor continuous
watch -n 1 vcgencmd measure_temp

# Should stay below 80°C under load
```

### 2. PostgreSQL Performance

See section [PostgreSQL Production Setup](#postgresql-production-setup) untuk tuning.

Additional indexes untuk performa:

```sql
-- Connect to database
psql -U tpt_rfid -d tpt_rfid_db -h localhost

-- Add indexes (jika belum ada)
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_tool_id ON transactions(tool_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX idx_transactions_status ON transactions(status);

-- Analyze tables
ANALYZE transactions;
ANALYZE users;
ANALYZE tools;
```

### 3. Flask/Gunicorn Tuning

Edit systemd service:

```bash
sudo nano /etc/systemd/system/tpt-rfid.service
```

Adjust workers dan threads:

```ini
# For CPU-bound (heavy processing)
--workers 4 --threads 2

# For I/O-bound (recommended untuk RFID app)
--workers 2 --threads 4

# For memory-constrained (Pi 2GB)
--workers 1 --threads 4
```

Reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart tpt-rfid
```

### 4. Nginx Caching

Add caching untuk static assets:

```bash
sudo nano /etc/nginx/sites-available/tpt-rfid
```

```nginx
# Add inside server block
location ~* \.(jpg|jpeg|png|gif|ico|css|js|woff|woff2|ttf)$ {
    proxy_pass http://tpt_rfid_app;
    expires 7d;
    add_header Cache-Control "public, immutable";
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Swap File (untuk Pi 2GB/4GB)

Create swap file:

```bash
# Disable existing swap
sudo dphys-swapfile swapoff

# Edit config
sudo nano /etc/dphys-swapfile
```

Set:
```
CONF_SWAPSIZE=2048
# 2GB swap untuk Pi 4GB RAM
```

```bash
# Recreate swap
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Verify
free -h
# Should show 2GB swap
```

**Note:** Swap di SD card akan memperlambat dan memperpendek umur SD card. Gunakan SSD jika memungkinkan.

### 6. Disable GUI (jika tidak pakai kiosk mode)

Free up ~500MB RAM:

```bash
sudo systemctl set-default multi-user.target
sudo reboot
```

Revert:
```bash
sudo systemctl set-default graphical.target
sudo reboot
```

---

## Troubleshooting Common Issues

### Issue: Service Failed to Start

```bash
# Check detailed error
sudo journalctl -u tpt-rfid -n 100 --no-pager

# Check if port already in use
sudo netstat -tlnp | grep 5000

# Check permissions
ls -la /opt/tpt-rfid
ls -la /var/log/tpt-rfid
```

### Issue: Cannot Connect to Database

```bash
# Check PostgreSQL running
sudo systemctl status postgresql

# Check connection
psql -U tpt_rfid -d tpt_rfid_db -h localhost

# Check password in .env
grep DATABASE_URL /opt/tpt-rfid/.env
```

### Issue: MQTT Connection Failed

```bash
# Check Mosquitto running
sudo systemctl status mosquitto

# Check logs
tail -f /var/log/mosquitto/mosquitto.log

# Test connection
mosquitto_sub -h localhost -p 1883 -u tpt-rfid -P 'password' -t test/topic -v

# Check firewall
sudo ufw status
```

### Issue: High CPU Usage

```bash
# Check processes
htop

# Check Gunicorn workers
ps aux | grep gunicorn

# Reduce workers jika perlu
sudo nano /etc/systemd/system/tpt-rfid.service
# Set: --workers 1 --threads 4
sudo systemctl daemon-reload
sudo systemctl restart tpt-rfid
```

### Issue: Out of Memory

```bash
# Check memory
free -h

# Check swap
swapon --show

# Identify memory hogs
ps aux --sort=-%mem | head

# Restart services
sudo systemctl restart tpt-rfid
```

### Issue: SD Card Full

```bash
# Check disk usage
df -h

# Find large files/directories
sudo du -sh /var/* | sort -h
sudo du -sh /opt/* | sort -h
sudo du -sh /home/* | sort -h

# Clean up
sudo apt clean
sudo apt autoremove
sudo journalctl --vacuum-time=7d
```

**Untuk troubleshooting lebih detail, lihat:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Checklist Production Deployment

Gunakan checklist ini untuk memastikan deployment lengkap:

### Pre-Deployment

- [ ] Raspberry Pi 4B siap (4GB+ RAM)
- [ ] SD card 32GB+ atau SSD
- [ ] Power supply 5V 3A
- [ ] Network connectivity (Ethernet/WiFi)
- [ ] Static IP configured
- [ ] Domain name ready (optional)

### System Setup

- [ ] Raspberry Pi OS installed dan updated
- [ ] Hostname set: `tpt-rfid`
- [ ] Timezone: `Asia/Jakarta`
- [ ] SSH enabled dan accessible
- [ ] SSH key authentication (password disabled)
- [ ] Firewall (UFW) configured
- [ ] Fail2ban installed

### Database Setup

- [ ] PostgreSQL installed
- [ ] Database `tpt_rfid_db` created
- [ ] User `tpt_rfid` created dengan strong password
- [ ] PostgreSQL tuned untuk production
- [ ] Database backup script configured
- [ ] Admin user created

### MQTT Setup

- [ ] Mosquitto installed
- [ ] Authentication configured (password file)
- [ ] ACL configured (access control)
- [ ] TLS/SSL configured (optional)
- [ ] Firewall rules untuk MQTT ports

### Application Setup

- [ ] Repository cloned ke `/opt/tpt-rfid`
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] `.env` configured dengan production values
- [ ] Secret key generated (32+ chars)
- [ ] Database tables initialized
- [ ] Systemd service created dan enabled
- [ ] Application logs directory created

### Web Server Setup

- [ ] Nginx installed
- [ ] Site configuration created
- [ ] SSL certificate configured (optional)
- [ ] Static files served correctly
- [ ] WebSocket proxy configured

### Security

- [ ] All default passwords changed
- [ ] Firewall enabled dengan proper rules
- [ ] Fail2ban configured
- [ ] PostgreSQL tidak exposed ke internet
- [ ] MQTT hanya accept dari local network
- [ ] File permissions correct (`.env` = 600)
- [ ] Regular security updates scheduled

### Monitoring & Maintenance

- [ ] Log rotation configured
- [ ] Database backup scheduled (daily)
- [ ] Application backup scheduled (weekly)
- [ ] Monitoring script created
- [ ] Health check endpoint working
- [ ] Alert system configured (optional)

### Testing

- [ ] Web UI accessible dari browser
- [ ] Login works (admin user)
- [ ] Database operations work
- [ ] MQTT connection successful
- [ ] ESP32 can connect dan publish
- [ ] WebSocket real-time updates work
- [ ] All services auto-start setelah reboot

### Documentation

- [ ] `.env.example` updated
- [ ] README.md updated dengan production info
- [ ] Admin credentials documented (secure location!)
- [ ] Network diagram created
- [ ] Recovery procedures documented

---

## Kesimpulan

Setelah mengikuti panduan ini, Anda memiliki:

✅ **Production-ready TPT RFID system** running on Raspberry Pi 4B  
✅ **Secure configuration** dengan firewall, authentication, dan proper permissions  
✅ **Auto-start services** dengan systemd  
✅ **Monitoring & logging** untuk troubleshooting  
✅ **Backup procedures** untuk disaster recovery  
✅ **Performance tuning** untuk Raspberry Pi hardware  

### Next Steps

1. **Test thoroughly** - Simulasi berbagai scenario (normal operation, power loss, network issues)
2. **Document custom changes** - Catat semua perubahan spesifik untuk lab Anda
3. **Train users** - Latih user cara menggunakan dan basic troubleshooting
4. **Plan maintenance** - Schedule regular maintenance windows
5. **Monitor performance** - Track resource usage dan optimize jika perlu

### Referensi Lain

- [MQTT_SETUP.md](MQTT_SETUP.md) - Detail setup MQTT broker
- [ESP32_CLIENT_GUIDE.md](ESP32_CLIENT_GUIDE.md) - Programming ESP32 clients
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Comprehensive troubleshooting guide
- [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) - Migration history & technical details

### Support

Jika ada pertanyaan atau issues:

1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Check logs: `sudo journalctl -u tpt-rfid -f`
3. Verify service status: `sudo /usr/local/bin/tpt-status.sh

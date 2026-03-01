# Lab Fabrikasi ITB - RFID Tool Monitoring System

Sistem peminjaman alat workshop berbasis RFID untuk Lab Fabrikasi Teknik Fisika ITB dengan integrasi MQTT untuk komunikasi real-time dengan ESP32.

**Tech Stack:** Flask 3 (Python) · PostgreSQL · SQLAlchemy · MQTT (Mosquitto) · WebSocket · Tailwind CSS · Vanilla JS

---

## Daftar Isi

1. [Fitur](#fitur)
2. [CV Benchmark (Branch: cvtest)](#cv-benchmark-branch-cvtest)
3. [Arsitektur Sistem](#arsitektur-sistem)
4. [Arsitektur Proyek](#arsitektur-proyek)
5. [Setup Otomatis (Recommended)](#setup-otomatis-recommended)
6. [Setup di Laptop (Development)](#setup-di-laptop-development)
7. [Setup MQTT & ESP32](#setup-mqtt--esp32)
8. [Setup di Raspberry Pi (Production)](#setup-di-raspberry-pi-production)
9. [Seed Data (Opsional)](#seed-data-opsional)
10. [Cara Penggunaan Aplikasi](#cara-penggunaan-aplikasi)
11. [Environment Variables](#environment-variables)
12. [Troubleshooting](#troubleshooting)
13. [Dokumentasi Lengkap](#dokumentasi-lengkap)

---

## Fitur

- **Registrasi mahasiswa** — daftar dengan nama, NIM, email, telepon, foto, dan kartu RFID
- **Peminjaman alat** — scan kartu mahasiswa + tag RFID alat, konfirmasi pinjam
- **Pengembalian alat** — scan kartu mahasiswa + tag RFID alat, konfirmasi kembali
- **Monitor alat** — lihat status semua alat (tersedia / sedang dipinjam)
- **Admin panel** — monitor dengan info peminjam lengkap + kirim email peringatan
- **MQTT Integration** — komunikasi real-time dengan ESP32 RFID reader
- **WebSocket Support** — notifikasi real-time ke web clients
- **Mock Mode** — simulasi RFID dan MQTT untuk development tanpa hardware

---

## CV Benchmark (Branch: cvtest)

> **⚠️ EXPERIMENTAL FEATURE**  
> Branch `cvtest` berisi fitur **Computer Vision Benchmark** untuk testing face recognition pada Raspberry Pi 4B.

### Quick Access

```bash
git checkout cvtest
```

### Apa itu CV Benchmark?

Modul testing mandiri untuk mengevaluasi performa Computer Vision (face recognition) pada Raspberry Pi:
- **Live Monitor**: Stream kamera dengan dynamic sidebar panels
  - Panel Resolusi: Selector untuk mengubah resolusi (240p-1080p) dengan status available/disabled
  - Panel Performa: FPS counter real-time dan resolusi aktif
  - Panel Sistem: Progress bars untuk CPU, RAM, Temperature dengan auto warnings (CPU >90%, Temp ≥70°C)
- **Face Recognition**: Capture foto referensi + live matching realtime (dlib HOG + ResNet)
- **Multi-resolution**: Test dari 240p sampai 1080p dengan auto-probing saat kamera dibuka
- **Real-time Stats**: Semua metrics terupdate setiap 1 detik via polling `/cv/stats` endpoint

### Quick Start (Laptop Testing)

```bash
# 1. Checkout branch
git checkout cvtest

# 2. Install CV dependencies
pip install opencv-python face-recognition psutil

# 3. Jalankan Flask (database setup sama seperti main branch)
python app.py

# 4. Buka browser
# http://localhost:5000 → Klik "CV Benchmark (Beta)"
```

**TIDAK BUTUH:**
- ✗ RFID hardware
- ✗ MQTT broker
- ✗ ESP32
- ✗ Seed data (student/tool)

**HANYA BUTUH:**
- ✓ Kamera (webcam/laptop camera)
- ✓ PostgreSQL (minimal setup)
- ✓ Python dependencies

### Performance Benchmark Results

Expected performance pada **Raspberry Pi 4B (4GB RAM)**:

| Resolusi | Face Rec FPS | CPU Load | Recommendation |
|----------|--------------|----------|----------------|
| 240p     | 15-20        | 30-40%   | ⚡ Very fast, low accuracy |
| 360p     | 12-15        | 40-50%   | ✅ Good balance |
| **480p** | **8-12**     | **50-65%** | **⭐ RECOMMENDED** |
| 720p     | 5-8          | 70-85%   | 🔥 High CPU usage |
| 1080p    | 2-4          | 85-95%   | ❌ Too slow |

### Dokumentasi Lengkap

📖 **[QUICKSTART_CV_BENCHMARK.md](QUICKSTART_CV_BENCHMARK.md)** — Panduan testing step-by-step (laptop & RPi)  
📖 **[docs/CV_BENCHMARK.md](docs/CV_BENCHMARK.md)** — Dokumentasi teknis lengkap

---

## Arsitektur Sistem

### Mode Development (Mock)
```
┌─────────────────┐
│   Flask App     │
│  (Mock Mode)    │◄─── Browser Console (simulateRFID)
│                 │
│ - Mock MQTT     │
│ - Mock RFID     │
└─────────────────┘
```

### Mode Production (Real Hardware)
```
┌─────────────┐        MQTT           ┌──────────────┐        WebSocket        ┌──────────────┐
│  ESP32 #1   │────rfid/scan─────────▶│   Flask App  │────────────────────────▶│ Web Clients  │
│ RFID Reader │   (QoS 1)             │  + Mosquitto │   (Real-time updates)   │  (Browser)   │
└─────────────┘                       │              │                         └──────────────┘
                                      │              │
┌─────────────┐        MQTT           │              │
│  ESP32 #2   │────sensor/*──────────▶│              │
│  Sensors    │   (QoS 0)             │              │
└─────────────┘                       └──────────────┘
                                              │
                                       ┌──────┴──────┐
                                       │ PostgreSQL  │
                                       │  Database   │
                                       └─────────────┘
```

### MQTT Topics

| Topic | Direction | QoS | Deskripsi |
|-------|-----------|-----|-----------|
| `rfid/scan` | ESP32 → Server | 1 | RFID card scans |
| `transaction/update` | Server → Clients | 1 | Borrow/return events |
| `tool/status` | Server → Clients | 1 | Tool availability |
| `sensor/*` | ESP32 → Server | 0 | Sensor data (temp, humidity, etc.) |

---

## Arsitektur Proyek

```
tpt-rfid/
├── app.py                     # Aplikasi Flask utama (dengan MQTT integration)
├── config.py                  # Konfigurasi (dev/production + MQTT)
├── seed_database.py           # Script seed data testing
├── setup.sh                   # Script setup otomatis
├── requirements.txt           # Dependensi Python (base)
├── requirements-mqtt.txt      # Dependensi MQTT (optional)
├── .env                       # Environment variables
├── .env.example               # Template environment variables
│
├── templates/                 # HTML templates (Jinja2)
│   ├── base.html
│   ├── landing.html           # Halaman landing (pilih role)
│   ├── welcome.html           # Menu mahasiswa
│   ├── register.html          # Form registrasi
│   ├── scan.html              # Halaman scan pinjam/kembali
│   ├── monitor.html           # Monitor alat (publik)
│   ├── admin_welcome.html     # Menu admin
│   └── admin_monitor.html     # Monitor alat (admin)
│
├── static/
│   ├── css/                   # Stylesheet
│   ├── js/                    # JavaScript
│   └── assets/                # Gambar dan ikon
│
├── utils/
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy models (Student, Tool, Transaction)
│   ├── database_handler.py    # Operasi CRUD PostgreSQL
│   ├── mqtt_client.py         # MQTT client (Mock + Real)
│   ├── websocket_handler.py   # WebSocket handler (Mock + Real)
│   ├── rfid_mock.py           # Simulasi RFID reader
│   └── helpers.py             # Fungsi utilitas
│
├── scripts/
│   ├── install_mosquitto.sh   # Install Mosquitto broker
│   ├── test_mqtt.sh           # Test MQTT broker
│   ├── test_mqtt_integration.py # Test MQTT dengan app
│   ├── migrate_database.sh    # Migrate dari Firebase
│   └── verify_database.py     # Verifikasi database
│
└── docs/
    ├── MIGRATION_SUMMARY.md   # Summary migrasi & setup
    ├── MQTT_SETUP.md          # Panduan setup MQTT
    ├── ESP32_CLIENT_GUIDE.md  # Panduan programming ESP32
    ├── DEPLOYMENT.md          # Panduan deployment production
    └── TROUBLESHOOTING.md     # Troubleshooting guide
```

---

## Setup Otomatis (Recommended)

Kami menyediakan script installer otomatis untuk Raspberry Pi dan Ubuntu/Debian. Script ini akan:
1. Update sistem
2. Install dependencies (Python, PostgreSQL, dll)
3. Setup database dan user PostgreSQL otomatis
4. Clone/Update repository
5. Setup Python environment
6. Setup auto-start service (systemd)
7. Setup Kiosk mode (opsional)

**Cara Pakai:**

Download script installer:
```bash
wget https://raw.githubusercontent.com/Naktekfis/tpt-rfid/main/tpt-rfid-installer.sh
chmod +x tpt-rfid-installer.sh
./tpt-rfid-installer.sh
```

Ikuti instruksi di layar.

---

## Setup di Laptop (Development)

Panduan ini untuk development di laptop/PC biasa (Linux, macOS, atau WSL di Windows).
RFID disimulasikan via browser console.

### Langkah 1 — Install Prerequisites

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git postgresql postgresql-contrib -y
```

**macOS (Homebrew):**
```bash
brew install python3 git postgresql@14
brew services start postgresql@14
```

**Windows:**
Gunakan WSL2 (Windows Subsystem for Linux), lalu ikuti langkah Ubuntu di atas.

### Langkah 2 — Setup PostgreSQL

```bash
# Masuk ke PostgreSQL sebagai superuser
sudo -u postgres psql
```

Di dalam prompt `psql`, jalankan:
```sql
-- Buat role untuk user kamu (ganti 'namauser' dan 'passwordmu')
CREATE ROLE namauser WITH LOGIN CREATEDB PASSWORD 'passwordmu';

-- Buat database
CREATE DATABASE tpt_rfid OWNER namauser;

-- Keluar
\q
```

> **Catatan:** `namauser` harus sesuai dengan username yang akan kamu pakai untuk
> menjalankan aplikasi. Jika username Linux kamu `ahmad`, maka buat role `ahmad`.

### Langkah 3 — Clone Repository

```bash
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
```

### Langkah 4 — Setup Python Environment

```bash
# Buat virtual environment
python3 -m venv venv

# Aktifkan virtual environment
source venv/bin/activate

# Install dependensi
pip install --upgrade pip
pip install -r requirements.txt
```

### Langkah 5 — Konfigurasi Environment Variables

```bash
cp .env.example .env
```

Edit file `.env`:
```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=ganti-dengan-random-string

# Sesuaikan dengan role PostgreSQL yang sudah dibuat
DATABASE_URL=postgresql://namauser:passwordmu@localhost/tpt_rfid

# PIN untuk akses admin panel (bebas, contoh: 1234)
ADMIN_PIN=1234
```

### Langkah 6 — Inisialisasi Database

```bash
# Jalankan migrasi database (membuat tabel)
flask db upgrade

# (Opsional) Isi data sample untuk testing
python seed_database.py
```

> Jika folder `migrations/` belum ada di repo, jalankan dulu:
> ```bash
> flask db init
> flask db migrate -m "initial"
> flask db upgrade
> ```

### Langkah 7 — Jalankan Aplikasi

```bash
python app.py
```

Buka browser: **http://localhost:5000**

> **Catatan MQTT:** Secara default, aplikasi berjalan dalam **mock mode** (tidak perlu MQTT broker).
> Untuk mengaktifkan MQTT, lihat [Setup MQTT & ESP32](#setup-mqtt--esp32).

### Simulasi RFID (Development)

Karena di laptop tidak ada hardware RFID, gunakan browser console (F12):

```javascript
// Simulasi scan kartu mahasiswa
simulateRFID('STUDENT001')

// Simulasi scan tag alat
simulateRFID('TOOL001')

// Clear RFID
clearRFID()
```

Atau lewat URL (hanya mode development):
```
http://localhost:5000/debug/scan?uid=STUDENT001
```

---

## Setup MQTT & ESP32

Sistem mendukung dua mode operasi:

### Mode 1: Mock Mode (Default - Development)

**Tidak perlu MQTT broker atau ESP32.** Semua operasi MQTT di-log saja.

```bash
# Di .env (default):
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false

# Jalankan app
python app.py

# Logs akan menampilkan:
# [MOCK] MQTT Client initialized
# [MOCK] WebSocket handler initialized
```

### Mode 2: Real MQTT (Production)

**Butuh Mosquitto broker dan ESP32.**

#### Step 1: Install Mosquitto

```bash
# Install Mosquitto MQTT broker
sudo ./scripts/install_mosquitto.sh

# Verifikasi service running
sudo systemctl status mosquitto

# Test MQTT broker
./scripts/test_mqtt.sh
```

Service akan berjalan di:
- Port `1883` - MQTT (TCP)
- Port `8083` - WebSocket

#### Step 2: Install Dependencies MQTT

```bash
source venv/bin/activate
pip install -r requirements-mqtt.txt
```

Dependencies yang diinstall:
- `paho-mqtt` - MQTT client library
- `flask-socketio` - WebSocket support
- `python-socketio` - Socket.IO client

#### Step 3: Enable MQTT di .env

```bash
# Edit .env
MQTT_ENABLED=true
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID=tpt-rfid-server

# Optional: WebSocket untuk real-time updates ke browser
WEBSOCKET_ENABLED=true
```

#### Step 4: Test MQTT Integration

```bash
# Terminal 1: Jalankan Flask app
python app.py

# Terminal 2: Test dengan simulator ESP32
./scripts/test_mqtt_integration.py
```

Jika berhasil, logs Flask app akan menampilkan:
```
MQTT client connected successfully
Subscribed to MQTT topics
MQTT RFID scan received: 1234567890 from esp32_01
Student identified: Ahmad Fauzi (NIM: 1234567890)
```

#### Step 5: Programming ESP32

Lihat dokumentasi lengkap di [docs/ESP32_CLIENT_GUIDE.md](docs/ESP32_CLIENT_GUIDE.md)

**Quick Start:**

1. Install Arduino IDE + library:
   - `PubSubClient` (MQTT)
   - `MFRC522` (RFID reader)
   - `ArduinoJson`

2. Upload code ke ESP32 (contoh di docs)

3. Konfigurasi WiFi dan MQTT broker:
   ```cpp
   const char* mqtt_server = "192.168.1.100";  // IP Raspberry Pi
   const char* mqtt_topic = "rfid/scan";
   ```

4. ESP32 akan publish RFID scans ke broker

**Hardware yang dibutuhkan:**
- ESP32 Dev Board
- MFRC522 RFID Reader Module
- RFID cards/tags
- Jumper wires

**Wiring:**
```
MFRC522 → ESP32
SDA     → GPIO 21
SCK     → GPIO 18
MOSI    → GPIO 23
MISO    → GPIO 19
IRQ     → (not connected)
GND     → GND
RST     → GPIO 22
3.3V    → 3.3V
```

### Mode Switching

Untuk berpindah antara mock dan real mode, cukup ubah `.env`:

```bash
# Development (mock mode)
MQTT_ENABLED=false

# Production (real mode)
MQTT_ENABLED=true
```

Tidak perlu ubah code. Aplikasi otomatis menggunakan mock atau real client berdasarkan config.

---

## Setup di Raspberry Pi (Production)

Panduan ini untuk deployment di Raspberry Pi sebagai kiosk station di Lab Fabrikasi.
Diasumsikan menggunakan Raspberry Pi OS (Debian-based).

### Langkah 1 — Update Sistem dan Install Prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git postgresql postgresql-contrib -y
```

### Langkah 2 — Setup PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE pi WITH LOGIN CREATEDB PASSWORD 'ganti-password-ini';
CREATE DATABASE tpt_rfid OWNER pi;
\q
```

> Ganti `pi` dengan username Raspberry Pi kamu jika berbeda.

### Langkah 3 — Clone Repository

```bash
cd ~
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
```

### Langkah 4 — Setup Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Langkah 5 — Konfigurasi Environment Variables

```bash
cp .env.example .env
nano .env
```

Isi `.env` untuk production:
```env
FLASK_ENV=production
DEBUG=False
SECRET_KEY=ganti-dengan-random-string-panjang-dan-acak

DATABASE_URL=postgresql://pi:ganti-password-ini@localhost/tpt_rfid

ADMIN_PIN=pin-admin-yang-aman

# (Opsional) Konfigurasi email untuk kirim peringatan
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=email-lab@gmail.com
MAIL_PASSWORD=app-password-gmail
MAIL_DEFAULT_SENDER=email-lab@gmail.com
```

> **Tips:** Untuk `SECRET_KEY`, generate random string:
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```

### Langkah 6 — Inisialisasi Database

```bash
source venv/bin/activate

flask db upgrade

# (Opsional) Seed data awal
python seed_database.py
```

### Langkah 7 — Test Manual

```bash
# Jalankan sekali untuk memastikan tidak ada error
python app.py
```

Buka browser di Raspberry Pi: **http://localhost:5000** — pastikan halaman muncul.
Tekan `Ctrl+C` untuk stop.

### Langkah 8 — Setup systemd Service (Auto-start)

Buat service file agar aplikasi jalan otomatis saat boot:

```bash
sudo nano /etc/systemd/system/tpt-rfid.service
```

Paste konfigurasi berikut (sesuaikan `User` dan path jika perlu):

```ini
[Unit]
Description=TPT RFID Tool Monitoring System
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=pi
WorkingDirectory=/home/pi/tpt-rfid
Environment="PATH=/home/pi/tpt-rfid/venv/bin:/usr/bin"
ExecStart=/home/pi/tpt-rfid/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Aktifkan dan jalankan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tpt-rfid
sudo systemctl start tpt-rfid
```

Cek status:
```bash
sudo systemctl status tpt-rfid
```

### Langkah 9 — (Opsional) Setup Kiosk Mode

Agar Raspberry Pi langsung membuka browser fullscreen ke aplikasi saat boot:

```bash
# Install Chromium jika belum ada
sudo apt install chromium-browser -y
```

Buat autostart file:
```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/kiosk.desktop
```

Paste:
```ini
[Desktop Entry]
Type=Application
Name=TPT RFID Kiosk
Exec=chromium-browser --kiosk --disable-restore-session-state http://localhost:5000
X-GNOME-Autostart-enabled=true
```

Agar layar tidak mati otomatis:
```bash
# Disable screen blanking
sudo nano /etc/lightdm/lightdm.conf
```

Tambahkan di bawah `[Seat:*]`:
```
xserver-command=X -s 0 -dpms
```

Reboot untuk test:
```bash
sudo reboot
```

---

## Seed Data (Opsional)

Script `seed_database.py` menambahkan data sample untuk testing. Aman dijalankan berkali-kali (skip data yang sudah ada).

```bash
source venv/bin/activate
python seed_database.py
```

**Data sample yang ditambahkan:**

| Mahasiswa        | UID        | NIM        |
|------------------|------------|------------|
| Ahmad Fauzi      | STUDENT001 | 1234567890 |
| Siti Nurhaliza   | STUDENT002 | 0987654321 |
| Budi Santoso     | STUDENT003 | 1122334455 |
| Dewi Lestari     | STUDENT004 | 5544332211 |
| Rizki Pratama    | STUDENT005 | 6677889900 |

| Alat             | UID    | Kategori      |
|------------------|--------|---------------|
| Drill Machine    | TOOL001| Power Tools   |
| Angle Grinder    | TOOL002| Power Tools   |
| Soldering Iron   | TOOL003| Electronics   |
| Multimeter Digital| TOOL004| Electronics  |
| Circular Saw     | TOOL005| Power Tools   |
| Oscilloscope     | TOOL006| Electronics   |
| Impact Driver    | TOOL007| Power Tools   |
| Hot Air Station  | TOOL008| Electronics   |
| Belt Sander      | TOOL009| Power Tools   |
| Wire Stripper Set| TOOL010| Hand Tools    |

---

## Cara Penggunaan Aplikasi

### Registrasi Mahasiswa Baru

1. Buka aplikasi, pilih **Mahasiswa**
2. Pilih **Registrasi**
3. Isi form: nama, NIM, email, telepon
4. Upload foto
5. Tap kartu RFID (atau `simulateRFID('UID')` di console untuk development)
6. Klik **Daftar**

### Pinjam Alat

1. Pilih **Sudah Punya Akun** dari menu mahasiswa
2. Tap kartu mahasiswa (scan RFID)
3. Tap tag alat yang ingin dipinjam
4. Klik **Confirm Pinjam**

### Kembalikan Alat

1. Buka halaman **Scan**
2. Tap kartu mahasiswa
3. Tap tag alat yang dikembalikan
4. Klik **Confirm Kembalikan**

### Monitor Alat

- Halaman **/monitor** — lihat status semua alat (publik)
- Halaman **/admin** — masuk admin panel, lihat info peminjam lengkap dan kirim email peringatan

---

## Environment Variables

| Variable | Wajib | Deskripsi | Contoh |
|----------|-------|-----------|--------|
| `DATABASE_URL` | Ya | URL koneksi PostgreSQL | `postgresql://user:pass@localhost/tpt_rfid` |
| `SECRET_KEY` | Ya | Secret key Flask session | random string panjang |
| `FLASK_ENV` | Tidak | Mode aplikasi | `development` / `production` |
| `ADMIN_PIN` | Ya | PIN untuk admin API | `BLlVwramuPg` |
| `MQTT_ENABLED` | Tidak | Enable MQTT client | `true` / `false` (default: false) |
| `MQTT_BROKER_HOST` | Tidak | MQTT broker hostname | `localhost` |
| `MQTT_BROKER_PORT` | Tidak | MQTT broker port | `1883` |
| `MQTT_CLIENT_ID` | Tidak | Client ID untuk MQTT | `tpt-rfid-server` |
| `MQTT_USERNAME` | Tidak | Username MQTT (optional) | `mqtt_user` |
| `MQTT_PASSWORD` | Tidak | Password MQTT (optional) | `mqtt_pass` |
| `WEBSOCKET_ENABLED` | Tidak | Enable WebSocket | `true` / `false` (default: false) |
| `WEBSOCKET_CORS_ORIGINS` | Tidak | CORS origins untuk WS | `*` (dev), `https://domain.com` (prod) |
| `MAIL_SERVER` | Tidak | SMTP server | `smtp.gmail.com` |
| `MAIL_PORT` | Tidak | SMTP port | `587` |
| `MAIL_USE_TLS` | Tidak | Gunakan TLS | `True` |
| `MAIL_USERNAME` | Tidak | Email pengirim | `lab@gmail.com` |
| `MAIL_PASSWORD` | Tidak | Password / app password | `xxxx-xxxx-xxxx` |
| `MAIL_DEFAULT_SENDER` | Tidak | Default sender | `lab@gmail.com` |

### Contoh .env Development (Mock Mode)

```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
DATABASE_URL=postgresql://ahmad:password@localhost/tpt_rfid
ADMIN_PIN=1234

# MQTT & WebSocket (disabled by default)
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false
```

### Contoh .env Production (Real MQTT)

```env
FLASK_ENV=production
DEBUG=False
SECRET_KEY=449840b0530d247ccf6e3772e21174aa43b177e00061a192423075f632d37855
DATABASE_URL=postgresql://pi:secure_password@localhost/tpt_rfid
ADMIN_PIN=secure_pin_here

# MQTT & WebSocket (enabled for production)
MQTT_ENABLED=true
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID=tpt-rfid-server

# Enable WebSocket for real-time updates
WEBSOCKET_ENABLED=true
WEBSOCKET_CORS_ORIGINS=*

# Email notifications
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=lab@itb.ac.id
MAIL_PASSWORD=app_password_here
MAIL_DEFAULT_SENDER=lab@itb.ac.id
```

---

## Troubleshooting

### PostgreSQL tidak bisa konek

```bash
# Cek PostgreSQL berjalan
sudo systemctl status postgresql

# Restart jika perlu
sudo systemctl restart postgresql

# Cek apakah role dan database sudah ada
sudo -u postgres psql -c "\du"          # list roles
sudo -u postgres psql -c "\l"           # list databases
```

### Port 5000 sudah dipakai

```bash
sudo lsof -i :5000
sudo kill -9 <PID>
```

### Migrasi gagal

```bash
# Reset migrasi (HATI-HATI: hapus semua data)
flask db downgrade base
flask db upgrade

# Atau drop dan buat ulang database
sudo -u postgres psql -c "DROP DATABASE tpt_rfid;"
sudo -u postgres psql -c "CREATE DATABASE tpt_rfid OWNER namauser;"
flask db upgrade
python seed_database.py
```

### Service tidak start di Raspberry Pi

```bash
# Lihat log error
sudo journalctl -u tpt-rfid -f

# Cek apakah PostgreSQL sudah ready sebelum service start
sudo systemctl status postgresql
```

### Permission denied

```bash
chmod +x app.py setup.sh
```

### MQTT tidak konek

```bash
# Cek Mosquitto service
sudo systemctl status mosquitto

# Restart Mosquitto
sudo systemctl restart mosquitto

# Test koneksi MQTT
mosquitto_sub -h localhost -t '#' -v

# Cek port listening
ss -tlnp | grep -E '1883|8083'

# Lihat logs Mosquitto
sudo journalctl -u mosquitto -f
```

### ESP32 tidak bisa publish

```bash
# Test dari laptop dulu
mosquitto_pub -h <raspberry-pi-ip> -t rfid/scan -m '{"rfid_uid":"test"}'

# Cek firewall
sudo ufw status
sudo ufw allow 1883
sudo ufw allow 8083

# Verify network
ping <raspberry-pi-ip>
```

### App tidak menerima MQTT messages

```bash
# Verifikasi MQTT_ENABLED=true di .env
cat .env | grep MQTT_ENABLED

# Install dependencies MQTT
pip install -r requirements-mqtt.txt

# Test dengan simulator
./scripts/test_mqtt_integration.py

# Cek logs Flask app
# Seharusnya ada: "MQTT client connected successfully"
```

### ModuleNotFoundError: No module named 'paho'

```bash
# Install MQTT dependencies
pip install -r requirements-mqtt.txt

# Atau install manual
pip install paho-mqtt flask-socketio
```

---

## Dokumentasi Lengkap

Dokumentasi detail tersedia di folder `docs/`:

- **[MIGRATION_SUMMARY.md](docs/MIGRATION_SUMMARY.md)** - Summary lengkap migrasi database & MQTT setup
- **[MQTT_SETUP.md](docs/MQTT_SETUP.md)** - Panduan setup Mosquitto broker step-by-step
- **[ESP32_CLIENT_GUIDE.md](docs/ESP32_CLIENT_GUIDE.md)** - Programming ESP32 dengan RFID reader
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Deployment ke Raspberry Pi production
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Troubleshooting guide lengkap
- **[CV_BENCHMARK.md](docs/CV_BENCHMARK.md)** - 🆕 CV Benchmark technical documentation (branch: cvtest)

### CV Benchmark Quick Links

- **[QUICKSTART_CV_BENCHMARK.md](QUICKSTART_CV_BENCHMARK.md)** - 🚀 Quick start guide untuk testing CV
- **[CV_INTEGRATION_CHECKLIST.md](CV_INTEGRATION_CHECKLIST.md)** - Checklist integrasi untuk developer

### Quick Links

- Test MQTT broker: `./scripts/test_mqtt.sh`
- Test MQTT integration: `./scripts/test_mqtt_integration.py`
- Migrate from Firebase: `./scripts/migrate_database.sh`
- Verify database: `./scripts/verify_database.py`

---

## Keamanan

Sebelum deploy ke production:

1. Ganti `SECRET_KEY` dengan random string yang panjang
2. Set `FLASK_ENV=production` dan `DEBUG=False`
3. Ganti password PostgreSQL default
4. Set `ADMIN_PIN` yang aman
5. Jangan commit file `.env` ke git (sudah ada di `.gitignore`)

---

## Lisensi

MIT License

---

Lab Fabrikasi Teknik Fisika ITB

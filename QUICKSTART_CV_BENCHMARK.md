# QUICKSTART — CV Benchmark Testing

> **Branch:** `cvtest`  
> **Purpose:** Testing fitur Computer Vision (face recognition) untuk mengevaluasi performa Raspberry Pi 4B

## 📋 Overview

CV Benchmark adalah **fitur testing terpisah** dari sistem RFID utama. Fitur ini untuk:
- Mengukur FPS kamera pada berbagai resolusi (240p - 1080p)
- Testing face recognition realtime (dlib HOG + ResNet)
- Monitoring load sistem (CPU %, RAM %, suhu °C)
- Evaluasi apakah RPi 4B cukup powerful untuk face recognition

**PENTING:** Fitur ini **TIDAK butuh database, MQTT, atau RFID hardware**. Hanya butuh:
- Kamera (webcam USB atau laptop camera)
- Python environment dengan dependencies CV

---

## 🚀 Quick Start (Laptop / PC Development)

**Untuk testing cepat tanpa database dan MQTT.**

### Step 1: Clone Repository & Checkout Branch

```bash
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest
```

### Step 2: Setup Python Environment

```bash
# Buat virtual environment
python3 -m venv venv

# Aktifkan venv
source venv/bin/activate

# Install dependencies BASE (Flask, PostgreSQL, dll)
pip install -r requirements.txt

# Install dependencies CV Benchmark
pip install opencv-python face-recognition psutil
```

**Total install time:** ~2-5 menit (tergantung koneksi internet)

### Step 3: Setup Database Minimal (Required by Flask app)

CV Benchmark sendiri tidak butuh database, tapi `app.py` memerlukan PostgreSQL untuk inisialisasi.

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y

# Setup database
sudo -u postgres psql
```

Di prompt `psql`:
```sql
CREATE ROLE yourusername WITH LOGIN CREATEDB PASSWORD 'yourpassword';
CREATE DATABASE tpt_rfid OWNER yourusername;
\q
```

**macOS (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14

# Setup database (ganti 'yourusername')
psql postgres
CREATE DATABASE tpt_rfid;
\q
```

**Buat file `.env`:**
```bash
cp .env.example .env
```

Edit `.env` (minimal config):
```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=dev-secret-key-for-testing

# Sesuaikan dengan username/password PostgreSQL kamu
DATABASE_URL=postgresql://yourusername:yourpassword@localhost/tpt_rfid

# Pin admin (bebas, tidak penting untuk CV Benchmark)
ADMIN_PIN=1234

# MQTT/WebSocket DISABLED (tidak perlu untuk CV testing)
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false
```

**Run migrasi database:**
```bash
flask db upgrade
```

> **Skip seed data** — tidak perlu student/tool data untuk CV Benchmark

### Step 4: Test Kamera

Sebelum jalankan Flask, cek apakah kamera terdeteksi:

```bash
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('Kamera OK:', cap.isOpened()); cap.release()"
```

Expected output: `Kamera OK: True`

Jika `False`, pastikan:
- Webcam terpasang dengan benar
- Tidak ada aplikasi lain yang pakai kamera (Zoom, Skype, dll.)
- Di Linux, user punya akses ke `/dev/video0`: `ls -l /dev/video0`

### Step 5: Jalankan Flask App

```bash
python app.py
```

Output yang diharapkan:
```
 * Running on http://0.0.0.0:5000
 * PostgreSQL database handler initialized successfully
 * CV Benchmark blueprint registered
 * MQTT disabled - using mock mode
```

### Step 6: Buka Browser & Test

1. Buka **http://localhost:5000**
2. Di landing page, scroll ke bawah → klik **"CV Benchmark (Beta)"**
3. Pilih salah satu:
   - **Live Monitor** → stream kamera langsung + FPS counter
   - **Face Recognition** → ambil foto referensi → live matching

---

## 🧪 Testing Checklist

### Test 1: Live Monitor
- [ ] Kamera stream muncul (gambar realtime)
- [ ] FPS counter terlihat di pojok kanan atas frame
- [ ] Sidebar stats menampilkan nilai CPU, RAM, suhu (update ~1 detik sekali)
- [ ] Dropdown resolusi di top bar berfungsi
- [ ] Ganti resolusi → stream restart dengan resolusi baru
- [ ] Resolusi yang tidak didukung kamera di-disable (opacity rendah)

### Test 2: Face Recognition
**Fase Capture:**
- [ ] Stream preview muncul dengan overlay lingkaran panduan
- [ ] Klik "📸 Ambil Foto Referensi" → foto ter-capture
- [ ] Jika tidak ada wajah → muncul error message "Tidak ada wajah terdeteksi"

**Fase Recognition:**
- [ ] Stream berganti ke mode recognition
- [ ] Wajah terdeteksi → muncul bounding box
- [ ] Jika match dengan foto referensi → box hijau + "COCOK XX%"
- [ ] Jika tidak match → box merah + "TIDAK XX%"
- [ ] Tombol "Coba Lagi" → threshold turun (0.50 → 0.55 → 0.60)
- [ ] Tombol "Ulang dari Awal" → kembali ke fase capture

### Test 3: Performance Benchmark

**Low resolution (240p):**
- Target FPS: >20
- CPU load: <50%

**Medium resolution (480p):**
- Target FPS: 10-15 (laptop), 8-12 (RPi)
- CPU load: 50-70%

**High resolution (720p):**
- Target FPS: 5-10 (laptop), 3-7 (RPi)
- CPU load: 70-90%

---

## 🍓 Raspberry Pi 4B Setup

**Untuk testing di Raspberry Pi target production.**

### Prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git postgresql postgresql-contrib -y
sudo apt install cmake build-essential libopenblas-dev liblapack-dev -y
```

### Setup Database (sama seperti laptop)

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE pi WITH LOGIN CREATEDB PASSWORD 'password';
CREATE DATABASE tpt_rfid OWNER pi;
\q
```

### Clone & Setup Python

```bash
cd ~
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest

python3 -m venv venv
source venv/bin/activate

# Install dependencies base
pip install -r requirements.txt
```

### Install CV Dependencies (⚠️ PENTING — Lama!)

**Kompilasi dlib membutuhkan ~20-30 menit di RPi 4B.**

```bash
# OPTIONAL: Tambah swap jika RAM < 2GB
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Ubah: CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Install dlib (ini yang lama)
pip install dlib --break-system-packages

# Kalau berhasil, install sisanya
pip install opencv-python face-recognition psutil --break-system-packages
```

**Verify installation:**
```bash
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"
python3 -c "import face_recognition; print('face_recognition: OK')"
python3 -c "import psutil; print('psutil: OK')"
```

### Setup .env

```bash
cp .env.example .env
nano .env
```

Isi:
```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=dev-secret

DATABASE_URL=postgresql://pi:password@localhost/tpt_rfid

ADMIN_PIN=1234
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false
```

### Jalankan Migrasi & App

```bash
flask db upgrade
python app.py
```

Buka browser di RPi: **http://localhost:5000** → CV Benchmark

---

## ⚠️ Troubleshooting

### Kamera tidak terbuka

**Error:** "Kamera tidak dapat dibuka"

**Solusi:**
```bash
# Cek device kamera
ls -l /dev/video*

# Test manual
python3 -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"

# RPi Camera Module (CSI) → perlu enable
sudo raspi-config
# Interface Options → Camera → Enable
sudo modprobe bcm2835-v4l2

# Reboot
sudo reboot
```

### FPS sangat rendah (<5 FPS)

**Penyebab:**
- Resolusi terlalu tinggi (coba 360p atau 480p)
- CPU throttling (overheating)
- Background process berat

**Solusi:**
```bash
# Cek suhu CPU (RPi)
vcgencmd measure_temp

# Tutup aplikasi lain
pkill chromium

# Turunkan resolusi di UI
```

### Face recognition tidak match (false negative)

**Penyebab:**
- Pencahayaan berbeda antara foto capture vs live stream
- Sudut wajah berbeda
- Threshold terlalu ketat

**Solusi:**
1. Ambil foto referensi dengan pencahayaan yang sama dengan live stream
2. Posisi wajah tegak, langsung ke kamera
3. Gunakan tombol "Coba Lagi" 2-3 kali (threshold akan turun)

### Import error: No module named 'cv2'

```bash
pip install opencv-python
```

### Import error: No module named 'face_recognition'

```bash
pip install face-recognition

# Jika error "No module named 'dlib'":
pip install dlib
# Atau di RPi:
pip install dlib --break-system-packages
```

### Dlib compilation failed (RPi)

**Error:** "Killed" atau "virtual memory exhausted"

**Solusi:** Tambah swap size (lihat section "Install CV Dependencies" di atas)

### Database error saat start app

**Error:** "FATAL: role 'yourusername' does not exist"

**Solusi:**
```bash
# Buat role PostgreSQL
sudo -u postgres psql
CREATE ROLE yourusername WITH LOGIN CREATEDB PASSWORD 'yourpassword';
\q

# Update .env dengan credentials yang benar
```

---

## 📊 Expected Performance (Raspberry Pi 4B, 4GB RAM)

| Resolusi | Live Monitor FPS | Face Rec FPS | CPU Load | RAM Usage |
|----------|------------------|--------------|----------|-----------|
| 240p     | 25-30            | 15-20        | 30-40%   | ~500MB    |
| 360p     | 20-25            | 12-15        | 40-50%   | ~600MB    |
| 480p     | 15-20            | 8-12         | 50-65%   | ~700MB    |
| 720p     | 10-15            | 5-8          | 70-85%   | ~900MB    |
| 1080p    | 5-10             | 2-4          | 85-95%   | ~1.2GB    |

**Rekomendasi untuk production:** 480p (balance antara akurasi dan performa)

---

## 🎯 Kesimpulan Testing

Setelah testing selesai, laporkan hasil:

**Laptop (untuk baseline comparison):**
- [ ] Live Monitor berhasil, FPS: ___
- [ ] Face Recognition berhasil, akurasi: baik / cukup / buruk
- [ ] Resolusi optimal: ___

**Raspberry Pi 4B (target production):**
- [ ] Live Monitor berhasil, FPS: ___
- [ ] Face Recognition berhasil, akurasi: baik / cukup / buruk
- [ ] Resolusi optimal: ___
- [ ] Load CPU stabil < 80%: ya / tidak
- [ ] Suhu CPU < 70°C: ya / tidak

**Kesimpulan:** RPi 4B layak / tidak layak untuk face recognition realtime

---

## 🔄 Kembali ke Main Branch

Setelah testing CV Benchmark selesai, untuk kembali ke branch `main`:

```bash
git checkout main
```

CV Benchmark hanya ada di branch `cvtest` dan tidak mengganggu branch `main` (production).

---

## 📖 Dokumentasi Lengkap

- **CV_BENCHMARK.md** — Dokumentasi teknis lengkap (model stack, API endpoints, troubleshooting)
- **CV_INTEGRATION_CHECKLIST.md** — Checklist integrasi untuk developer

---

**Happy Testing!** 🚀

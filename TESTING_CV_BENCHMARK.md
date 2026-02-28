# 🎯 TESTING INSTRUCTIONS — CV Benchmark (Branch: cvtest)

> **Untuk Tim Testing**  
> Dokumen ini menjelaskan cara testing fitur CV Benchmark di laptop ATAU Raspberry Pi.

---

## 📌 Informasi Penting

**Branch:** `cvtest`  
**Tujuan:** Testing face recognition untuk evaluasi performa Raspberry Pi 4B  
**Status:** Experimental / Beta  

**Fitur ini TERPISAH dari sistem RFID utama:**
- ✗ Tidak perlu RFID hardware
- ✗ Tidak perlu MQTT broker
- ✗ Tidak perlu ESP32
- ✗ Tidak perlu seed data mahasiswa/alat
- ✓ **Hanya butuh: Kamera + PostgreSQL minimal + Python dependencies**

---

## 🚀 Option 1: Testing di Laptop (Recommended untuk Quick Test)

**Waktu setup:** ~10-15 menit (tergantung koneksi internet)  
**Kegunaan:** Quick testing, development, baseline comparison

### Step-by-Step

#### 1. Clone & Checkout Branch

```bash
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest
```

#### 2. Install PostgreSQL (Jika Belum Ada)

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y
```

**macOS (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14
```

#### 3. Setup Database Minimal

```bash
sudo -u postgres psql
```

Di prompt `psql`:
```sql
-- Ganti 'yourname' dengan username Linux kamu
CREATE ROLE yourname WITH LOGIN CREATEDB PASSWORD 'password123';
CREATE DATABASE tpt_rfid OWNER yourname;
\q
```

#### 4. Setup Python Environment

```bash
# Buat virtual environment
python3 -m venv venv

# Aktifkan
source venv/bin/activate

# Install base dependencies
pip install -r requirements.txt

# Install CV Benchmark dependencies
pip install opencv-python face-recognition psutil
```

**Perhatian:** Install `face-recognition` akan download dlib (~100MB). Total waktu: 2-5 menit.

#### 5. Konfigurasi .env

```bash
cp .env.example .env
nano .env
```

Isi minimal (ganti `yourname` dan `password123` sesuai step 3):
```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=dev-testing-key

DATABASE_URL=postgresql://yourname:password123@localhost/tpt_rfid

ADMIN_PIN=1234
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false
```

#### 6. Migrasi Database

```bash
flask db upgrade
```

**SKIP seed data** — tidak perlu untuk CV Benchmark.

#### 7. Test Kamera (PENTING!)

Sebelum jalankan Flask, pastikan kamera terdeteksi:

```bash
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('Kamera OK:', cap.isOpened()); cap.release()"
```

Expected: `Kamera OK: True`

Jika `False`:
- Pastikan webcam terpasang
- Tutup aplikasi lain yang pakai kamera (Zoom, Skype, dll.)

#### 8. Jalankan Flask

```bash
python app.py
```

Expected output:
```
 * Running on http://0.0.0.0:5000
 * PostgreSQL database handler initialized successfully
 * CV Benchmark blueprint registered
 * MQTT disabled - using mock mode
```

#### 9. Buka Browser & Test

1. Buka **http://localhost:5000**
2. Scroll ke bawah → klik **"CV Benchmark (Beta)"**
3. Pilih mode testing:
   - **Live Monitor** — stream kamera + FPS counter + CPU/RAM stats
   - **Face Recognition** — capture foto → live matching

---

## 🍓 Option 2: Testing di Raspberry Pi 4B

**Waktu setup:** ~45-60 menit (termasuk kompilasi dlib ~20-30 menit)  
**Kegunaan:** Testing performa target production

### Prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git postgresql postgresql-contrib -y

# Build tools untuk compile dlib
sudo apt install cmake build-essential libopenblas-dev liblapack-dev -y
```

### Setup Database

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE pi WITH LOGIN CREATEDB PASSWORD 'password';
CREATE DATABASE tpt_rfid OWNER pi;
\q
```

### Clone & Setup Environment

```bash
cd ~
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest

python3 -m venv venv
source venv/bin/activate

# Install base
pip install -r requirements.txt
```

### Install CV Dependencies (⏱️ Lama!)

**PERHATIAN:** Kompilasi dlib memakan waktu ~20-30 menit dan membutuhkan RAM cukup.

```bash
# OPTIONAL: Jika RAM < 2GB, tambah swap dulu
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Ubah baris: CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Install dlib (ini yang lama, sabar ya!)
pip install dlib --break-system-packages

# Kalau berhasil (cek: python3 -c "import dlib"), install sisanya:
pip install opencv-python face-recognition psutil --break-system-packages
```

**Verify:**
```bash
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"
python3 -c "import face_recognition; print('face_recognition: OK')"
python3 -c "import psutil; print('psutil: OK')"
```

### Konfigurasi & Run

```bash
cp .env.example .env
nano .env
```

Isi (sesuaikan password):
```env
FLASK_ENV=development
DEBUG=True
SECRET_KEY=rpi-testing-key

DATABASE_URL=postgresql://pi:password@localhost/tpt_rfid

ADMIN_PIN=1234
MQTT_ENABLED=false
WEBSOCKET_ENABLED=false
```

```bash
# Migrasi
flask db upgrade

# Jalankan
python app.py
```

Buka browser di RPi: **http://localhost:5000** → CV Benchmark

---

## ✅ Testing Checklist

Gunakan checklist ini untuk memastikan semua fitur berfungsi:

### Test 1: Live Monitor

- [ ] Stream kamera muncul (realtime)
- [ ] FPS counter terlihat di pojok kanan atas frame
- [ ] Sidebar stats menampilkan CPU %, RAM %, suhu (update ~1 detik)
- [ ] Dropdown resolusi di top bar berfungsi
- [ ] Ganti resolusi → stream restart dengan benar
- [ ] Resolusi yang tidak didukung kamera di-disable

### Test 2: Face Recognition

**Fase Capture:**
- [ ] Stream preview + overlay lingkaran panduan muncul
- [ ] Klik "📸 Ambil Foto Referensi" → foto ter-capture
- [ ] Jika tidak ada wajah → error message muncul

**Fase Recognition:**
- [ ] Stream berganti ke mode recognition
- [ ] Wajah terdeteksi → bounding box muncul
- [ ] Match dengan referensi → box hijau + "COCOK XX%"
- [ ] Tidak match → box merah + "TIDAK XX%"
- [ ] Tombol "Coba Lagi" → threshold turun (lihat label threshold di top bar)
- [ ] Tombol "Ulang dari Awal" → kembali ke fase capture

### Test 3: Performance Benchmark

**Catat hasil testing:**

| Resolusi | FPS (Live) | FPS (Face Rec) | CPU Load | Keterangan |
|----------|------------|----------------|----------|------------|
| 240p     |            |                |          |            |
| 360p     |            |                |          |            |
| 480p     |            |                |          |            |
| 720p     |            |                |          |            |
| 1080p    |            |                |          |            |

**Expected (Raspberry Pi 4B):**
- 480p Face Rec: 8-12 FPS, CPU 50-65%
- 720p Face Rec: 5-8 FPS, CPU 70-85%

---

## ⚠️ Troubleshooting Umum

### 1. Kamera tidak terbuka

**Gejala:** Error "Kamera tidak dapat dibuka"

**Solusi:**
```bash
# Cek device
ls -l /dev/video*

# RPi Camera Module → enable dulu
sudo raspi-config
# Interface Options → Camera → Enable
sudo modprobe bcm2835-v4l2
sudo reboot
```

### 2. FPS sangat rendah (<5)

**Solusi:**
- Turunkan resolusi ke 360p atau 480p
- Cek suhu CPU: `vcgencmd measure_temp` (harus < 70°C)
- Tutup aplikasi lain

### 3. Face recognition tidak match (false negative)

**Solusi:**
1. Ambil foto referensi dengan pencahayaan baik
2. Posisi wajah tegak, langsung ke kamera
3. Gunakan tombol "Coba Lagi" 2-3x (threshold akan turun)

### 4. Import error: No module named 'cv2'

```bash
pip install opencv-python
```

### 5. Import error: No module named 'face_recognition'

```bash
# Laptop
pip install face-recognition

# Raspberry Pi
pip install dlib --break-system-packages
pip install face-recognition --break-system-packages
```

### 6. Dlib compilation failed (RPi)

**Error:** "Killed" atau "Out of memory"

**Solusi:** Tambah swap size (lihat section "Install CV Dependencies" di Option 2)

---

## 📊 Hasil Testing yang Diharapkan

**Target Minimum (Raspberry Pi 4B):**
- ✅ Live Monitor: 15+ FPS pada 480p
- ✅ Face Recognition: 8+ FPS pada 480p
- ✅ CPU load: < 70% saat recognition
- ✅ Suhu CPU: < 70°C sustained
- ✅ Akurasi match: baik (minimal 2/3 percobaan berhasil dengan pencahayaan baik)

**Kesimpulan:**
- Jika semua target tercapai → **RPi 4B LAYAK untuk face recognition**
- Jika FPS < 5 atau CPU > 85% → **Perlu optimasi atau hardware lebih kuat**

---

## 📝 Laporan Hasil Testing

Setelah testing, isi form hasil:

**Device yang dipakai:**
- [ ] Laptop (spesifikasi: _________________)
- [ ] Raspberry Pi 4B (RAM: 2GB / 4GB / 8GB)

**Resolusi optimal:** _____ (pilih dari 240p/360p/480p/720p/1080p)

**FPS rata-rata (Face Recognition):** _____ FPS

**CPU load rata-rata:** _____ %

**Suhu CPU (RPi only):** _____ °C

**Akurasi matching:**
- [ ] Baik (match consistently dengan pencahayaan baik)
- [ ] Cukup (match setelah 2-3 retry)
- [ ] Buruk (sering false negative)

**Masalah yang ditemukan:**
- (tuliskan di sini jika ada bug/error)

**Kesimpulan:**
- [ ] ✅ LAYAK untuk production
- [ ] ⚠️ PERLU OPTIMASI
- [ ] ❌ TIDAK LAYAK (performa terlalu rendah)

---

## 🔄 Setelah Testing

Untuk kembali ke branch `main` (sistem RFID utama):

```bash
git checkout main
```

CV Benchmark hanya ada di branch `cvtest` dan tidak akan muncul di `main`.

---

## 📖 Dokumentasi Lengkap

Jika perlu detail lebih lanjut:
- **[QUICKSTART_CV_BENCHMARK.md](QUICKSTART_CV_BENCHMARK.md)** — Quick start guide lengkap
- **[docs/CV_BENCHMARK.md](docs/CV_BENCHMARK.md)** — Technical documentation (model stack, API, dll.)

---

**Happy Testing!** 🚀  
Jika ada pertanyaan atau menemukan bug, laporkan via Issues atau contact Ahmad.

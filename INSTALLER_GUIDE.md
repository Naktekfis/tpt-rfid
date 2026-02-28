# TPT-RFID Installer & Launcher Guide

Panduan lengkap untuk instalasi dan menjalankan TPT-RFID menggunakan **all-in-one installer**.

---

## 📦 File Installer

### 1. `tpt-rfid-installer.sh` - All-in-One Installer
**Fungsi:** Instalasi lengkap sistem (sekali jalan, auto-start dengan systemd)

**Fitur:**
- ✅ Auto-install semua dependencies (Python, PostgreSQL, OpenCV, dll)
- ✅ Setup database otomatis
- ✅ Clone/update repository dari GitHub
- ✅ Pilihan branch: `main` (standard) atau `cvtest` (CV Benchmark)
- ✅ Setup systemd service (auto-start saat boot)
- ✅ Optional: Kiosk mode (Raspberry Pi fullscreen)

### 2. `start-app.sh` - Quick Launcher
**Fungsi:** Jalankan app secara manual untuk development/testing (tanpa systemd)

**Fitur:**
- ✅ Flask development server dengan auto-reload
- ✅ Tidak perlu systemd, langsung jalankan app
- ✅ Cocok untuk testing dan development
- ✅ Stop dengan Ctrl+C

---

## 🚀 Cara Penggunaan

### Method A: Full Installation (Production)

Gunakan ini untuk **instalasi pertama kali** atau **fresh install di Raspberry Pi**.

```bash
cd ~/tpt-rfid
./tpt-rfid-installer.sh
```

**Pilihan saat instalasi:**
```
Select installation mode:
  1) Standard (main branch) - RFID Tool Monitoring
  2) CV Benchmark (cvtest branch) - Face Recognition Testing

Enter choice [1-2]: 2  # Pilih 2 untuk CV Benchmark
```

**Output:**
- ✅ System packages installed
- ✅ PostgreSQL configured
- ✅ Repository cloned (branch cvtest)
- ✅ Python venv created
- ✅ CV dependencies installed (opencv, dlib, face-recognition)
- ✅ Systemd service enabled
- ✅ App running di `http://localhost:5000`

**Estimasi waktu:**
- Standard mode: 30-45 menit
- CV Benchmark mode: 45-90 menit (kompilasi dlib di Raspberry Pi)

---

### Method B: Quick Start (Development)

Gunakan ini jika **sudah install dependencies** dan hanya mau jalankan app.

```bash
cd ~/tpt-rfid
./start-app.sh
```

**Output:**
```
╔════════════════════════════════════════════════╗
║        TPT-RFID Application Launcher           ║
╚════════════════════════════════════════════════╝

Branch:      cvtest
Directory:   /home/ahmad/tpt-rfid
Python:      /home/ahmad/tpt-rfid/venv/bin/python

Starting Flask development server...
Press Ctrl+C to stop

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

**Keuntungan:**
- ⚡ Cepat, langsung jalan
- 🔄 Auto-reload saat edit code
- 🐛 Debug logs langsung terlihat
- 🛑 Stop dengan Ctrl+C (tidak perlu systemctl)

---

## 🔧 Command Reference

### Installer Mode
```bash
# Full installation (akan prompt pilih branch)
./tpt-rfid-installer.sh

# Setelah install, check status
sudo systemctl status tpt-rfid

# View logs
sudo journalctl -u tpt-rfid -f

# Restart service
sudo systemctl restart tpt-rfid

# Stop service
sudo systemctl stop tpt-rfid
```

### Launcher Mode
```bash
# Jalankan app (development mode)
./start-app.sh

# Stop: tekan Ctrl+C

# Background mode (optional)
nohup ./start-app.sh > app.log 2>&1 &

# Check if running
ps aux | grep "python app.py"

# Stop background process
pkill -f "python app.py"
```

---

## 🎯 Use Cases

### Case 1: Fresh Raspberry Pi Setup
**Scenario:** RPi baru, belum install apa-apa, mau setup CV Benchmark

```bash
# 1. Clone repository
cd ~
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid

# 2. Run installer
chmod +x tpt-rfid-installer.sh
./tpt-rfid-installer.sh

# 3. Pilih mode 2 (CV Benchmark)
# 4. Wait 60-90 minutes
# 5. Reboot
sudo reboot

# 6. App auto-start, akses via browser
# http://<raspberry-pi-ip>:5000
```

---

### Case 2: Development di Laptop
**Scenario:** Development di laptop, sering edit code, butuh auto-reload

```bash
# 1. Clone repository
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest

# 2. Manual install dependencies (lebih cepat di laptop)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python face-recognition psutil

# 3. Setup .env (copy dari .env.example)
cp .env.example .env
nano .env  # Edit DATABASE_URL

# 4. Setup database
# (Setup PostgreSQL manual atau gunakan installer)
flask db upgrade

# 5. Jalankan dengan launcher
./start-app.sh

# 6. Edit code → auto-reload
# 7. Stop dengan Ctrl+C
```

---

### Case 3: Switch dari Main ke CVTest
**Scenario:** Sudah install standard mode, mau coba CV Benchmark

```bash
# 1. Stop service
sudo systemctl stop tpt-rfid

# 2. Switch branch
cd ~/tpt-rfid
git fetch --all
git checkout cvtest

# 3. Install CV dependencies
source venv/bin/activate
pip install opencv-python face-recognition psutil

# 4. Jalankan dengan launcher (tidak pakai systemd)
./start-app.sh

# 5. Akses http://localhost:5000 → CV Benchmark
```

---

### Case 4: Testing CV Benchmark Tanpa Install Penuh
**Scenario:** Mau testing cepat tanpa installer penuh

```bash
# Prerequisites: Python3, venv, PostgreSQL installed

# 1. Clone dan setup minimal
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
git checkout cvtest

# 2. Create venv
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install opencv-python face-recognition psutil

# 4. Setup .env
cp .env.example .env
# Edit DATABASE_URL di .env

# 5. Jalankan
./start-app.sh

# 6. Test CV Benchmark di browser
```

---

## 🐛 Troubleshooting

### Problem: `./tpt-rfid-installer.sh` permission denied
**Solution:**
```bash
chmod +x tpt-rfid-installer.sh
./tpt-rfid-installer.sh
```

### Problem: `./start-app.sh` says venv not found
**Solution:**
```bash
# Run installer first
./tpt-rfid-installer.sh

# OR create venv manually
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Problem: App tidak bisa diakses dari luar RPi
**Solution:**
```bash
# Check firewall
sudo ufw status
sudo ufw allow 5000/tcp

# Check service binding
sudo systemctl status tpt-rfid
# Pastikan bind ke 0.0.0.0:5000 bukan 127.0.0.1:5000
```

### Problem: CV Benchmark error "No module named 'cv2'"
**Solution:**
```bash
source venv/bin/activate
pip install opencv-python face-recognition psutil
```

### Problem: Database connection error
**Solution:**
```bash
# Check PostgreSQL running
sudo systemctl status postgresql

# Check .env file
cat .env | grep DATABASE_URL

# Test connection
source venv/bin/activate
python -c "from config import Config; print(Config.DATABASE_URL)"
```

---

## 📊 Comparison: Installer vs Launcher

| Feature | `tpt-rfid-installer.sh` | `start-app.sh` |
|---------|------------------------|----------------|
| **Install dependencies** | ✅ Auto | ❌ Manual |
| **Setup database** | ✅ Auto | ❌ Manual |
| **Clone repository** | ✅ Auto | ❌ Manual |
| **Auto-start on boot** | ✅ Yes (systemd) | ❌ No |
| **Auto-reload code** | ❌ No | ✅ Yes |
| **Production ready** | ✅ Yes | ❌ No |
| **Development friendly** | ❌ No | ✅ Yes |
| **Speed** | 🐢 45-90 min | ⚡ Instant |
| **Use case** | Fresh install, RPi | Development, testing |

---

## ✅ Recommendation

### For Production (Raspberry Pi):
```bash
./tpt-rfid-installer.sh  # Pilih mode 2 (CV Benchmark)
```

### For Development (Laptop):
```bash
# Setup sekali
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python face-recognition psutil

# Jalankan berulang kali
./start-app.sh  # Auto-reload on code changes
```

---

## 📚 Related Documentation

- **CV Benchmark Testing:** `QUICKSTART_CV_BENCHMARK.md`
- **Team Checklist:** `TESTING_CV_BENCHMARK.md`
- **Technical Docs:** `docs/CV_BENCHMARK.md`
- **Integration Guide:** `CV_INTEGRATION_CHECKLIST.md`

---

**Last Updated:** March 1, 2026  
**Branch:** cvtest  
**Version:** 1.0.0

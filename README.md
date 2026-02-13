# Lab Fabrikasi ITB - RFID Tool Monitoring System

Sistem peminjaman alat workshop berbasis RFID untuk Lab Fabrikasi Teknik Fisika ITB.

**Tech Stack:** Flask 3 (Python) · PostgreSQL · SQLAlchemy · Tailwind CSS · Vanilla JS

---

## Daftar Isi

1. [Fitur](#fitur)
2. [Arsitektur Proyek](#arsitektur-proyek)
3. [Setup di Laptop (Development)](#setup-di-laptop-development)
4. [Setup di Raspberry Pi (Production)](#setup-di-raspberry-pi-production)
5. [Seed Data (Opsional)](#seed-data-opsional)
6. [Cara Penggunaan Aplikasi](#cara-penggunaan-aplikasi)
7. [Environment Variables](#environment-variables)
8. [Troubleshooting](#troubleshooting)

---

## Fitur

- **Registrasi mahasiswa** — daftar dengan nama, NIM, email, telepon, foto, dan kartu RFID
- **Peminjaman alat** — scan kartu mahasiswa + tag RFID alat, konfirmasi pinjam
- **Pengembalian alat** — scan kartu mahasiswa + tag RFID alat, konfirmasi kembali
- **Monitor alat** — lihat status semua alat (tersedia / sedang dipinjam)
- **Admin panel** — monitor dengan info peminjam lengkap + kirim email peringatan
- **Mock RFID** — simulasi RFID via browser console untuk development tanpa hardware

---

## Arsitektur Proyek

```
tpt-rfid/
├── app.py                     # Aplikasi Flask utama
├── config.py                  # Konfigurasi (dev/production)
├── seed_database.py           # Script seed data testing
├── setup.sh                   # Script setup otomatis
├── requirements.txt           # Dependensi Python
├── .env.example               # Template environment variables
├── templates/                 # HTML templates (Jinja2)
│   ├── base.html
│   ├── landing.html           # Halaman landing (pilih role)
│   ├── welcome.html           # Menu mahasiswa
│   ├── register.html          # Form registrasi
│   ├── scan.html              # Halaman scan pinjam/kembali
│   ├── monitor.html           # Monitor alat (publik)
│   ├── admin_welcome.html     # Menu admin
│   └── admin_monitor.html     # Monitor alat (admin)
├── static/
│   ├── css/                   # Stylesheet
│   ├── js/                    # JavaScript
│   └── assets/                # Gambar dan ikon
└── utils/
    ├── __init__.py
    ├── models.py              # SQLAlchemy models (Student, Tool, Transaction)
    ├── database_handler.py    # Operasi CRUD PostgreSQL
    ├── rfid_mock.py           # Simulasi RFID reader
    └── helpers.py             # Fungsi utilitas
```

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
| `ADMIN_PIN` | Tidak | PIN untuk admin API | `1234` (auto-generate jika kosong) |
| `MAIL_SERVER` | Tidak | SMTP server | `smtp.gmail.com` |
| `MAIL_PORT` | Tidak | SMTP port | `587` |
| `MAIL_USE_TLS` | Tidak | Gunakan TLS | `True` |
| `MAIL_USERNAME` | Tidak | Email pengirim | `lab@gmail.com` |
| `MAIL_PASSWORD` | Tidak | Password / app password | `xxxx-xxxx-xxxx` |
| `MAIL_DEFAULT_SENDER` | Tidak | Default sender | `lab@gmail.com` |

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

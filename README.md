# Lab Fabrikasi ITB - RFID Tool Monitoring System

Kiosk layar sentuh untuk peminjaman alat workshop dengan kartu/tag RFID, Lab Fabrikasi Teknik Fisika ITB.

**Stack:** Flask 3 · SQLite (Flask-SQLAlchemy) · Jinja + Tailwind + vanilla JS · reader UHF USB HW-VX6336 lewat serial.
**Target:** NVIDIA Jetson Nano 4GB (JetPack 4.6.1, Ubuntu 18.04, Python 3.8), browser mode kiosk. Development di laptop.

## Fitur
- **Registrasi mahasiswa**: nama, NIM, email, telepon, foto, kartu RFID.
- **Pinjam / kembalikan alat**: tap kartu mahasiswa, lalu tap tag alat, lalu konfirmasi. Kartu dan tag dibaca di reader yang sama.
- **Monitor** (`/monitor`): status semua alat.
- **Admin** (`/admin`): info peminjam, tambah alat, riwayat dan ekspor, email peringatan.
- **Mock mode**: tanpa reader, MQTT, atau kamera, aplikasi tetap jalan.
- **CV Benchmark** (eksperimen, `/cv`): uji face recognition. Butuh `requirements-cv.txt`; lihat [docs/CV_BENCHMARK.md](docs/CV_BENCHMARK.md).

## Development di laptop
```bash
./setup.sh                    # .venv + dependensi + .env dari .env.example
.venv/bin/python app.py       # http://localhost:5000
.venv/bin/python seed_database.py   # opsional: data contoh
```
Database default adalah SQLite di `instance/tpt_rfid.db`. Tabel dibuat otomatis saat app start. Jangan isi `DATABASE_URL` kecuali memang mau database lain.

**Simulasi scan tanpa reader** (hanya `FLASK_ENV=development`):
```
http://localhost:5000/debug/scan?uid=STUDENT001
http://localhost:5000/debug/clear
```

**Dengan reader asli di laptop:** colok reader, pastikan user ada di grup `dialout`, lalu di `.env` isi:
```
RFID_READER_ENABLED=true
RFID_READER_PORT=/dev/ttyUSB0
```
`GET /api/rfid/status` menunjukkan mode reader dan apakah sudah terhubung.

**Cek sebelum commit:** `scripts/check.sh` (ruff + pytest). Kode harus jalan di Python 3.8.

## Deploy ke Jetson Nano
Lihat [deploy/jetson/README.md](deploy/jetson/README.md). Isinya `install.sh` (bisa `DRY_RUN=1`), service systemd (gunicorn 1 worker), backup SQLite harian, udev rule `/dev/rfid-reader`, dan autostart browser kiosk.

## Konfigurasi (`.env`)
| Variable | Default | Keterangan |
|---|---|---|
| `FLASK_ENV` | `development` | `production` di perangkat (route debug mati, cookie `Secure`) |
| `SECRET_KEY` | dev key | Wajib di production |
| `DATABASE_URL` | SQLite `instance/tpt_rfid.db` | Biarkan kosong |
| `RFID_READER_ENABLED` | `false` | `true` = baca reader VX6336 lewat serial |
| `RFID_READER_PORT` | `/dev/ttyUSB0` | `/dev/rfid-reader` di Jetson |
| `RFID_ABSENT_TIMEOUT` | `2.5` | Detik tag harus menjauh sebelum dianggap tap baru |
| `MQTT_ENABLED`, `WEBSOCKET_ENABLED` | `false` | Jalur ESP32 lama; lihat [docs/MQTT_SETUP.md](docs/MQTT_SETUP.md) |
| `MAIL_*` | Gmail SMTP | Untuk email peringatan dan ekspor dari admin |

`ADMIN_PIN` di `.env.example` **tidak dipakai**: hash PIN admin masih tertulis langsung di `app.py`.

## Data contoh
`seed_database.py` menambahkan 5 mahasiswa (UID `STUDENT001`–`STUDENT005`) dan 10 alat (`TOOL001`–`TOOL010`). Aman dijalankan berulang.

## Struktur
```
app.py              semua route halaman dan /api/* (monolit)
config.py           konfigurasi dari .env
utils/              models, database_handler, vx6336 (protokol reader),
                    rfid_reader (mock/real + debounce), mqtt_client,
                    websocket_handler, helpers, cv_handler
routes/cv_routes.py blueprint /cv (eksperimen)
templates/, static/ halaman Jinja + JS per halaman
deploy/jetson/      file bring-up perangkat
tests/              pytest (SQLite in-memory)
docs/               panduan hardware, MQTT/ESP32, dan dokumen lama (RPi + Postgres)
```

## Lisensi
MIT License. Lab Fabrikasi Teknik Fisika ITB.

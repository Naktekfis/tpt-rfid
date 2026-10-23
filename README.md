# Lab Fabrikasi ITB - Kiosk Peminjaman Alat

Kiosk peminjaman alat workshop Lab Fabrikasi Teknik Fisika ITB. Mahasiswa dikenali lewat **wajah** (kamera USB), alat dipantau terus oleh **reader UHF RFID** (tag di tiap alat): alat yang diambil saat sesi tercatat sebagai pinjaman (2 hari), alat yang keluar tanpa sesi memicu alarm.

**Stack:** Flask 3 · SQLite (Flask-SQLAlchemy) · Jinja + CSS sendiri + vanilla JS (tanpa CDN, jalan offline) · OpenCV YuNet + SFace (wajah) · reader HW-VX6336 lewat serial.
**Target:** NVIDIA Jetson Nano 4GB (JetPack 4.6.1, Ubuntu 18.04, Python 3.8), monitor + mouse + keyboard USB, browser mode kiosk. Development di laptop.

## Alur
- **Kiosk** (`/kiosk`): lihat ke kamera → tengok kanan dan kiri (liveness) → sesi 60 s: ambil alat = pinjam, letakkan kembali = kembalikan. Alat diambil tanpa sesi → alarm (buzzer reader + layar merah); scan wajah dalam 30 s mengubahnya jadi pinjaman. Alat kembali tanpa sesi → "dikembalikan, belum diverifikasi".
- **Daftar** (`/register` = `/daftar`): isi data + persetujuan, lalu rekam wajah.
- **Monitor** (`/monitor`): papan alat.
- **Admin** (`/admin`, PIN): monitor (alarm, verifikasi pengembalian, pinjaman, data wajah), input alat (tag baru di depan reader + foto jenis alat), riwayat + ekspor.

## Development di laptop
```bash
./setup.sh                                   # .venv + dependensi + .env dari .env.example
.venv/bin/pip install -r requirements-cv.txt # wajah (OpenCV)
.venv/bin/python scripts/fetch_face_models.py
.venv/bin/python seed_database.py            # data contoh (5 jenis alat, 20 unit)
.venv/bin/python app.py                      # http://localhost:5000
```
Tanpa reader/kamera: `RFID_READER_ENABLED=false`, `CAMERA_ENABLED=false`, lalu `scripts/kiosk_demo.sh` (butuh `FLASK_ENV=development`) memutar semua state kiosk.
Reader asli: user di grup `dialout`, `.env` `RFID_READER_ENABLED=true`, `RFID_READER_PORT=/dev/ttyUSB0`. Uji reader: `.venv/bin/python scripts/rfid_probe.py /dev/ttyUSB0 --stats --duration 60 --quiet`.
Uji wajah: `.venv/bin/python scripts/face_bench.py --challenge --show`.

**Cek sebelum commit:** `scripts/check.sh` (ruff + pytest). Kode harus jalan di Python 3.8.

## Deploy ke Jetson Nano
Lihat [deploy/jetson/README.md](deploy/jetson/README.md): `deploy/jetson/install.sh` (coba dulu dengan `DRY_RUN=1`) memasang dependensi + model wajah, membuat `.env`, service systemd (gunicorn 1 worker), backup SQLite harian, udev rule `/dev/rfid-reader`, grup `dialout`/`video`, dan autostart browser ke `/kiosk`.

## Konfigurasi (`.env`, lihat `.env.example`)
| Variable | Default | Keterangan |
|---|---|---|
| `FLASK_ENV` | `development` | `production` di perangkat (route debug mati) |
| `SECRET_KEY` | dev key | Wajib di production |
| `RFID_READER_ENABLED` / `RFID_READER_PORT` | `false` / `/dev/ttyUSB0` | `/dev/rfid-reader` di Jetson |
| `RFID_MISSING_AFTER` | `5` | Detik tag tak terbaca sebelum alat dianggap keluar (8 disarankan dengan banyak tag) |
| `RFID_ALARM_CONFIRM_SECONDS` | `2` | Detik tambahan alat (tidak dipinjam) harus tetap hilang sebelum alarm; mencegah alarm palsu dari bacaan lemah |
| `RFID_ALARM_ENABLED` | `true` | Buzzer reader saat alarm |
| `CAMERA_ENABLED` / `CAMERA_INDEX` | `false` / `0` | Kamera USB |
| `FACE_ENGINE` / `FACE_MATCH_THRESHOLD` | `yunet_sface` / bawaan engine | |
| `KIOSK_SESSION_SECONDS` / `ALARM_GRACE_SECONDS` | `60` / `30` | |
| `MAIL_*` | Gmail SMTP | Email peringatan dan ekspor |

**PIN admin:** default `133133`; ganti dengan `.venv/bin/python scripts/set_admin_pin.py` (hash disimpan di `.env`).

## Struktur
```
app.py              pembuatan app + route halaman dan API lama
config.py           konfigurasi dari .env
utils/              models, database_handler, vx6336 + rfid_reader (reader), presence +
                    tool_presence (alat di rak / alarm), camera, face + liveness +
                    face_service (wajah), kiosk (state machine sesi), helpers
routes/             presence, face, kiosk, admin (blueprint), cv (benchmark eksperimen)
templates/, static/ halaman Jinja, CSS (tokens/ui/pages/kiosk), JS per halaman, font
deploy/jetson/      bring-up perangkat
scripts/            check, rfid_probe, face_bench, fetch_face_models, kiosk_demo, set_admin_pin
tests/              pytest (SQLite in-memory)
docs/               manual reader (docs/hardware), dokumen CV benchmark
```
Requirement: `requirements.txt` (inti), `requirements-cv.txt` (wajah, dipakai kiosk), `requirements-dlib.txt` (opsional, tidak perlu di Jetson), `requirements-dev.txt` (pytest).

## Lisensi
MIT License. Lab Fabrikasi Teknik Fisika ITB.

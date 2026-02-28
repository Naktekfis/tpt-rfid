# CV Benchmark — Computer Vision Testing Module

## Overview

CV Benchmark adalah modul pengujian mandiri untuk mengukur performa Computer Vision (face recognition) pada Raspberry Pi 4B. Modul ini **bukan bagian dari alur peminjaman RFID utama**, melainkan tools development untuk menguji kelayakan hardware.

### Fitur

1. **Live Monitor** — Stream kamera realtime dengan pengukuran:
   - FPS (frames per second) pada berbagai resolusi (240p - 1080p)
   - Load CPU, RAM, dan suhu sistem
   - Switching resolusi on-the-fly

2. **Face Recognition Benchmark** — Pipeline face matching:
   - Capture foto referensi pada resolusi tertinggi
   - Live matching dengan deteksi wajah HOG (dlib)
   - Similarity score (0-100%)
   - Retry mechanism dengan threshold progresif (0.50 → 0.55 → 0.60)

## Installation

### Standard Installation (Development Machine)

```bash
pip install opencv-python face-recognition psutil
```

### Raspberry Pi Installation

Pada Raspberry Pi, `dlib` (dependency dari `face_recognition`) perlu dikompile dari source karena tidak tersedia wheel binary untuk ARM. **Proses kompilasi membutuhkan ~20-30 menit** dan memerlukan ~2GB RAM.

#### Prerequisites

```bash
sudo apt-get update
sudo apt-get install -y cmake build-essential libopenblas-dev liblapack-dev
```

#### Install Dependencies

```bash
# Pastikan menggunakan Python venv yang aktif
source .venv/bin/activate

# Install dlib (akan compile dari source, ~20 menit)
pip install dlib --break-system-packages

# Install face_recognition
pip install face-recognition --break-system-packages

# Install psutil dan opencv
pip install psutil opencv-python --break-system-packages
```

**CATATAN:** Jika RAM RPi < 2GB atau swap tidak cukup, kompilasi dlib mungkin gagal dengan error "Killed" atau "Out of memory". Solusi:

1. Tambah swap size sementara:
   ```bash
   sudo dphys-swapfile swapoff
   sudo nano /etc/dphys-swapfile
   # Ubah CONF_SWAPSIZE=100 menjadi CONF_SWAPSIZE=2048
   sudo dphys-swapfile setup
   sudo dphys-swapfile swapon
   ```

2. Install ulang dlib

3. Kembalikan swap size setelah selesai

#### Verify Installation

```bash
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"
python3 -c "import face_recognition; print('face_recognition: OK')"
python3 -c "import psutil; print('psutil: OK')"
```

## Usage

### Akses Halaman

1. Jalankan Flask server:
   ```bash
   python app.py
   ```

2. Buka browser: `http://localhost:5000`

3. Pada landing page, scroll ke bawah, klik **"CV Benchmark (Beta)"**

4. Pilih mode:
   - **Live Monitor** → pengujian FPS dan load sistem
   - **Face Recognition** → pengujian face matching

### Live Monitor Workflow

1. Kamera otomatis terbuka saat halaman dimuat
2. Stream video muncul dengan FPS counter di pojok kanan atas
3. Sidebar menampilkan stats realtime (CPU, RAM, suhu)
4. Ganti resolusi menggunakan tombol di top bar
5. Kembali ke menu utama dengan tombol "← CV Benchmark"

### Face Recognition Workflow

**Fase 1: Capture**
1. Posisikan wajah di dalam lingkaran panduan
2. Klik **"📸 Ambil Foto Referensi"**
3. Jika tidak ada wajah terdeteksi, ulangi dengan pencahayaan lebih baik

**Fase 2: Recognition**
1. Stream berganti ke mode recognition
2. Wajah di frame akan diberi bounding box:
   - **Hijau** → COCOK (match dengan foto referensi)
   - **Merah** → TIDAK (tidak match)
3. Similarity score ditampilkan di bawah bounding box
4. Jika tidak match, klik **"Coba Lagi"** untuk menurunkan threshold
5. Maksimal 3 percobaan (threshold: 0.50 → 0.55 → 0.60)

**Kontrol:**
- **Ulang dari Awal** → kembali ke fase capture (ambil foto baru)
- **Kembali** → kembali ke menu CV Benchmark

## Technical Notes

### Model Stack
- **Face Detection**: dlib HOG (Histogram of Oriented Gradients)
  - Lebih cepat di ARM dibanding CNN (~3-7 FPS di 480p)
  - Trade-off: akurasi sedikit lebih rendah dalam kondisi cahaya buruk
- **Face Encoding**: dlib ResNet (128-dimensional embedding)
- **Matching**: Euclidean distance < threshold

### Threshold Logic
```
Attempt 1: 0.50 → similarity ≥ 80% needed
Attempt 2: 0.55 → similarity ≥ 73% needed (dlib default)
Attempt 3: 0.60 → similarity ≥ 67% needed (lenient)
```

### Performance Expectations (RPi 4B, 4GB RAM)

| Resolusi | FPS (Live) | FPS (Face Rec) | CPU Load | RAM Usage |
|----------|------------|----------------|----------|-----------|
| 240p     | 25-30      | 15-20          | 30-40%   | ~500MB    |
| 360p     | 20-25      | 12-15          | 40-50%   | ~600MB    |
| 480p     | 15-20      | 8-12           | 50-65%   | ~700MB    |
| 720p     | 10-15      | 5-8            | 70-85%   | ~900MB    |
| 1080p    | 5-10       | 2-4            | 85-95%   | ~1.2GB    |

**Rekomendasi:** 480p untuk balance antara akurasi dan performa.

## Troubleshooting

### Kamera tidak terbuka

**Gejala:** Stream menampilkan "Kamera tidak dapat dibuka"

**Solusi:**
1. Pastikan kamera USB terpasang dengan benar
2. Cek apakah kamera digunakan aplikasi lain:
   ```bash
   lsof /dev/video0
   ```
3. Untuk RPi Camera Module (CSI), pastikan driver aktif:
   ```bash
   sudo raspi-config
   # Interface Options → Camera → Enable
   sudo modprobe bcm2835-v4l2
   ```

### FPS sangat rendah (<5 FPS)

**Penyebab:**
- Resolusi terlalu tinggi
- CPU throttling karena overheating
- Background process yang berat

**Solusi:**
1. Turunkan resolusi ke 480p atau 360p
2. Cek suhu CPU (ditampilkan di sidebar stats):
   ```bash
   vcgencmd measure_temp
   ```
   Jika >70°C, tambahkan heatsink atau aktifkan fan
3. Tutup aplikasi lain yang tidak diperlukan

### Face recognition tidak match (false negative)

**Penyebab:**
- Pencahayaan berbeda antara foto capture dan live stream
- Sudut wajah berbeda
- Threshold terlalu ketat

**Solusi:**
1. Ambil ulang foto referensi dengan pencahayaan konsisten
2. Gunakan tombol "Coba Lagi" untuk menurunkan threshold
3. Jika tetap gagal setelah 3 percobaan, coba kondisi cahaya lebih baik

### Import error: "No module named 'face_recognition'"

**Penyebab:** Dependencies CV Benchmark belum terinstall

**Solusi:**
```bash
pip install opencv-python face-recognition psutil
# Atau di RPi:
pip install opencv-python face-recognition psutil --break-system-packages
```

### Dlib compilation failed (RPi)

**Gejala:** Error "Killed" atau "virtual memory exhausted" saat install dlib

**Solusi:** Tambah swap size (lihat section Installation > Raspberry Pi Installation)

## API Endpoints

Untuk referensi developer:

| Method | Endpoint                  | Deskripsi                              |
|--------|---------------------------|----------------------------------------|
| GET    | `/cv`                     | Landing page CV Benchmark              |
| GET    | `/cv/live`                | Live Monitor page                      |
| GET    | `/cv/face-rec`            | Face Recognition page                  |
| GET    | `/cv/stream/live`         | MJPEG stream (bare camera)             |
| GET    | `/cv/stream/recognition`  | MJPEG stream (face overlay)            |
| GET    | `/cv/stats`               | JSON system stats (FPS, CPU, RAM, etc) |
| POST   | `/cv/camera/open`         | Open camera, probe resolutions         |
| POST   | `/cv/camera/close`        | Release camera                         |
| POST   | `/cv/resolution`          | Set camera resolution                  |
| GET    | `/cv/resolutions`         | List available resolutions             |
| POST   | `/cv/capture`             | Capture reference photo                |
| POST   | `/cv/retry`               | Increment retry attempt                |
| POST   | `/cv/reset`               | Reset recognition state                |

## Limitations

- **Single camera only**: Modul ini hanya support 1 kamera (index 0)
- **No persistence**: Foto referensi tidak disimpan ke database, hanya di memory
- **No multi-face**: Hanya mendeteksi dan match 1 wajah per frame
- **RPi-specific stats**: Pengukuran suhu CPU hanya bekerja di Raspberry Pi (fallback 0.0°C di platform lain)

## Future Improvements

- [ ] Support multiple cameras (dropdown selector)
- [ ] Save reference photos to database
- [ ] Export benchmark results (CSV/JSON)
- [ ] Comparison mode (A/B testing different threshold)
- [ ] GPU acceleration testing (if available)

## Credits

- **Face Recognition**: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition)
- **dlib**: [davisking/dlib](https://github.com/davisking/dlib)
- **OpenCV**: [opencv/opencv](https://github.com/opencv/opencv)

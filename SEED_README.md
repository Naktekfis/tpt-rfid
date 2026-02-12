# Database Seeding Guide

Quick script untuk populate Firebase dengan sample data untuk testing.

## Usage

```bash
cd /home/ahmad/tpt-rfid
source venv/bin/activate
python seed_database.py
```

## Sample Data yang Ditambahkan

### Students (5 mahasiswa)
- Ahmad Fauzi (STUDENT001) - NIM: 1234567890
- Siti Nurhaliza (STUDENT002) - NIM: 0987654321
- Budi Santoso (STUDENT003) - NIM: 1122334455
- Dewi Lestari (STUDENT004) - NIM: 5544332211
- Rizki Pratama (STUDENT005) - NIM: 6677889900

### Tools (10 alat)
- TOOL001: Drill Machine (Power Tools)
- TOOL002: Angle Grinder (Power Tools)
- TOOL003: Soldering Iron (Electronics)
- TOOL004: Multimeter Digital (Electronics)
- TOOL005: Circular Saw (Power Tools)
- TOOL006: Oscilloscope (Electronics)
- TOOL007: Impact Driver (Power Tools)
- TOOL008: Hot Air Station (Electronics)
- TOOL009: Belt Sander (Power Tools)
- TOOL010: Wire Stripper Set (Hand Tools)

## Testing Workflow

1. Jalankan seed script
2. Buka aplikasi: http://localhost:5000
3. Pilih "Sudah Punya Akun"
4. Buka browser console (F12)
5. Simulate RFID:
   ```javascript
   simulateRFID('STUDENT001')  // Scan kartu mahasiswa
   simulateRFID('TOOL001')     // Scan tag alat
   ```
6. Klik "Confirm Pinjam"
7. Test return: scan student + tool yang sama, klik "Confirm Kembalikan"

## Notes

- Script akan skip data yang sudah ada (tidak akan duplicate)
- Semua tools default status: "available"
- Students tidak punya foto (photo_url kosong)
- Bisa run script berulang kali tanpa masalah

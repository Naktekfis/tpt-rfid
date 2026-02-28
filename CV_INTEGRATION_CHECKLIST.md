# CV Benchmark Integration Checklist

## ✅ Integration Completed Successfully

### File Structure
- [x] `routes/` directory created
- [x] `routes/__init__.py` created
- [x] `routes/cv_routes.py` installed
- [x] `utils/cv_handler.py` installed
- [x] `templates/cv_benchmark.html` installed
- [x] `templates/cv_live.html` installed  
- [x] `templates/cv_face_rec.html` installed
- [x] `docs/CV_BENCHMARK.md` created

### Code Integration
- [x] cv_bp blueprint imported in app.py
- [x] cv_bp blueprint registered in app.py
- [x] Navigation link added to landing.html
- [x] Dependencies added to requirements.txt

### Routes Registered
All CV routes registered under `/cv` prefix:
- GET  /cv                        → Landing page (cv_benchmark.html)
- GET  /cv/live                   → Live Monitor page (cv_live.html)
- GET  /cv/face-rec               → Face Recognition page (cv_face_rec.html)
- GET  /cv/stream/live            → MJPEG stream (bare camera)
- GET  /cv/stream/recognition     → MJPEG stream (face recognition overlay)
- GET  /cv/stats                  → JSON system stats (SSE polling)
- POST /cv/camera/open            → Open camera, probe resolutions
- POST /cv/camera/close           → Release camera
- POST /cv/resolution             → Set camera resolution
- GET  /cv/resolutions            → List available + current resolution
- POST /cv/capture                → Capture reference photo
- POST /cv/retry                  → Increment retry attempt (lower threshold)
- POST /cv/reset                  → Reset recognition state

### Design Consistency
- [x] All CV pages extend base.html
- [x] Dark mode design (bg-gray-950, cards gray-900, borders gray-800)
- [x] Violet accent (Live Monitor)
- [x] Emerald accent (Face Recognition)
- [x] Consistent breadcrumb navigation
- [x] Beta badge on landing page navigation

### Documentation
- [x] Full installation guide (standard + Raspberry Pi)
- [x] Usage instructions (Live Monitor + Face Recognition workflows)
- [x] Technical notes (model stack, threshold logic, performance expectations)
- [x] Troubleshooting section
- [x] API endpoints reference

## Next Steps

### For Development Environment
```bash
pip install opencv-python face-recognition psutil
python app.py
# Navigate to http://localhost:5000
# Click "CV Benchmark (Beta)" button
```

### For Raspberry Pi 4B (Production)
See detailed instructions in `docs/CV_BENCHMARK.md`, section "Raspberry Pi Installation"

Key points:
- Install build dependencies (cmake, libopenblas, liblapack)
- Compile dlib from source (~20-30 minutes)
- May require increasing swap size to 2GB temporarily
- Test with: python3 -c "import face_recognition; print('OK')"

## Testing Checklist

When you run the app, verify:
- [ ] `/cv` page loads correctly
- [ ] "CV Benchmark (Beta)" button appears on landing page
- [ ] Clicking Live Monitor opens camera stream
- [ ] FPS counter displays in top-right corner of stream
- [ ] Resolution dropdown populates with available options
- [ ] System stats sidebar updates every ~1 second
- [ ] Clicking Face Recognition opens capture page
- [ ] Capture button triggers photo capture
- [ ] Recognition phase starts after successful capture
- [ ] Bounding boxes appear around detected faces
- [ ] Similarity percentage displays
- [ ] Retry button increments attempt (threshold loosens)
- [ ] "Ulang dari Awal" button resets to capture phase

## Known Limitations
- CV dependencies (opencv, face_recognition) must be installed separately
- Camera must be available (not used by other applications)
- Face recognition requires good lighting conditions
- Performance varies by RPi model and camera resolution
- Single camera support only (index 0)
- Reference photos not persisted (memory only)

## Rollback (if needed)
To remove CV Benchmark integration:
```bash
rm -rf routes/
rm utils/cv_handler.py
rm templates/cv_*.html
rm docs/CV_BENCHMARK.md
# Revert app.py changes (remove cv_bp import and registration)
# Revert landing.html changes (remove CV Benchmark card)
# Revert requirements.txt changes (remove opencv, face_recognition, psutil)
```

---
Integration completed: $(date)

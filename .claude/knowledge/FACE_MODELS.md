# Face models

Files live in `models/face/` (gitignored). `scripts/fetch_face_models.py` downloads them and refuses a SHA256 mismatch; models are loaded only as ONNX through `cv2.dnn`, never executed.

| File | Use | Source | License | SHA256 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face + 5 landmarks | github.com/opencv/opencv_zoo `models/face_detection_yunet` | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face_recognition_sface_2021dec.onnx` | SFace 128-d embedding | opencv_zoo `models/face_recognition_sface` | Apache-2.0 | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |
| `MiniFASNetV2.onnx` | passive liveness, crop scale 2.7 | github.com/yakhyo/face-anti-spoofing release `weights` (from Silent-Face-Anti-Spoofing) | Apache-2.0 (repo LICENSE) | `b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907` |
| `MiniFASNetV1SE.onnx` | passive liveness, crop scale 4.0 | same release | Apache-2.0 | `ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676` |
| `MiniFASNetV2SE_facenox.onnx` | liveness `minifas_se`: square crop 1.5x, RGB, 128, /255, logits, index 0 = real | github.com/facenox/face-antispoof-onnx `models/best/98.20/best_model.onnx` @ `2f8dd93` (fp32; the INT8 file does not load in cv2.dnn) | Apache-2.0 | `af2381b88f38769222ed93379e12444e2a50814575de1c46170de570c55a42b6` |
| `anti-spoof-mn3.onnx` | liveness `mn3`: box crop, RGB, 128, (x-mean)/scale, softmax, index 0 = real | OpenVINO Open Model Zoo `public/2022.1/anti-spoof-mn3` (MobileNetV3, CelebA-Spoof) | MIT | `c4c99af04603b62d7e44f6f4daeb33e0daeccc696008c0b1d62f6f5cebbb3262` |

Facts checked on OpenCV 5.0.0 (dev): both MiniFASNet files take 1x3x80x80 float (BGR, 0-255, no normalisation) and output 3 logits; index 1 = real. The input size is not read from the file (cv2.dnn cannot report it); 80 is hardcoded in `utils/liveness.py`.

Open: not yet verified that OpenCV 4.x on the Jetson loads `..._2023mar.onnx` (needs 4.5.4+ / 4.8 for the 2023 YuNet ops); fall back to `face_detection_yunet_2022mar.onnx` if not.

Engines (`utils/face.py`): `yunet_sface` (distance 1 - cosine, threshold 0.637) and `dlib` (raw 128-d, L2, threshold 0.5). Stored embeddings carry the engine name; switching `FACE_ENGINE` needs re-enrolment.

## Anti-spoofing for admin face login (research 2026-10-24)
Jetson facts (checked): `.venv` (Py 3.8) has OpenCV 5.0.0 **without CUDA**; no onnxruntime;
TensorRT 8.2.1 exists only for the system Python, so inference is CPU `cv2.dnn`. Camera is a
generic USB RGB webcam ("YLX Streaming Webcams", `/dev/video0`), no IR or depth.
- RGB-only passive models do not generalise well across camera/lighting; numbers in READMEs
  are self-reported on public datasets. Calibrate thresholds on this camera with real
  print and phone-replay attempts.
- Candidates: current MiniFASNetV2 + V1SE (80x80, cv2.dnn, ms per frame on CPU);
  `facenox/face-antispoof-onnx` (Apache-2.0, MiniFAS-based, 128x128, 1.8 MB fp32 ONNX,
  98.2% self-reported on CelebA-Spoof, built for onnxruntime; cv2.dnn loading untested);
  EasyShield v2.5 (MIT, YOLOv12n, ~75 ms on unknown GPU; too heavy for Nano CPU).
- rPPG (pulse from video) catches photos/masks but not good screen replays and needs
  seconds of stable video; not worth it here.
- Strongest cheap upgrade is hardware: an RGB+NIR USB camera with IR illuminator (phone
  screens look dark/flat in NIR). Depth cameras cost much more.
- Plan: layered — YuNet+SFace match, MiniFASNet ensemble over several frames, a random
  active challenge (head turn, `HeadTurnChallenge` in legacy), failure lockout → PIN,
  photo log of every attempt. Face login only via the Jetson camera (server-side capture,
  so a remote browser cannot inject video).

### Update 2026-10-24 (later): passive only
The user found the head-turn challenge too hard: removed. Login now = look at the camera
for 6 frames; >= 5 must pass every model in `FACE_LIVENESS_MODELS` and all 6 must match
the same admin. On random noise MiniFASNet scores 0.97 "real", minifas_se 0.17, mn3 0.04.
Choose models + thresholds from `scripts/face_spoof_bench.py` runs (real / print / screen)
on the kiosk camera; the log line "Face login passed/failed ..., liveness {...}" gives
per-attempt means.

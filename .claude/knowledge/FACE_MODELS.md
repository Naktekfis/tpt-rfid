# Face models

Files live in `models/face/` (gitignored). `scripts/fetch_face_models.py` downloads them and refuses a SHA256 mismatch; models are loaded only as ONNX through `cv2.dnn`, never executed.

| File | Use | Source | License | SHA256 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face + 5 landmarks | github.com/opencv/opencv_zoo `models/face_detection_yunet` | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face_recognition_sface_2021dec.onnx` | SFace 128-d embedding | opencv_zoo `models/face_recognition_sface` | Apache-2.0 | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |
| `MiniFASNetV2.onnx` | passive liveness, crop scale 2.7 | github.com/yakhyo/face-anti-spoofing release `weights` (from Silent-Face-Anti-Spoofing) | Apache-2.0 (repo LICENSE) | `b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907` |
| `MiniFASNetV1SE.onnx` | passive liveness, crop scale 4.0 | same release | Apache-2.0 | `ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676` |

Facts checked on OpenCV 5.0.0 (dev): both MiniFASNet files take 1x3x80x80 float (BGR, 0-255, no normalisation) and output 3 logits; index 1 = real. The input size is not read from the file (cv2.dnn cannot report it); 80 is hardcoded in `utils/liveness.py`.

Open: not yet verified that OpenCV 4.x on the Jetson loads `..._2023mar.onnx` (needs 4.5.4+ / 4.8 for the 2023 YuNet ops); fall back to `face_detection_yunet_2022mar.onnx` if not.

Engines (`utils/face.py`): `yunet_sface` (distance 1 - cosine, threshold 0.637) and `dlib` (raw 128-d, L2, threshold 0.5). Stored embeddings carry the engine name; switching `FACE_ENGINE` needs re-enrolment.

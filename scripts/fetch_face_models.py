"""
Download the face models into models/face/ (pinned SHA256, see
.claude/knowledge/FACE_MODELS.md).

    .venv/bin/python scripts/fetch_face_models.py

Downloads are untrusted data: they are only checked and later loaded as ONNX
by cv2.dnn, never executed. A file that fails the hash check is deleted.
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "face"
)

_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
_FAS = "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/"

# filename -> (url, sha256)
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        _ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        _ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
    "MiniFASNetV2.onnx": (
        _FAS + "MiniFASNetV2.onnx",
        "b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907",
    ),
    "MiniFASNetV1SE.onnx": (
        _FAS + "MiniFASNetV1SE.onnx",
        "ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676",
    ),
}


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    os.makedirs(MODEL_DIR, exist_ok=True)
    failed = False
    for name, (url, want) in MODELS.items():
        path = os.path.join(MODEL_DIR, name)
        if os.path.exists(path) and sha256_of(path) == want:
            print(f"ok      {name}")
            continue
        tmp = path + ".part"
        try:
            print(f"fetch   {name}")
            urllib.request.urlretrieve(url, tmp)
            got = sha256_of(tmp)
        except OSError as exc:
            print(f"FAILED  {name}: {exc}")
            failed = True
            continue
        if got != want:
            os.remove(tmp)
            print(f"REFUSED {name}: sha256 {got} != pinned {want}")
            failed = True
            continue
        os.replace(tmp, path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

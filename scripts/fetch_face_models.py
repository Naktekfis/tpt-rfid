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
import zipfile

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "face"
)

_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
_FAS = "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/"
# Pinned commit of facenox/face-antispoof-onnx (Apache-2.0).
_FACENOX = (
    "https://raw.githubusercontent.com/facenox/face-antispoof-onnx/"
    "2f8dd93dd0fd9d120f08e83d9020719f67ffdb68/models/best/98.20/best_model.onnx"
)
_OMZ = "https://storage.openvinotoolkit.org/repositories/open_model_zoo/public/2022.1/"
# InsightFace buffalo_s pack (~120 MB zip); only w600k_mbf.onnx is kept.
_BUFFALO_S = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip"

# filename -> (url, sha256); a .zip url means "extract the member of that name"
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
    "MiniFASNetV2SE_facenox.onnx": (
        _FACENOX,
        "af2381b88f38769222ed93379e12444e2a50814575de1c46170de570c55a42b6",
    ),
    "anti-spoof-mn3.onnx": (
        _OMZ + "anti-spoof-mn3/anti-spoof-mn3.onnx",
        "c4c99af04603b62d7e44f6f4daeb33e0daeccc696008c0b1d62f6f5cebbb3262",
    ),
    "w600k_mbf.onnx": (
        _BUFFALO_S,
        "9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",
    ),
}


def download(url: str, name: str, tmp: str) -> None:
    """Fetch url to tmp; for a zip, keep only the member `name`."""
    if not url.endswith(".zip"):
        urllib.request.urlretrieve(url, tmp)
        return
    archive = tmp + ".zip"
    try:
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as zf:
            member = next(m for m in zf.namelist() if os.path.basename(m) == name)
            with zf.open(member) as src, open(tmp, "wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    dst.write(chunk)
    except (StopIteration, zipfile.BadZipFile) as exc:
        raise OSError(f"{name} not found in {url}: {exc!r}") from exc
    finally:
        if os.path.exists(archive):
            os.remove(archive)


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
            download(url, name, tmp)
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

"""
Passive liveness (face anti-spoofing) for admin face login: is the face in
front of the kiosk camera a real face, or a photo / a screen?

Three small ONNX models, all run with cv2.dnn on the CPU (the Jetson's OpenCV
has no CUDA). Each gives a real-face probability 0..1; `Liveness` combines
the configured ones and a frame passes only if every model passes its own
threshold (FACE_LIVENESS_MODELS, e.g. "mn3:0.8,minifas_se:0.6").

  minifas     MiniFASNetV2 + V1SE (Silent-Face, Apache-2.0), mean of both
  minifas_se  MiniFASNetV2-SE 128x128 (facenox/face-antispoof-onnx, Apache-2.0)
  mn3         anti-spoof-mn3 MobileNetV3 (OpenVINO model zoo, MIT; CelebA-Spoof)

Files and hashes: scripts/fetch_face_models.py and .claude/knowledge/FACE_MODELS.md.
Fail closed: a missing model or cv2 raises LivenessUnavailable and face login
stays off. No model is reliable on its own across cameras and lighting:
calibrate the thresholds on site with scripts/face_spoof_bench.py.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


class LivenessUnavailable(RuntimeError):
    """Liveness cannot be evaluated (models/cv2 missing)."""


def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise LivenessUnavailable(f"OpenCV/numpy not installed: {exc}") from exc
    return cv2, np


def _load(cv2, model_dir: str, filename: str):
    path = os.path.join(model_dir, filename)
    if not os.path.isfile(path):
        raise LivenessUnavailable(f"Liveness model missing: {path}")
    try:
        return cv2.dnn.readNetFromONNX(path)
    except cv2.error as exc:
        raise LivenessUnavailable(f"Cannot load {path}: {exc}") from exc


def _softmax(np, logits):
    logits = np.asarray(logits, np.float64).reshape(-1)
    e = np.exp(logits - logits.max())
    return e / e.sum()


def crop_scaled(frame, box, scale: float, out_size: int):
    """Silent-Face crop: box centre, box size * scale kept inside the frame."""
    import cv2

    src_h, src_w = frame.shape[:2]
    x, y, w, h = box
    w = max(1, w)
    h = max(1, h)
    scale = min((src_h - 1) / h, (src_w - 1) / w, scale)
    new_w, new_h = w * scale, h * scale
    cx, cy = x + w / 2.0, y + h / 2.0
    left, top = cx - new_w / 2.0, cy - new_h / 2.0
    right, bottom = cx + new_w / 2.0, cy + new_h / 2.0
    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > src_w - 1:
        left -= right - (src_w - 1)
        right = src_w - 1
    if bottom > src_h - 1:
        top -= bottom - (src_h - 1)
        bottom = src_h - 1
    left, top = max(0, int(left)), max(0, int(top))
    crop = frame[top : int(bottom) + 1, left : int(right) + 1]
    return cv2.resize(crop, (out_size, out_size))


def crop_square(frame, box, expansion: float):
    """Square crop of max(w, h) * expansion around the box centre; edges reflected."""
    import cv2

    fh, fw = frame.shape[:2]
    x, y, w, h = box
    size = max(1, int(max(w, h) * expansion))
    x0 = int(x + w / 2.0 - size / 2.0)
    y0 = int(y + h / 2.0 - size / 2.0)
    crop = frame[max(0, y0) : min(fh, y0 + size), max(0, x0) : min(fw, x0 + size)]
    return cv2.copyMakeBorder(
        crop,
        max(0, -y0),
        max(0, y0 + size - fh),
        max(0, -x0),
        max(0, x0 + size - fw),
        cv2.BORDER_REFLECT_101,
    )


class MiniFAS:
    """MiniFASNetV2 + V1SE: 80x80 BGR 0-255, 3 classes, index 1 = real."""

    name = "minifas"
    MODELS = (("MiniFASNetV2.onnx", 2.7), ("MiniFASNetV1SE.onnx", 4.0))

    def __init__(self, model_dir: str):
        self._cv2, self._np = _cv()
        self._nets = [(_load(self._cv2, model_dir, f), s) for f, s in self.MODELS]

    def score(self, frame, face) -> float:
        np = self._np
        out = []
        for net, scale in self._nets:
            crop = crop_scaled(frame, face.box, scale, 80)
            net.setInput(crop.astype(np.float32).transpose(2, 0, 1)[None])
            out.append(float(_softmax(np, net.forward())[1]))
        return sum(out) / len(out)


class MiniFASSE:
    """facenox MiniFASNetV2-SE: square crop 1.5x, RGB, 128x128, /255, logits, index 0 = real."""

    name = "minifas_se"
    FILE = "MiniFASNetV2SE_facenox.onnx"

    def __init__(self, model_dir: str):
        self._cv2, self._np = _cv()
        self._net = _load(self._cv2, model_dir, self.FILE)

    def score(self, frame, face) -> float:
        cv2, np = self._cv2, self._np
        crop = cv2.resize(
            crop_square(frame, face.box, 1.5), (128, 128), interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self._net.setInput(rgb.transpose(2, 0, 1)[None])
        return float(_softmax(np, self._net.forward())[0])


class AntiSpoofMN3:
    """OpenVINO anti-spoof-mn3: face box crop, RGB, 128x128, (x - mean) / scale,
    softmax output, index 0 = real."""

    name = "mn3"
    FILE = "anti-spoof-mn3.onnx"
    MEAN = (151.2405, 119.5950, 107.8395)
    SCALE = (63.0105, 56.4570, 55.0035)

    def __init__(self, model_dir: str):
        self._cv2, self._np = _cv()
        self._net = _load(self._cv2, model_dir, self.FILE)

    def score(self, frame, face) -> float:
        cv2, np = self._cv2, self._np
        crop = cv2.resize(
            crop_square(frame, face.box, 1.0), (128, 128), interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)
        x = (rgb - np.array(self.MEAN, np.float32)) / np.array(self.SCALE, np.float32)
        self._net.setInput(x.transpose(2, 0, 1)[None])
        out = np.asarray(self._net.forward(), np.float64).reshape(-1)
        return float(out[0])  # the model ends in a softmax


MODELS = {cls.name: cls for cls in (MiniFAS, MiniFASSE, AntiSpoofMN3)}


def parse_spec(spec: str) -> List[Tuple[str, float]]:
    """ "mn3:0.8,minifas_se:0.6" -> [("mn3", 0.8), ("minifas_se", 0.6)]."""
    out = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        name, _, thr = part.partition(":")
        name = name.strip()
        if name not in MODELS:
            raise ValueError(f"Unknown liveness model {name!r} (use {sorted(MODELS)})")
        out.append((name, float(thr) if thr else 0.5))
    if not out:
        raise ValueError("No liveness model configured")
    return out


class Liveness:
    """The configured models; a frame is live only if every model passes."""

    def __init__(self, model_dir: str, spec: str):
        self.models: List[Tuple[Any, float]] = [
            (MODELS[name](model_dir), thr) for name, thr in parse_spec(spec)
        ]

    def check(self, frame, face) -> Tuple[bool, Dict[str, float]]:
        scores = {m.name: m.score(frame, face) for m, _ in self.models}
        return all(scores[m.name] >= thr for m, thr in self.models), scores


def yaw(landmarks) -> float:
    """(nose_x - eyes_mid_x) / eye distance; 0 = facing the camera."""
    re, le, nose = landmarks[0], landmarks[1], landmarks[2]
    eye_dist = abs(float(le[0]) - float(re[0]))
    if eye_dist < 1e-6:
        return 0.0
    return (float(nose[0]) - (float(re[0]) + float(le[0])) / 2.0) / eye_dist

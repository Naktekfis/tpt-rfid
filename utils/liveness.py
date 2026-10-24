"""
Liveness for admin face login (from legacy/face/utils/liveness.py, trimmed).

PassiveLiveness: two MiniFASNet anti-spoofing models (Silent-Face weights as
ONNX, loaded with cv2.dnn). Fail closed: missing models or cv2 raise
LivenessUnavailable and face login stays off.

HeadTurnChallenge: pure logic on 5-point landmarks for the active check.
"""

from __future__ import annotations

import os
from typing import Any, List, Tuple

MODEL_V2 = ("MiniFASNetV2.onnx", 2.7)
MODEL_V1SE = ("MiniFASNetV1SE.onnx", 4.0)
INPUT_SIZE = 80  # both ONNX files take 1x3x80x80 and give 3 logits (1 = real)


class LivenessUnavailable(RuntimeError):
    """Liveness cannot be evaluated (models/cv2 missing)."""


def crop_scaled(frame, box, scale: float, out_size: int = INPUT_SIZE):
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


class PassiveLiveness:
    def __init__(self, model_dir: str):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise LivenessUnavailable(f"OpenCV/numpy not installed: {exc}") from exc
        self._np = np
        self._nets: List[Tuple[Any, float]] = []
        for filename, scale in (MODEL_V2, MODEL_V1SE):
            path = os.path.join(model_dir, filename)
            if not os.path.isfile(path):
                raise LivenessUnavailable(f"Liveness model missing: {path}")
            try:
                self._nets.append((cv2.dnn.readNetFromONNX(path), scale))
            except cv2.error as exc:
                raise LivenessUnavailable(f"Cannot load {path}: {exc}") from exc
        for net, _ in self._nets:  # fail early on a model without 3 classes
            out = self._forward(net, np.zeros((INPUT_SIZE, INPUT_SIZE, 3), np.uint8))
            if out.size != 3:
                raise LivenessUnavailable(f"Unexpected liveness output size {out.size}")

    def _forward(self, net, crop):
        np = self._np
        blob = crop.astype(np.float32).transpose(2, 0, 1)[None]  # BGR, 0-255, NCHW
        net.setInput(blob)
        logits = net.forward().reshape(-1).astype(np.float64)
        e = np.exp(logits - logits.max())
        return e / e.sum()

    def score(self, frame, face) -> float:
        """Mean real-face probability over both models (0..1)."""
        scores = [
            float(self._forward(net, crop_scaled(frame, face.box, scale))[1])
            for net, scale in self._nets
        ]
        return sum(scores) / len(scores)


def yaw(landmarks) -> float:
    """(nose_x - eyes_mid_x) / eye distance; 0 = frontal, sign = image direction."""
    re, le, nose = landmarks[0], landmarks[1], landmarks[2]
    eye_dist = abs(float(le[0]) - float(re[0]))
    if eye_dist < 1e-6:
        return 0.0
    return (float(nose[0]) - (float(re[0]) + float(le[0])) / 2.0) / eye_dist


class HeadTurnChallenge:
    """Pass when the head turns past `yaw_threshold` in the asked direction
    after at least one near-frontal frame (so a photo held turned fails).

    Direction is in the raw (unmirrored) image: "left" = nose toward smaller x,
    i.e. the person turns toward THEIR OWN RIGHT. A mirrored preview must word
    its prompt in the person's terms (see FaceLogin.instruction).
    """

    def __init__(
        self,
        direction: str,
        yaw_threshold: float = 0.25,
        frontal_threshold: float = 0.1,
    ):
        if direction not in ("left", "right"):
            raise ValueError("direction must be 'left' or 'right'")
        self.direction = direction
        self._sign = -1.0 if direction == "left" else 1.0
        self.yaw_threshold = yaw_threshold
        self.frontal_threshold = frontal_threshold
        self._seen_frontal = False
        self.passed = False

    def update(self, landmarks) -> bool:
        if not self.passed and landmarks is not None:
            y = yaw(landmarks)
            if abs(y) < self.frontal_threshold:
                self._seen_frontal = True
            elif self._seen_frontal and y * self._sign > self.yaw_threshold:
                self.passed = True
        return self.passed

"""
Liveness checks.

PassiveLiveness: two MiniFASNet anti-spoofing models (Silent-Face-Anti-Spoofing
weights exported to ONNX, loaded with cv2.dnn). Fail closed: if the models or
cv2 are missing, LivenessUnavailable is raised and callers must refuse.

HeadTurnChallenge: pure logic on 5-point landmarks, for the active check.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, List, Tuple

MODEL_V2 = ("MiniFASNetV2.onnx", 2.7)
MODEL_V1SE = ("MiniFASNetV1SE.onnx", 4.0)
INPUT_SIZE = 80  # both ONNX files take 1x3x80x80 and give 3 logits


class LivenessUnavailable(RuntimeError):
    """Liveness cannot be evaluated (models/cv2 missing). Callers must refuse."""


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
    def __init__(self, model_dir: str, threshold: float = 0.5):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise LivenessUnavailable(f"OpenCV/numpy not installed: {exc}") from exc
        self._cv2 = cv2
        self._np = np
        self.threshold = threshold
        self.input_size = INPUT_SIZE
        self._nets: List[Tuple[Any, float]] = []
        for filename, scale in (MODEL_V2, MODEL_V1SE):
            path = os.path.join(model_dir, filename)
            if not os.path.isfile(path):
                raise LivenessUnavailable(
                    f"Liveness model missing: {path} (run scripts/fetch_face_models.py)"
                )
            try:
                self._nets.append((cv2.dnn.readNetFromONNX(path), scale))
            except cv2.error as exc:
                raise LivenessUnavailable(f"Cannot load {path}: {exc}") from exc
        # Fail early if a model does not have the 3 classes (1 = real).
        for net, _ in self._nets:
            out = self._forward(net, np.zeros((INPUT_SIZE, INPUT_SIZE, 3), np.uint8))
            if out.size != 3:
                raise LivenessUnavailable(
                    f"Unexpected liveness output size {out.size} (want 3 classes)"
                )

    def _forward(self, net, crop):
        np = self._np
        blob = crop.astype(np.float32).transpose(2, 0, 1)[None]  # BGR, 0-255, NCHW
        net.setInput(blob)
        logits = net.forward().reshape(-1).astype(np.float64)
        e = np.exp(logits - logits.max())
        return e / e.sum()

    def check(self, frame, face) -> Tuple[bool, float]:
        """(is_live, mean real probability over both models)."""
        scores = []
        for net, scale in self._nets:
            crop = crop_scaled(frame, face.box, scale, self.input_size)
            scores.append(float(self._forward(net, crop)[1]))
        score = sum(scores) / len(scores)
        return score >= self.threshold, score


class HeadTurnChallenge:
    """Ask the person to turn the head and watch the landmarks.

    Direction is defined in the raw (unmirrored) camera image, never in screen
    terms, so mirroring the preview in the UI does not change the logic:
      "left"  = the nose moves toward smaller x (image left). This is the
                person turning toward THEIR OWN RIGHT.
      "right" = the nose moves toward larger x (image right), i.e. the person
                turns toward their own left.
    A UI that shows a mirrored preview must word its prompt accordingly
    (with a mirrored preview, "left" looks like turning toward screen right).

    yaw proxy = (nose_x - eyes_mid_x) / eye_distance, landmarks in YuNet order
    (right eye, left eye, nose, ...). Passes when the proxy beyond the
    threshold in the asked direction is seen after at least one near-frontal
    frame (|yaw| < frontal_threshold), so a photo already held turned fails.
    """

    def __init__(
        self,
        direction: str,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 6.0,
        yaw_threshold: float = 0.25,
        frontal_threshold: float = 0.1,
    ):
        if direction not in ("left", "right"):
            raise ValueError("direction must be 'left' or 'right'")
        self.direction = direction
        self._sign = -1.0 if direction == "left" else 1.0
        self._clock = clock
        self.timeout = timeout
        self.yaw_threshold = yaw_threshold
        self.frontal_threshold = frontal_threshold
        self._started = clock()
        self._seen_frontal = False
        self.state = "pending"

    @staticmethod
    def yaw(landmarks) -> float:
        re, le, nose = landmarks[0], landmarks[1], landmarks[2]
        eye_dist = abs(float(le[0]) - float(re[0]))
        if eye_dist < 1e-6:
            return 0.0
        mid = (float(re[0]) + float(le[0])) / 2.0
        return (float(nose[0]) - mid) / eye_dist

    def update(self, landmarks) -> str:
        """Feed one frame's landmarks (or None when no face): pending|passed|timeout."""
        if self.state != "pending":
            return self.state
        if self._clock() - self._started > self.timeout:
            self.state = "timeout"
            return self.state
        if landmarks is None:
            return self.state
        yaw = self.yaw(landmarks)
        if abs(yaw) < self.frontal_threshold:
            self._seen_frontal = True
        elif self._seen_frontal and yaw * self._sign > self.yaw_threshold:
            self.state = "passed"
        return self.state

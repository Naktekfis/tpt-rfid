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


# ---- Blink (eye aspect ratio on 68-point landmarks) ----

# dlib 68-point indices: eyes as p1..p6 (Soukupova & Cech 2016), mouth centre.
RIGHT_EYE = range(36, 42)
LEFT_EYE = range(42, 48)
UPPER_LIP, LOWER_LIP = 51, 57


def eye_aspect_ratio(pts) -> float:
    """EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|) for six eye points."""
    import math

    def d(a, b):
        return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))

    p1, p2, p3, p4, p5, p6 = pts
    width = d(p1, p4)
    if width < 1e-6:
        return 0.0
    return (d(p2, p6) + d(p3, p5)) / (2.0 * width)


def blink_metrics(lm68) -> Tuple[float, float]:
    """(raw EAR, EAR normalised by face proportions), averaged over both eyes.

    Tilting a phone photo forward or back squashes the whole face vertically,
    which lowers the raw EAR like a blink would. Dividing by the face's own
    height/width ratio (eye line to mouth centre over eye distance) cancels
    that: a real blink only moves the eyelids.
    """
    import math

    ear = (
        eye_aspect_ratio([lm68[i] for i in RIGHT_EYE])
        + eye_aspect_ratio([lm68[i] for i in LEFT_EYE])
    ) / 2.0

    def centre(idx):
        xs = [float(lm68[i][0]) for i in idx]
        ys = [float(lm68[i][1]) for i in idx]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    re, le = centre(RIGHT_EYE), centre(LEFT_EYE)
    eye_mid = ((re[0] + le[0]) / 2.0, (re[1] + le[1]) / 2.0)
    mouth = centre((UPPER_LIP, LOWER_LIP))
    eye_dist = math.hypot(le[0] - re[0], le[1] - re[1])
    face_h = math.hypot(mouth[0] - eye_mid[0], mouth[1] - eye_mid[1])
    if eye_dist < 1e-6 or face_h < 1e-6:
        return ear, 0.0
    return ear, ear / (face_h / eye_dist)


class Landmarks68:
    """dlib's 68-point shape predictor run on a box from any detector."""

    def __init__(self, model_path: str = ""):
        try:
            import dlib
        except ImportError as exc:
            raise LivenessUnavailable(f"dlib not installed: {exc}") from exc
        if not model_path:
            try:
                import face_recognition_models
            except ImportError as exc:
                raise LivenessUnavailable(
                    f"face_recognition_models not installed: {exc}"
                ) from exc
            model_path = face_recognition_models.pose_predictor_model_location()
        if not os.path.isfile(model_path):
            raise LivenessUnavailable(f"Landmark model missing: {model_path}")
        self._dlib = dlib
        self._predictor = dlib.shape_predictor(model_path)

    def __call__(self, frame, box) -> List[Tuple[int, int]]:
        x, y, w, h = box
        rect = self._dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
        shape = self._predictor(frame, rect)
        return [(shape.part(i).x, shape.part(i).y) for i in range(68)]


class BlinkChallenge:
    """Pass after `blinks_needed` blinks within `timeout` seconds.

    Fed one value per frame (normalised EAR from blink_metrics, or None when
    there is no face). The open-eye level is learnt as a running maximum-ish
    baseline (90th percentile of recent open values), so it adapts to each
    face. A blink = the value falls below `close_ratio` x baseline and comes
    back above `open_ratio` x baseline within `max_closed_frames` frames
    (longer closures are eyes shut / looking down, not a blink).
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 8.0,
        blinks_needed: int = 1,
        close_ratio: float = 0.65,
        open_ratio: float = 0.85,
        max_closed_frames: int = 12,
        warmup_frames: int = 5,
    ):
        self._clock = clock
        self.timeout = timeout
        self.blinks_needed = blinks_needed
        self.close_ratio = close_ratio
        self.open_ratio = open_ratio
        self.max_closed_frames = max_closed_frames
        self.warmup_frames = warmup_frames
        self._started = clock()
        self._open: List[float] = []
        self._closed_frames = 0
        self.blinks = 0
        self.state = "pending"

    @property
    def baseline(self) -> float:
        if not self._open:
            return 0.0
        ordered = sorted(self._open[-30:])
        return ordered[int(0.9 * (len(ordered) - 1))]

    def update(self, value) -> str:
        if self.state != "pending":
            return self.state
        if self._clock() - self._started > self.timeout:
            self.state = "timeout"
            return self.state
        if value is None:
            self._closed_frames = 0
            return self.state
        base = self.baseline
        if len(self._open) < self.warmup_frames or base <= 0:
            self._open.append(value)
            return self.state
        if self._closed_frames:
            if value >= self.open_ratio * base:
                if self._closed_frames <= self.max_closed_frames:
                    self.blinks += 1
                self._closed_frames = 0
                self._open.append(value)
                if self.blinks >= self.blinks_needed:
                    self.state = "passed"
            else:
                self._closed_frames += 1
        elif value < self.close_ratio * base:
            self._closed_frames = 1
        else:
            self._open.append(value)
        return self.state

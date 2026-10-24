"""
Face detection and embedding for admin face login, all via cv2.dnn:
YuNet detector + one recognizer (FACE_RECOGNIZER):

  arcface_mbf  ArcFace MobileFaceNet trained on WebFace600K (InsightFace
               buffalo_s w600k_mbf; non-commercial research licence),
               more accurate than SFace and a bit faster on the Jetson
  sface        OpenCV zoo SFace (Apache-2.0), the original choice

Brought back from legacy/face/utils/face.py, trimmed to what admin login
uses. cv2 and numpy are imported lazily, so the app and the tests run without
them; tests pass a fake engine with the same three methods.

Embeddings are L2-normalised float32; distance = 1 - cosine similarity.
Landmarks are 5 points in YuNet order: right eye, left eye, nose, right mouth
corner, left mouth corner ("right" = the person's right = smaller x in the
unmirrored camera frame).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
ARCFACE_MBF_FILE = "w600k_mbf.onnx"


class FaceModelsMissing(RuntimeError):
    """Model files or an optional dependency (cv2, numpy) is missing."""


@dataclass
class Face:
    box: Tuple[int, int, int, int]  # x, y, w, h
    landmarks: Any  # 5 (x, y) points, YuNet order
    score: float
    raw: Any = None  # engine-specific row


class YuNetSFaceEngine:
    name = "yunet_sface"
    threshold = 1.0 - 0.363  # OpenCV's cosine threshold for SFace

    def __init__(
        self,
        model_dir: str,
        threshold: Optional[float] = None,
        score_threshold: float = 0.8,
    ):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceModelsMissing(f"OpenCV/numpy not installed: {exc}") from exc
        det_path = os.path.join(model_dir, YUNET_FILE)
        rec_path = os.path.join(model_dir, SFACE_FILE)
        for path in (det_path, rec_path):
            if not os.path.isfile(path):
                raise FaceModelsMissing(f"Model file missing: {path}")
        self._np = np
        self._lock = threading.Lock()
        try:
            self._detector = cv2.FaceDetectorYN.create(
                det_path, "", (320, 320), score_threshold, 0.3, 5000
            )
            self._recognizer = cv2.FaceRecognizerSF.create(rec_path, "")
        except cv2.error as exc:
            raise FaceModelsMissing(f"Cannot load face models: {exc}") from exc
        if threshold is not None:
            self.threshold = threshold

    def detect(self, frame) -> List[Face]:
        """Faces, largest first."""
        np = self._np
        h, w = frame.shape[:2]
        with self._lock:
            self._detector.setInputSize((w, h))
            _, rows = self._detector.detect(frame)
        if rows is None:
            return []
        faces = []
        for row in rows:
            x, y, bw, bh = (int(round(float(v))) for v in row[:4])
            lm = np.array(row[4:14], dtype=np.float32).reshape(5, 2)
            faces.append(Face((x, y, bw, bh), lm, float(row[14]), row))
        faces.sort(key=lambda f: f.box[2] * f.box[3], reverse=True)
        return faces

    def embed(self, frame, face: Face):
        np = self._np
        with self._lock:
            aligned = self._recognizer.alignCrop(frame, face.raw)
            feat = self._recognizer.feature(aligned)
        vec = np.asarray(feat, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def distance(self, a, b) -> float:
        np = self._np
        return float(1.0 - np.dot(np.asarray(a, np.float32), np.asarray(b, np.float32)))


class YuNetArcFaceEngine(YuNetSFaceEngine):
    """YuNet + ArcFace MobileFaceNet. The SFace model is still loaded for its
    alignCrop (the same 5-point ArcFace template, 112x112)."""

    name = "yunet_arcface_mbf"
    # Cosine similarity 0.35; calibrate with the distances in the login log.
    threshold = 0.65

    def __init__(self, model_dir: str, threshold: Optional[float] = None, **kw):
        super().__init__(model_dir, threshold, **kw)
        import cv2

        path = os.path.join(model_dir, ARCFACE_MBF_FILE)
        if not os.path.isfile(path):
            raise FaceModelsMissing(f"Model file missing: {path}")
        try:
            self._arcface = cv2.dnn.readNetFromONNX(path)
        except cv2.error as exc:
            raise FaceModelsMissing(f"Cannot load {path}: {exc}") from exc
        self._cv2 = cv2

    def embed(self, frame, face: Face):
        np, cv2 = self._np, self._cv2
        with self._lock:
            aligned = self._recognizer.alignCrop(frame, face.raw)
            blob = cv2.dnn.blobFromImage(
                aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True
            )
            self._arcface.setInput(blob)
            vec = np.asarray(self._arcface.forward(), dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec


ENGINES = {"arcface_mbf": YuNetArcFaceEngine, "sface": YuNetSFaceEngine}


def create_engine(model_dir: str, recognizer: str = "arcface_mbf"):
    if recognizer not in ENGINES:
        raise ValueError(f"Unknown FACE_RECOGNIZER {recognizer!r} (use {sorted(ENGINES)})")
    return ENGINES[recognizer](model_dir)


def sharpness(frame, face: Face) -> float:
    """Laplacian variance of the face crop; low means blurred."""
    import cv2

    x, y, w, h = face.box
    crop = frame[max(0, y) : y + h, max(0, x) : x + w]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def portrait_box(frame_shape, face: Face) -> Tuple[int, int, int, int]:
    """(x, y, w, h) of a 4:5 head-and-shoulders close-up.

    Measured from the landmarks: D = eye line to chin (the box bottom). The
    top of the hair is about 1.1 D above the eyes, so the top is 1.5 D above
    them (a little space over the hair) and the bottom 0.9 D below the chin
    (the top of the shoulders). Shifted (not padded) to stay inside the frame;
    clipped only if the frame is smaller than the portrait."""
    fh, fw = frame_shape[:2]
    x, y, w, h = face.box
    lm = face.landmarks
    eye_y = (float(lm[0][1]) + float(lm[1][1])) / 2.0
    chin = float(y + h)
    d = max(1.0, chin - eye_y)
    top = eye_y - 1.5 * d
    ph = min(float(fh), (chin + 0.9 * d) - top)
    pw = min(float(fw), ph * 4.0 / 5.0)
    cx = (float(lm[0][0]) + float(lm[1][0]) + float(lm[2][0])) / 3.0
    left = min(max(0.0, cx - pw / 2.0), fw - pw)
    top = min(max(0.0, top), fh - ph)
    return int(round(left)), int(round(top)), int(round(pw)), int(round(ph))


def portrait_jpeg(frame, face: Face, width: int = 480) -> Optional[bytes]:
    """The registration photo: portrait_box, scaled to `width` px wide."""
    import cv2

    x, y, w, h = portrait_box(frame.shape, face)
    crop = frame[y : y + h, x : x + w]
    if crop.size == 0:
        return None
    if crop.shape[1] > width:
        crop = cv2.resize(
            crop, (width, round(crop.shape[0] * width / crop.shape[1])),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None


def face_jpeg(frame, face: Face, margin: float = 0.4) -> Optional[bytes]:
    """JPEG of the face with some margin, for the login log."""
    import cv2

    x, y, w, h = face.box
    fh, fw = frame.shape[:2]
    mx, my = int(w * margin), int(h * margin)
    crop = frame[
        max(0, y - my) : min(fh, y + h + my), max(0, x - mx) : min(fw, x + w + mx)
    ]
    if crop.size == 0:
        return None
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else None

"""
Face detection, embedding and matching.

cv2, numpy and face_recognition are optional and imported lazily, so the app
and the core tests run without them. Only cv2 APIs that exist since OpenCV
4.5.4 are used (FaceDetectorYN, FaceRecognizerSF), because the Jetson target
has OpenCV 4.x.

Engines
- YuNetSFaceEngine: YuNet detector + SFace 128-d embedding (cv2.dnn, ONNX).
  Embeddings are L2-normalised; distance = 1 - cosine similarity; default
  threshold 1 - 0.363 (OpenCV's cosine threshold for SFace).
- DlibEngine: face_recognition (dlib HOG + ResNet 128-d). The embedding is the
  raw dlib vector (NOT normalised, its scale is what the 0.6 / 0.5 rule of
  thumb refers to); distance = Euclidean (L2), default threshold 0.5. The
  distance scales of the two engines differ, so thresholds and stored
  embeddings are always per engine (FaceEmbedding.engine).

Landmarks are always 5 points in YuNet order: right eye, left eye, nose, right
mouth corner, left mouth corner ("right" = the person's right = smaller x in
an unmirrored camera frame). dlib's small model has no mouth corners; they are
estimated from the eyes and nose (good enough for the quality checks, the head
turn challenge only uses eyes and nose).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"

AMBIGUOUS_MARGIN = 0.05


class FaceModelsMissing(RuntimeError):
    """Model files or an optional dependency (cv2, face_recognition) is missing."""


@dataclass
class Face:
    box: Tuple[int, int, int, int]  # x, y, w, h
    landmarks: Any  # 5x2 float array (right eye, left eye, nose, right mouth, left mouth)
    score: float
    raw: Any = None  # engine-specific row


@dataclass
class Match:
    student_id: int
    distance: float


class FaceEngine:
    name = ""
    threshold = 1.0

    def detect(self, frame) -> List[Face]:
        raise NotImplementedError

    def embed(self, frame, face: Face):
        """float32 vector (see the engine docs for normalisation)."""
        raise NotImplementedError

    def distance(self, a, b) -> float:
        raise NotImplementedError


class YuNetSFaceEngine(FaceEngine):
    name = "yunet_sface"
    threshold = 1.0 - 0.363

    def __init__(self, model_dir: str, threshold: Optional[float] = None,
                 score_threshold: float = 0.8):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceModelsMissing(f"OpenCV/numpy not installed: {exc}") from exc
        det_path = os.path.join(model_dir, YUNET_FILE)
        rec_path = os.path.join(model_dir, SFACE_FILE)
        for path in (det_path, rec_path):
            if not os.path.isfile(path):
                raise FaceModelsMissing(
                    f"Model file missing: {path} (run scripts/fetch_face_models.py)"
                )
        self._cv2 = cv2
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
        # Both vectors are L2-normalised, so the dot product is the cosine.
        return float(1.0 - self._np.dot(a, b))


class DlibEngine(FaceEngine):
    name = "dlib"
    threshold = 0.5

    def __init__(self, model_dir: str = "", threshold: Optional[float] = None):
        try:
            import face_recognition
            import numpy as np
        except ImportError as exc:
            raise FaceModelsMissing(f"face_recognition not installed: {exc}") from exc
        self._fr = face_recognition
        self._np = np
        self._lock = threading.Lock()
        if threshold is not None:
            self.threshold = threshold

    @staticmethod
    def _rgb(frame):
        return frame[:, :, ::-1].copy()  # BGR -> RGB, contiguous for dlib

    def detect(self, frame) -> List[Face]:
        np = self._np
        rgb = self._rgb(frame)
        with self._lock:
            locs = self._fr.face_locations(rgb, 1, "hog")
            marks = (
                self._fr.face_landmarks(rgb, locs, model="small") if locs else []
            )
        faces = []
        for loc, mk in zip(locs, marks):
            top, right, bottom, left = loc
            re = np.mean(mk["right_eye"], axis=0)
            le = np.mean(mk["left_eye"], axis=0)
            nose = np.array(mk["nose_tip"][0], dtype=np.float64)
            # Mouth corners are not in the 5-point model: estimate them.
            eye_mid = (re + le) / 2.0
            down = nose - eye_mid
            rm = nose + down * 0.6 + (re - le) * 0.3
            lm_ = nose + down * 0.6 + (le - re) * 0.3
            lm = np.array([re, le, nose, rm, lm_], dtype=np.float32)
            faces.append(
                Face((left, top, right - left, bottom - top), lm, 1.0, loc)
            )
        faces.sort(key=lambda f: f.box[2] * f.box[3], reverse=True)
        return faces

    def embed(self, frame, face: Face):
        rgb = self._rgb(frame)
        with self._lock:
            encs = self._fr.face_encodings(rgb, [face.raw], 1, "small")
        return self._np.asarray(encs[0], dtype=self._np.float32)

    def distance(self, a, b) -> float:
        return float(self._np.linalg.norm(a - b))




ENGINES: Dict[str, Callable[..., FaceEngine]] = {
    "yunet_sface": YuNetSFaceEngine,
    "dlib": DlibEngine,
}


def create_face_engine(
    name: str, model_dir: str, threshold: Optional[float] = None
) -> FaceEngine:
    try:
        cls = ENGINES[name]
    except KeyError:
        raise ValueError(
            f"Unknown FACE_ENGINE {name!r} (use {sorted(ENGINES)})"
        ) from None
    return cls(model_dir, threshold)


def quality_issues(
    frame, faces: List[Face], min_face_px: int = 120, min_sharpness: float = 60.0
) -> List[str]:
    """Codes: no_face, multiple_faces, too_small, blurry. Empty list = good."""
    if not faces:
        return ["no_face"]
    if len(faces) > 1:
        return ["multiple_faces"]
    import cv2

    x, y, w, h = faces[0].box
    issues = []
    if min(w, h) < min_face_px:
        issues.append("too_small")
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    crop = frame[y0 : min(fh, y + h), x0 : min(fw, x + w)]
    if crop.size == 0:
        return ["no_face"]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if cv2.Laplacian(gray, cv2.CV_64F).var() < min_sharpness:
        issues.append("blurry")
    return issues


def sharpness(frame, face: Face) -> float:
    """Laplacian variance of the face crop (used to pick the best frame)."""
    import cv2

    x, y, w, h = face.box
    crop = frame[max(0, y) : y + h, max(0, x) : x + w]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class FaceIndex:
    """In-memory nearest-student lookup for one engine."""

    def __init__(self, distance: Callable[[Any, Any], float], threshold: float,
                 ambiguous_margin: float = AMBIGUOUS_MARGIN):
        self._distance = distance
        self.threshold = threshold
        self.margin = ambiguous_margin
        self._lock = threading.Lock()
        self._rows: List[Tuple[int, Any]] = []
        self.loaded = False

    def load(self, rows: List[Tuple[int, Any]]) -> None:
        rows = list(rows)
        with self._lock:  # swap atomically so identify never sees a half load
            self._rows = rows
            self.loaded = True

    def __len__(self) -> int:
        return len(self._rows)

    def identify_detail(self, vec) -> Tuple[Optional[Match], bool]:
        """(match, ambiguous). ambiguous means no match was returned because a
        second student is within the margin of the best one."""
        with self._lock:
            rows = self._rows
        best: Dict[int, float] = {}
        for sid, stored in rows:
            d = self._distance(vec, stored)
            if sid not in best or d < best[sid]:
                best[sid] = d
        ranked = sorted(best.items(), key=lambda kv: kv[1])
        if not ranked or ranked[0][1] > self.threshold:
            return None, False
        if (
            len(ranked) > 1
            and ranked[1][1] <= self.threshold
            and ranked[1][1] - ranked[0][1] < self.margin
        ):
            return None, True
        return Match(ranked[0][0], ranked[0][1]), False

    def identify(self, vec) -> Optional[Match]:
        return self.identify_detail(vec)[0]

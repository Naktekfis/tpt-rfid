"""
Face identify / enroll on top of the engine, liveness and DB.

Methods that touch the DB must be called inside a Flask app context (request
handlers already are). numpy/cv2 are only needed once a frame is processed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from .face import (
    FaceEngine,
    FaceIndex,
    FaceModelsMissing,
    create_face_engine,
    quality_issues,
    sharpness,
)
from .liveness import LivenessUnavailable, PassiveLiveness

logger = logging.getLogger(__name__)

MIN_ENROLL_FRAMES = 3


class FaceService:
    def __init__(
        self,
        app,
        database,
        camera,
        engine: Optional[FaceEngine],
        liveness,
        index: Optional[FaceIndex],
        min_face_px: int = 120,
        min_sharpness: float = 60.0,
    ):
        self.app = app
        self.database = database
        self.camera = camera
        self.engine = engine  # None = models/deps missing
        self.liveness = liveness  # None = fail closed
        self.index = index
        self.min_face_px = min_face_px
        self.min_sharpness = min_sharpness
        self._load_lock = threading.Lock()

    # ---- index ----

    def reload_index(self) -> None:
        if self.engine is None or self.index is None:
            return
        import numpy as np

        rows = self.database.get_face_embeddings(self.engine.name)
        self.index.load(
            [(sid, np.frombuffer(blob, dtype=np.float32)) for sid, blob in rows]
        )

    def _ensure_index(self) -> None:
        if self.index is not None and not self.index.loaded:
            with self._load_lock:
                if not self.index.loaded:
                    self.reload_index()

    # ---- shared per-frame steps ----

    def _unavailable(self) -> Optional[str]:
        # The passive liveness model is optional: the head-turn challenge is
        # the real gate (MiniFASNet passes phone photos), so only a missing
        # engine fails closed.
        if self.engine is None:
            return "models_missing"
        return None

    def _analyse(self, frame) -> Dict[str, Any]:
        """detect + quality (+ passive liveness score, informational only).
        Returns {"status": code} on failure, else {"status": "ok", "face",
        "liveness"} with liveness None when the model is missing."""
        faces = self.engine.detect(frame)
        issues = quality_issues(
            frame, faces, self.min_face_px, self.min_sharpness
        )
        if issues:
            return {"status": issues[0], "issues": issues}
        face = faces[0]
        score = None
        if self.liveness is not None:
            try:
                _, score = self.liveness.check(frame, face)
            except LivenessUnavailable:
                score = None
        logger.debug("passive liveness score: %s", score)
        return {"status": "ok", "face": face, "liveness": score}

    def landmarks(self, frame):
        """5-point landmarks of the single face in the frame, else None.
        Cheap (detect only, no quality/embedding): fed to the head-turn
        challenge on every frame."""
        if frame is None or self.engine is None:
            return None
        faces = self.engine.detect(frame)
        if len(faces) != 1:
            return None
        return faces[0].landmarks

    # ---- identify ----

    def identify_frame(self, frame) -> Dict[str, Any]:
        if frame is None:
            return {"status": "no_camera"}
        unavailable = self._unavailable()
        if unavailable:
            return {"status": unavailable}
        res = self._analyse(frame)
        if res["status"] != "ok":
            return {k: v for k, v in res.items() if k != "face"}
        face, liveness = res["face"], res["liveness"]
        self._ensure_index()
        vec = self.engine.embed(frame, face)
        match, ambiguous = self.index.identify_detail(vec)
        live = None if liveness is None else round(liveness, 3)
        if ambiguous:
            return {"status": "ambiguous", "liveness": live}
        if match is None:
            return {"status": "unknown", "liveness": live}
        student = self.database.get_student_by_id(str(match.student_id))
        if student is None:  # embeddings of a deleted student: stale index
            self.reload_index()
            return {"status": "unknown", "liveness": live}
        return {
            "status": "ok",
            "student": {
                "student_id": student["student_id"],
                "name": student["name"],
                "nim": student["nim"],
                "photo_url": student["photo_url"],
            },
            "distance": round(match.distance, 4),
            "liveness": live,
        }

    # ---- enroll ----

    def enroll(self, student_id: int, frames: List[Any]) -> Dict[str, Any]:
        unavailable = self._unavailable()
        if unavailable:
            return {"status": unavailable}
        frames = [f for f in frames if f is not None]
        if not frames:
            return {"status": "no_camera"}
        if self.database.get_student_by_id(str(student_id)) is None:
            return {"status": "not_found"}
        self._ensure_index()

        good = []  # (frame, face, vector)
        problems: Dict[str, int] = {}
        for frame in frames:
            res = self._analyse(frame)
            if res["status"] != "ok":
                problems[res["status"]] = problems.get(res["status"], 0) + 1
                continue
            good.append((frame, res["face"], self.engine.embed(frame, res["face"])))

        if len(good) < MIN_ENROLL_FRAMES:
            return {
                "status": "insufficient",
                "good_frames": len(good),
                "needed": MIN_ENROLL_FRAMES,
                "problems": problems,
            }

        for _, _, vec in good:
            other = self.index.nearest_other(vec, int(student_id))
            if other is not None:
                return {"status": "duplicate", "other_student_id": other.student_id}

        import numpy as np

        self.database.add_face_embeddings(
            student_id,
            self.engine.name,
            [np.asarray(v, dtype=np.float32).tobytes() for _, _, v in good],
            replace=True,
        )
        best_frame, best_face, _ = max(good, key=lambda g: g[1].box[2] * g[1].box[3] * sharpness(g[0], g[1]))
        jpeg = _face_jpeg(best_frame, best_face)
        if jpeg:
            self.database.update_student_photo(str(student_id), jpeg, "image/jpeg")
        self.reload_index()

        held_out = good[-1][0]
        check = self.identify_frame(held_out)
        verified = (
            check["status"] == "ok"
            and check["student"]["student_id"] == str(student_id)
        )
        return {
            "status": "ok",
            "stored": len(good),
            "verified": verified,
            "verify_status": check["status"],
        }

    def delete(self, student_id: int) -> bool:
        ok = self.database.delete_face_data(student_id)
        self.reload_index()
        return ok


def _face_jpeg(frame, face, margin: float = 0.4) -> Optional[bytes]:
    """JPEG of the face with a margin around the box."""
    import cv2

    fh, fw = frame.shape[:2]
    x, y, w, h = face.box
    x0, y0 = max(0, int(x - w * margin)), max(0, int(y - h * margin))
    x1, y1 = min(fw, int(x + w * (1 + margin))), min(fh, int(y + h * (1 + margin)))
    ok, buf = cv2.imencode(".jpg", frame[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else None


def build_face_service(app, database, camera, model_dir, engine_name, threshold=None):
    """FaceService that degrades instead of raising when deps/models are missing."""
    engine = liveness = index = None
    problems = []
    try:
        engine = create_face_engine(engine_name, model_dir, threshold)
        index = FaceIndex(engine.distance, engine.threshold)
    except (FaceModelsMissing, ValueError) as exc:
        problems.append(str(exc))
    try:
        liveness = PassiveLiveness(model_dir)
    except LivenessUnavailable as exc:
        problems.append(str(exc))
    if problems:
        logger.warning("Face identification degraded: %s", "; ".join(problems))
    return FaceService(app, database, camera, engine, liveness, index)

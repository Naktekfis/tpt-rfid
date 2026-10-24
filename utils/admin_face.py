"""
Admin face login and enrolment.

One attempt at a time reads the kiosk camera in a background thread: the admin
just looks at the camera for a moment, no head movement. Every frame used
must hold exactly one face, big enough and roughly facing the camera; a second
face or the face leaving the camera for long ends the attempt. Each used frame
is embedded and checked by the passive liveness models (utils/liveness.py).
After FRAMES_NEEDED frames, most must be live and every one must match the
same enrolled admin (login) or the same person (enrolment), so a photo cannot
be swapped in for part of the attempt.

Failures are logged with a face photo (AdminLoginEvent); repeated login
failures lock face login for a while, so the PIN is the way in. The engine,
liveness, camera, photo encoder and clock are injected, so tests use fakes and
run without cv2.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from array import array
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.liveness import yaw
from utils.models import AdminFace, AdminLoginEvent, db

logger = logging.getLogger(__name__)

LOGIN = "login"
ENROLL = "enroll"

REASONS = {
    "spoof": "Wajah tidak lolos pemeriksaan keaslian.",
    "unknown_face": "Wajah tidak dikenali.",
    "timeout": "Waktu habis.",
    "face_lost": "Wajah hilang dari kamera.",
    "cancelled": "Dibatalkan.",
    "camera": "Kamera tidak mengirim gambar.",
    "other_admin": "Wajah ini sudah terdaftar atas nama admin lain.",
    "name_taken": "Nama ini sudah dipakai wajah lain.",
    "face_changed": "Wajah berganti selama pemeriksaan.",
    "multiple_faces": "Lebih dari satu wajah di depan kamera.",
    "error": "Terjadi kesalahan.",
}


class FaceUnavailable(RuntimeError):
    """Face login is off or cannot run (models, camera)."""


class FaceLocked(RuntimeError):
    """Too many failed face logins; use the PIN."""


@dataclass
class FaceSettings:
    frames_needed: int = 6  # frames looked at per attempt (~2 s on the Jetson)
    min_live: int = 5  # of those, how many must pass liveness
    match_threshold: Optional[float] = None  # None = engine default
    ambiguous_margin: float = 0.05
    min_face_px: int = 100
    facing_yaw: float = 0.35  # roughly facing the camera
    timeout: float = 12.0
    face_lost_seconds: float = 1.5
    lockout_failures: int = 3
    lockout_window: float = 600.0
    lockout_seconds: float = 300.0


@dataclass
class Attempt:
    id: str
    mode: str
    started: float
    name: Optional[str] = None  # enrol: the new admin; login: who matched
    state: str = "running"  # running | passed | failed
    reason: Optional[str] = None
    hint: Optional[str] = None
    consumed: bool = False  # login passed and turned into a session
    frames: List[Tuple[Any, bool]] = field(default_factory=list)  # (embedding, live)
    scores: Dict[str, List[float]] = field(default_factory=dict)  # per liveness model
    last_face_at: Optional[float] = None
    photo: Optional[bytes] = None
    needed: int = 6

    @property
    def instruction(self) -> str:
        if self.state == "passed":
            return "Berhasil."
        if self.state == "failed":
            return REASONS.get(self.reason or "", "Gagal.")
        return "Lihat ke kamera"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.id,
            "mode": self.mode,
            "state": self.state,
            "instruction": self.instruction,
            "hint": self.hint,
            "progress": min(1.0, len(self.frames) / max(1, self.needed)),
            "reason": self.reason,
            "name": self.name if self.state == "passed" else None,
        }


def pack(vec) -> bytes:
    return array("f", [float(v) for v in vec]).tobytes()


def unpack(blob: bytes) -> List[float]:
    out = array("f")
    out.frombytes(blob)
    return list(out)


class FaceAuth:
    def __init__(
        self,
        app,
        camera,
        engine=None,
        liveness=None,
        settings: Optional[FaceSettings] = None,
        unavailable: Optional[str] = None,
        photo: Optional[Callable[[Any, Any], Optional[bytes]]] = None,
        clock: Callable[[], float] = time.monotonic,
        threaded: bool = True,
    ):
        self.app = app
        self.camera = camera
        self.engine = engine
        self.liveness = liveness
        self.settings = settings or FaceSettings()
        self.unavailable = unavailable or (
            None if engine and liveness else "Model wajah tidak tersedia."
        )
        self._photo = photo
        self._clock = clock
        self._threaded = threaded
        self._lock = threading.Lock()
        self._attempts: Dict[str, Attempt] = {}
        self._running: Optional[Attempt] = None
        self._failures: deque = deque()
        self._locked_until = 0.0

    @property
    def available(self) -> bool:
        return self.unavailable is None

    @property
    def threshold(self) -> float:
        t = self.settings.match_threshold
        return t if t is not None else self.engine.threshold

    def locked_for(self) -> float:
        """Seconds face login stays locked (0 = open)."""
        return max(0.0, self._locked_until - self._clock())

    # ---------- Attempts ----------

    def start(self, mode: str, name: Optional[str] = None) -> Attempt:
        if not self.available:
            raise FaceUnavailable(self.unavailable)
        if mode == LOGIN and self.locked_for() > 0:
            raise FaceLocked()
        attempt = Attempt(
            id=uuid.uuid4().hex,
            mode=mode,
            started=self._clock(),
            name=name if mode == ENROLL else None,
            needed=self.settings.frames_needed,
        )
        with self._lock:
            if self._running is not None:  # one camera: the newest attempt wins
                self._fail(self._running, "cancelled")
            self._running = attempt
            self._attempts[attempt.id] = attempt
            for old in list(self._attempts)[:-10]:
                del self._attempts[old]
        if self._threaded:
            threading.Thread(
                target=self._run, args=(attempt,), name="face-login", daemon=True
            ).start()
        else:
            self._run(attempt)
        return attempt

    def get(self, attempt_id: Optional[str]) -> Optional[Attempt]:
        with self._lock:
            return self._attempts.get(attempt_id or "")

    def cancel(self, attempt_id: Optional[str]) -> None:
        with self._lock:
            attempt = self._attempts.get(attempt_id or "")
            if attempt is not None and attempt.state == "running":
                self._fail(attempt, "cancelled")

    def consume(self, attempt_id: Optional[str]) -> Optional[str]:
        """Admin name of a passed, unused login attempt (once), else None."""
        with self._lock:
            a = self._attempts.get(attempt_id or "")
            if a is None or a.mode != LOGIN or a.state != "passed" or a.consumed:
                return None
            a.consumed = True
            return a.name

    def _run(self, attempt: Attempt) -> None:
        try:
            while attempt.state == "running":
                if self._clock() - attempt.started > self.settings.timeout:
                    self._finish(attempt, False, "timeout")
                    break
                frame = self.camera.read()
                if frame is None:
                    if not self._threaded:  # mock camera ran out of frames
                        self._finish(attempt, False, "camera")
                        break
                    time.sleep(0.05)
                    continue
                self.step(attempt, frame)
                if self._threaded:
                    time.sleep(0.05)  # about the camera frame rate
        except Exception:  # thread boundary: OpenCV can raise anything
            logger.exception("Face attempt failed")
            self._finish(attempt, False, "error")

    def step(self, attempt: Attempt, frame) -> None:
        """Feed one camera frame to a running attempt."""
        s = self.settings
        now = self._clock()
        detected = self.engine.detect(frame)
        # Small faces (far in the background) are ignored altogether.
        faces = [f for f in detected if min(f.box[2], f.box[3]) >= s.min_face_px]
        if len(faces) != 1:
            if faces and attempt.last_face_at is not None:
                self._finish(attempt, False, "multiple_faces")
                return
            if faces:
                attempt.hint = "Hanya satu wajah di depan kamera"
            else:
                attempt.hint = "Mendekat ke kamera" if detected else None
            if (
                attempt.last_face_at is not None
                and now - attempt.last_face_at > s.face_lost_seconds
            ):
                self._finish(attempt, False, "face_lost")
            return
        face = faces[0]
        attempt.last_face_at = now
        if abs(yaw(face.landmarks)) > s.facing_yaw:
            attempt.hint = "Hadapkan wajah ke kamera"
            return
        attempt.hint = None
        if attempt.photo is None and self._photo is not None:
            attempt.photo = self._photo(frame, face)
        live, scores = self.liveness.check(frame, face)
        for model, value in scores.items():
            attempt.scores.setdefault(model, []).append(float(value))
        attempt.frames.append((self.engine.embed(frame, face), bool(live)))
        if len(attempt.frames) >= s.frames_needed:
            self._decide(attempt)

    def _decide(self, attempt: Attempt) -> None:
        s = self.settings
        if sum(1 for _, live in attempt.frames if live) < s.min_live:
            self._finish(attempt, False, "spoof")
            return
        vecs = [v for v, _ in attempt.frames]
        gallery = self._gallery()
        if attempt.mode == LOGIN:
            name = self._match(vecs, gallery)
            if name is None:
                self._finish(attempt, False, "unknown_face")
                return
            attempt.name = name
            self._finish(attempt, True, None)
            return
        if not self._close_to(vecs[:1], vecs, self.threshold):
            self._finish(attempt, False, "face_changed")
            return
        own = [(n, v) for n, v in gallery if n == attempt.name]
        if own and self._match(vecs, own) != attempt.name:
            self._finish(attempt, False, "name_taken")
            return
        others = [(n, v) for n, v in gallery if n != attempt.name]
        if others and self._match(vecs, others, require_all=False):
            self._finish(attempt, False, "other_admin")
            return
        self._finish(attempt, True, None, store=vecs)

    def _close_to(self, reference, vecs, limit: float) -> bool:
        """Every vector is within `limit` of its nearest reference vector."""
        return bool(reference) and all(
            min(self.engine.distance(v, r) for r in reference) <= limit for v in vecs
        )

    def _match(self, vecs, gallery, require_all: bool = True) -> Optional[str]:
        """The admin every embedding matches (or, with require_all=False, any one
        embedding matches), else None. Ambiguous best/second-best counts as no match."""
        names = []
        for vec in vecs:
            best: Dict[str, float] = {}
            for name, stored in gallery:
                d = self.engine.distance(vec, stored)
                if name not in best or d < best[name]:
                    best[name] = d
            ranked = sorted(best.items(), key=lambda kv: kv[1])
            ok = (
                bool(ranked)
                and ranked[0][1] <= self.threshold
                and not (
                    len(ranked) > 1
                    and ranked[1][1] - ranked[0][1] < self.settings.ambiguous_margin
                )
            )
            if not require_all and ok:
                return ranked[0][0]
            names.append(ranked[0][0] if ok else None)
        if require_all and names and None not in names and len(set(names)) == 1:
            return names[0]
        return None

    def _fail(self, attempt: Attempt, reason: str) -> None:
        attempt.state = "failed"
        attempt.reason = reason
        if self._running is attempt:
            self._running = None

    def _finish(
        self, attempt: Attempt, ok: bool, reason: Optional[str], store=None
    ) -> None:
        with self._lock:
            if attempt.state != "running":
                return
            if ok:
                attempt.state = "passed"
                if self._running is attempt:
                    self._running = None
            else:
                self._fail(attempt, reason or "error")
            # Per-model liveness means, for calibrating the thresholds from the log.
            logger.info(
                "Face %s %s%s, liveness %s",
                attempt.mode,
                "passed" if ok else "failed",
                f" ({reason})" if reason else "",
                {m: round(sum(v) / len(v), 3) for m, v in attempt.scores.items()},
            )
            # A passer-by in the picture is bad luck, not an attack attempt.
            if attempt.mode == LOGIN and not ok and reason not in ("cancelled", "multiple_faces"):
                self._note_failure()
        with self.app.app_context():
            if store:
                engine = self.engine.name
                db.session.add_all(
                    AdminFace(name=attempt.name, engine=engine, vector=pack(v))
                    for v in store
                )
            db.session.add(
                AdminLoginEvent(
                    method="face" if attempt.mode == LOGIN else "enroll",
                    success=ok,
                    admin_name=attempt.name,
                    reason=reason,
                    photo=attempt.photo,
                )
            )
            db.session.commit()

    def _note_failure(self) -> None:
        s = self.settings
        now = self._clock()
        self._failures.append(now)
        while self._failures and now - self._failures[0] > s.lockout_window:
            self._failures.popleft()
        if len(self._failures) >= s.lockout_failures:
            self._locked_until = now + s.lockout_seconds
            self._failures.clear()
            logger.warning(
                "Face login locked for %.0f s after repeated failures",
                s.lockout_seconds,
            )

    # ---------- Enrolled admins ----------

    def _gallery(self) -> List[Tuple[str, List[float]]]:
        with self.app.app_context():
            rows = AdminFace.query.filter_by(engine=self.engine.name).all()
            return [(r.name, unpack(r.vector)) for r in rows]


def list_admin_faces() -> List[Dict[str, Any]]:
    """Enrolled admins: name, number of embeddings, first enrolment (UTC)."""
    rows = (
        db.session.query(
            AdminFace.name,
            db.func.count(AdminFace.id),
            db.func.min(AdminFace.created_at),
        )
        .group_by(AdminFace.name)
        .order_by(AdminFace.name)
        .all()
    )
    return [{"name": n, "samples": c, "created_at": t} for n, c, t in rows]


def delete_admin_face(name: str) -> int:
    count = AdminFace.query.filter_by(name=name).delete()
    db.session.commit()
    return count


def log_pin_login(success: bool) -> None:
    db.session.add(
        AdminLoginEvent(
            method="pin", success=success, reason=None if success else "wrong_pin"
        )
    )
    db.session.commit()


def build_face_auth(app, camera) -> FaceAuth:
    """FaceAuth from config; unavailable (with a reason) when off or models fail."""
    cfg = app.config
    settings = FaceSettings(match_threshold=cfg.get("FACE_MATCH_THRESHOLD"))
    if not cfg.get("FACE_LOGIN_ENABLED", False):
        return FaceAuth(
            app, camera, settings=settings, unavailable="Login wajah dimatikan."
        )
    if not cfg.get("CAMERA_ENABLED", False):
        return FaceAuth(
            app, camera, settings=settings, unavailable="Kamera tidak aktif."
        )
    from utils.face import FaceModelsMissing, YuNetSFaceEngine, face_jpeg
    from utils.liveness import Liveness, LivenessUnavailable

    model_dir = cfg.get("FACE_MODEL_DIR", "models/face")
    try:
        engine = YuNetSFaceEngine(model_dir)
        liveness = Liveness(model_dir, cfg.get("FACE_LIVENESS_MODELS", "mn3:0.5"))
    except (FaceModelsMissing, LivenessUnavailable, ValueError) as exc:
        logger.warning("Face login unavailable: %s", exc)
        return FaceAuth(
            app, camera, settings=settings, unavailable="Model wajah tidak tersedia."
        )
    logger.info(
        "Face login on (liveness %s)", cfg.get("FACE_LIVENESS_MODELS", "mn3:0.5")
    )
    return FaceAuth(app, camera, engine, liveness, settings, photo=face_jpeg)

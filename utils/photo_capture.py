"""
Guided face photo for student self-registration at the kiosk.

The student presses "Ambil foto"; a background thread reads the kiosk camera:
a moment to read "Lihat ke kamera", a 3-2-1 countdown with a short beep from
the reader's buzzer on each count, a longer beep ("cekrek"), then up to
`capture_seconds` of frames. A frame counts only if YuNet finds exactly one
face that is big enough, roughly facing the camera and sharp; after
`frames_needed` such frames the sharpest one is kept as a 4:5 portrait from
the forehead to the chin (utils.face.portrait_box). No recognition or liveness: this is a record photo.

Like the NFC capture, the photo stays on the server: the browser gets a
token bound to its session (capture_owner), and /api/register takes the
photo by token, so a client cannot upload an arbitrary picture. Engine,
camera, beep and clock are injected; tests use fakes and run without cv2.
"""

from __future__ import annotations

import logging
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from utils.liveness import yaw

logger = logging.getLogger(__name__)

REASONS = {
    "no_face": "Wajah tidak terlihat jelas. Mendekat ke kamera dan ulangi.",
    "multiple_faces": "Lebih dari satu wajah di depan kamera. Ulangi sendirian.",
    "camera": "Kamera tidak mengirim gambar.",
    "cancelled": "Dibatalkan.",
    "error": "Terjadi kesalahan. Ulangi.",
}


@dataclass
class PhotoSettings:
    prepare: float = 1.0  # time to read "Lihat ke kamera"
    countdown: int = 3  # 3-2-1, one second each
    capture_seconds: float = 3.0  # then look for good frames this long
    frames_needed: int = 3
    min_face_px: int = 110
    facing_yaw: float = 0.35
    min_sharpness: float = 25.0  # Laplacian variance of the face crop
    expires: float = 300.0  # a ready photo is kept this long


@dataclass
class Capture:
    token: str
    owner: str
    started: float
    shoot_at: float  # frames are used from this time on
    state: str = "running"  # running | ready | failed
    reason: Optional[str] = None
    hint: Optional[str] = None
    countdown: Optional[int] = None
    shooting: bool = False  # after the "cekrek"
    good: int = 0
    best: Optional[bytes] = None
    best_sharpness: float = -1.0
    finished_at: float = 0.0
    seen: Dict[str, int] = field(default_factory=dict)

    @property
    def instruction(self) -> str:
        if self.state == "ready":
            return "Foto tersimpan."
        if self.state == "failed":
            return REASONS.get(self.reason or "", "Gagal.")
        if self.countdown:
            return str(self.countdown)
        if self.shooting:
            return "Tahan…"
        return "Lihat ke kamera"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "state": self.state,
            "instruction": self.instruction,
            "hint": self.hint,
            "countdown": self.countdown,
            "reason": self.reason,
        }


class PhotoCaptureError(RuntimeError):
    pass


class PhotoCapture:
    def __init__(
        self,
        camera,
        engine=None,
        beep: Optional[Callable[..., None]] = None,
        sharpness: Optional[Callable[[Any, Any], float]] = None,
        encode: Optional[Callable[[Any, Any], Optional[bytes]]] = None,
        settings: Optional[PhotoSettings] = None,
        unavailable: Optional[str] = None,
        clock: Callable[[], float] = time.monotonic,
        threaded: bool = True,
    ):
        self.camera = camera
        self.engine = engine
        self.settings = settings or PhotoSettings()
        self.unavailable = unavailable or (None if engine else "Kamera tidak aktif.")
        self._beep = beep
        self._sharpness = sharpness or (lambda frame, face: 100.0)
        self._encode = encode or (lambda frame, face: b"jpeg")
        self._clock = clock
        self._threaded = threaded
        self._lock = threading.Lock()
        self._captures: Dict[str, Capture] = {}  # by owner: one per browser
        self._running: Optional[Capture] = None

    @property
    def available(self) -> bool:
        return self.unavailable is None

    def start(self, owner: str) -> Capture:
        if not self.available:
            raise PhotoCaptureError(self.unavailable)
        s = self.settings
        now = self._clock()
        capture = Capture(
            token=secrets.token_urlsafe(18),
            owner=owner,
            started=now,
            shoot_at=now + s.prepare + s.countdown,
        )
        with self._lock:
            if self._running is not None:  # one camera: the newest capture wins
                self._fail(self._running, "cancelled")
            self._running = capture
            self._captures[owner] = capture
            self._expire(now)
        if self._threaded:
            threading.Thread(
                target=self._run, args=(capture,), name="register-photo", daemon=True
            ).start()
        else:
            self._run(capture)
        return capture

    def get(self, owner: str, token: str) -> Optional[Capture]:
        with self._lock:
            c = self._captures.get(owner)
            return c if c is not None and c.token == token else None

    def cancel(self, owner: str, token: str) -> None:
        with self._lock:
            c = self._captures.get(owner)
            if c is not None and c.token == token:
                if c.state == "running":
                    self._fail(c, "cancelled")
                del self._captures[owner]

    def take(self, owner: str, token: str) -> Optional[bytes]:
        """The ready photo of this browser's capture (once), else None."""
        with self._lock:
            self._expire(self._clock())
            c = self._captures.get(owner)
            if c is None or c.token != token or c.state != "ready":
                return None
            del self._captures[owner]
            return c.best

    def preview(self, owner: str, token: str) -> Optional[bytes]:
        c = self.get(owner, token)
        return c.best if c is not None and c.state == "ready" else None

    # ---------- Capture loop ----------

    def _run(self, capture: Capture) -> None:
        s = self.settings
        try:
            while capture.state == "running":
                if self._clock() > capture.shoot_at + s.capture_seconds:
                    self._fail(capture, self._why_not(capture))
                    break
                frame = self.camera.read()
                if frame is None:
                    if not self._threaded:  # mock camera ran out of frames
                        self._fail(capture, "camera")
                        break
                    time.sleep(0.05)
                    continue
                self.step(capture, frame)
                if self._threaded:
                    time.sleep(0.05)
        except Exception:  # thread boundary: OpenCV can raise anything
            logger.exception("Registration photo failed")
            self._fail(capture, "error")

    def step(self, capture: Capture, frame) -> None:
        s = self.settings
        now = self._clock()
        if now < capture.shoot_at:
            left = capture.shoot_at - now
            count = math.ceil(left) if left <= s.countdown else None
            if count and count != capture.countdown:
                self._buzz(active=2, silent=1, times=1)
            capture.countdown = count
            return
        if not capture.shooting:  # the capture starts now: "cekrek"
            capture.shooting = True
            capture.countdown = None
            self._buzz(active=6, silent=1, times=1)
        faces = [
            f
            for f in self.engine.detect(frame)
            if min(f.box[2], f.box[3]) >= s.min_face_px
        ]
        if len(faces) != 1:
            kind = "multiple_faces" if faces else "no_face"
            capture.seen[kind] = capture.seen.get(kind, 0) + 1
            capture.hint = (
                "Hanya satu wajah di depan kamera" if faces else "Mendekat ke kamera"
            )
            return
        face = faces[0]
        if abs(yaw(face.landmarks)) > s.facing_yaw:
            capture.hint = "Hadapkan wajah ke kamera"
            return
        sharp = self._sharpness(frame, face)
        if sharp < s.min_sharpness:
            capture.hint = "Diam sebentar"
            return
        capture.hint = None
        capture.good += 1
        if sharp > capture.best_sharpness:
            jpeg = self._encode(frame, face)
            if jpeg:
                capture.best, capture.best_sharpness = jpeg, sharp
        if capture.good >= s.frames_needed and capture.best:
            with self._lock:
                if capture.state != "running":
                    return
                capture.state = "ready"
                capture.finished_at = now
                if self._running is capture:
                    self._running = None
            logger.info(
                "Registration photo ready (sharpness %.0f)", capture.best_sharpness
            )

    # ---------- Helpers ----------

    def _why_not(self, capture: Capture) -> str:
        if capture.seen.get("multiple_faces", 0) > capture.seen.get("no_face", 0):
            return "multiple_faces"
        return "no_face"

    def _fail(self, capture: Capture, reason: str) -> None:
        if capture.state != "running":
            return
        capture.state = "failed"
        capture.reason = reason
        capture.countdown = None
        capture.finished_at = self._clock()
        if self._running is capture:
            self._running = None

    def _buzz(self, **pattern) -> None:
        if self._beep is None:
            return
        try:
            self._beep(**pattern)
        except Exception:  # a buzzer fault must not end the capture
            logger.exception("Registration photo beep failed")

    def _expire(self, now: float) -> None:
        for owner, c in list(self._captures.items()):
            if c.state != "running" and now - c.finished_at > self.settings.expires:
                del self._captures[owner]


def build_photo_capture(app, camera, beep=None) -> PhotoCapture:
    """PhotoCapture from config; unavailable (photo not required) without a
    camera or the YuNet model, so registration still works on a dev laptop."""
    cfg = app.config
    if not cfg.get("CAMERA_ENABLED", False):
        return PhotoCapture(camera, unavailable="Kamera tidak aktif.")
    from utils.face import FaceModelsMissing, YuNetSFaceEngine, portrait_jpeg, sharpness

    try:
        engine = YuNetSFaceEngine(cfg.get("FACE_MODEL_DIR", "models/face"))
    except FaceModelsMissing as exc:
        logger.warning("Registration photo unavailable: %s", exc)
        return PhotoCapture(camera, unavailable="Model wajah tidak tersedia.")
    return PhotoCapture(
        camera,
        engine,
        beep=beep,
        sharpness=sharpness,
        encode=portrait_jpeg,
    )

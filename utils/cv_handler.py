"""
CV Handler — TPT-RFID Computer Vision Benchmark
Handles camera management, face recognition pipeline, and system stats.

Dependencies:
    pip install opencv-python face_recognition psutil
    (on RPi: pip install opencv-python face_recognition psutil --break-system-packages)

Face Recognition stack:
    face_recognition (ageitgey) → dlib HOG detector + 128-dim ResNet embedding
    Detection model: HOG (fast on ARM, ~3–7 FPS at 480p on RPi 4B)
    Matching: Euclidean distance on embeddings, threshold-based binary result
    Similarity score: (1.0 - distance) * 100, displayed as percentage
"""

import cv2
import threading
import time
import subprocess
import logging

logger = logging.getLogger(__name__)

# Lazy-import face_recognition (dlib takes ~3s to load)
_face_recognition = None


def _get_fr():
    global _face_recognition
    if _face_recognition is None:
        import face_recognition as fr

        _face_recognition = fr
    return _face_recognition


# ─── Resolution presets ───────────────────────────────────────────────────────

RESOLUTIONS = {
    "240p": (426, 240),
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}

RESOLUTION_ORDER = ["240p", "360p", "480p", "720p", "1080p"]


# ─── Camera singleton ─────────────────────────────────────────────────────────


class CVCamera:
    """
    Thread-safe camera wrapper.
    One instance shared across all CV routes via module-level `camera`.
    """

    def __init__(self):
        self.cap: cv2.VideoCapture | None = None
        self.lock = threading.Lock()
        self.current_res: str = "480p"
        self.available_res: list[str] = []

        # FPS tracking
        self._frame_count = 0
        self._fps_tick = time.time()
        self.fps: float = 0.0

        # Face recognition state
        self.reference_encoding = None  # numpy array from capture
        self.reference_frame = None  # BGR frame of the captured photo
        self.recognition_active: bool = False
        self.current_threshold: float = 0.55
        self.attempt_number: int = 1  # 1→3, threshold loosens each retry
        self.last_match: bool = False
        self.last_similarity: float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self, index: int = 0) -> bool:
        with self.lock:
            if self.cap and self.cap.isOpened():
                return True
            self.cap = cv2.VideoCapture(index)
            if not self.cap.isOpened():
                logger.error("Cannot open camera index %d", index)
                return False
        self._probe_resolutions()
        logger.info("Camera opened. Available: %s", self.available_res)
        return True

    def release(self):
        with self.lock:
            if self.cap:
                self.cap.release()
                self.cap = None
        self.available_res = []
        logger.info("Camera released.")

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    # ── Resolution management ─────────────────────────────────────────────────

    def _probe_resolutions(self):
        """Test each preset and record which ones the camera actually supports."""
        found = []
        with self.lock:
            for label in RESOLUTION_ORDER:
                w, h = RESOLUTIONS[label]
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                aw = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                ah = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                # Allow ±5% tolerance
                if abs(aw - w) / w <= 0.05 and abs(ah - h) / h <= 0.05:
                    found.append(label)
        self.available_res = found

        # Default to 480p, else best available
        default = "480p" if "480p" in found else (found[-1] if found else None)
        if default:
            self._apply_resolution(default)
            self.current_res = default

    def set_resolution(self, label: str) -> dict:
        """
        Try to set resolution. Returns status dict:
          { ok: bool, applied: str, available: list }
        """
        if label not in RESOLUTIONS:
            return {
                "ok": False,
                "reason": "unknown_label",
                "applied": self.current_res,
                "available": self.available_res,
            }

        if label not in self.available_res:
            # Try anyway, revert if fails
            success = self._apply_resolution(label)
            if not success:
                self._apply_resolution(self.current_res)  # revert
                return {
                    "ok": False,
                    "reason": "not_supported",
                    "applied": self.current_res,
                    "available": self.available_res,
                }

        self._apply_resolution(label)
        self.current_res = label
        return {"ok": True, "applied": label, "available": self.available_res}

    def _apply_resolution(self, label: str) -> bool:
        w, h = RESOLUTIONS[label]
        with self.lock:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            aw = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return abs(aw - w) / w <= 0.05 and abs(ah - h) / h <= 0.05

    def get_highest_available_res(self) -> str | None:
        for label in reversed(RESOLUTION_ORDER):
            if label in self.available_res:
                return label
        return None

    # ── Frame capture ─────────────────────────────────────────────────────────

    def read_frame(self):
        """Return BGR frame (mirrored horizontally) and update FPS counter."""
        with self.lock:
            if not self.cap or not self.cap.isOpened():
                return None
            ret, frame = self.cap.read()
        if not ret:
            return None

        # Mirror horizontally for natural preview
        frame = cv2.flip(frame, 1)

        # FPS
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._fps_tick
        if elapsed >= 0.5:  # update every 0.5s
            self.fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_tick = now
        return frame

    # ── Face recognition ──────────────────────────────────────────────────────

    def capture_reference_photo(self) -> dict:
        """
        Capture a single frame at highest resolution, extract face encoding.
        Returns { ok, message, resolution_used }
        """
        fr = _get_fr()

        best = self.get_highest_available_res()
        if best:
            self._apply_resolution(best)
        time.sleep(0.3)  # let camera adjust exposure

        frame = self.read_frame()
        if frame is None:
            return {"ok": False, "message": "Gagal mengambil frame dari kamera."}

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = fr.face_locations(rgb, model="hog")

        if not locations:
            return {
                "ok": False,
                "message": "Tidak ada wajah terdeteksi. Posisikan wajah dengan benar.",
            }

        encodings = fr.face_encodings(rgb, locations)
        if not encodings:
            return {"ok": False, "message": "Gagal mengekstrak fitur wajah."}

        self.reference_encoding = encodings[0]
        self.reference_frame = frame.copy()
        self.attempt_number = 1
        self.current_threshold = _threshold_for_attempt(1)
        logger.info("Reference face captured at %s", best)

        # Revert to benchmark resolution (480p)
        self.set_resolution(self.current_res)
        return {
            "ok": True,
            "message": "Foto referensi berhasil diambil.",
            "resolution_used": best,
        }

    def reset_recognition(self):
        """Clear reference — used when navigating away."""
        self.reference_encoding = None
        self.reference_frame = None
        self.recognition_active = False
        self.attempt_number = 1
        self.current_threshold = _threshold_for_attempt(1)
        self.last_match = False
        self.last_similarity = 0.0

    def retry_recognition(self) -> dict:
        """
        Called on each retry. Lowers threshold progressively.
        After attempt 3, threshold is at its most lenient.
        Returns { attempt, threshold, max_attempts }
        """
        self.attempt_number = min(self.attempt_number + 1, 3)
        self.current_threshold = _threshold_for_attempt(self.attempt_number)
        self.last_match = False
        return {
            "attempt": self.attempt_number,
            "threshold": self.current_threshold,
            "max_attempts": 3,
        }

    def process_recognition_frame(self, frame):
        """
        Run face recognition on a live frame against stored reference.
        Returns (annotated_frame, match: bool, similarity: float 0–1)
        """
        if self.reference_encoding is None:
            return frame, False, 0.0

        fr = _get_fr()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Use HOG — faster on ARM than CNN
        locations = fr.face_locations(rgb, model="hog")
        best_match = False
        best_sim = 0.0

        for loc in locations:
            encodings = fr.face_encodings(rgb, [loc])
            if not encodings:
                continue
            distance = fr.face_distance([self.reference_encoding], encodings[0])[0]
            sim = float(max(0.0, 1.0 - distance))
            match = distance < self.current_threshold

            if sim > best_sim:
                best_sim = sim
                best_match = match

            # Draw bounding box
            top, right, bottom, left = loc
            color = (0, 200, 80) if match else (0, 60, 220)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(
                frame, (left, bottom - 28), (right, bottom), color, cv2.FILLED
            )
            text = f"{'COCOK' if match else 'TIDAK'} {sim * 100:.0f}%"
            cv2.putText(
                frame,
                text,
                (left + 4, bottom - 8),
                cv2.FONT_HERSHEY_DUPLEX,
                0.55,
                (255, 255, 255),
                1,
            )

        self.last_match = best_match
        self.last_similarity = best_sim
        return frame, best_match, best_sim


def _threshold_for_attempt(attempt: int) -> float:
    """
    Attempt 1: strict  (0.50) → ~80% similarity needed
    Attempt 2: normal  (0.55) → ~73% similarity needed
    Attempt 3: lenient (0.60) → dlib default, ~67% needed
    """
    return {1: 0.50, 2: 0.55, 3: 0.60}.get(attempt, 0.60)


# ─── System stats ─────────────────────────────────────────────────────────────


def get_system_stats() -> dict:
    """
    Returns { cpu: float, ram: float, temp: float }
    CPU and RAM in percent. Temp in Celsius.
    Works on RPi (vcgencmd / thermal_zone) and generic Linux.
    """
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
    except ImportError:
        cpu, ram = 0.0, 0.0

    temp = _read_temperature()
    return {"cpu": round(cpu, 1), "ram": round(ram, 1), "temp": round(temp, 1)}


def _read_temperature() -> float:
    """Read CPU temperature. Returns 0.0 if unavailable."""
    # RPi method 1: vcgencmd
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if result.returncode == 0:
            raw = result.stdout.strip()
            temp = float(raw.split("=")[1].replace("'C", "").strip())
            logger.debug(f"Temperature via vcgencmd: {temp}°C")
            return temp
    except FileNotFoundError:
        logger.debug("vcgencmd not found (not RPi)")
    except Exception as e:
        logger.debug(f"vcgencmd failed: {e}")

    # RPi / Linux method 2: thermal_zone
    for zone in range(4):
        path = f"/sys/class/thermal/thermal_zone{zone}/temp"
        try:
            with open(path) as f:
                temp = int(f.read().strip()) / 1000.0
                logger.debug(f"Temperature via {path}: {temp}°C")
                return temp
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.debug(f"Failed reading {path}: {e}")
            continue

    logger.debug("No temperature sensor found, returning 0")
    return 0.0


# ─── MJPEG frame generators ───────────────────────────────────────────────────


def generate_live_frames(cam: "CVCamera"):
    """MJPEG generator for /cv/stream/live — bare camera, no recognition."""
    while True:
        frame = cam.read_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        # Minimal FPS overlay
        _draw_fps_overlay(frame, cam.fps, cam.current_res)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


def generate_recognition_frames(cam: "CVCamera"):
    """MJPEG generator for /cv/stream/recognition — with face overlay."""
    while True:
        frame = cam.read_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        if cam.reference_encoding is not None:
            frame, _, _ = cam.process_recognition_frame(frame)

        _draw_fps_overlay(frame, cam.fps, cam.current_res)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


def _draw_fps_overlay(frame, fps: float, res_label: str):
    h, w = frame.shape[:2]
    text = f"{fps:.1f} FPS  {res_label}"
    # Dark background pill
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    x, y = w - tw - 16, 28
    cv2.rectangle(
        frame, (x - 6, y - th - 6), (x + tw + 6, y + 6), (0, 0, 0), cv2.FILLED
    )
    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 120),
        1,
        cv2.LINE_AA,
    )


# Module-level singleton
camera = CVCamera()

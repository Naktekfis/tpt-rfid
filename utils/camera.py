"""
Camera behind a factory, like the RFID reader: OpenCVCamera for a real USB
camera, MockCamera for tests and machines without one. cv2 is imported lazily
so the app runs without OpenCV.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RECONNECT_INTERVAL = 3.0  # s between attempts to reopen a failed camera
MAX_FRAME_AGE = 3.0  # never serve a frozen frame as current evidence


class MockCamera:
    """Cycles through frames given to set_frames(); no thread, no device."""

    def __init__(self):
        self._frames: List[Any] = []
        self._i = 0
        self._lock = threading.Lock()

    def set_frames(self, frames: List[Any]) -> None:
        with self._lock:
            self._frames = list(frames)
            self._i = 0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def read(self):
        with self._lock:
            if not self._frames:
                return None
            frame = self._frames[self._i % len(self._frames)]
            self._i += 1
            return frame.copy()

    def jpeg(self) -> Optional[bytes]:
        frame = self.read()
        if frame is None:
            return None
        import cv2

        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None

    def status(self) -> Dict[str, Any]:
        return {"enabled": False, "mock": True, "running": False, "has_frame": bool(self._frames)}


class OpenCVCamera:
    """Reads cv2.VideoCapture in a daemon thread and keeps the latest frame."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.index = index
        self.width = width
        self.height = height
        self._lock = threading.Lock()
        self._frame = None
        self._frame_time = 0.0
        self._opened = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="camera", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def read(self):
        """Latest frame (a copy, BGR) or None."""
        with self._lock:
            if self._frame is None or time.monotonic() - self._frame_time > MAX_FRAME_AGE:
                return None
            return self._frame.copy()

    def jpeg(self) -> Optional[bytes]:
        frame = self.read()
        if frame is None:
            return None
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            age = time.monotonic() - self._frame_time if self._frame is not None else None
        return {
            "enabled": True,
            "mock": False,
            "running": bool(self._thread and self._thread.is_alive()),
            "opened": self._opened,
            "index": self.index,
            "frame_age": age,
        }

    def _open(self):
        import cv2

        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap

    def _run(self) -> None:
        cap = None
        while not self._stop.is_set():
            if cap is None:
                try:
                    cap = self._open()
                except Exception:  # thread boundary: OpenCV can raise anything
                    logger.exception("Camera open failed")
                    cap = None
                self._opened = cap is not None
                if cap is None:
                    self._stop.wait(RECONNECT_INTERVAL)
                    continue
                logger.info("Camera %s opened", self.index)
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Camera %s read failed, reconnecting", self.index)
                cap.release()
                cap = None
                self._opened = False
                with self._lock:
                    self._frame = None
                self._stop.wait(RECONNECT_INTERVAL)
                continue
            with self._lock:
                self._frame = frame
                self._frame_time = time.monotonic()
        if cap is not None:
            cap.release()
        self._opened = False


def create_camera(enabled: bool, index: int = 0, width: int = 640, height: int = 480):
    if not enabled:
        return MockCamera()
    try:
        import cv2  # noqa: F401
    except ImportError:
        logger.warning("CAMERA_ENABLED but OpenCV is not installed; using mock camera")
        return MockCamera()
    return OpenCVCamera(index, width, height)

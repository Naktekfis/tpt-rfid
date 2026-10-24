"""Private alarm evidence and conservative camera-health monitoring.

No face analysis. A uniformly dark/flat image is only suspected obstruction or
poor lighting. Evidence is append-only; the image budget stops new captures
rather than deleting existing files.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
EVENT_ID = re.compile(r"^[a-f0-9]{32}$")


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def frame_condition(frame):
    """Small grayscale sample; numpy comes with optional OpenCV, loaded lazily."""
    if frame is None:
        return "unavailable"
    import numpy as np

    sample = np.asarray(frame)[::8, ::8]
    if sample.size == 0:
        return "unavailable"
    if sample.ndim == 3:
        sample = sample.mean(axis=2)
    # Bright flat surfaces can also be a cover. Never claim verified tampering.
    if float(sample.mean()) < 18 or float(sample.std()) < 3:
        return "suspected_obstruction"
    return "healthy"


class ObstructionDetector:
    """Camera cover check that learns what the healthy scene looks like.

    Brightness alone misses a cover that lets light through and flags a dim
    room (Bosch VCA tamper note; LeDat98/CameraTamperingDetection compares
    edge histograms to a baseline for the same reason). So, on a 160x120
    grayscale copy: dark or flat is a cover as before; otherwise the frame is
    split into 12x16 blocks and a block counts as "textured" when Canny finds
    edges in it. While healthy, the textured blocks are averaged into a slow
    reference. A frame that keeps under `lost_fraction` of the reference's
    textured blocks has lost the scene: a hand, paper or sticker over the lens
    rather than a person walking by, who adds edges of their own. The
    SecurityService debounce then requires that for several seconds.
    """

    GRID = (12, 16)  # blocks of 10x10 px on the 160x120 copy

    def __init__(self, lost_fraction: float = 0.2, learn_rate: float = 0.05,
                 min_reference_blocks: int = 20):
        self.lost_fraction = lost_fraction
        self.learn_rate = learn_rate
        self.min_reference_blocks = min_reference_blocks
        self.reference = None  # per-block edge density, healthy frames only

    def condition(self, frame):
        base = frame_condition(frame)
        if base != "healthy":
            return base
        try:
            import cv2
        except ImportError:
            return base
        import numpy as np

        small = cv2.resize(np.asarray(frame), (160, 120), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
        edges = cv2.Canny(gray, 50, 150) > 0
        rows, cols = self.GRID
        density = edges.reshape(rows, 120 // rows, cols, 160 // cols).mean(axis=(1, 3))
        textured = density > 0.02
        if self.reference is not None:
            ref_textured = self.reference > 0.02
            known = int(ref_textured.sum())
            if known >= self.min_reference_blocks:
                kept = int((ref_textured & textured).sum()) / known
                if kept < self.lost_fraction:
                    return "suspected_obstruction"
        if self.reference is None:
            self.reference = density
        else:
            self.reference = (1 - self.learn_rate) * self.reference + self.learn_rate * density
        return "healthy"


class EvidenceStore:
    def __init__(self, directory, max_storage_bytes=200 * 1024 * 1024):
        self.directory = Path(directory)
        self.max_storage_bytes = max_storage_bytes
        self._lock = threading.RLock()

    def _prepare(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(str(self.directory), 0o700)

    def _atomic(self, path, data):
        temporary = self.directory / ("." + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as handle:
                os.chmod(str(temporary), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(path))
        finally:
            if temporary.exists():
                temporary.unlink()

    def save(self, event):
        with self._lock:
            self._prepare()
            previous = self.get(event["event_id"])
            if previous and previous.get("acknowledged_at"):
                event["acknowledged_at"] = previous["acknowledged_at"]
            self._atomic(self.directory / (event["event_id"] + ".json"),
                         json.dumps(event, ensure_ascii=False).encode("utf-8"))

    def get(self, event_id):
        if not EVENT_ID.fullmatch(event_id):
            return None
        try:
            with (self.directory / (event_id + ".json")).open() as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None

    def events(self, limit=100):
        if not self.directory.exists():
            return []
        paths = sorted(self.directory.glob("*.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        result = []
        for path in paths:
            try:
                event = self.get(path.stem)
            except (OSError, ValueError):
                logger.warning("Invalid security event %s", path.name)
                continue
            if event:
                result.append(event)
        # Use occurrence time, since acknowledgement changes the file mtime.
        return sorted(result, key=lambda event: event["started_at"], reverse=True)[:limit]

    def add_photo(self, event, jpeg):
        with self._lock:
            used = sum(path.stat().st_size for path in self.directory.glob("*.jpg"))
            if used + len(jpeg) > self.max_storage_bytes:
                event["photo_status"] = "storage_full"
            else:
                self._atomic(self.directory / (event["event_id"] + ".jpg"), jpeg)
                event["photo_status"] = "captured"
                event["captured_at"] = utc_now()
            self.save(event)

    def acknowledge(self, event_id):
        with self._lock:
            event = self.get(event_id)
            if event is None:
                return False
            if not event.get("acknowledged_at"):
                event["acknowledged_at"] = utc_now()
                self.save(event)
            return True

    def photo_path(self, event_id):
        event = self.get(event_id)
        if not event or event.get("photo_status") != "captured":
            return None
        path = self.directory / (event_id + ".jpg")
        return path if path.is_file() else None


class SecurityService:
    def __init__(self, camera, reader, storage_dir, enabled=False,
                 alarm_enabled=True, debounce_seconds=5, recovery_seconds=3,
                 max_storage_bytes=200 * 1024 * 1024, clock=time.monotonic):
        self.camera = camera
        self.reader = reader
        self.enabled = enabled
        self.alarm_enabled = alarm_enabled
        self.store = EvidenceStore(storage_dir, max_storage_bytes)
        self.debounce_seconds = debounce_seconds
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._queue = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._thread = None
        self._candidate = None
        self._candidate_since = 0
        self._active = None
        self._pending_recoveries = []
        self._storage_retry = False
        self.storage_error = None
        self.condition = "disabled" if not enabled else "warming_up"
        self.detector = ObstructionDetector()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="security", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _event(self, kind, **fields):
        event = {"event_id": uuid.uuid4().hex, "kind": kind,
                 "started_at": utc_now(), "recovered_at": None,
                 "acknowledged_at": None, "photo_status": "pending"}
        event.update(fields)
        return event

    def record_tool_alarm(self, alarm):
        # Copy the latest frame at the event time; encode and disk I/O happen
        # off the reader thread. Never reopen the camera here.
        event = self._event("tool_alarm", alarm_id=str(alarm["alarm_id"]),
                            tool_id=alarm.get("tool_id"),
                            tool_name=alarm.get("tool_name"))
        try:
            frame = self.camera.read()
        except Exception:  # callback boundary: evidence must not suppress the alarm
            logger.exception("Alarm camera snapshot failed")
            frame = None
        try:
            self._queue.put_nowait((event, frame))
        except queue.Full:
            # Preserve a failure record even if camera work is saturated.
            event["photo_status"] = "queue_full"
            self.store.save(event)
            logger.warning("Security evidence queue full")

    def _capture(self, event, frame):
        self.store.save(event)
        if frame is None:
            event["photo_status"] = "camera_unavailable"
            self.store.save(event)
            return
        try:
            import cv2

            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise ValueError("JPEG encoding failed")
            self.store.add_photo(event, encoded.tobytes())
        except Exception:  # worker boundary: an image failure must not stop monitoring
            logger.exception("Security image capture failed")
            event["photo_status"] = "capture_failed"
            self.store.save(event)

    def sample(self, now=None):
        if not self.enabled:
            return
        now = self._clock() if now is None else now
        status = self.camera.status()
        age = status.get("frame_age")
        if status.get("mock") or not status.get("running") or age is None or age > 3:
            frame, condition = None, "unavailable"
        else:
            frame = self.camera.read()
            condition = self.detector.condition(frame)
        if condition != self._candidate:
            self._candidate, self._candidate_since = condition, now
        threshold = self.recovery_seconds if condition == "healthy" else self.debounce_seconds
        if now - self._candidate_since < threshold:
            return
        if self.condition == condition and not self._storage_retry:
            return
        if self._active and self._active["kind"] != "camera_" + condition:
            self._active["recovered_at"] = utc_now()
            self._active["recovery_reason"] = condition
            self._pending_recoveries.append(self._active)
            self._active = None
        self.condition = condition

        # Establish the live incident and sound its alarm independently of disk
        # writes. Keep failed persistence work in memory and retry next sample.
        history_failed = False
        try:
            history = self.store.events(limit=None)
        except OSError:
            logger.exception("Cannot read camera incident history")
            history = []
            history_failed = True
            self._storage_retry = True
        new_incident = False
        if condition != "healthy" and self._active is None:
            self._active = next((event for event in history
                                 if event["kind"] == "camera_" + condition
                                 and not event.get("recovered_at")), None)
            if self._active is None:
                self._active = self._event("camera_" + condition)
                new_incident = True
                if self.alarm_enabled:
                    if condition == "suspected_obstruction":
                        # Covered lens: a long run of beeps, unlike a tool alarm.
                        self.reader.beep(active=2, silent=2, times=7)
                    else:
                        self.reader.beep()
        try:
            for previous in self._pending_recoveries:
                self.store.save(previous)
            self._pending_recoveries.clear()
            # Resolve persisted incidents after restart, once a stable sample
            # confirms recovery or a different camera fault.
            for previous in history:
                if (previous["kind"].startswith("camera_")
                        and not previous.get("recovered_at")
                        and previous["kind"] != "camera_" + condition):
                    previous["recovered_at"] = utc_now()
                    previous["recovery_reason"] = condition
                    self.store.save(previous)
            if self._active and (new_incident or self._storage_retry):
                self._capture(self._active, frame)
        except OSError as error:
            logger.exception("Cannot persist camera incident; alarm remains active")
            self.storage_error = str(error)
            self._storage_retry = True
        else:
            self.storage_error = "Incident history unavailable" if history_failed else None
            self._storage_retry = history_failed

    def _run(self):
        while not self._stop.is_set() or not self._queue.empty():
            try:
                try:
                    event, frame = self._queue.get(timeout=0.5)
                except queue.Empty:
                    pass
                else:
                    self._capture(event, frame)
                if not self._stop.is_set():
                    self.sample()
            except Exception:  # background boundary: retain reconnect/monitor loop
                logger.exception("Security monitor failed")
                self._stop.wait(1)

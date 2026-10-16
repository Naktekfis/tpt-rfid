"""
Kiosk session state machine.

Ties face identification and the two-way head-turn challenge to tool presence
events. States:

  idle          nobody identified; frames are scanned for a known face
  identifying   a known face was seen; running the head-turn challenges
  unknown_face  a face that matches nobody (5 s, then idle)
  session       a student is identified: tools leaving are borrowed by them,
                tools coming back are returned by them
  summary       the session ended; borrowed/returned lists for a few seconds

Open alarms are not a state; the state API reports them next to any state.
Timeouts are evaluated lazily (tick() is also called by every public method),
so the state is right even when no camera loop runs.

Everything runs under one lock: the reader thread (tool events), the camera
loop (frames) and request threads share it. Face work happens outside the
lock; its result is applied only if the state did not change meanwhile.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .liveness import HeadTurnChallenge

logger = logging.getLogger(__name__)

IDENTIFY_INTERVAL = 1.0 / 3  # s between identify attempts while idle
REIDENTIFY_INTERVAL = 1.0  # s between identity re-checks while identifying
MISMATCHES_TO_ABORT = 2
NO_FACE_ABORT = 3.0  # s without a single clear face aborts identifying
RETRY_PAUSE = 2.0  # s of no identifying after an aborted challenge
UNKNOWN_FACE_SECONDS = 5.0
SUMMARY_SECONDS = 8.0
CHALLENGE_TIMEOUT = 8.0
YAW_THRESHOLD = 0.25
DIRECTIONS = ("left", "right")


class Kiosk:
    def __init__(
        self,
        app,
        database,
        face_service,
        clock: Callable[[], float] = time.monotonic,
        rng: Optional[random.Random] = None,
        session_seconds: float = 60.0,
        extend_seconds: float = 30.0,
        max_seconds: float = 120.0,
        alarm_grace_seconds: float = 30.0,
    ):
        self.app = app
        self.database = database
        self.face_service = face_service
        self._clock = clock
        self._rng = rng or random.Random()
        self.session_seconds = session_seconds
        self.extend_seconds = extend_seconds
        self.max_seconds = max_seconds
        self.alarm_grace_seconds = alarm_grace_seconds
        self._lock = threading.RLock()
        self._reset_all()

    # ---- state helpers (call with the lock held) ----

    def _reset_all(self) -> None:
        self._state = "idle"
        self._retry_at = float("-inf")
        self._reason: Optional[str] = None  # why we fell back to idle
        self._student: Optional[Dict[str, Any]] = None
        self._order: List[str] = []
        self._step = 0
        self._challenge: Optional[HeadTurnChallenge] = None
        self._last_identify = float("-inf")
        self._last_face = 0.0
        self._mismatches = 0
        self._until = 0.0  # unknown_face / summary end
        self._expires = 0.0  # session end
        self._tool_events = 0
        self._borrowed: List[Dict[str, Any]] = []
        self._returned: List[Dict[str, Any]] = []

    def _to_idle(self, reason: Optional[str] = None) -> None:
        self._reset_all()
        self._reason = reason
        if reason in ("challenge_timeout", "different_face", "face_lost"):
            self._retry_at = self._clock() + RETRY_PAUSE

    def _new_challenge(self) -> HeadTurnChallenge:
        return HeadTurnChallenge(
            self._order[self._step],
            clock=self._clock,
            timeout=CHALLENGE_TIMEOUT,
            yaw_threshold=YAW_THRESHOLD,
        )

    # ---- timeouts ----

    def tick(self) -> None:
        with self._lock:
            self._tick_locked()

    def _tick_locked(self) -> None:
        now = self._clock()
        if self._state == "session" and now >= self._expires:
            self._end_locked()
        if self._state == "summary" and now >= self._until:
            self._to_idle()
        elif self._state == "unknown_face" and now >= self._until:
            self._to_idle()
        elif self._state == "identifying" and self._challenge is not None:
            if self._challenge.update(None) == "timeout":
                logger.info("Kiosk: head-turn challenge timed out")
                self._to_idle("challenge_timeout")
            elif now - self._last_face > NO_FACE_ABORT:
                self._to_idle("face_lost")

    # ---- camera frames ----

    def on_frame(self, frame) -> None:
        if frame is None:
            self.tick()
            return
        now = self._clock()
        with self._lock:
            self._tick_locked()
            mode = self._state
            if mode == "idle":
                if now < self._retry_at or now - self._last_identify < IDENTIFY_INTERVAL:
                    return
                self._last_identify = now
            elif mode == "identifying":
                token = self._challenge
                reidentify = now - self._last_identify >= REIDENTIFY_INTERVAL
                if reidentify:
                    self._last_identify = now
            else:
                return

        # Face work outside the lock.
        if mode == "idle":
            result = self._identify(frame)
            with self._lock:
                if self._state == "idle":
                    self._apply_idle_result(result, now)
            return

        landmarks = self.face_service.landmarks(frame)
        result = self._identify(frame) if reidentify else None
        with self._lock:
            if self._state == "identifying" and self._challenge is token:
                self._apply_identifying(landmarks, result, now)

    def _identify(self, frame) -> Optional[Dict[str, Any]]:
        try:
            with self.app.app_context():
                return self.face_service.identify_frame(frame)
        except Exception:  # camera-thread boundary
            logger.exception("Kiosk: identify failed")
            return None

    def _apply_idle_result(self, result, now: float) -> None:
        if not result:
            return
        status = result.get("status")
        if status == "ok":
            self._reset_all()
            self._last_identify = now
            self._last_face = now
            self._state = "identifying"
            self._student = result["student"]
            self._order = self._rng.sample(DIRECTIONS, 2)
            self._challenge = self._new_challenge()
            logger.info("Kiosk: identifying student %s", self._student["student_id"])
        elif status in ("unknown", "ambiguous"):
            self._reset_all()
            self._state = "unknown_face"
            self._until = now + UNKNOWN_FACE_SECONDS

    def _apply_identifying(self, landmarks, result, now: float) -> None:
        if landmarks is not None:
            self._last_face = now
        elif now - self._last_face > NO_FACE_ABORT:
            self._to_idle("face_lost")
            return

        if result is not None:
            status = result.get("status")
            if (
                status == "ok"
                and result["student"]["student_id"] == self._student["student_id"]
            ):
                self._mismatches = 0
                self._last_face = now
            elif status in ("ok", "unknown", "ambiguous"):
                self._mismatches += 1
                if self._mismatches >= MISMATCHES_TO_ABORT:
                    logger.info("Kiosk: different face during challenge, abort")
                    self._to_idle("different_face")
                    return

        outcome = self._challenge.update(landmarks)
        if outcome == "timeout":
            self._to_idle("challenge_timeout")
        elif outcome == "passed":
            self._step += 1
            if self._step >= len(self._order):
                student = self._student
                self._start_session_locked(student)
            else:
                self._challenge = self._new_challenge()

    # ---- session ----

    def start_session(self, student: Dict[str, Any]) -> bool:
        """Start a session as if identification and both turns passed (debug
        route and tests). False if a session is already running."""
        with self._lock:
            self._tick_locked()
            if self._state == "session":
                return False
            self._start_session_locked(student)
            return True

    def _start_session_locked(self, student: Dict[str, Any]) -> None:
        now = self._clock()
        self._reset_all()
        self._state = "session"
        self._student = student
        self._expires = now + self.session_seconds
        sid = int(student["student_id"])
        try:
            with self.app.app_context():
                for txn in self.database.convert_recent_alarms_to_borrows(
                    sid, self.alarm_grace_seconds
                ):
                    self._borrowed.append(_entry(txn, late=True))
                    self._tool_events += 1  # attributed: "Bukan saya" no longer allowed
                self.database.verify_returns_by_borrower(sid)
        except Exception:  # keep the session usable
            logger.exception("Kiosk: session start bookkeeping failed")
        logger.info("Kiosk: session started for student %s", sid)

    def _extend_locked(self, now: float) -> None:
        self._expires = min(self._expires + self.extend_seconds, now + self.max_seconds)

    def _end_locked(self) -> None:
        if self._state != "session":
            return
        self._state = "summary"
        self._until = self._clock() + SUMMARY_SECONDS
        logger.info("Kiosk: session ended")

    def end(self) -> bool:
        with self._lock:
            self._tick_locked()
            if self._state != "session":
                return False
            self._end_locked()
            return True

    def cancel(self) -> str:
        """ "Bukan saya": 'ok' | 'no_session' | 'conflict' (tool events happened)."""
        with self._lock:
            self._tick_locked()
            if self._state != "session":
                return "no_session"
            if self._tool_events:
                return "conflict"
            self._to_idle("cancelled")
            return "ok"

    # ---- tool events (reader thread) ----

    def on_tool_left(self, info: Dict[str, Any]) -> bool:
        with self._lock:
            self._tick_locked()
            if self._state != "session" or info.get("status") != "available":
                return False
            try:
                with self.app.app_context():
                    txn = self.database.borrow_tool_atomic(
                        self._student["student_id"], str(info["id"])
                    )
            except ValueError as exc:
                logger.warning("Kiosk: borrow refused: %s", exc)
                return False
            self._borrowed.append(_entry(txn))
            self._tool_events += 1
            self._extend_locked(self._clock())
            return True

    def on_tool_back(self, info: Dict[str, Any]) -> bool:
        with self._lock:
            self._tick_locked()
            if self._state != "session" or info.get("status") != "borrowed":
                return False
            student_id = int(self._student["student_id"])
            with self.app.app_context():
                txn = self.database.close_borrow(info["id"], student_id, True)
            if txn is None:
                return False
            entry = _entry(txn)
            entry["own"] = txn["student_id"] == str(student_id)
            self._returned.append(entry)
            self._tool_events += 1
            self._extend_locked(self._clock())
            return True

    # ---- state for the API ----

    def state_dict(self) -> Dict[str, Any]:
        with self._lock:
            self._tick_locked()
            now = self._clock()
            out: Dict[str, Any] = {
                "state": self._state,
                "reason": self._reason,
                "student": self._student if self._state != "idle" else None,
            }
            if self._state == "identifying":
                out["direction"] = self._challenge.direction
                out["step"] = self._step + 1
                out["steps"] = len(self._order)
            elif self._state == "session":
                out["expires_in"] = round(max(0.0, self._expires - now), 1)
                out["can_cancel"] = self._tool_events == 0
            if self._state in ("session", "summary"):
                out["borrowed"] = list(self._borrowed)
                out["returned"] = list(self._returned)
            if self._state == "summary":
                out["summary_ends_in"] = round(max(0.0, self._until - now), 1)
            elif self._state == "unknown_face":
                out["unknown_ends_in"] = round(max(0.0, self._until - now), 1)
            return out


def _entry(txn: Dict[str, Any], late: bool = False) -> Dict[str, Any]:
    due = txn.get("due_at")
    entry = {
        "transaction_id": txn["transaction_id"],
        "tool_id": txn["tool_id"],
        "tool_name": txn["tool_name"],
        "due_at": due.isoformat() if due is not None else None,
    }
    if late:
        entry["late_identify"] = True
    return entry


class KioskLoop(threading.Thread):
    """Feeds camera frames to the kiosk at ~10 fps."""

    def __init__(self, camera, kiosk: Kiosk, fps: float = 10.0):
        super().__init__(name="KioskLoop", daemon=True)
        self.camera = camera
        self.kiosk = kiosk
        self.interval = 1.0 / fps
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                self.kiosk.on_frame(self.camera.read())
            except Exception:  # thread boundary: never die
                logger.exception("Kiosk loop error")
            self._stop_event.wait(
                max(0.01, self.interval - (time.monotonic() - started))
            )

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout)

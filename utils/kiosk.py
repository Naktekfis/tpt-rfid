"""NFC kiosk sessions tied to UHF tool-presence events.

Card identity opens borrowing and return sessions. Timeouts are evaluated
lazily by every public method, including the state API's regular polling.
A lock serializes NFC callbacks, UHF events, and request threads.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

UNKNOWN_CARD_SECONDS = 5.0
SUMMARY_SECONDS = 5.0


class Kiosk:
    def __init__(
        self,
        app,
        database,
        clock: Callable[[], float] = time.monotonic,
        session_seconds: float = 60.0,
        extend_seconds: float = 30.0,
        max_seconds: float = 120.0,
        alarm_grace_seconds: float = 30.0,
    ):
        self.app = app
        self.database = database
        self._clock = clock
        self.session_seconds = session_seconds
        self.extend_seconds = extend_seconds
        self.max_seconds = max_seconds
        self.alarm_grace_seconds = alarm_grace_seconds
        self._lock = threading.RLock()
        self._reset_all()

    # ---- state helpers (call with the lock held) ----

    def _reset_all(self) -> None:
        self._state = "idle"
        self._reason: Optional[str] = None
        self._student: Optional[Dict[str, Any]] = None
        self._until = 0.0  # unknown_card / summary end
        self._expires = 0.0  # session end
        self._tool_events = 0
        self._borrowed: List[Dict[str, Any]] = []
        self._returned: List[Dict[str, Any]] = []

    def _to_idle(self, reason: Optional[str] = None) -> None:
        self._reset_all()
        self._reason = reason

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
        elif self._state == "unknown_card" and now >= self._until:
            self._to_idle()

    # ---- NFC identity ----

    def on_card(self, uid: str) -> str:
        """Open a session for a registered card; never replace an active user.

        The reader supplies a normalized UID and suppresses held-card repeats.
        Return 'session', 'unknown_card', or 'busy' for an existing session.
        """
        with self._lock:
            self._tick_locked()
            if self._state == "session":
                return "busy"
            with self.app.app_context():
                student = self.database.get_student_by_nfc(uid)
            if student is None:
                self._reset_all()
                self._state = "unknown_card"
                self._until = self._clock() + UNKNOWN_CARD_SECONDS
                return "unknown_card"
            self._start_session_locked(student)
            return "session"

    # ---- session ----

    def start_session(self, student: Dict[str, Any]) -> bool:
        """Start a session for a known student; False if one is already running."""
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
            if self._state == "session":
                out["expires_in"] = round(max(0.0, self._expires - now), 1)
                out["can_cancel"] = self._tool_events == 0
            if self._state in ("session", "summary"):
                out["borrowed"] = list(self._borrowed)
                out["returned"] = list(self._returned)
            if self._state == "summary":
                out["summary_ends_in"] = round(max(0.0, self._until - now), 1)
            elif self._state == "unknown_card":
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

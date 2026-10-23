"""
Glue between the reader's inventory rounds, the presence monitor and the DB.

Known tags (Tool.rfid_uid) get their presence stored; an unborrowed tool that
stays out of the reader field for `alarm_confirm_seconds` raises an AlarmEvent
and a reader beep. Unknown tags in the field are kept in memory for tool
registration.

With `background=True` the reader thread only updates the monitor; DB, kiosk
and alarm work runs on one worker thread so slow handling never delays the next
inventory round.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Set

from .presence import PresenceEvent, PresenceMonitor
from .rfid_diagnostics import LossDiagnostics

logger = logging.getLogger(__name__)

LAST_SEEN_WRITE_INTERVAL = 10.0  # s between last_seen_at writes per tool
WORKER_IDLE_CHECK = 0.5  # s; pending alarms still fire if rounds stop


class ToolPresenceService:
    def __init__(
        self,
        app,
        database,
        reader,
        monitor: PresenceMonitor,
        alarm_enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
        kiosk=None,
        alarm_observer=None,
        alarm_confirm_seconds: float = 0.0,
        background: bool = False,
    ):
        self.app = app
        self.database = database
        self.reader = reader
        self.monitor = monitor
        self.alarm_enabled = alarm_enabled
        self._clock = clock
        self.kiosk = kiosk  # optional Kiosk: gets first look at tool events
        self.alarm_observer = alarm_observer
        self._lock = threading.Lock()
        self._unknown: Set[str] = set()
        self._known: Dict[str, int] = {}  # epc -> tool id
        self._last_write: Dict[str, float] = {}
        self._diagnostics = LossDiagnostics()
        # A missing unborrowed tool waits here (epc -> (due, event)) so a short
        # read gap at the edge of the field does not become a false alarm.
        self.alarm_confirm_seconds = alarm_confirm_seconds
        self._pending: Dict[str, tuple] = {}
        self._queue: Optional[queue.Queue] = None
        if background:
            self._queue = queue.Queue()
            threading.Thread(
                target=self._work,
                args=(self._queue,),
                name="tool-presence",
                daemon=True,
            ).start()
        reader.add_round_listener(self.on_round)

    def on_round(self, epcs: Iterable[str]) -> None:
        epcs = list(epcs)
        events = self.monitor.update(epcs)
        now = self._clock()
        if self._queue is not None:
            self._queue.put((events, epcs, now))
        else:
            self._process(events, epcs, now)

    def stop(self) -> None:
        """End the worker; later rounds are handled inline on the caller."""
        work, self._queue = self._queue, None
        if work is not None:
            work.put(None)

    def _work(self, work: queue.Queue) -> None:
        while True:
            try:
                item = work.get(timeout=WORKER_IDLE_CHECK)
            except queue.Empty:
                item = ([], None, self._clock())
            if item is None:
                return
            try:
                self._process(*item)
            except Exception:  # worker boundary: keep monitoring after a bad round
                logger.exception("Tool presence handling failed")

    def _process(self, events: List[PresenceEvent], epcs, now: float) -> None:
        with self.app.app_context():
            for event in events:
                self._diagnostics.increment("presence_events_total")
                self._diagnostics.record(
                    "event_to_handler", max(0.0, self._clock() - event.at)
                )
                if event.kind == "left":
                    self._diagnostics.increment("missing_events_total")
                started = self._clock()
                try:
                    self._handle(event, now)
                finally:
                    self._diagnostics.record("event_handler", self._clock() - started)
            self._fire_due_alarms(self._clock())
            if epcs is not None:
                self._touch_last_seen(epcs, now)

    def _handle(self, event: PresenceEvent, now: float) -> None:
        epc = event.epc
        if event.kind in ("new", "back"):
            if self._pending.pop(epc, None) is not None:
                self._diagnostics.increment("alarms_cancelled_total")
            info = self.database.get_tool_presence_info(epc)
            if info is None:
                with self._lock:
                    self._unknown.add(epc)
                return
            with self._lock:
                self._unknown.discard(epc)
                self._known[epc] = info["id"]
                self._last_write[epc] = now
            self.database.set_tool_presence(info["id"], "present", datetime.utcnow())
            # "new" counts too: a borrowed tool already in the field at boot
            # came back while the app was down.
            if not self._kiosk_handled("on_tool_back", info):
                if info["status"] == "borrowed":
                    # Nobody identified: record the return, flag it unverified.
                    self.database.close_borrow(info["id"], None, False)
                self.database.close_alarms_for_tool(info["id"], "returned")
            return

        # "left"
        with self._lock:
            self._unknown.discard(epc)
            self._last_write.pop(epc, None)
            tool_id = self._known.get(epc)
        if tool_id is None:
            return
        info = self.database.get_tool_presence_info(epc)
        if info is None:
            return
        # Borrowed tools are meant to leave; in a session the kiosk borrows it.
        alarm = info["status"] == "available" and not self._kiosk_handled(
            "on_tool_left", info
        )
        if alarm and self.alarm_confirm_seconds > 0:
            # Stay "present" on the board until the alarm is confirmed, so the
            # tile turns red together with the alarm, not before it.
            self._pending[epc] = (event.at + self.alarm_confirm_seconds, event)
            return
        self.database.set_tool_presence(info["id"], "missing")
        if alarm:
            self._raise_alarm(info, event)

    def _fire_due_alarms(self, now: float) -> None:
        due = [epc for epc, (at, _) in self._pending.items() if now >= at]
        for epc in due:
            _, event = self._pending.pop(epc)
            info = self.database.get_tool_presence_info(epc)
            if info is None:
                continue
            self.database.set_tool_presence(info["id"], "missing")
            if info["status"] != "available":
                continue
            # A session may have started while we waited: it borrows the tool.
            if self._kiosk_handled("on_tool_left", info):
                continue
            self._raise_alarm(info, event)

    def _raise_alarm(self, info: Dict, event: PresenceEvent) -> None:
        if self.database.open_alarm_for_tool(info["id"]) is not None:
            return
        alarm = self.database.create_alarm(info["id"])
        alarm_committed_at = self._clock()
        self._diagnostics.record(
            "missing_to_alarm_commit", max(0.0, alarm_committed_at - event.at)
        )
        if self.alarm_observer is not None:
            try:
                self.alarm_observer(alarm)
            except Exception:  # background callback boundary: preserve alarm/beep
                logger.exception("Alarm evidence capture failed")
        logger.warning(f"ALARM: tool {info['id']} left the reader field")
        if self.alarm_enabled:
            self.reader.beep()
            enqueued_at = self._clock()
            self._diagnostics.record(
                "alarm_commit_to_beep_enqueue",
                max(0.0, enqueued_at - alarm_committed_at),
            )
            self._diagnostics.record(
                "missing_to_beep_enqueue", max(0.0, enqueued_at - event.at)
            )
            self._diagnostics.increment("alarm_beeps_enqueued_total")

    def _kiosk_handled(self, method: str, info: Dict) -> bool:
        if self.kiosk is None:
            return False
        try:
            return bool(getattr(self.kiosk, method)(info))
        except Exception:  # reader-thread boundary: fall back to the no-session path
            logger.exception("Kiosk %s failed", method)
            return False

    def _touch_last_seen(self, epcs: List[str], now: float) -> None:
        with self._lock:
            due = [
                (epc, tool_id)
                for epc, tool_id in self._known.items()
                if epc in epcs
                and now - self._last_write.get(epc, float("-inf"))
                >= LAST_SEEN_WRITE_INTERVAL
            ]
            for epc, _ in due:
                self._last_write[epc] = now
        for _, tool_id in due:
            self.database.set_tool_presence(tool_id, "present", datetime.utcnow())

    def tool_registered(self, epc: str, tool_id: int) -> None:
        """A unit was just created for this EPC (admin, in a request). If the
        tag is in the field as "unknown", the monitor will not report it again,
        so take it over here: known, present now, not listed as unknown."""
        with self._lock:
            if epc not in self._unknown:
                return
            self._unknown.discard(epc)
            self._known[epc] = tool_id
            self._last_write[epc] = self._clock()
        self.database.set_tool_presence(tool_id, "present", datetime.utcnow())

    def unknown_epcs(self) -> List[str]:
        with self._lock:
            return sorted(self._unknown)

    def open_alarms(self) -> List[Dict]:
        with self.app.app_context():
            return self.database.get_open_alarms()

    def diagnostics(self) -> dict:
        return self._diagnostics.snapshot()

    def acknowledge(self, alarm_id: int) -> bool:
        with self.app.app_context():
            return self.database.acknowledge_alarm(alarm_id, "admin")

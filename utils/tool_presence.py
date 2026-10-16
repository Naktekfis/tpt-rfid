"""
Glue between the reader's inventory rounds, the presence monitor and the DB.

Known tags (Tool.rfid_uid) get their presence stored; an unborrowed tool that
leaves the reader field raises an AlarmEvent and a reader beep. Unknown tags
in the field are kept in memory for tool registration.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Set

from .presence import PresenceEvent, PresenceMonitor

logger = logging.getLogger(__name__)

LAST_SEEN_WRITE_INTERVAL = 10.0  # s between last_seen_at writes per tool


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
    ):
        self.app = app
        self.database = database
        self.reader = reader
        self.monitor = monitor
        self.alarm_enabled = alarm_enabled
        self._clock = clock
        self.kiosk = kiosk  # optional Kiosk: gets first look at tool events
        self._lock = threading.Lock()
        self._unknown: Set[str] = set()
        self._known: Dict[str, int] = {}  # epc -> tool id
        self._last_write: Dict[str, float] = {}
        reader.add_round_listener(self.on_round)

    def on_round(self, epcs: Iterable[str]) -> None:
        epcs = list(epcs)
        events = self.monitor.update(epcs)
        now = self._clock()
        with self.app.app_context():
            for event in events:
                self._handle(event, now)
            self._touch_last_seen(epcs, now)

    def _handle(self, event: PresenceEvent, now: float) -> None:
        epc = event.epc
        if event.kind in ("new", "back"):
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
        self.database.set_tool_presence(info["id"], "missing")
        if info["status"] != "available":
            return  # borrowed tools are meant to leave
        if self._kiosk_handled("on_tool_left", info):
            return  # a kiosk session borrowed it
        if self.database.open_alarm_for_tool(info["id"]) is not None:
            return
        self.database.create_alarm(info["id"])
        logger.warning(f"ALARM: tool {info['id']} left the reader field")
        if self.alarm_enabled:
            self.reader.beep()

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

    def unknown_epcs(self) -> List[str]:
        with self._lock:
            return sorted(self._unknown)

    def open_alarms(self) -> List[Dict]:
        with self.app.app_context():
            return self.database.get_open_alarms()

    def acknowledge(self, alarm_id: int) -> bool:
        with self.app.app_context():
            return self.database.acknowledge_alarm(alarm_id, "admin")

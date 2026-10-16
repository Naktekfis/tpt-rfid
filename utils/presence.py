"""
Tool presence from repeated inventory rounds.

Pure logic, no hardware or database: feed it the EPCs seen in each round and
it reports tags that left the reader field, came back, or appeared for the
first time since start. The consumer decides what an EPC means.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List

PRESENT = "present"
MISSING = "missing"


@dataclass(frozen=True)
class PresenceEvent:
    kind: str  # "left" | "back" | "new"
    epc: str
    at: float  # monitor clock time


class PresenceMonitor:
    """
    Track per-EPC presence. An EPC is MISSING once it has not been seen for
    more than `missing_after` seconds. An EPC never seen since start has no
    state, so nothing is reported as "left" on boot.
    """

    def __init__(
        self,
        missing_after: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.missing_after = missing_after
        self._clock = clock
        self._lock = threading.Lock()
        self._last_seen: Dict[str, float] = {}
        self._state: Dict[str, str] = {}

    def update(self, epcs: Iterable[str]) -> List[PresenceEvent]:
        """Record one inventory round (may be empty); return the events."""
        now = self._clock()
        events: List[PresenceEvent] = []
        seen_now = set(epcs)
        with self._lock:
            # Departures first, judged against the time before this round.
            for epc, seen in self._last_seen.items():
                if (
                    self._state[epc] == PRESENT
                    and epc not in seen_now
                    and now - seen > self.missing_after
                ):
                    self._state[epc] = MISSING
                    events.append(PresenceEvent("left", epc, now))
            for epc in sorted(seen_now):
                previous = self._state.get(epc)
                if previous is None:
                    events.append(PresenceEvent("new", epc, now))
                elif previous == MISSING:
                    events.append(PresenceEvent("back", epc, now))
                self._state[epc] = PRESENT
                self._last_seen[epc] = now
        return events

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            return {
                epc: {"state": self._state[epc], "last_seen": seen}
                for epc, seen in self._last_seen.items()
            }

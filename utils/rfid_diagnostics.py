"""Bounded, identifier-free timing summaries for the inventory loop."""

from __future__ import annotations

import math
import json
import logging
import threading
import time
from collections import Counter, deque
from typing import Iterable

SAMPLE_LIMIT = 120
logger = logging.getLogger(__name__)


def timing_summary(values: Iterable[float]) -> dict:
    values = list(values)
    samples = sorted(values)
    if not samples:
        return {
            "samples": 0,
            "last_ms": None,
            "mean_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    return {
        "samples": len(samples),
        "last_ms": round(values[-1] * 1000, 3),
        "mean_ms": round(sum(samples) / len(samples) * 1000, 3),
        "p95_ms": round(samples[math.ceil(len(samples) * 0.95) - 1] * 1000, 3),
        "max_ms": round(samples[-1] * 1000, 3),
    }


class RoundDiagnostics:
    def __init__(self):
        self._lock = threading.Lock()
        self._samples = deque(maxlen=SAMPLE_LIMIT)
        self._rounds = 0
        self._errors = 0
        self._no_response = 0
        self._incomplete = 0
        self._listener_errors = 0
        self._skipped_presence = 0
        self._response_statuses = Counter()
        self._terminal_statuses = Counter()
        self._accepted_empty = 0
        self._rejected_with_epcs = 0
        self._next_log = time.monotonic() + 30.0

    def record(self, sample: dict) -> None:
        log_due = False
        with self._lock:
            self._samples.append(sample)
            self._rounds += 1
            self._errors += int(sample["error"])
            self._no_response += int(sample["no_response"])
            self._incomplete += int(sample["incomplete"])
            self._listener_errors += sample["listener_errors"]
            self._skipped_presence += int(sample["skipped_presence"])
            self._response_statuses.update(sample.get("response_statuses", ()))
            terminal_status = sample.get("terminal_status")
            if terminal_status is not None:
                self._terminal_statuses[terminal_status] += 1
            self._accepted_empty += int(sample.get("accepted_empty", False))
            self._rejected_with_epcs += int(sample.get("rejected_with_epcs", False))
            if time.monotonic() >= self._next_log:
                self._next_log = time.monotonic() + 30.0
                log_due = True
        if log_due:
            logger.info("UHF timing %s", json.dumps(self.snapshot(), sort_keys=True))

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            samples = list(self._samples)
            result = {
                "sample_limit": SAMPLE_LIMIT,
                "rounds_total": self._rounds,
                "round_errors_total": self._errors,
                "no_response_total": self._no_response,
                "incomplete_response_total": self._incomplete,
                "listener_errors_total": self._listener_errors,
                "skipped_presence_rounds_total": self._skipped_presence,
                "response_status_counts_total": {
                    "0x%02X" % status: count
                    for status, count in sorted(self._response_statuses.items())
                },
                "terminal_status_counts_total": {
                    "0x%02X" % status: count
                    for status, count in sorted(self._terminal_statuses.items())
                },
                "accepted_empty_rounds_total": self._accepted_empty,
                "rejected_rounds_with_epcs_total": self._rejected_with_epcs,
            }
        starts = [sample["started"] for sample in samples]
        intervals = [b - a for a, b in zip(starts, starts[1:])]
        elapsed = starts[-1] - starts[0] if len(starts) > 1 else 0
        result.update(
            {
                "round_hz": round((len(starts) - 1) / elapsed, 3)
                if elapsed > 0
                else None,
                "last_round_age_s": round(max(0, now - samples[-1]["finished"]), 3)
                if samples
                else None,
                "round_interval": timing_summary(intervals),
            }
        )
        for name in ("inventory", "listeners", "queued_commands", "total"):
            result[name] = timing_summary([sample[name] for sample in samples])
        # Missing observations are excluded, never treated as zero latency.
        # first_epc starts at command send, not physical tag placement.
        for name in ("first_frame", "first_epc", "epc_to_terminal"):
            result[name] = timing_summary(
                sample[name] for sample in samples if name in sample
            )
        return result


class LossDiagnostics:
    """Bounded, identifier-free timings for accepted presence callbacks."""

    STAGES = (
        "event_to_handler",
        "event_handler",
        "missing_to_alarm_commit",
        "alarm_commit_to_beep_enqueue",
        "missing_to_beep_enqueue",
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = {stage: deque(maxlen=SAMPLE_LIMIT) for stage in self.STAGES}
        self._counters = {
            "presence_events_total": 0,
            "missing_events_total": 0,
            "alarm_beeps_enqueued_total": 0,
            "alarms_cancelled_total": 0,
        }

    def record(self, stage: str, elapsed: float) -> None:
        if stage not in self._samples or not math.isfinite(elapsed):
            return
        with self._lock:
            self._samples[stage].append(max(0.0, elapsed))

    def increment(self, counter: str) -> None:
        with self._lock:
            if counter in self._counters:
                self._counters[counter] += 1

    def snapshot(self) -> dict:
        with self._lock:
            samples = {name: list(values) for name, values in self._samples.items()}
            counters = dict(self._counters)
        return {
            **counters,
            "sample_limit": SAMPLE_LIMIT,
            "timings": {
                name: timing_summary(values) for name, values in samples.items()
            },
        }


class BuzzerDiagnostics:
    """Bounded buzzer queue/write/response timings; never claims sound onset."""

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = {
            name: deque(maxlen=SAMPLE_LIMIT)
            for name in (
                "enqueue_to_dequeue",
                "dequeue_to_write",
                "write_to_response",
                "transaction",
            )
        }
        self._counters = {
            "enqueued_total": 0,
            "dequeued_total": 0,
            "write_calls_total": 0,
            "write_returns_total": 0,
            "responses_total": 0,
            "success_responses_total": 0,
            "error_responses_total": 0,
            "no_response_total": 0,
            "dequeued_without_write_total": 0,
            "transaction_errors_total": 0,
        }

    def increment(self, counter: str) -> None:
        with self._lock:
            if counter in self._counters:
                self._counters[counter] += 1

    def record(self, stage: str, elapsed: float) -> None:
        if stage not in self._samples or not math.isfinite(elapsed):
            return
        with self._lock:
            self._samples[stage].append(max(0.0, elapsed))

    def snapshot(self) -> dict:
        with self._lock:
            samples = {name: list(values) for name, values in self._samples.items()}
            counters = dict(self._counters)
        return {
            **counters,
            "sample_limit": SAMPLE_LIMIT,
            "timings": {
                name: timing_summary(values) for name, values in samples.items()
            },
        }

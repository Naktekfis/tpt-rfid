"""Offline VX6336 pipeline benchmark. No serial port, app.py, or config import.

Synthetic frames traverse the real splitter/driver, presence service, SQLite
in memory, and kiosk GET route. Virtual serial delays are injected scenarios,
NOT RF measurements. CPU/HTTP times use the host's real perf_counter clock.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask  # noqa: E402

from routes.kiosk_routes import create_kiosk_blueprint  # noqa: E402
from utils import DatabaseHandler, db, vx6336  # noqa: E402
from utils import rfid_reader  # noqa: E402
from utils.kiosk import Kiosk  # noqa: E402
from utils.models import Tool, ToolType  # noqa: E402
from utils.presence import PresenceMonitor  # noqa: E402
from utils.rfid_diagnostics import timing_summary  # noqa: E402
from utils.tool_presence import ToolPresenceService  # noqa: E402

SYNTHETIC_EPC = "000000000000000000000001"


class VirtualClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def frame(epc=None, status=vx6336.STATUS_INVENTORY_DONE):
    data = bytes((1, len(bytes.fromhex(epc)))) + bytes.fromhex(epc) if epc else b"\0"
    body = bytes((len(data) + 5, 0, vx6336.CMD_INVENTORY, status)) + data
    crc = vx6336.crc16(body)
    return body + bytes((crc & 255, crc >> 8))


class ScriptedSerial:
    """Synthetic 01 rounds and read-only 21 recovery; never opens serial."""

    def __init__(self, clock, replies):
        self.clock = clock
        self.replies = iter(replies)
        self.pending = []
        self.writes = 0

    def reset_input_buffer(self):
        self.pending = []

    def write(self, command):
        if command == vx6336.reader_info_command():
            # A recovery handshake does not consume an inventory scenario.
            data = bytes((2, 32, 0xD1, 0, 0x13, 0x40, 13, 255))
            body = bytes((13, 0, vx6336.CMD_GET_READER_INFO, 0)) + data
            crc = vx6336.crc16(body)
            self.pending.append(
                [self.clock.monotonic(), body + bytes((crc & 255, crc >> 8))]
            )
            return
        if command != vx6336.inventory_command():
            raise AssertionError("Offline transport only accepts inventory 01/info 21")
        self.writes += 1
        at = self.clock.monotonic()
        for delay, chunk in next(self.replies):
            at += delay
            self.pending.append([at, chunk])

    @property
    def in_waiting(self):
        if self.pending and self.pending[0][0] <= self.clock.monotonic():
            return len(self.pending[0][1])
        return 0

    def read(self, size):
        now = self.clock.monotonic()
        if not self.pending or self.pending[0][0] > now + 0.05:
            self.clock.advance(0.05)
            return b""
        at, chunk = self.pending[0]
        self.clock.advance(max(0, at - now))
        result = chunk[:size]
        if chunk[size:]:
            self.pending[0][1] = chunk[size:]
        else:
            self.pending.pop(0)
        return result


class MeasuredPresenceMonitor(PresenceMonitor):
    def __init__(self, clock):
        super().__init__(clock=clock)
        self.wall_samples = []

    def update(self, epcs):
        started = time.perf_counter()
        events = super().update(epcs)
        self.wall_samples.append(time.perf_counter() - started)
        return events


def polling_model(poll_ms, request_ms=0, dom_ms=0, phases=1000):
    """Uniform event phases; server snapshot at request START (conservative).

    Sequential schedule matches kiosk.js: request + DOM + poll sleep. A state
    change just after a snapshot waits a full cycle plus the following response.
    Network, request and DOM durations here are model inputs, not browser data.
    """
    cycle = poll_ms + request_ms + dom_ms
    waits = [
        (cycle * phase / phases + request_ms + dom_ms) / 1000
        for phase in range(1, phases + 1)
    ]
    return {
        "poll_ms": poll_ms,
        "request_ms_input": request_ms,
        "dom_ms_input": dom_ms,
        "requests_per_second": round(1000 / cycle, 3),
        "event_to_dom_model": timing_summary(waits),
    }


def run_case(name, replies, photo_bytes=0, tools=1, unit_photo_bytes=0):
    clock = VirtualClock()
    app = Flask("vx6336-offline-benchmark")
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True)
    database = DatabaseHandler(app)
    with app.app_context():
        kind = ToolType(name="Synthetic type", photo_data=b"x" * photo_bytes or None)
        db.session.add(kind)
        db.session.flush()
        for index in range(tools):
            db.session.add(
                Tool(
                    name="Synthetic tool",
                    rfid_uid=f"{index + 1:024X}",
                    type_id=kind.id,
                    unit_no=index + 1,
                    photo_data=b"y" * unit_photo_bytes or None,
                )
            )
        db.session.commit()

    reader = rfid_reader.VX6336Reader(serial_factory=lambda: None)
    reader.response_timeout = 0.3
    monitor = MeasuredPresenceMonitor(clock.monotonic)
    kiosk = Kiosk(app, database, clock=clock.monotonic)
    dispatch = []
    processing = []
    hit_processing = []
    cpu_start = []
    reader.add_round_listener(lambda epcs: cpu_start.append(time.perf_counter()))
    ToolPresenceService(
        app,
        database,
        reader,
        monitor,
        alarm_enabled=False,
        clock=clock.monotonic,
        kiosk=kiosk,
    )

    def processed(epcs):
        processing.append(time.perf_counter() - cpu_start[-1])
        if SYNTHETIC_EPC in epcs:
            hit_processing.append(processing[-1])
            dispatch.append(clock.monotonic())

    reader.add_round_listener(processed)
    app.register_blueprint(create_kiosk_blueprint(database, kiosk, lambda fn: fn))
    serial = ScriptedSerial(clock, replies)
    try:
        # Replace only this module's time binding, never the process-wide clock.
        with patch.object(rfid_reader, "time", clock):
            for _ in replies:
                reader.poll_once(serial)
        client = app.test_client()
        http_times = []
        for _ in range(20):
            started = time.perf_counter()
            response = client.get("/api/kiosk/state")
            http_times.append(time.perf_counter() - started)
            assert response.status_code == 200
        payload = response.get_json()
        unit = payload["board"][0]["units"][0]
        diag = reader.diagnostics()
        return {
            "scenario": name,
            "injected_elapsed_ms": round(clock.now * 1000, 3),
            "first_presence_dispatch_ms": round(dispatch[0] * 1000, 3)
            if dispatch
            else None,
            "final_kiosk_presence": unit["presence"],
            "rounds": serial.writes,
            "skipped_presence_rounds": diag["skipped_presence_rounds_total"],
            "serial_virtual": {
                key: diag[key]
                for key in ("inventory", "first_frame", "first_epc", "epc_to_terminal")
            },
            "presence_service_host_wall": timing_summary(processing),
            "presence_hit_service_host_wall": timing_summary(hit_processing),
            "presence_monitor_host_wall": timing_summary(monitor.wall_samples),
            "kiosk_get_host_wall": timing_summary(http_times),
        }
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def scenarios():
    hit = [(0.05, frame(SYNTHETIC_EPC))]
    return {
        "immediate": [hit],
        "ten_missed_rounds": [[(0.05, frame())]] * 10 + [hit],
        "hundred_missed_rounds": [[(0.05, frame())]] * 100 + [hit],
        "slow_terminal": [
            [(0.05, frame(SYNTHETIC_EPC, vx6336.STATUS_INVENTORY_MORE)), (0.2, frame())]
        ],
        "partial_then_complete": [
            [(0.05, frame(SYNTHETIC_EPC, vx6336.STATUS_INVENTORY_MORE))],
            hit,
        ],
        "no_response_then_complete": [[], hit],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo-kib", type=int, default=0)
    parser.add_argument("--unit-photo-kib", type=int, default=0)
    parser.add_argument("--tools", type=int, default=1)
    args = parser.parse_args()
    if (
        not 0 <= args.photo_kib <= 2048
        or not 0 <= args.unit_photo_kib <= 2048
        or not 1 <= args.tools <= 200
    ):
        parser.error("photo-kib/unit-photo-kib must be 0..2048; tools must be 1..200")
    print(
        json.dumps(
            {
                "kind": "offline_synthetic_not_rf_measurement",
                "photo_kib": args.photo_kib,
                "unit_photo_kib": args.unit_photo_kib,
                "tools": args.tools,
                "cases": [
                    run_case(
                        name,
                        replies,
                        args.photo_kib * 1024,
                        args.tools,
                        args.unit_photo_kib * 1024,
                    )
                    for name, replies in scenarios().items()
                ],
                "polling_models": [
                    polling_model(ms, request_ms=20, dom_ms=5)
                    for ms in (1000, 500, 250)
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

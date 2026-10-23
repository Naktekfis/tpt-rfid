"""Offline loss/alarm/buzzer trace: fake serial, synthetic tool, SQLite memory.

Never imports app.py/config or opens a device. Virtual milliseconds represent
injected waits only; host HTTP duration is reported separately. No browser or
physical removal/sound measurement is made. Run directly to print JSON.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask  # noqa: E402

from routes.kiosk_routes import create_kiosk_blueprint  # noqa: E402
from scripts.vx6336_latency_bench import (  # noqa: E402
    SYNTHETIC_EPC,
    ScriptedSerial,
    VirtualClock,
    frame,
)
from utils import DatabaseHandler, db, rfid_reader, vx6336  # noqa: E402
from utils.kiosk import Kiosk  # noqa: E402
from utils.models import Tool, ToolType  # noqa: E402
from utils.presence import PresenceMonitor  # noqa: E402
from utils.tool_presence import ToolPresenceService  # noqa: E402

# Binary-exact cadence makes the strict >5 s boundary reproducible.
STEP = 0.0625
CASES = (
    "healthy",
    "rejected_empty_02",
    "rejected_empty_04",
    "no_poll_for_8s",
    "observer_750ms",
    "tail_listener_500ms",
    "three_commands_ahead",
    "inventory_timeout",
)


def run_loss_case(name):
    if name not in CASES:
        raise ValueError("Unknown synthetic scenario")
    clock = VirtualClock()
    trace = []
    origin = [0.0]

    def mark(stage, **fields):
        trace.append(
            {
                "stage": stage,
                "virtual_ms": round((clock.now - origin[0]) * 1000, 3),
                **fields,
            }
        )

    class TracedMonitor(PresenceMonitor):
        def update(self, epcs):
            events = super().update(epcs)
            for event in events:
                if event.kind == "left":
                    mark("missing_event")
            return events

    class TracedDatabase(DatabaseHandler):
        def set_tool_presence(self, tool_id, presence, last_seen_at=None):
            super().set_tool_presence(tool_id, presence, last_seen_at)
            if presence == "missing":
                mark("missing_committed")

        def create_alarm(self, tool_id):
            alarm = super().create_alarm(tool_id)
            mark("alarm_committed")
            return alarm

    class TracedReader(rfid_reader.VX6336Reader):
        enqueues = 0

        def beep(self, *args, **kwargs):
            super().beep(*args, **kwargs)
            self.enqueues += 1
            mark(
                "beep_enqueued",
                command_index=self.enqueues,
                queue_depth=self._commands.qsize(),
            )

        def _transact(self, ser, command, expect_cmd):
            responses = super()._transact(ser, command, expect_cmd)
            if expect_cmd == vx6336.CMD_ACOUSTO_OPTIC:
                mark(
                    "buzzer_response_received",
                    command_index=ser.buzzer_writes,
                    response_count=len(responses),
                )
            return responses

    class BuzzerSerial(ScriptedSerial):
        buzzer_writes = 0

        def write(self, command):
            if command[2] == vx6336.CMD_ACOUSTO_OPTIC:
                self.buzzer_writes += 1
                mark("buzzer_write_called", command_index=self.buzzer_writes)
                # Synthetic ACK only: no claim about physical sound or pattern duration.
                body = bytes((5, 0, vx6336.CMD_ACOUSTO_OPTIC, 0))
                crc = vx6336.crc16(body)
                self.pending.append(
                    [clock.now + STEP, body + bytes((crc & 255, crc >> 8))]
                )
            else:
                super().write(command)

    app = Flask("offline-uhf-loss-trace")
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True)
    database = TracedDatabase(app)
    with app.app_context():
        kind = ToolType(name="Synthetic type")
        db.session.add(kind)
        db.session.flush()
        db.session.add(
            Tool(name="Synthetic tool", rfid_uid=SYNTHETIC_EPC, type_id=kind.id)
        )
        db.session.commit()
    reader = TracedReader(serial_factory=lambda: None)
    reader.response_timeout = 0.25  # injected deadline, NOT deployment config
    monitor = TracedMonitor(missing_after=5, clock=clock.monotonic)
    kiosk = Kiosk(app, database, clock=clock.monotonic)
    app.register_blueprint(create_kiosk_blueprint(database, kiosk, lambda fn: fn))
    client = app.test_client()

    def api_probe(stage):
        started = time.perf_counter()
        response = client.get("/api/kiosk/state")
        host_ms = (time.perf_counter() - started) * 1000
        assert response.status_code == 200
        payload = response.get_json()
        mark(
            stage,
            presence=payload["board"][0]["units"][0]["presence"],
            alarm_count=len(payload["alarms"]),
            host_http_ms=round(host_ms, 3),
        )

    def observer(alarm):
        # Deliberate same-thread test-client probe: verifies logical visibility,
        # not concurrent SQLite/network/browser behavior or production overhead.
        api_probe("api_before_alarm_beep_enqueue")
        if name == "observer_750ms":
            clock.advance(0.75)
        if name == "three_commands_ahead":
            for _ in range(3):
                reader.beep()

    ToolPresenceService(
        app, database, reader, monitor, True, clock.monotonic, kiosk, observer
    )

    tail_applied = False

    def tail(epcs):
        nonlocal tail_applied
        if name == "tail_listener_500ms" and reader.enqueues and not tail_applied:
            clock.advance(0.5)
            tail_applied = True

    reader.add_round_listener(tail)
    hit = [(STEP, frame(SYNTHETIC_EPC))]
    empty = [(STEP, frame())]
    if name.startswith("rejected_empty_"):
        status = 2 if name.endswith("02") else 4
        departure_rounds = [[(STEP, frame(status=status))]] * 112 + [empty]
    elif name == "no_poll_for_8s":
        departure_rounds = [empty]
    elif name == "inventory_timeout":
        departure_rounds = [[], empty]
    else:
        departure_rounds = [empty] * 81
    # Four more polls suffice to flush the largest injected FIFO backlog.
    serial = BuzzerSerial(clock, [hit] + departure_rounds + [empty] * 4)
    try:
        with patch.object(rfid_reader, "time", clock):
            reader.poll_once(serial)
            origin[0] = clock.now
            mark("last_sighting_and_synthetic_removal")
            if name == "no_poll_for_8s":
                clock.advance(8)
                api_probe("api_after_8s_without_round")
            for index, _ in enumerate(departure_rounds):
                reader.poll_once(serial)
                if name == "healthy" and index == 79:
                    api_probe("api_at_exact_missing_threshold")
            mark("loss_round_finished")
            api_probe("api_after_loss_round_before_next_poll")
            for _ in range(4):
                reader.poll_once(serial)
        alarm_command_index = reader.enqueues
        alarm_write = next(
            e
            for e in trace
            if e["stage"] == "buzzer_write_called"
            and e["command_index"] == alarm_command_index
        )
        alarm_enqueue = next(
            e
            for e in trace
            if e["stage"] == "beep_enqueued"
            and e["command_index"] == alarm_command_index
        )
        missing = next(e for e in trace if e["stage"] == "missing_event")
        diag = reader.diagnostics()
        return {
            "scenario": name,
            "clock": "virtual_injected_waits_only",
            "last_sighting_to_missing_ms": missing["virtual_ms"],
            "missing_to_alarm_beep_enqueue_ms": alarm_enqueue["virtual_ms"]
            - missing["virtual_ms"],
            "alarm_beep_enqueue_to_write_call_ms": alarm_write["virtual_ms"]
            - alarm_enqueue["virtual_ms"],
            "skipped_presence_rounds": diag["skipped_presence_rounds_total"],
            "transaction_timeouts": reader._recovery_counts[
                "transaction_timeouts_total"
            ],
            "trace": trace,
        }
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "kind": "offline_synthetic_not_device_measurement",
                "cases": [run_loss_case(name) for name in CASES],
            },
            indent=2,
        )
    )

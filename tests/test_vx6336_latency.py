"""Synthetic end-to-end timing and polling-model regression checks."""

import pytest
from sqlalchemy import event

from scripts.vx6336_latency_bench import (
    SYNTHETIC_EPC,
    ScriptedSerial,
    VirtualClock,
    frame,
    polling_model,
    run_case,
    scenarios,
)
from utils import rfid_reader, vx6336
from utils.models import db, Student, Tool, ToolType, Transaction


@pytest.mark.parametrize(
    "name, dispatch_ms, presence, skipped",
    [
        ("immediate", 50, "present", 0),
        ("ten_missed_rounds", 550, "present", 0),
        ("hundred_missed_rounds", 5050, "present", 0),
        ("slow_terminal", 250, "present", 0),
        ("partial_then_complete", 26350, "present", 1),
        ("no_response_then_complete", 26350, "present", 1),
    ],
)
def test_real_pipeline_with_injected_acquisition(name, dispatch_ms, presence, skipped):
    result = run_case(name, scenarios()[name])
    assert result["first_presence_dispatch_ms"] == dispatch_ms
    assert result["final_kiosk_presence"] == presence
    assert result["skipped_presence_rounds"] == skipped
    assert SYNTHETIC_EPC not in str(result)
    assert result["presence_service_host_wall"]["samples"] > 0
    assert result["kiosk_get_host_wall"]["samples"] == 20
    if name == "slow_terminal":
        assert result["serial_virtual"]["first_epc"]["mean_ms"] == 50
        assert result["serial_virtual"]["epc_to_terminal"]["mean_ms"] == 200


def test_epc_timing_excludes_empty_rounds_and_survives_fragmentation(monkeypatch):
    clock = VirtualClock()
    hit = frame(SYNTHETIC_EPC)
    replies = [[(0.02, frame())], [(0.01, hit[:4]), (0.02, hit[4:])]]
    reader = rfid_reader.VX6336Reader()
    serial = ScriptedSerial(clock, replies)
    monkeypatch.setattr(rfid_reader, "time", clock)
    reader.poll_once(serial)
    reader.poll_once(serial)
    timing = reader.diagnostics()
    assert timing["first_frame"]["samples"] == 2
    assert timing["first_epc"]["samples"] == 1
    assert timing["first_epc"]["mean_ms"] == 30
    assert timing["epc_to_terminal"]["mean_ms"] == 0
    assert SYNTHETIC_EPC not in str(timing)


def test_partial_only_is_not_kiosk_presence():
    result = run_case(
        "partial_only", [[(0.05, frame(SYNTHETIC_EPC, vx6336.STATUS_INVENTORY_MORE))]]
    )
    assert result["first_presence_dispatch_ms"] is None
    assert result["final_kiosk_presence"] == "unknown"
    assert result["serial_virtual"]["first_epc"]["samples"] == 1
    assert result["serial_virtual"]["epc_to_terminal"]["samples"] == 0


def test_presence_lookup_reads_only_state_columns(app, database):
    with app.app_context():
        tool = Tool(
            name="Synthetic",
            rfid_uid=SYNTHETIC_EPC,
            photo_data=b"x" * (2 * 1024 * 1024),
            presence="present",
        )
        db.session.add(tool)
        db.session.commit()
        expected = {"id": tool.id, "status": "available", "presence": "present"}
        db.session.remove()
        statements = []

        def capture(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            assert database.get_tool_presence_info(SYNTHETIC_EPC) == expected
            assert database.get_tool_presence_info("unknown-synthetic") is None
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert len(statements) == 2
        assert all("photo_data" not in sql for sql in statements)


def test_polling_model_includes_response_and_dom_in_cadence():
    slow = polling_model(1000, request_ms=20, dom_ms=5)
    fast = polling_model(250, request_ms=20, dom_ms=5)
    assert slow["event_to_dom_model"]["max_ms"] == 1050
    assert fast["event_to_dom_model"]["max_ms"] == 300
    assert slow["event_to_dom_model"]["p95_ms"] == 998.75
    assert fast["requests_per_second"] == 3.636


@pytest.mark.parametrize("photo", [None, b"", b"synthetic image bytes"])
def test_board_preserves_photo_and_borrower_without_fetching_blobs(
    app, database, photo
):
    from datetime import datetime, timedelta

    with app.app_context():
        kind = ToolType(name="Synthetic photo type", photo_data=photo)
        student = Student(
            name="Synthetic student",
            nim="99999999",
            email="test@example.com",
            phone="000",
            photo_data=b"synthetic student photo",
        )
        db.session.add_all([kind, student])
        db.session.flush()
        tool = Tool(
            name="Synthetic borrowed tool",
            rfid_uid=SYNTHETIC_EPC,
            type_id=kind.id,
            photo_data=b"synthetic tool photo",
            status="borrowed",
        )
        db.session.add(tool)
        db.session.flush()
        db.session.add(
            Transaction(
                student_id=student.id,
                student_name=student.name,
                tool_id=tool.id,
                tool_name=tool.name,
                due_at=datetime.utcnow() - timedelta(hours=1),
            )
        )
        db.session.add(Tool(name="Untyped", rfid_uid="000000000000000000000002"))
        db.session.commit()
        type_id = kind.id
        db.session.remove()  # Ensure no identity-map photo can mask a lazy fetch.
        statements = []

        def capture(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            board = database.get_board()
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert len(statements) == 1
        projection = statements[0].split("FROM")[0]
        assert "tools.photo_data" not in projection
        assert "students.photo_data" not in projection
        assert "tool_types.photo_data AS" not in projection
        group = next(g for g in board if g["type_id"] == str(type_id))
        assert group["photo_url"] == (
            f"/api/tool_type/{type_id}/photo" if photo else ""
        )
        unit = group["units"][0]
        assert unit["borrower_name"] == "Synthetic student"
        assert unit["borrower_nim"] == "99999999"
        assert unit["is_overdue"] is True
        untyped = next(g for g in board if g["type_id"] is None)
        assert untyped["photo_url"] == ""

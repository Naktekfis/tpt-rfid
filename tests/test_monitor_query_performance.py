"""Monitor polling must not transfer image BLOBs or lazily reload each row."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from utils.helpers import utc_to_wib
from utils.models import AlarmEvent, Student, Tool, ToolType, Transaction, db


@pytest.mark.parametrize("include_email", [False, True])
def test_monitor_query_preserves_response_without_loading_images(
    database, include_email
):
    now = datetime.utcnow()
    expected = []
    photos = [None, b"", b"x" * (2 * 1024 * 1024)]
    for index, photo in enumerate(photos):
        student = Student(
            name=f"Synthetic student {index}",
            nim=f"SYNTH-{index}",
            email=f"synthetic-{index}@example.com",
            phone="000",
            photo_data=photo,
        )
        tool = Tool(
            name=f"Tool {index}",
            rfid_uid=f"SYNTH-TOOL-{index}",
            photo_data=photo,
            presence="present",
            status="borrowed",
            unit_no=index + 1,
            last_seen_at=now,
        )
        db.session.add_all([student, tool])
        db.session.flush()
        transaction = Transaction(
            student_id=student.id,
            student_name=student.name,
            tool_id=tool.id,
            tool_name=tool.name,
            borrow_time=now,
            due_at=now + timedelta(days=1),
        )
        db.session.add(transaction)
        item = tool.to_dict()
        item.update(
            borrower_name=student.name,
            borrower_nim=student.nim,
            borrow_time=utc_to_wib(now),
            due_at=utc_to_wib(transaction.due_at),
            is_overdue=False,
        )
        if include_email:
            item.update(
                borrower_email=student.email,
                borrower_photo_url=f"/api/student/{student.id}/photo" if photo else "",
            )
        expected.append(item)

    available = Tool(name="Tool 3", rfid_uid="SYNTH-AVAILABLE")
    db.session.add(available)
    db.session.flush()
    item = available.to_dict()
    item.update(
        borrower_name=None,
        borrower_nim=None,
        borrow_time=None,
        due_at=None,
        is_overdue=False,
    )
    if include_email:
        item.update(borrower_email=None, borrower_photo_url=None)
    expected.append(item)
    db.session.commit()
    db.session.expunge_all()

    columns = []

    def record_columns(connection, cursor, statement, parameters, context, executemany):
        if cursor.description:
            columns.append([column[0] for column in cursor.description])

    event.listen(db.engine, "after_cursor_execute", record_columns)
    try:
        actual = database.get_all_tools_with_borrowers(include_email=include_email)
    finally:
        event.remove(db.engine, "after_cursor_execute", record_columns)

    assert actual == expected
    assert len(columns) == 1, "Polling must not issue per-row lazy image queries"
    assert not any("photo_data" in column for column in columns[0])
    assert "tool_has_photo" in columns[0]
    assert "student_has_photo" in columns[0]
    assert (
        database.get_all_tools_with_borrowers(
            include_email=include_email, limit=2, offset=1
        )
        == expected[1:3]
    )


def test_tool_type_poll_projects_photo_flags_and_preserves_counts(database):
    expected = []
    for index, photo in enumerate([None, b"", b"x" * (2 * 1024 * 1024)]):
        tool_type = ToolType(name=f"Type {index}", photo_data=photo)
        db.session.add(tool_type)
        db.session.flush()
        for unit_no in range(1, index + 1):
            db.session.add(
                Tool(
                    name=f"Tool {index}-{unit_no}",
                    rfid_uid=f"SYNTH-{index}-{unit_no}",
                    type_id=tool_type.id,
                    unit_no=unit_no * 2,
                )
            )
        item = tool_type.to_dict()
        item.pop("created_at")
        item.update(units=index, next_unit_no=index * 2 + 1)
        expected.append(item)
    db.session.commit()
    db.session.expunge_all()
    columns = []

    def record_columns(connection, cursor, statement, parameters, context, executemany):
        if cursor.description:
            columns.append([column[0] for column in cursor.description])

    event.listen(db.engine, "after_cursor_execute", record_columns)
    try:
        actual = database.get_tool_types()
    finally:
        event.remove(db.engine, "after_cursor_execute", record_columns)
    assert actual == expected
    assert len(columns) == 1
    assert not any("photo_data" in column for column in columns[0])
    assert "type_has_photo" in columns[0]


def test_open_alarm_poll_loads_all_tool_names_in_one_query_without_images(database):
    now = datetime.utcnow()
    expected = []
    for index in range(10):
        tool = Tool(
            name=f"Tool {index}",
            rfid_uid=f"SYNTH-{index}",
            photo_data=b"x" * (256 * 1024),
        )
        db.session.add(tool)
        db.session.flush()
        alarm = AlarmEvent(tool_id=tool.id, started_at=now + timedelta(seconds=index))
        db.session.add(alarm)
        db.session.flush()
        expected.append(alarm.to_dict())
    db.session.add(
        AlarmEvent(tool_id=tool.id, started_at=now, ended_at=now, ended_by="returned")
    )
    db.session.commit()
    db.session.expunge_all()
    columns = []

    def record_columns(connection, cursor, statement, parameters, context, executemany):
        if cursor.description:
            columns.append([column[0] for column in cursor.description])

    event.listen(db.engine, "after_cursor_execute", record_columns)
    try:
        actual = database.get_open_alarms()
    finally:
        event.remove(db.engine, "after_cursor_execute", record_columns)
    assert actual == expected
    assert len(columns) == 1, "Alarm polling must not load tools one at a time"
    assert not any("photo_data" in column for column in columns[0])

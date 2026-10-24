import pytest

from tests.conftest import TEST_PIN

EPC = "E2000017221101AA01000000"


@pytest.fixture()
def admin(admin_client):
    assert (
        admin_client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200
    )
    return admin_client


def test_delete_requires_admin(client):
    assert client.post("/api/admin/students/1/delete").status_code == 401
    assert client.post("/api/admin/tool_units/1/delete").status_code == 401


def test_delete_student_hides_but_keeps_history(admin, database, student, tool):
    database.bind_student_nfc(student["student_id"], "04AABBCC")
    database.borrow_tool_atomic(student["student_id"], tool["tool_id"])
    database.return_tool_atomic(student["student_id"], tool["tool_id"])

    resp = admin.post(f"/api/admin/students/{student['student_id']}/delete")
    assert resp.status_code == 200 and resp.get_json()["success"] is True

    assert admin.get("/api/admin/students").get_json()["students"] == []
    assert database.get_student_by_nfc("04AABBCC") is None
    assert database.get_student_by_nim(student["nim"]) is None
    assert database.get_student_by_id(student["student_id"]) is None
    rows = database.get_transactions_filtered()
    assert len(rows) == 1 and rows[0]["student_name"] == "Budi"
    # Already deleted -> 404.
    resp = admin.post(f"/api/admin/students/{student['student_id']}/delete")
    assert resp.status_code == 404


def test_delete_student_refused_with_active_borrow(admin, database, student, tool):
    database.borrow_tool_atomic(student["student_id"], tool["tool_id"])
    resp = admin.post(f"/api/admin/students/{student['student_id']}/delete")
    assert resp.status_code == 409
    assert "pinjaman aktif" in resp.get_json()["error"]
    assert len(admin.get("/api/admin/students").get_json()["students"]) == 1


def test_delete_missing_student_is_404(admin):
    assert admin.post("/api/admin/students/999/delete").status_code == 404


def test_reregister_deleted_nim_restores(admin, database, student):
    database.bind_student_nfc(student["student_id"], "04AABBCC")
    admin.post(f"/api/admin/students/{student['student_id']}/delete")

    restored = database.create_student(
        {
            "name": "Budi Baru",
            "nim": student["nim"],
            "email": "baru@example.com",
            "phone": "0899",
            "nfc_uid": "04DDEEFF",
        }
    )
    assert restored["student_id"] == student["student_id"]
    listed = admin.get("/api/admin/students").get_json()["students"]
    assert len(listed) == 1 and listed[0]["name"] == "Budi Baru"
    assert database.get_student_by_nfc("04DDEEFF")["name"] == "Budi Baru"
    # An active student's NIM is still found (registration rejects it).
    assert database.get_student_by_nim(student["nim"]) is not None


def test_delete_tool_unit_frees_tag_and_hides(admin, database):
    ttype = database.create_tool_type("Bor Listrik")
    unit = database.create_tool_unit(int(ttype["type_id"]), 1, EPC)
    database.create_alarm(int(unit["tool_id"]))

    resp = admin.post(f"/api/admin/tool_units/{unit['tool_id']}/delete")
    assert resp.status_code == 200

    assert database.get_board() == []
    assert database.get_all_tools() == []
    assert database.get_all_tools_with_borrowers() == []
    assert database.get_tools_presence() == []
    assert database.get_tool_by_name("Bor Listrik #1") is None
    assert database.get_open_alarms() == []
    history = database.get_alarm_history()
    assert len(history) == 1 and history[0]["ended_by"] == "deleted"
    types = database.get_tool_types()
    assert types[0]["units"] == 0 and types[0]["next_unit_no"] == 1
    assert database.get_tool_presence_info(EPC) is None
    # The tag and unit number can be used again.
    again = database.create_tool_unit(int(ttype["type_id"]), 1, EPC)
    assert again["tool_id"] != unit["tool_id"]
    assert (
        admin.post(f"/api/admin/tool_units/{unit['tool_id']}/delete").status_code == 404
    )


def test_delete_tool_refused_when_borrowed(admin, database, student, tool):
    database.borrow_tool_atomic(student["student_id"], tool["tool_id"])
    resp = admin.post(f"/api/admin/tool_units/{tool['tool_id']}/delete")
    assert resp.status_code == 409

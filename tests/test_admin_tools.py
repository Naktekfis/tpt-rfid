import io

import pytest

import app as app_module
from tests.conftest import TEST_PIN
from utils import db
from utils.models import Tool, ToolType

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
EPC = "E2000017221101AA01000000"


@pytest.fixture()
def admin(admin_client):
    assert (
        admin_client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200
    )
    return admin_client


@pytest.fixture()
def tool_type(database):
    return database.create_tool_type("Bor Listrik")


ADMIN_ONLY = [
    ("get", "/api/admin/tool_types", None),
    ("post", "/api/admin/tool_types", {"name": "X"}),
    ("post", "/api/admin/tool_types/1/photo/capture", None),
    ("post", "/api/admin/tool_units", {"type_id": 1, "epc": EPC}),
    ("get", "/api/admin/students", None),
]


@pytest.mark.parametrize("method,url,body", ADMIN_ONLY)
def test_admin_tool_api_requires_session(client, method, url, body):
    resp = (
        getattr(client, method)(url, json=body)
        if body
        else getattr(client, method)(url)
    )
    assert resp.status_code == 401


def test_photo_upload_requires_session(client, tool_type):
    resp = client.post(
        f"/api/admin/tool_types/{tool_type['type_id']}/photo",
        data={"photo": (io.BytesIO(PNG), "a.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 401


def test_create_and_list_tool_types(admin):
    resp = admin.post("/api/admin/tool_types", json={"name": "Obeng Set"})
    assert resp.status_code == 200
    created = resp.get_json()["tool_type"]
    assert created["next_unit_no"] == 1
    # Duplicate (case-insensitive) and empty names are refused.
    assert (
        admin.post("/api/admin/tool_types", json={"name": "obeng set"}).status_code
        == 400
    )
    assert admin.post("/api/admin/tool_types", json={"name": " "}).status_code == 400
    types = admin.get("/api/admin/tool_types").get_json()["tool_types"]
    assert [t["name"] for t in types] == ["Obeng Set"]


def test_upload_tool_type_photo(admin, tool_type):
    url = f"/api/admin/tool_types/{tool_type['type_id']}/photo"
    resp = admin.post(
        url,
        data={"photo": (io.BytesIO(PNG), "a.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    row = db.session.get(ToolType, int(tool_type["type_id"]))
    assert row.photo_data == PNG and row.photo_mimetype == "image/png"
    assert admin.get(f"/api/tool_type/{tool_type['type_id']}/photo").data == PNG

    # Wrong extension, not an image, unknown type.
    bad = admin.post(
        url,
        data={"photo": (io.BytesIO(PNG), "a.txt")},
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400
    bad = admin.post(
        url,
        data={"photo": (io.BytesIO(b"hello"), "a.png")},
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400
    missing = admin.post(
        "/api/admin/tool_types/999/photo",
        data={"photo": (io.BytesIO(PNG), "a.png")},
        content_type="multipart/form-data",
    )
    assert missing.status_code == 404


def test_capture_tool_type_photo(admin, tool_type):
    url = f"/api/admin/tool_types/{tool_type['type_id']}/photo/capture"
    # Mock camera without frames: no picture.
    assert admin.post(url).status_code == 503
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")  # MockCamera.jpeg encodes with OpenCV
    frame = np.full((48, 64, 3), 120, np.uint8)
    app_module.camera.set_frames([frame])
    try:
        resp = admin.post(url)
    finally:
        app_module.camera.set_frames([])
    assert resp.status_code == 200
    row = db.session.get(ToolType, int(tool_type["type_id"]))
    assert row.photo_mimetype == "image/jpeg"
    assert row.photo_data.startswith(b"\xff\xd8\xff")
    assert admin.post("/api/admin/tool_types/999/photo/capture").status_code == 404


def test_create_unit_from_epc(admin, database, tool_type):
    tid = tool_type["type_id"]
    resp = admin.post(
        "/api/admin/tool_units",
        json={"type_id": tid, "epc": "e200 0017 2211 01aa 0100 0000"},
    )
    assert resp.status_code == 200, resp.get_json()
    tool = resp.get_json()["tool"]
    assert tool["name"] == "Bor Listrik #1"
    assert tool["rfid_uid"] == EPC
    assert tool["unit_no"] == 1
    row = db.session.get(Tool, int(tool["tool_id"]))
    assert row.type_id == int(tid) and row.status == "available"

    # Next unit number is suggested; explicit numbers are kept.
    types = admin.get("/api/admin/tool_types").get_json()["tool_types"]
    assert types[0]["units"] == 1 and types[0]["next_unit_no"] == 2
    resp = admin.post(
        "/api/admin/tool_units", json={"type_id": tid, "unit_no": 5, "epc": "ABCD1234"}
    )
    assert resp.get_json()["tool"]["name"] == "Bor Listrik #5"

    # Same EPC, same unit number, bad EPC, unknown type.
    assert (
        admin.post(
            "/api/admin/tool_units", json={"type_id": tid, "epc": EPC}
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/admin/tool_units", json={"type_id": tid, "unit_no": 1, "epc": "BEEF"}
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/admin/tool_units", json={"type_id": tid, "epc": "XYZ!"}
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/admin/tool_units", json={"type_id": 999, "epc": "BEEF"}
        ).status_code
        == 404
    )


def test_new_unit_in_field_stops_being_unknown(admin, database, tool_type):
    service = app_module.presence_service
    service.on_round(["CAFE0001"])
    assert "CAFE0001" in admin.get("/api/presence").get_json()["unknown_epcs"]
    resp = admin.post(
        "/api/admin/tool_units",
        json={"type_id": tool_type["type_id"], "epc": "CAFE0001"},
    )
    assert resp.status_code == 200
    assert "CAFE0001" not in admin.get("/api/presence").get_json()["unknown_epcs"]
    row = db.session.get(Tool, int(resp.get_json()["tool"]["tool_id"]))
    assert row.presence == "present"


def test_students_list_has_face_flag(admin, database, student):
    database.add_face_embeddings(int(student["student_id"]), "test", [b"\x00" * 8])
    other = database.create_student(
        {"name": "Sari", "nim": "22222222", "email": "s@example.com", "phone": "0811"}
    )
    rows = {
        s["nim"]: s for s in admin.get("/api/admin/students").get_json()["students"]
    }
    assert rows[student["nim"]]["has_face"] is True
    assert rows[other["nim"]]["has_face"] is False
    assert rows[other["nim"]]["open_loans"] == 0

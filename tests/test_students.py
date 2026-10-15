import app as app_module

FORM = {
    "name": "Budi",
    "nim": "12345678",
    "email": "budi@example.com",
    "phone": "08123456789",
    "rfid_uid": "STU-001",
}


def test_register_student_without_photo(client):
    resp = client.post("/api/register", data=FORM)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["student"]["nim"] == "12345678"
    assert "student_id" in body["student"]


def test_register_missing_field(client):
    data = dict(FORM)
    del data["email"]
    resp = client.post("/api/register", data=data)
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_register_invalid_nim(client):
    resp = client.post("/api/register", data=dict(FORM, nim="12"))
    assert resp.status_code == 400


def test_register_duplicate_nim_and_uid(client, student):
    resp = client.post("/api/register", data=dict(FORM, rfid_uid="OTHER"))
    assert resp.status_code == 400
    resp = client.post("/api/register", data=dict(FORM, nim="99999999"))
    assert resp.status_code == 400


def test_check_rfid_idle_and_detected(client):
    body = client.get("/api/check_rfid").get_json()
    assert body == {
        "success": True,
        "uid": None,
        "detected": False,
        "reader_connected": True,
    }

    app_module.rfid_reader.simulate_scan("ABC123")
    try:
        body = client.get("/api/check_rfid").get_json()
        assert body["detected"] is True
        assert body["uid"] == "ABC123"
    finally:
        app_module.rfid_reader.clear()


def test_scan_student(client, student):
    resp = client.post("/api/scan_student", json={"rfid_uid": "STU-001"})
    assert resp.status_code == 200
    assert resp.get_json()["student"]["nim"] == "12345678"


def test_scan_student_unknown_and_empty(client):
    assert client.post("/api/scan_student", json={"rfid_uid": "nope"}).status_code == 404
    assert client.post("/api/scan_student", json={"rfid_uid": ""}).status_code == 400


def test_scan_student_without_json_body(client):
    # NOTE: non-JSON body makes request.get_json() raise, caught by the broad
    # handler and reported as 500 rather than 400/415.
    resp = client.post("/api/scan_student", data="x")
    assert resp.status_code == 500


def test_student_photo_missing(client, student):
    assert client.get(f"/api/student/{student['student_id']}/photo").status_code == 404

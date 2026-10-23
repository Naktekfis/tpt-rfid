import app as app_module
from tests.conftest import TEST_PIN

FORM = dict(
    name="Sintetis", nim="87654321", email="test@example.com", phone="08123456789"
)


def capture(client, uid="01020304"):
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan(uid)
    return token


def test_capture_routes_without_leaking_uid(client, database):
    token = capture(client)
    state = client.get("/api/nfc/registration").get_json()
    assert state["ready"] and "uid" not in state
    assert app_module.kiosk.state_dict()["state"] == "idle"
    response = client.post(
        "/api/register", data=dict(FORM, nfc_token=token, rfid_uid="FFFFFFFF")
    )
    assert response.status_code == 200
    assert database.get_student_by_nfc("01020304")
    assert not database.get_student_by_nfc("FFFFFFFF")
    assert (
        client.post(
            "/api/register", data=dict(FORM, nim="99999999", nfc_token=token)
        ).status_code
        == 409
    )
    app_module.nfc_reader.simulate_scan("01020304")
    assert app_module.kiosk.state_dict()["state"] == "session"
    assert client.post("/api/nfc/registration/start").status_code == 409


def test_capture_owner_and_unknown_card(client, app):
    token = capture(client)
    other = app.test_client()
    assert other.get("/api/nfc/registration").get_json()["ready"] is False
    assert other.post("/api/nfc/registration/start").status_code == 409
    assert (
        other.post("/api/register", data=dict(FORM, nfc_token=token)).status_code == 409
    )
    other.post("/api/nfc/registration/cancel")
    assert client.get("/api/nfc/registration").get_json()["ready"] is True
    client.post("/api/nfc/registration/cancel", json={"nfc_token": token})
    app_module.nfc_reader.simulate_scan("01020304")
    assert app_module.kiosk.state_dict()["state"] == "unknown_card"


def test_expired_capture_and_old_event(client, monkeypatch):
    now = [10.0]
    monkeypatch.setattr(app_module.nfc_service, "clock", lambda: now[0])
    app_module.nfc_reader.simulate_scan("01020304")
    old = app_module.nfc_reader.latest_event()
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_service.on_card(old)
    assert not client.get("/api/nfc/registration").get_json()["ready"]
    now[0] += 121
    assert (
        client.post("/api/register", data=dict(FORM, nfc_token=token)).status_code
        == 409
    )


def test_admin_can_bind_only_unbound_student(client, database):
    student = database.create_student(dict(FORM, rfid_uid=None))
    url = "/api/admin/students/" + student["student_id"] + "/nfc"
    token = capture(client)
    assert client.post(url, json=dict(nfc_token=token)).status_code == 401
    client.post("/api/admin/login", json={"pin": TEST_PIN})
    assert client.post(url, json=dict(nfc_token=token)).status_code == 200
    token = capture(client, "AABBCCDD")
    assert client.post(url, json=dict(nfc_token=token)).status_code == 409
    assert (
        database.get_student_by_nfc("01020304")["student_id"] == student["student_id"]
    )


def test_duplicate_card_not_rebound(client, database):
    database.create_student(dict(FORM, nfc_uid="01020304"))
    token = capture(client)
    response = client.post(
        "/api/register", data=dict(FORM, nim="11111111", nfc_token=token)
    )
    assert response.status_code == 409
    assert not database.get_student_by_nim("11111111")


def test_face_not_registered_and_camera_retained(client, app):
    assert "face" not in app.blueprints and "cv" not in app.blueprints
    assert client.get("/camera/stream").status_code == 503


def test_old_uhf_binding_preserved(client, database):
    old_uid = "E20000112233445566778899"
    student = database.create_student(dict(FORM, rfid_uid=old_uid))
    assert not database.get_students_admin()[0]["has_nfc"]
    database.bind_student_nfc(student["student_id"], "01020304")
    assert database.get_student_by_uid(old_uid)["student_id"] == student["student_id"]
    assert (
        database.get_student_by_nfc("01020304")["student_id"] == student["student_id"]
    )
    assert database.get_students_admin()[0]["has_nfc"]


def test_old_cancel_does_not_cancel_new_capture(client):
    first = client.post("/api/nfc/registration/start").get_json()["token"]
    second = capture(client)
    client.post("/api/nfc/registration/cancel", json={"nfc_token": first})
    assert client.get("/api/nfc/registration").get_json()["ready"]
    assert (
        client.post("/api/register", data=dict(FORM, nfc_token=second)).status_code
        == 200
    )

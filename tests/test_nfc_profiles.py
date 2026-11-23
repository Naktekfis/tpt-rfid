"""Admin-registered cards skip the KTM check; the kiosk locks each bound card
to its chip data (ATQA, SAK, ATS) so a cloned UID is refused."""

from __future__ import annotations

import pytest

import app as app_module
from tests.test_nfc_policy import EMONEY, FORM, KTM, admin_session, policy_with_db
from utils.models import NFCCardProfile

PHONE_UID = "ff:4e:8e:f9"
UID = "FF4E8EF9"


@pytest.fixture()
def policy(database, monkeypatch):
    policy = policy_with_db(database)
    monkeypatch.setattr(app_module.nfc_service, "policy", policy)
    monkeypatch.setattr(app_module, "card_policy", policy)
    return policy


def kiosk_state():
    return app_module.kiosk.state_dict()


def tap(uid, card):
    app_module.kiosk._to_idle()
    app_module.nfc_reader.simulate_scan(uid, card)
    return kiosk_state()


def row(uid=UID):
    return NFCCardProfile.query.filter_by(uid=uid).first()


def phone_register(client, uid=PHONE_UID, **form):
    res = client.post("/api/admin/nfc/phone-capture", json={"uid": uid})
    assert res.status_code == 200, res.get_json()
    return client.post(
        "/api/register", data=dict(FORM, nfc_token=res.get_json()["token"], **form)
    )


def test_phone_capture_admin_only_validated_and_pending(client, database, policy):
    url = "/api/admin/nfc/phone-capture"
    assert client.post(url, json={"uid": PHONE_UID}).status_code == 401
    admin_session(client)
    for bad in ("ff:4e:8e", "zz:4e:8e:f9", 12345678, None):
        assert client.post(url, json={"uid": bad}).status_code == 400
    assert phone_register(client).status_code == 200
    assert database.get_student_by_nfc(UID)
    assert row().source == "admin_phone" and row().completed_at is None
    again = client.post(url, json={"uid": PHONE_UID})
    assert (
        again.status_code == 409 and again.get_json()["error"] == "KTM sudah terdaftar"
    )
    # The phone token never occupies the kiosk reader.
    assert app_module.nfc_service.capture is None


def test_phone_token_binds_an_existing_student(client, database, policy):
    student = database.create_student(dict(FORM, rfid_uid=None))
    admin_session(client)
    token = client.post(
        "/api/admin/nfc/phone-capture", json={"uid": PHONE_UID}
    ).get_json()["token"]
    url = "/api/admin/students/" + student["student_id"] + "/nfc"
    assert client.post(url, json={"nfc_token": token}).status_code == 200
    assert row().completed_at is None


def test_admin_reader_accepts_non_ktm_and_stores_complete_profile(
    client, database, policy
):
    admin_session(client)
    token = client.post("/api/admin/cards/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan(UID, EMONEY)
    res = client.post("/api/register", data=dict(FORM, nfc_token=token))
    assert res.status_code == 200
    assert row().source == "admin_reader" and row().completed_at is not None
    assert (row().atqa, row().sak, row().ats) == (
        EMONEY["atqa"],
        EMONEY["sak"],
        EMONEY["ats"],
    )
    assert tap(UID, EMONEY)["state"] == "session"


def test_self_registration_still_refuses_non_ktm(client, database, policy):
    admin_session(client)  # a lingering admin session does not relax /register
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan(UID, EMONEY)
    assert not client.get("/api/nfc/registration").get_json()["ready"]
    assert (
        client.post("/api/register", data=dict(FORM, nfc_token=token)).status_code
        == 409
    )
    app_module.nfc_reader.simulate_scan(UID, KTM)
    assert (
        client.post("/api/register", data=dict(FORM, nfc_token=token)).status_code
        == 200
    )
    assert row().source == "kiosk" and row().completed_at is not None


def test_pending_card_opens_with_any_chip_then_locks(client, database, policy, caplog):
    admin_session(client)
    phone_register(client)
    assert tap(UID, EMONEY)["state"] == "session"
    assert row().completed_at is not None and row().ats == EMONEY["ats"]
    with caplog.at_level("WARNING"):
        state = tap(UID, KTM)  # same UID, other chip: a clone
    assert state["state"] == "unknown_card" and state["reason"] == "card_mismatch"
    assert UID not in caplog.text and "...8EF9" in caplog.text
    assert tap(UID, dict(EMONEY, ats=""))["state"] == "unknown_card"
    assert tap(UID, EMONEY)["state"] == "session"


def test_card_without_ats_compares_what_was_stored(client, database, policy):
    no_ats = dict(EMONEY, ats="")
    admin_session(client)
    phone_register(client)
    assert tap(UID, no_ats)["state"] == "session"
    assert row().ats == ""
    assert tap(UID, no_ats)["state"] == "session"
    assert tap(UID, EMONEY)["reason"] == "card_mismatch"


def test_legacy_card_keeps_todays_policy_then_learns(client, database, policy):
    student = database.create_student(dict(FORM, rfid_uid=None))
    database.bind_student_nfc(student["student_id"], UID)
    assert row() is None
    state = tap(UID, EMONEY)
    assert state["state"] == "unknown_card" and state["reason"] is None
    assert row() is None
    assert tap(UID, KTM)["state"] == "session"
    assert row().source == "legacy" and row().completed_at is not None
    assert tap(UID, dict(KTM, sak=0x20))["reason"] == "card_mismatch"


def test_reset_profile_admin_only_and_relearns(client, database, policy):
    admin_session(client)
    phone_register(client)
    tap(UID, EMONEY)
    student = database.get_student_by_nfc(UID)
    url = "/api/admin/students/" + student["student_id"] + "/nfc/reset"
    listed = client.get("/api/admin/students").get_json()["students"][0]
    assert listed["nfc_profile_complete"] is True
    other = app_module.app.test_client()
    assert other.post(url).status_code == 401
    assert row().completed_at is not None
    assert client.post(url).status_code == 200
    assert row().completed_at is None and row().ats is None
    listed = client.get("/api/admin/students").get_json()["students"][0]
    assert listed["has_nfc"] and listed["nfc_profile_complete"] is False
    assert tap(UID, KTM)["state"] == "session"
    assert row().ats == KTM["ats"]
    assert client.post("/api/admin/students/999/nfc/reset").status_code == 404


def test_soft_delete_drops_the_profile(client, database, policy):
    admin_session(client)
    phone_register(client)
    student = database.get_student_by_nfc(UID)
    assert database.delete_student(student["student_id"]) == "ok"
    assert row() is None

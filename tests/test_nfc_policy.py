from __future__ import annotations

import app as app_module
from utils.nfc_policy import MSG_BROKEN, MSG_NOT_KTM, CardPolicy

KTM = {"atqa": "0004", "sak": 0x28, "ats": "0D78007003990200D103042201"}
KTM_B = {"atqa": "0004", "sak": 0x28, "ats": "0D7800A10257694C4C20230307"}
EMONEY = {"atqa": "0004", "sak": 0x28, "ats": "0C788071024D49464152452B"}
SPECIAL_UID = "04A1B2C3"
SPECIAL_NIM = "13323018"
FORM = dict(
    name="Sintetis", nim="87654321", email="test@example.com", phone="08123456789"
)


def make_policy():
    base = CardPolicy(pepper="test-pepper")
    return CardPolicy(
        pepper="test-pepper",
        special_uid_hmac=base.digest("uid", SPECIAL_UID),
        special_nim_hmac=base.digest("nim", SPECIAL_NIM),
    )


def test_ats_not_just_sak_identifies_a_ktm():
    policy = make_policy()
    assert policy.check_tap({"uid": "01020304", "card": KTM}) is None
    assert policy.check_tap({"uid": "01020304", "card": KTM_B}) is None
    assert policy.check_tap({"uid": "01020304", "card": EMONEY}) == MSG_NOT_KTM
    assert (
        policy.check_tap({"uid": "01020304", "card": dict(KTM, ats="")}) == MSG_NOT_KTM
    )
    assert policy.check_tap({"uid": "01020304", "card": None}) is None  # mock tap


def test_special_card_is_limited_to_one_nim_and_digests_hide_both():
    policy = make_policy()
    event = {"uid": SPECIAL_UID, "card": EMONEY}
    assert policy.check_tap(event) is None
    assert policy.check_student(SPECIAL_UID, SPECIAL_NIM) is None
    assert policy.check_student(SPECIAL_UID, "13323019") == MSG_BROKEN
    assert policy.check_student("01020304", "13323019") is None
    assert not CardPolicy(pepper="other").is_special(SPECIAL_UID)
    assert SPECIAL_UID not in policy._uid_hmac and SPECIAL_NIM not in policy._nim_hmac


def test_policy_disabled_or_unconfigured_never_exempts_anything():
    assert CardPolicy(enforce=False).check_tap({"uid": "01", "card": EMONEY}) is None
    assert not CardPolicy().is_special(SPECIAL_UID)


def test_registration_refuses_non_ktm_then_accepts_ktm(client, monkeypatch):
    monkeypatch.setattr(app_module.nfc_service, "policy", make_policy())
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan("01020304", EMONEY)
    state = client.get("/api/nfc/registration").get_json()
    assert not state["ready"] and state["rejected"] == MSG_NOT_KTM
    app_module.nfc_reader.simulate_scan("05060708", KTM)
    state = client.get("/api/nfc/registration").get_json()
    assert state["ready"] and state["rejected"] is None
    assert (
        client.post("/api/register", data=dict(FORM, nfc_token=token)).status_code
        == 200
    )


def test_special_card_registers_only_for_its_nim(client, database, monkeypatch):
    monkeypatch.setattr(app_module.nfc_service, "policy", make_policy())
    monkeypatch.setattr(app_module, "card_policy", make_policy())
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan(SPECIAL_UID, EMONEY)
    wrong = client.post("/api/register", data=dict(FORM, nfc_token=token))
    assert wrong.status_code == 409 and wrong.get_json()["error"] == MSG_BROKEN
    assert database.get_student_by_nfc(SPECIAL_UID) is None
    right = client.post(
        "/api/register", data=dict(FORM, nim=SPECIAL_NIM, nfc_token=token)
    )
    assert right.status_code == 200
    assert database.get_student_by_nfc(SPECIAL_UID)


def test_kiosk_refuses_non_ktm_tap(monkeypatch):
    monkeypatch.setattr(app_module.nfc_service, "policy", make_policy())
    app_module.nfc_reader.simulate_scan("01020304", EMONEY)
    assert app_module.kiosk.state_dict()["state"] == "unknown_card"


def test_refusal_is_logged_without_the_uid(monkeypatch, caplog):
    monkeypatch.setattr(app_module.nfc_service, "policy", make_policy())
    with caplog.at_level("INFO"):
        app_module.nfc_reader.simulate_scan("0A0B0C0D", EMONEY)
    assert "ATS=0C788071024D49464152452B" in caplog.text
    assert "0A0B0C0D" not in caplog.text


def admin_session(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_until"] = 9999999999


def policy_with_db(database):
    policy = make_policy()
    policy.lookup = database.get_card_exception
    return policy


def add_card(client, kind, nim=""):
    token = client.post("/api/admin/cards/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan("0A0B0C0D", EMONEY)
    return client.post(
        "/api/admin/cards", json={"nfc_token": token, "kind": kind, "nim": nim}
    )


def test_admin_ktm_exception_lets_a_rejected_ktm_register(
    client, database, monkeypatch
):
    policy = policy_with_db(database)
    monkeypatch.setattr(app_module.nfc_service, "policy", policy)
    monkeypatch.setattr(app_module, "card_policy", policy)
    admin_session(client)
    assert policy.check_tap({"uid": "0A0B0C0D", "card": EMONEY}) == MSG_NOT_KTM
    assert add_card(client, "ktm").status_code == 200
    assert policy.check_tap({"uid": "0A0B0C0D", "card": EMONEY}) is None
    assert policy.check_student("0A0B0C0D", "87654321") is None  # any NIM
    assert "0A0B0C0D" not in str(database.list_card_exceptions())


def test_admin_other_card_works_for_one_nim_only(client, database, monkeypatch):
    policy = policy_with_db(database)
    monkeypatch.setattr(app_module.nfc_service, "policy", policy)
    monkeypatch.setattr(app_module, "card_policy", policy)
    admin_session(client)
    assert add_card(client, "other").status_code == 400  # NIM required
    assert add_card(client, "other", "87654321").status_code == 200
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan("0A0B0C0D", EMONEY)
    wrong = client.post(
        "/api/register", data=dict(FORM, nim="87654322", nfc_token=token)
    )
    assert wrong.status_code == 409 and wrong.get_json()["error"] == MSG_BROKEN
    right = client.post("/api/register", data=dict(FORM, nfc_token=token))
    assert right.status_code == 200


def test_register_nim_check(client, student):
    assert client.get("/api/register/nim?nim=12345678").get_json()["taken"] is True
    assert client.get("/api/register/nim?nim=99999999").get_json()["taken"] is False


def test_session_entries_carry_a_wib_time(client, student, tool, database):
    app_module.kiosk.start_session(student)
    from utils.kiosk import _entry

    entry = _entry(
        {"transaction_id": 1, "tool_id": 1, "tool_name": "x", "due_at": None}
    )
    assert len(entry["at"]) >= 16 and "Z" not in entry["at"]

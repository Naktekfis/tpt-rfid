import random
from datetime import datetime, timedelta

import pytest

import app as app_module
from tests.conftest import TEST_PIN
from utils import AlarmEvent, Tool, Transaction, db
from utils.kiosk import Kiosk
from utils.presence import PresenceMonitor
from utils.tool_presence import ToolPresenceService


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeReader:
    def __init__(self):
        self.beeps = 0

    def add_round_listener(self, cb):
        pass

    def beep(self, *a):
        self.beeps += 1


class FakeFaces:
    """Frames are dicts: who (student dict | "unknown" | None), yaw, face (bool)."""

    def identify_frame(self, frame):
        who = frame.get("who")
        if who is None:
            return {"status": "no_face"}
        if who == "unknown":
            return {"status": "unknown"}
        return {"status": "ok", "student": who}

    def landmarks(self, frame):
        if not frame.get("face", True):
            return None
        return [(0, 0), (10, 0), (5 + 10 * frame.get("yaw", 0.0), 5), (0, 9), (10, 9)]


def make_student(database, n):
    return database.create_student(
        {
            "name": f"S{n}",
            "nim": f"2000000{n}",
            "email": f"s{n}@example.com",
            "phone": "0800000000",
        }
    )


def make_tool(database, uid, status="available"):
    return database.create_tool(
        {"name": uid, "rfid_uid": uid, "category": "x", "status": status}
    )


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def kiosk(app, database, clock):
    return Kiosk(app, database, FakeFaces(), clock=clock, rng=random.Random(1))


@pytest.fixture()
def env(app, database, kiosk, clock):
    reader = FakeReader()
    service = ToolPresenceService(
        app, database, reader, PresenceMonitor(5.0, clock=clock), True,
        clock=clock, kiosk=kiosk,
    )
    return service, reader


@pytest.fixture()
def alice(database):
    return make_student(database, 1)


@pytest.fixture()
def bob(database):
    return make_student(database, 2)


def feed(kiosk, clock, frame, n=1, dt=0.4):
    for _ in range(n):
        clock.t += dt
        kiosk.on_frame(frame)


def run_challenges(kiosk, clock, who):
    """Pass both head turns for `who`."""
    while kiosk.state_dict()["state"] == "identifying":
        direction = kiosk.state_dict()["direction"]
        yaw = -0.5 if direction == "left" else 0.5
        feed(kiosk, clock, {"who": who, "yaw": 0.0}, 2, dt=0.1)
        feed(kiosk, clock, {"who": who, "yaw": yaw}, 1, dt=0.1)


def start_session(kiosk, clock, who):
    feed(kiosk, clock, {"who": who})
    assert kiosk.state_dict()["state"] == "identifying"
    run_challenges(kiosk, clock, who)
    assert kiosk.state_dict()["state"] == "session"


def leave_and_return_setup(service, clock, uid, status="available"):
    t = make_tool(service.database, uid, status)
    service.on_round([uid])
    clock.t += 6
    return t


def tool_left(service, clock, uids_present=()):
    clock.t += 6
    service.on_round(list(uids_present))


def tool_back(service, clock, uid):
    clock.t += 1
    service.on_round([uid])


# ---- identification ----


def test_identify_and_both_turns_start_session(kiosk, clock, alice):
    assert kiosk.state_dict()["state"] == "idle"
    feed(kiosk, clock, {"who": alice})
    st = kiosk.state_dict()
    assert st["state"] == "identifying" and st["step"] == 1 and st["steps"] == 2
    first = st["direction"]
    feed(kiosk, clock, {"who": alice, "yaw": 0.0}, 2, dt=0.1)
    # wrong direction does not pass
    feed(kiosk, clock, {"who": alice, "yaw": 0.5 if first == "left" else -0.5}, 1, dt=0.1)
    assert kiosk.state_dict()["step"] == 1
    feed(kiosk, clock, {"who": alice, "yaw": -0.5 if first == "left" else 0.5}, 1, dt=0.1)
    st = kiosk.state_dict()
    assert st["state"] == "identifying" and st["step"] == 2
    assert st["direction"] != first  # both directions, once each
    run_challenges(kiosk, clock, alice)
    st = kiosk.state_dict()
    assert st["state"] == "session"
    assert st["student"]["student_id"] == alice["student_id"]
    assert 59.0 <= st["expires_in"] <= 60.0


def test_challenge_timeout_returns_to_idle(kiosk, clock, alice):
    feed(kiosk, clock, {"who": alice})
    # keep the face visible and frontal but never turn
    feed(kiosk, clock, {"who": alice, "yaw": 0.0}, 21, dt=0.4)
    st = kiosk.state_dict()
    assert st["state"] == "idle" and st["reason"] == "challenge_timeout"
    # a short pause before the next attempt, then it starts again
    feed(kiosk, clock, {"who": alice}, 1, dt=0.4)
    assert kiosk.state_dict()["state"] == "idle"
    feed(kiosk, clock, {"who": alice}, 1, dt=2.0)
    assert kiosk.state_dict()["state"] == "identifying"


def test_different_face_mid_challenge_aborts(kiosk, clock, alice, bob):
    feed(kiosk, clock, {"who": alice})
    feed(kiosk, clock, {"who": bob, "yaw": 0.0}, 1, dt=1.1)
    assert kiosk.state_dict()["state"] == "identifying"  # one mismatch only
    feed(kiosk, clock, {"who": bob, "yaw": 0.0}, 1, dt=1.1)
    st = kiosk.state_dict()
    assert st["state"] == "idle" and st["reason"] == "different_face"


def test_face_lost_aborts(kiosk, clock, alice):
    feed(kiosk, clock, {"who": alice})
    feed(kiosk, clock, {"who": None, "face": False}, 1, dt=3.5)
    assert kiosk.state_dict()["reason"] == "face_lost"


def test_unknown_face_then_idle(kiosk, clock):
    feed(kiosk, clock, {"who": "unknown"})
    assert kiosk.state_dict()["state"] == "unknown_face"
    clock.t += 4
    assert kiosk.state_dict()["state"] == "unknown_face"
    clock.t += 1.5
    assert kiosk.state_dict()["state"] == "idle"


# ---- session: tool events ----


def test_session_borrow_on_left(env, kiosk, clock, alice, database):
    service, reader = env
    t = leave_and_return_setup(service, clock, "T1")
    start_session(kiosk, clock, alice)
    tool_left(service, clock)
    row = db.session.get(Tool, int(t["tool_id"]))
    assert row.status == "borrowed" and row.presence == "missing"
    assert service.open_alarms() == [] and reader.beeps == 0
    txn = Transaction.query.one()
    assert txn.student_id == int(alice["student_id"])
    assert txn.due_at - txn.borrow_time == timedelta(days=2)
    st = kiosk.state_dict()
    assert [b["tool_id"] for b in st["borrowed"]] == [t["tool_id"]]
    assert st["can_cancel"] is False


def test_session_return_own_and_others(env, kiosk, clock, alice, bob, database):
    service, _ = env
    mine = make_tool(database, "T1")
    theirs = make_tool(database, "T2")
    service.on_round(["T1", "T2"])
    database.borrow_tool_atomic(alice["student_id"], mine["tool_id"])
    database.borrow_tool_atomic(bob["student_id"], theirs["tool_id"])
    clock.t += 6
    service.on_round([])  # both leave: borrowed, no alarm
    start_session(kiosk, clock, alice)
    tool_back(service, clock, "T1")
    tool_back(service, clock, "T2")
    rows = {t.tool_name: t for t in Transaction.query.all()}
    assert rows["T1"].status == "returned" and rows["T1"].returned_by_id == int(alice["student_id"])
    assert rows["T2"].status == "returned" and rows["T2"].returned_by_id == int(alice["student_id"])
    assert rows["T2"].student_id == int(bob["student_id"])
    assert rows["T2"].return_verified is True
    assert Tool.query.filter_by(status="available").count() == 2
    ret = kiosk.state_dict()["returned"]
    assert [r["own"] for r in ret] == [True, False]


def test_extension_and_cap(env, kiosk, clock, alice, database):
    service, _ = env
    for uid in ("T1", "T2", "T3", "T4"):
        make_tool(database, uid)
    service.on_round(["T1", "T2", "T3", "T4"])
    clock.t += 6
    start_session(kiosk, clock, alice)
    left0 = kiosk.state_dict()["expires_in"]
    service.on_round(["T2", "T3", "T4"])  # T1 left at once (monotonic clock unchanged)
    assert kiosk.state_dict()["expires_in"] == pytest.approx(left0 + 30, abs=0.2)
    # events in quick succession: capped at 120 s from now
    clock.t += 6
    service.on_round(["T3", "T4"])
    clock.t += 6
    service.on_round(["T4"])
    clock.t += 6
    service.on_round([])
    assert kiosk.state_dict()["expires_in"] <= 120.0


def test_timeout_summary_idle(env, kiosk, clock, alice):
    service, _ = env
    start_session(kiosk, clock, alice)
    clock.t += 61
    st = kiosk.state_dict()
    assert st["state"] == "summary" and st["borrowed"] == []
    clock.t += 7
    assert kiosk.state_dict()["state"] == "summary"
    clock.t += 2
    assert kiosk.state_dict()["state"] == "idle"


def test_end_goes_to_summary(kiosk, clock, alice):
    assert kiosk.end() is False
    start_session(kiosk, clock, alice)
    assert kiosk.end() is True
    assert kiosk.state_dict()["state"] == "summary"


def test_cancel_before_and_after_tool_events(env, kiosk, clock, alice, database):
    service, _ = env
    assert kiosk.cancel() == "no_session"
    make_tool(database, "T1")
    service.on_round(["T1"])
    clock.t += 6
    start_session(kiosk, clock, alice)
    assert kiosk.state_dict()["can_cancel"] is True
    assert kiosk.cancel() == "ok"
    assert kiosk.state_dict()["state"] == "idle"
    start_session(kiosk, clock, alice)
    service.on_round([])
    assert kiosk.cancel() == "conflict"
    assert kiosk.state_dict()["state"] == "session"


# ---- no session ----


def test_no_session_left_raises_alarm(env, kiosk, clock, database):
    service, reader = env
    leave_and_return_setup(service, clock, "T1")
    tool_left(service, clock)
    assert len(service.open_alarms()) == 1 and reader.beeps == 1


def test_no_session_back_of_borrowed_is_unverified_return(env, clock, alice, database):
    service, reader = env
    t = make_tool(database, "T1")
    service.on_round(["T1"])
    database.borrow_tool_atomic(alice["student_id"], t["tool_id"])
    clock.t += 6
    service.on_round([])
    tool_back(service, clock, "T1")
    txn = Transaction.query.one()
    assert txn.status == "returned" and txn.return_verified is False
    assert txn.returned_by_id is None
    assert db.session.get(Tool, int(t["tool_id"])).status == "available"
    assert service.open_alarms() == [] and reader.beeps == 0
    assert [u["tool_id"] for u in database.get_unverified_returns()] == [t["tool_id"]]


def test_session_start_verifies_own_unverified_returns(env, kiosk, clock, alice, bob, database):
    service, _ = env
    a = make_tool(database, "T1")
    b = make_tool(database, "T2")
    service.on_round(["T1", "T2"])
    database.borrow_tool_atomic(alice["student_id"], a["tool_id"])
    database.borrow_tool_atomic(bob["student_id"], b["tool_id"])
    clock.t += 6
    service.on_round([])
    clock.t += 1
    service.on_round(["T1", "T2"])
    assert len(database.get_unverified_returns()) == 2
    start_session(kiosk, clock, alice)
    left = database.get_unverified_returns()
    assert [u["tool_id"] for u in left] == [b["tool_id"]]
    own = Transaction.query.filter_by(tool_id=int(a["tool_id"])).one()
    assert own.return_verified is True and own.returned_by_id == int(alice["student_id"])


# ---- alarm grace ----


def test_grace_conversion(env, kiosk, clock, alice, database):
    service, reader = env
    fresh = make_tool(database, "T1")
    old = make_tool(database, "T2")
    service.on_round(["T1", "T2"])
    clock.t += 6
    service.on_round([])
    assert len(service.open_alarms()) == 2
    old_alarm = AlarmEvent.query.filter_by(tool_id=int(old["tool_id"])).one()
    old_alarm.started_at = datetime.utcnow() - timedelta(seconds=40)
    fresh_alarm = AlarmEvent.query.filter_by(tool_id=int(fresh["tool_id"])).one()
    fresh_alarm.started_at = datetime.utcnow() - timedelta(seconds=20)
    db.session.commit()
    start_session(kiosk, clock, alice)
    f = db.session.get(Tool, int(fresh["tool_id"]))
    o = db.session.get(Tool, int(old["tool_id"]))
    assert f.status == "borrowed" and o.status == "available"
    db.session.refresh(fresh_alarm)
    assert fresh_alarm.ended_by == "late_identify"
    assert fresh_alarm.student_id == int(alice["student_id"])
    open_ = service.open_alarms()
    assert [a["tool_id"] for a in open_] == [old["tool_id"]]
    assert Transaction.query.one().student_id == int(alice["student_id"])
    st = kiosk.state_dict()
    assert st["borrowed"][0]["late_identify"] is True and st["can_cancel"] is False


# ---- overdue ----


def test_overdue_from_due_at(database, alice):
    t = make_tool(database, "T1")
    database.borrow_tool_atomic(alice["student_id"], t["tool_id"])
    txn = Transaction.query.one()
    assert txn.to_dict()["is_overdue"] is False
    txn.due_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert txn.to_dict()["is_overdue"] is True
    # old row without due_at: borrow_time + LOAN_DAYS
    txn.due_at = None
    txn.borrow_time = datetime.utcnow() - timedelta(days=2, hours=1)
    db.session.commit()
    d = txn.to_dict()
    assert d["is_overdue"] is True and d["due_at"] is not None
    txn.borrow_time = datetime.utcnow() - timedelta(days=1)
    db.session.commit()
    assert txn.to_dict()["is_overdue"] is False
    board = database.get_board()
    assert board[0]["units"][0]["is_overdue"] is False


# ---- routes ----


@pytest.fixture()
def app_kiosk(app, clock, monkeypatch):
    monkeypatch.setattr(app_module.kiosk, "_clock", clock)
    app_module.kiosk._reset_all()
    yield app_module.kiosk
    app_module.kiosk._reset_all()


def test_state_shape(client, app_kiosk, database):
    make_tool(database, "T1")
    data = client.get("/api/kiosk/state").get_json()
    assert data["success"] is True and data["state"] == "idle"
    assert set(data) >= {"board", "alarms", "unverified_returns", "student", "reason"}
    unit = data["board"][0]["units"][0]
    assert set(unit) >= {
        "tool_id", "unit_no", "presence", "status",
        "borrower_name", "borrower_nim", "due_at", "is_overdue",
    }
    assert data["board"][0]["type_name"]


def test_debug_identify_end_cancel(client, app_kiosk, alice):
    assert client.get("/debug/kiosk/identify?student_id=999").status_code == 404
    res = client.get(f"/debug/kiosk/identify?student_id={alice['student_id']}")
    assert res.get_json()["success"] is True
    assert client.get(f"/debug/kiosk/identify?student_id={alice['student_id']}").status_code == 409
    data = client.get("/api/kiosk/state").get_json()
    assert data["state"] == "session" and data["student"]["name"] == "S1"
    assert "photo_data" not in data["student"]
    assert client.post("/api/kiosk/end").status_code == 200
    assert client.get("/api/kiosk/state").get_json()["state"] == "summary"
    assert client.post("/api/kiosk/end").status_code == 409
    client.get(f"/debug/kiosk/identify?student_id={alice['student_id']}")
    assert client.post("/api/kiosk/cancel").status_code == 200
    assert client.post("/api/kiosk/cancel").status_code == 409


def test_cancel_conflict_after_tool_event(client, app_kiosk, alice, database):
    app_kiosk.start_session(alice)
    t = make_tool(database, "T1")
    assert app_kiosk.on_tool_left({"id": int(t["tool_id"]), "status": "available"})
    assert client.post("/api/kiosk/cancel").status_code == 409


def test_verify_return_requires_admin(client, database, alice):
    t = make_tool(database, "T1")
    database.borrow_tool_atomic(alice["student_id"], t["tool_id"])
    database.close_borrow(int(t["tool_id"]), None, False)
    txn = Transaction.query.one()
    url = f"/api/admin/transactions/{txn.id}/verify_return"
    assert client.post(url, headers={"Accept": "application/json"}).status_code == 401
    assert Transaction.query.one().return_verified is False
    assert client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200
    assert client.post(url).get_json() == {"success": True}
    assert Transaction.query.one().return_verified is True
    assert client.post(url).status_code == 404

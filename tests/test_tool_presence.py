import pytest

import app as app_module
from utils import Tool, db
from utils.presence import PresenceMonitor
from utils.tool_presence import ToolPresenceService


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeReader:
    def __init__(self):
        self.listeners = []
        self.beeps = 0

    def add_round_listener(self, cb):
        self.listeners.append(cb)

    def beep(self, *a):
        self.beeps += 1


@pytest.fixture()
def env(app, database):
    clock = Clock()
    reader = FakeReader()
    service = ToolPresenceService(
        app, database, reader, PresenceMonitor(5.0, clock=clock), True, clock=clock
    )
    return service, reader, clock


def make_tool(database, uid, status="available"):
    return database.create_tool(
        {"name": uid, "rfid_uid": uid, "category": "x", "status": status}
    )


def test_unborrowed_tool_leaving_raises_alarm_and_beep(env, database):
    service, reader, clock = env
    t = make_tool(database, "T1")
    service.on_round(["T1"])
    assert db.session.get(Tool, int(t["tool_id"])).presence == "present"
    clock.t = 6
    service.on_round([])
    assert db.session.get(Tool, int(t["tool_id"])).presence == "missing"
    alarms = service.open_alarms()
    assert len(alarms) == 1 and alarms[0]["tool_id"] == t["tool_id"]
    assert reader.beeps == 1
    clock.t = 8
    service.on_round([])
    assert reader.beeps == 1 and len(service.open_alarms()) == 1


def test_back_closes_alarm(env, database):
    service, _, clock = env
    make_tool(database, "T1")
    service.on_round(["T1"])
    clock.t = 6
    service.on_round([])
    clock.t = 7
    service.on_round(["T1"])
    assert service.open_alarms() == []
    assert Tool.query.filter_by(rfid_uid="T1").one().presence == "present"


def test_borrowed_tool_leaving_is_no_alarm(env, database):
    service, reader, clock = env
    make_tool(database, "T1", status="borrowed")
    service.on_round(["T1"])
    clock.t = 6
    service.on_round([])
    assert service.open_alarms() == []
    assert reader.beeps == 0
    assert Tool.query.filter_by(rfid_uid="T1").one().presence == "missing"


def test_unknown_epcs_tracked_until_gone(env):
    service, _, clock = env
    service.on_round(["X1"])
    assert service.unknown_epcs() == ["X1"]
    clock.t = 6
    service.on_round([])
    assert service.unknown_epcs() == []


def test_acknowledge(env, database):
    service, _, clock = env
    make_tool(database, "T1")
    service.on_round(["T1"])
    clock.t = 6
    service.on_round([])
    alarm_id = int(service.open_alarms()[0]["alarm_id"])
    assert service.acknowledge(alarm_id) is True
    assert service.acknowledge(alarm_id) is False
    assert service.open_alarms() == []


def test_last_seen_write_is_throttled(env, database, monkeypatch):
    service, _, clock = env
    make_tool(database, "T1")
    writes = []
    orig = database.set_tool_presence
    monkeypatch.setattr(
        database, "set_tool_presence", lambda *a, **k: (writes.append(a), orig(*a, **k))
    )
    service.on_round(["T1"])
    for t in (1, 2, 5, 9):
        clock.t = t
        service.on_round(["T1"])
    assert len(writes) == 1
    clock.t = 11
    service.on_round(["T1"])
    assert len(writes) == 2


def test_presence_api(client, database):
    make_tool(database, "T9")
    data = client.get("/api/presence").get_json()
    assert data["success"] is True
    assert data["tools"][0]["presence"] == "unknown"
    assert data["alarms"] == [] and "unknown_epcs" in data


def test_ack_requires_admin(client, database):
    tool = make_tool(database, "T9")
    alarm = database.create_alarm(int(tool["tool_id"]))
    url = f"/api/alarms/{alarm['alarm_id']}/ack"
    assert client.post(url).status_code == 401
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    assert client.post(url).get_json() == {"success": True}
    assert client.post(url).status_code == 404


def test_borrow_sets_due_at_two_days(database, student, tool):
    result = database.borrow_tool_atomic(student["student_id"], tool["tool_id"])
    assert result["due_at"] is not None
    delta = result["due_at"] - result["borrow_time"]
    assert delta.days == 2


def test_student_without_card(database):
    s = database.create_student(
        {"name": "A", "nim": "1", "email": "a@b.c", "phone": "0"}
    )
    assert s["rfid_uid"] is None
    assert app_module.database is database


def test_borrowed_tool_seen_at_boot_is_unverified_return(env, database, student):
    service, _, _ = env
    t = make_tool(database, "T1")
    database.borrow_tool_atomic(student["student_id"], t["tool_id"])
    service.on_round(["T1"])  # first sighting since start ("new")
    assert Tool.query.filter_by(rfid_uid="T1").one().status == "available"
    unverified = database.get_unverified_returns()
    assert len(unverified) == 1 and unverified[0]["tool_id"] == t["tool_id"]

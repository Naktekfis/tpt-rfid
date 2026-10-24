"""Admin face login and enrolment with a fake engine, liveness and camera."""

from collections import deque

import pytest

import app as app_module
from tests.conftest import TEST_PIN
from utils.admin_face import Attempt, FaceSettings, pack
from utils.face import Face
from utils.models import AdminFace, AdminLoginEvent, db

VECS = {"A": [1.0, 0.0], "B": [0.0, 1.0], "C": [-1.0, 0.0]}
REMOTE = {"REMOTE_ADDR": "10.42.0.1"}


class FakeEngine:
    name = "fake"
    threshold = 0.5

    def detect(self, frame):
        return [
            Face((0, 0, 200, 200), [(0, 0), (10, 0), (5 + 10 * y, 5)], 0.9, who)
            for who, y in frame["faces"]
        ]

    def embed(self, frame, face):
        return VECS[face.raw]

    def distance(self, a, b):
        return 1.0 - sum(x * y for x, y in zip(a, b))


class FakeLiveness:
    def check(self, frame, face):
        return frame["live"] >= 0.7, {"fake": frame["live"]}


class FakeCamera:
    def __init__(self):
        self.frames = deque()

    def read(self):
        return self.frames.popleft() if self.frames else None


def front(who="A", live=0.95):
    return {"faces": [(who, 0.0)], "live": live}


def good(who="A", after=None, live=0.95):
    return [front(who, live)] * 3 + [front(after or who, live)] * 3


@pytest.fixture()
def face(app, monkeypatch):
    fa = app_module.face_auth
    for key, value in {
        "engine": FakeEngine(),
        "liveness": FakeLiveness(),
        "unavailable": None,
        "camera": FakeCamera(),
        "settings": FaceSettings(enrol_prepare=0, enrol_countdown=0),
        "_threaded": False,
        "_photo": lambda frame, f: b"jpeg",
        "_attempts": {},
        "_running": None,
        "_failures": deque(),
        "_locked_until": 0.0,
    }.items():
        monkeypatch.setattr(fa, key, value)
    return fa


def enrol(name, who):
    db.session.add(AdminFace(name=name, engine="fake", vector=pack(VECS[who])))
    db.session.commit()


def login(client, face, frames, **kw):
    face.camera.frames.extend(frames)
    started = client.post("/api/admin/face/login/start", **kw)
    if started.status_code != 200:
        return started, None
    return started, client.get("/api/admin/face/attempt").get_json()


def is_admin(client):
    return client.get("/admin", headers={"Accept": "text/html"}).status_code == 200


def test_face_login_is_off_by_default(client):
    status = client.get("/api/admin/face/status").get_json()
    assert status["available"] is False
    assert client.post("/api/admin/face/login/start").status_code == 503


def test_login_passes_and_gives_only_this_browser_a_session(app, client, face):
    enrol("Ahmad", "A")
    _, result = login(client, face, good())
    assert result["state"] == "passed" and result["name"] == "Ahmad"
    assert is_admin(client)
    other = app.test_client()
    assert other.get("/api/admin/face/attempt").status_code == 404
    assert not is_admin(other)
    event = AdminLoginEvent.query.one()
    assert (event.method, event.success, event.admin_name, event.photo) == (
        "face",
        True,
        "Ahmad",
        b"jpeg",
    )


@pytest.mark.parametrize(
    "frames, reason",
    [
        (good(live=0.3), "spoof"),
        (good("B"), "unknown_face"),
        (good("A", after="B"), "unknown_face"),  # swapped partway
        ([front()] * 3, "camera"),  # walked away: no more frames
    ],
)
def test_failed_login_gives_no_session(client, face, frames, reason):
    enrol("Ahmad", "A")
    _, result = login(client, face, frames)
    assert (result["state"], result["reason"]) == ("failed", reason)
    assert not is_admin(client)
    event = AdminLoginEvent.query.one()
    assert (event.success, event.reason) == (False, reason)


def test_face_leaving_the_camera_fails(client, face):
    face.settings.face_lost_seconds = 0.0
    enrol("Ahmad", "A")
    _, result = login(client, face, [front(), {"faces": [], "live": 0.9}, front()])
    assert result["reason"] == "face_lost"


def test_remote_browser_cannot_start_face_login(client, face):
    enrol("Ahmad", "A")
    resp, _ = login(client, face, good(), environ_base=REMOTE)
    assert resp.status_code == 403
    status = client.get("/api/admin/face/status", environ_base=REMOTE).get_json()
    assert status["local"] is False


def test_repeated_failures_lock_face_login_but_not_the_pin(client, face):
    enrol("Ahmad", "A")
    for _ in range(face.settings.lockout_failures):
        login(client, face, good("B"))
    resp, _ = login(client, face, good())
    assert resp.status_code == 429
    assert resp.get_json()["locked_seconds"] > 0
    assert client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200


def test_enrol_stores_faces_and_refuses_a_face_of_another_admin(admin_client, face):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    face.camera.frames.extend(good())
    admin_client.post("/api/admin/faces/enroll/start", json={"name": " Ahmad "})
    assert admin_client.get("/api/admin/face/attempt").get_json()["state"] == "passed"
    faces = admin_client.get("/api/admin/faces").get_json()["faces"]
    assert [(f["name"], f["samples"]) for f in faces] == [("Ahmad", 6)]

    face.camera.frames.extend(good())
    admin_client.post("/api/admin/faces/enroll/start", json={"name": "Budi"})
    result = admin_client.get("/api/admin/face/attempt").get_json()
    assert result["reason"] == "other_admin"
    assert AdminFace.query.filter_by(name="Budi").count() == 0

    assert (
        admin_client.post("/api/admin/faces/delete", json={"name": "Ahmad"}).status_code
        == 200
    )
    assert AdminFace.query.count() == 0


def test_enrol_needs_admin_and_a_name(client, admin_client, face):
    resp = client.post("/api/admin/faces/enroll/start", json={"name": "X"})
    assert resp.status_code == 401
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    assert (
        admin_client.post(
            "/api/admin/faces/enroll/start", json={"name": " "}
        ).status_code
        == 400
    )


def test_pin_logins_are_logged(admin_client):
    admin_client.post("/api/admin/login", json={"pin": "000000"})
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    rows = [
        (e.method, e.success)
        for e in AdminLoginEvent.query.order_by(AdminLoginEvent.id)
    ]
    assert rows == [("pin", False), ("pin", True)]
    events = admin_client.get("/api/admin/login_events").get_json()["events"]
    assert [e["success"] for e in events] == [True, False]



def test_second_face_during_the_attempt_fails(client, face):
    enrol("Ahmad", "A")
    two = {"faces": [("A", 0.0), ("B", 0.0)], "live": 0.95}
    _, result = login(client, face, [front()] * 2 + [two] + good())
    assert result["reason"] == "multiple_faces"


def test_enrol_under_an_existing_name_needs_the_same_face(admin_client, face):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    enrol("Ahmad", "A")
    face.camera.frames.extend(good("B"))
    admin_client.post("/api/admin/faces/enroll/start", json={"name": "Ahmad"})
    assert admin_client.get("/api/admin/face/attempt").get_json()["reason"] == "name_taken"
    assert AdminFace.query.filter_by(name="Ahmad").count() == 1


def test_face_session_ends_at_its_deadline(client, face):
    enrol("Ahmad", "A")
    login(client, face, good())
    assert is_admin(client)
    with client.session_transaction() as s:
        assert s["admin_until"] > 0 and not s.permanent
        s["admin_until"] = 1.0
    assert not is_admin(client)


def test_two_doubtful_frames_are_tolerated_three_are_not(client, face):
    enrol("Ahmad", "A")
    _, result = login(client, face, [front("A", 0.2)] * 2 + [front()] * 4)
    assert result["state"] == "passed"
    client.get("/admin/logout")
    _, result = login(client, face, [front("A", 0.2)] * 3 + [front()] * 3)
    assert result["reason"] == "spoof"


def test_face_turned_away_is_not_counted(client, face):
    enrol("Ahmad", "A")
    away = {"faces": [("B", 0.8)], "live": 0.95}  # someone else, looking aside
    _, result = login(client, face, [away] * 3 + good())
    assert result["state"] == "passed"


def test_enrol_refuses_two_people(admin_client, face):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    face.camera.frames.extend(good("A", after="B"))
    admin_client.post("/api/admin/faces/enroll/start", json={"name": "Ahmad"})
    assert admin_client.get("/api/admin/face/attempt").get_json()["reason"] == "face_changed"


def test_attempt_asks_only_to_look_at_the_camera():
    a = Attempt(id="x", mode="login", started=0.0)
    assert a.instruction == "Lihat ke kamera"
    assert a.to_dict()["progress"] == 0.0


def test_liveness_spec_parsing():
    from utils.liveness import parse_spec

    assert parse_spec("mn3:0.8, minifas_se:0.6") == [("mn3", 0.8), ("minifas_se", 0.6)]
    assert parse_spec("minifas") == [("minifas", 0.5)]
    with pytest.raises(ValueError):
        parse_spec("nope:0.5")


def test_enrol_counts_down_with_beeps_before_capturing(admin_client, face, monkeypatch):
    now = [0.0]
    beeps = []

    class TickingCamera(FakeCamera):
        def read(self):
            now[0] += 0.5  # each frame is half a second later
            return super().read()

    monkeypatch.setattr(face, "camera", TickingCamera())
    monkeypatch.setattr(face, "_clock", lambda: now[0])
    monkeypatch.setattr(face, "_beep", lambda **p: beeps.append(p["active"]))
    face.settings.enrol_prepare, face.settings.enrol_countdown = 1.0, 3
    seen = []
    real_step = face.step
    monkeypatch.setattr(
        face, "step", lambda a, f: (real_step(a, f), seen.append(a.instruction))
    )
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    # 1 s to read + 3 s countdown = 8 frames ignored, then 6 captured.
    face.camera.frames.extend([{"faces": [], "live": 0.0}] * 7 + good())
    admin_client.post("/api/admin/faces/enroll/start", json={"name": "Ahmad"})
    assert admin_client.get("/api/admin/face/attempt").get_json()["state"] == "passed"
    assert seen[:7] == ["Lihat ke kamera", "3", "3", "2", "2", "1", "1"]
    assert beeps == [2, 2, 2, 6]  # three short counts, one long "cekrek"
    assert AdminFace.query.filter_by(name="Ahmad").count() == 6


def test_login_tolerates_one_unmatched_frame_but_not_another_admin(client, face):
    enrol("Ahmad", "A")
    stranger = {"faces": [("C", 0.0)], "live": 0.95}
    _, result = login(client, face, [front()] * 5 + [stranger])
    assert result["state"] == "passed"
    client.get("/admin/logout")
    enrol("Budi", "B")
    _, result = login(client, face, [front()] * 5 + [front("B")])
    assert result["reason"] == "unknown_face"

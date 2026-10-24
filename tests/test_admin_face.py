"""Admin face login and enrolment with a fake engine, liveness and camera."""

from collections import deque

import pytest

import app as app_module
from tests.conftest import TEST_PIN
from utils.admin_face import Attempt, FaceSettings, pack
from utils.face import Face
from utils.models import AdminFace, AdminLoginEvent, db

VECS = {"A": [1.0, 0.0], "B": [0.0, 1.0]}
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
    def score(self, frame, face):
        return frame["live"]


class FakeCamera:
    def __init__(self):
        self.frames = deque()

    def read(self):
        return self.frames.popleft() if self.frames else None


class FirstChoice:
    def choice(self, seq):
        return seq[0]  # "left": nose toward image left


def front(who="A", live=0.95):
    return {"faces": [(who, 0.0)], "live": live}


def turned(who="A", live=0.95):
    return {"faces": [(who, -0.4)], "live": live}


def good(who="A", after=None, live=0.95):
    return (
        [front(who, live)] * 3 + [turned(who, live)] + [front(after or who, live)] * 2
    )


@pytest.fixture()
def face(app, monkeypatch):
    fa = app_module.face_auth
    for key, value in {
        "engine": FakeEngine(),
        "liveness": FakeLiveness(),
        "unavailable": None,
        "camera": FakeCamera(),
        "settings": FaceSettings(),
        "_threaded": False,
        "_rng": FirstChoice(),
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
        (good("A", after="B"), "unknown_face"),  # swapped after the turn
        ([front()] * 6, "camera"),  # never turned the head
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
    for _ in range(3):
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
    assert [(f["name"], f["samples"]) for f in faces] == [("Ahmad", 5)]

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


def test_turn_prompt_is_in_the_persons_own_terms():
    a = Attempt(id="x", mode="login", direction="left", started=0.0, phase="turn")
    assert a.instruction == "Tolehkan kepala ke kanan Anda"
    a.direction = "right"
    assert a.instruction == "Tolehkan kepala ke kiri Anda"


def test_photo_on_frontal_frames_with_a_live_face_in_between_fails(client, face):
    # Review finding: photo for the key frames, own live face for many turn frames.
    enrol("Ahmad", "A")
    frames = [front("A", 0.1)] * 3 + [turned("B")] * 20 + [front("A", 0.1)] * 2
    _, result = login(client, face, frames)
    assert result["reason"] == "spoof"
    assert not is_admin(client)


def test_other_face_during_the_turn_fails_even_when_live(client, face):
    enrol("Ahmad", "A")
    frames = [front("A")] * 3 + [turned("B")] + [front("A")] * 2
    _, result = login(client, face, frames)
    assert result["reason"] == "face_changed"


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

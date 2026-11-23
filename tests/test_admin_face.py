"""Admin face login and enrolment with a fake engine, liveness and camera."""

import json
from collections import deque

import pytest

import app as app_module
from routes import admin_face_routes
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
        "_quality": lambda frame, f: tuple(frame.get("q", (300.0, 100.0, 1.0))),
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


PROXIED = {"X-Forwarded-For": "100.64.0.2"}  # cloudflared / tailscale serve


@pytest.fixture()
def frames_as_json(monkeypatch):
    """Remote frames: the test posts JSON where the browser posts a JPEG."""
    monkeypatch.setattr(
        admin_face_routes,
        "decode_jpeg",
        lambda data: json.loads(data) if data.startswith(b"{") else None,
    )


def post_frame(client, frame, **kw):
    return client.post(
        "/api/admin/face/frame",
        data=json.dumps(frame).encode(),
        content_type="image/jpeg",
        **kw,
    )


def test_remote_login_uses_the_browsers_frames_not_the_kiosk_camera(
    client, face, frames_as_json
):
    enrol("Ahmad", "A")
    face.camera.frames.extend(good())  # must stay unread
    for env in ({"environ_base": REMOTE}, {"headers": PROXIED}):
        started = client.post("/api/admin/face/login/start", **env).get_json()
        assert started["remote"] is True and started["state"] == "running"
        status = client.get("/api/admin/face/status", **env).get_json()
        assert status["local"] is False
        for frame in good():
            result = post_frame(client, frame, **env).get_json()
        assert result["state"] == "passed" and result["name"] == "Ahmad"
        assert is_admin(client)
        client.get("/admin/logout", **env)
    assert len(face.camera.frames) == 6
    assert AdminLoginEvent.query.count() == 2


def test_remote_spoof_fails_and_bad_frames_are_refused(client, face, frames_as_json):
    enrol("Ahmad", "A")
    client.post("/api/admin/face/login/start", headers=PROXIED)
    bad = client.post(
        "/api/admin/face/frame", data=b"not a jpeg", content_type="image/jpeg"
    )
    assert bad.status_code == 400
    for frame in good(live=0.3):
        result = post_frame(client, frame).get_json()
    assert (result["state"], result["reason"]) == ("failed", "spoof")
    assert not is_admin(client)


BLURRED = {"faces": [("A", 0.0)], "live": 0.95, "q": (20.0, 100.0, 1.0)}


def test_poor_remote_frames_are_skipped_with_a_hint(client, face, frames_as_json):
    enrol("Ahmad", "A")
    client.post("/api/admin/face/login/start", headers=PROXIED)
    for q, hint in [
        ((20.0, 100.0, 1.0), "Tahan kamera tetap diam"),
        ((300.0, 40.0, 1.0), "Wajah terlalu gelap, cari tempat yang lebih terang"),
        (
            (300.0, 100.0, 2.5),
            "Cahaya di belakangmu terlalu terang, cari cahaya dari depan",
        ),
    ]:
        result = post_frame(client, {**front(), "q": q}).get_json()
        assert (result["state"], result["hint"]) == ("running", hint)
    for frame in good():
        result = post_frame(client, frame).get_json()
    assert result["state"] == "passed"


def test_only_poor_remote_frames_end_as_poor_image(client, face, frames_as_json):
    enrol("Ahmad", "A")
    client.post("/api/admin/face/login/start", headers=PROXIED)
    post_frame(client, BLURRED)
    face.settings.timeout = -1.0
    result = post_frame(client, BLURRED).get_json()
    assert (result["state"], result["reason"]) == ("failed", "poor_image")


def test_kiosk_frames_are_not_gated_on_image_quality(client, face):
    enrol("Ahmad", "A")
    _, result = login(client, face, [BLURRED] * 6)
    assert result["state"] == "passed"


def test_image_quality_sees_blur_darkness_and_backlight():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from utils.liveness import image_quality

    sharp = np.zeros((480, 640, 3), np.uint8)
    sharp[::4, :] = 255  # fine stripes
    blurred = cv2.GaussianBlur(sharp, (31, 31), 10)
    box = Face((200, 120, 240, 240), [], 0.9, None)
    assert image_quality(sharp, box)[0] > 10 * image_quality(blurred, box)[0]
    backlit = np.full((480, 640, 3), 230, np.uint8)
    backlit[120:360, 200:440] = 60  # dark face, bright surround
    _, light, back = image_quality(backlit, box)
    assert round(light) == 60 and back > 3


def test_only_the_starting_browser_can_feed_a_remote_attempt(
    app, client, face, frames_as_json
):
    enrol("Ahmad", "A")
    client.post("/api/admin/face/login/start", headers=PROXIED)
    other = app.test_client()
    assert post_frame(other, front()).status_code == 404


def test_remote_attempt_leaves_the_kiosk_attempt_running(client, face, frames_as_json):
    kiosk = Attempt(id="kiosk", mode="login", started=0.0)
    face._running = kiosk
    client.post("/api/admin/face/login/start", headers=PROXIED)
    assert face._running is kiosk and kiosk.state == "running"


def test_kiosk_attempt_takes_no_posted_frames(client, face, frames_as_json):
    enrol("Ahmad", "A")
    client.post("/api/admin/face/login/start")  # kiosk, mock camera: fails at once
    assert post_frame(client, front()).status_code == 409


def test_proxy_header_makes_a_loopback_request_remote(client):
    logout = client.get("/admin/logout", headers=PROXIED)
    assert logout.headers["Location"].endswith("/admin/login")
    logout = client.get("/admin/logout", headers={"Tailscale-User-Login": "a@b"})
    assert logout.headers["Location"].endswith("/admin/login")
    assert client.get("/admin/logout").headers["Location"].endswith("/kiosk")


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
    assert (
        admin_client.get("/api/admin/face/attempt").get_json()["reason"] == "name_taken"
    )
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
    assert (
        admin_client.get("/api/admin/face/attempt").get_json()["reason"]
        == "face_changed"
    )


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

"""Guided registration face photo with a fake detector, camera and clock."""

from collections import deque

import pytest

import app as app_module
from tests.test_students import FORM
from utils.face import Face
from utils.photo_capture import PhotoCapture, PhotoSettings


class FakeEngine:
    def detect(self, frame):
        return [
            Face((0, 0, size, size), [(0, 0), (10, 0), (5 + 10 * yaw, 5)], 0.9)
            for size, yaw in frame
        ]


class TickingCamera:
    """Each frame is half a second after the previous one."""

    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = deque(frames)

    def read(self):
        self.clock[0] += 0.5
        return self.frames.popleft() if self.frames else None


ONE = [(200, 0.0)]


def make(frames, **kw):
    now = [0.0]
    beeps = []
    capture = PhotoCapture(
        TickingCamera(now, frames),
        FakeEngine(),
        beep=lambda **p: beeps.append(p["active"]),
        settings=PhotoSettings(**kw),
        clock=lambda: now[0],
        threaded=False,
    )
    return capture, beeps


def test_counts_down_with_beeps_then_keeps_a_photo():
    # 1 s to read + 3 s countdown = 7 frames waited, then 3 good ones.
    capture, beeps = make([[]] * 7 + [ONE] * 3)
    c = capture.start("owner")
    assert c.state == "ready" and c.instruction == "Foto tersimpan."
    assert beeps == [2, 2, 2, 6]
    assert capture.take("other", c.token) is None
    assert capture.take("owner", c.token) == b"jpeg"
    assert capture.take("owner", c.token) is None  # only once


@pytest.mark.parametrize(
    "frames, reason",
    [
        ([[(60, 0.0)]] * 12, "no_face"),  # too far away
        ([[(200, 0.0), (200, 0.0)]] * 12, "multiple_faces"),
    ],
)
def test_bad_frames_fail_with_a_reason(frames, reason):
    capture, _ = make(frames, prepare=0, countdown=0, capture_seconds=2)
    c = capture.start("owner")
    assert (c.state, c.reason) == ("failed", reason)


def test_turned_away_frames_do_not_count():
    capture, _ = make([[(200, 0.8)]] * 2 + [ONE] * 3, prepare=0, countdown=0)
    assert capture.start("owner").state == "ready"


@pytest.fixture()
def photo(monkeypatch):
    """The app's PhotoCapture (the blueprint holds it) with the fakes of make()."""
    fake, _ = make([ONE] * 3, prepare=0, countdown=0)
    real = app_module.photo_capture
    for key in ("camera", "engine", "settings", "unavailable", "_beep", "_clock",
                "_threaded", "_captures", "_running", "_sharpness", "_encode"):
        monkeypatch.setattr(real, key, getattr(fake, key))
    return real


def register(client, **extra):
    token = client.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan("01020304")
    return client.post("/api/register", data=dict(FORM, nfc_token=token, **extra))


def test_registration_needs_the_photo_and_stores_it(client, photo):
    assert client.get("/api/register/photo/status").get_json()["available"]
    resp = register(client)
    assert resp.status_code == 400 and resp.get_json()["photo_missing"]

    started = client.post("/api/register/photo/start").get_json()
    assert started["state"] == "ready"
    preview = client.get("/api/register/photo/preview?token=" + started["token"])
    assert preview.status_code == 200 and preview.data == b"jpeg"
    resp = register(client, photo_token=started["token"])
    assert resp.status_code == 200
    sid = resp.get_json()["student"]["student_id"]
    assert client.get(f"/api/student/{sid}/photo").data == b"jpeg"


def test_another_browser_cannot_use_the_photo(app, client, photo):
    started = client.post("/api/register/photo/start").get_json()
    other = app.test_client()
    assert other.get("/api/register/photo?token=" + started["token"]).status_code == 404
    token = other.post("/api/nfc/registration/start").get_json()["token"]
    app_module.nfc_reader.simulate_scan("01020304")
    resp = other.post(
        "/api/register", data=dict(FORM, nfc_token=token, photo_token=started["token"])
    )
    assert resp.status_code == 400


def test_without_a_camera_the_photo_is_optional(client):
    assert not client.get("/api/register/photo/status").get_json()["available"]
    assert register(client).status_code == 200


def test_portrait_box_is_a_head_and_shoulders_close_up():
    from utils.face import portrait_box

    # 640x480 frame; eyes at y=200, chin (box bottom) at y=300 -> D = 100.
    face = Face((270, 160, 100, 140), [(290, 200), (350, 200), (320, 240)], 0.9)
    x, y, w, h = portrait_box((480, 640, 3), face)
    assert (y, y + h) == (50, 390)  # 1.5 D above the eyes, 0.9 D below the chin
    assert abs(w / h - 0.8) < 0.01 and abs((x + w / 2) - 320) <= 1


def test_portrait_box_stays_inside_the_frame():
    from utils.face import portrait_box

    face = Face((0, 10, 100, 140), [(20, 50), (80, 50), (50, 90)], 0.9)  # top-left corner
    x, y, w, h = portrait_box((480, 640, 3), face)
    assert x == 0 and y == 0 and y + h <= 480 and x + w <= 640

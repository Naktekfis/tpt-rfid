import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

import app as app_module  # noqa: E402
from tests.conftest import TEST_PIN  # noqa: E402
from utils.face import Face, FaceEngine, FaceIndex  # noqa: E402
from utils.face_service import FaceService  # noqa: E402
from utils.liveness import LivenessUnavailable  # noqa: E402

DIM = 8


def make_frame(identity, faces=1, blurry=False):
    """Synthetic frame; pixel (0,0) carries identity/face count for the fakes."""
    if blurry:
        frame = np.full((480, 640, 3), 128, np.uint8)
    else:
        frame = np.random.RandomState(identity).randint(
            0, 255, (480, 640, 3)
        ).astype(np.uint8)
    frame[0, 0] = (identity, faces, 0)
    return frame


class FakeEngine(FaceEngine):
    name = "fake"
    threshold = 0.5

    def detect(self, frame):
        n = int(frame[0, 0, 1])
        return [Face((200, 100, 200, 200), None, 1.0) for _ in range(n)]

    def embed(self, frame, face):
        vec = np.zeros(DIM, np.float32)
        vec[int(frame[0, 0, 0])] = 1.0
        return vec

    def distance(self, a, b):
        return float(np.linalg.norm(a - b))


class FakeLiveness:
    def __init__(self):
        self.live = True
        self.unavailable = False

    def check(self, frame, face):
        if self.unavailable:
            raise LivenessUnavailable("gone")
        return self.live, 0.9 if self.live else 0.1


@pytest.fixture()
def liveness():
    return FakeLiveness()


@pytest.fixture()
def service(app, database, liveness):
    engine = FakeEngine()
    return FaceService(
        app,
        database,
        app_module.camera,
        engine,
        liveness,
        FaceIndex(engine.distance, engine.threshold),
    )


def make_student(database, n):
    return database.create_student(
        {
            "name": f"S{n}",
            "nim": f"1000000{n}",
            "email": f"s{n}@example.com",
            "phone": "0800000000",
        }
    )


def test_identify_status_codes(service, liveness):
    assert service.identify_frame(None)["status"] == "no_camera"
    assert service.identify_frame(make_frame(1, faces=0))["status"] == "no_face"
    assert service.identify_frame(make_frame(1, faces=2))["status"] == "multiple_faces"
    assert service.identify_frame(make_frame(1, blurry=True))["status"] == "blurry"
    assert service.identify_frame(make_frame(1))["status"] == "unknown"
    liveness.live = False
    assert service.identify_frame(make_frame(1))["status"] == "not_live"
    liveness.unavailable = True
    assert service.identify_frame(make_frame(1))["status"] == "liveness_unavailable"


def test_identify_fails_closed_without_liveness_or_models(service):
    service.liveness = None
    assert service.identify_frame(make_frame(1))["status"] == "liveness_unavailable"
    service.engine = None
    assert service.identify_frame(make_frame(1))["status"] == "models_missing"
    assert service.enroll(1, [make_frame(1)])["status"] == "models_missing"


def test_enroll_then_identify(service, database):
    s = make_student(database, 1)
    sid = s["student_id"]
    res = service.enroll(int(sid), [make_frame(1) for _ in range(4)])
    assert res["status"] == "ok" and res["stored"] == 4 and res["verified"]
    assert database.student_has_face(int(sid))
    assert database.get_student_photo(sid)[1] == "image/jpeg"
    got = service.identify_frame(make_frame(1))
    assert got["status"] == "ok"
    assert got["student"]["name"] == "S1"
    assert "photo_data" not in got["student"]
    assert service.identify_frame(make_frame(5))["status"] == "unknown"


def test_enroll_needs_three_good_frames(service, database):
    sid = int(make_student(database, 1)["student_id"])
    frames = [make_frame(1), make_frame(1), make_frame(1, faces=0), make_frame(1, blurry=True)]
    res = service.enroll(sid, frames)
    assert res["status"] == "insufficient"
    assert res["good_frames"] == 2
    assert res["problems"] == {"no_face": 1, "blurry": 1}
    assert not database.student_has_face(sid)


def test_enroll_rejects_duplicate_of_other_student(service, database):
    a = int(make_student(database, 1)["student_id"])
    b = int(make_student(database, 2)["student_id"])
    assert service.enroll(a, [make_frame(1) for _ in range(3)])["status"] == "ok"
    res = service.enroll(b, [make_frame(1) for _ in range(3)])
    assert res["status"] == "duplicate"
    assert not database.student_has_face(b)
    # Re-enrolling the same student is fine and replaces the old embeddings.
    assert service.enroll(a, [make_frame(1) for _ in range(3)])["stored"] == 3
    assert len(database.get_face_embeddings("fake")) == 3


def test_enroll_fails_closed_when_liveness_unavailable(service, database, liveness):
    sid = int(make_student(database, 1)["student_id"])
    liveness.unavailable = True
    res = service.enroll(sid, [make_frame(1) for _ in range(4)])
    assert res["status"] == "liveness_unavailable"
    assert not database.student_has_face(sid)


def test_enroll_spoof_and_unknown_student(service, database, liveness):
    sid = int(make_student(database, 1)["student_id"])
    liveness.live = False
    res = service.enroll(sid, [make_frame(1) for _ in range(4)])
    assert res["status"] == "insufficient" and res["problems"] == {"not_live": 4}
    assert service.enroll(999, [make_frame(1)])["status"] == "not_found"


def test_delete_face_data_clears_photo_and_index(service, database):
    sid = int(make_student(database, 1)["student_id"])
    service.enroll(sid, [make_frame(1) for _ in range(3)])
    assert service.delete(sid)
    assert not database.student_has_face(sid)
    assert database.get_student_photo(str(sid)) is None
    assert service.identify_frame(make_frame(1))["status"] == "unknown"
    assert not service.delete(999)


# ---- DB layer ----


def test_embeddings_roundtrip_and_cascade(database, app):
    from utils import Student, db

    sid = int(make_student(database, 1)["student_id"])
    blob = np.arange(4, dtype=np.float32).tobytes()
    assert database.add_face_embeddings(sid, "fake", [blob, blob]) == 2
    database.add_face_embeddings(sid, "other", [blob])
    rows = database.get_face_embeddings("fake")
    assert [r[0] for r in rows] == [sid, sid]
    assert np.frombuffer(rows[0][1], dtype=np.float32).tolist() == [0, 1, 2, 3]
    db.session.delete(db.session.get(Student, sid))
    db.session.commit()
    assert database.get_face_embeddings("fake") == []
    assert database.get_face_embeddings("other") == []


# ---- routes ----


@pytest.fixture()
def wired(service, monkeypatch):
    monkeypatch.setattr(app_module.face_service, "engine", service.engine)
    monkeypatch.setattr(app_module.face_service, "liveness", service.liveness)
    monkeypatch.setattr(app_module.face_service, "index", service.index)
    monkeypatch.setattr("routes.face_routes.time.sleep", lambda s: None)
    yield service
    app_module.camera.set_frames([])


def test_identify_route_no_camera_and_no_face(client, wired):
    data = client.get("/api/face/identify").get_json()
    assert data["status"] == "no_camera" and data["success"] is False
    app_module.camera.set_frames([make_frame(1, faces=0)])
    assert client.get("/api/face/identify").get_json()["status"] == "no_face"


def test_enroll_route_then_identify(client, wired, database):
    sid = int(make_student(database, 1)["student_id"])
    app_module.camera.set_frames([make_frame(1)])
    res = client.post(f"/api/face/enroll/{sid}").get_json()
    assert res["success"] and res["verified"]
    assert client.get("/api/face/identify").get_json()["student"]["name"] == "S1"
    assert client.post("/api/face/enroll/999").status_code == 404


def test_stream_unavailable_with_mock_camera(client):
    assert client.get("/camera/stream").status_code == 503


def test_admin_delete_needs_login(client, wired, database):
    sid = int(make_student(database, 1)["student_id"])
    wired.enroll(sid, [make_frame(1) for _ in range(3)])
    url = f"/api/admin/students/{sid}/face/delete"
    assert client.post(url, headers={"Accept": "application/json"}).status_code == 401
    assert database.student_has_face(sid)


def test_admin_delete_after_login(admin_client, wired, database):
    sid = int(make_student(database, 1)["student_id"])
    wired.enroll(sid, [make_frame(1) for _ in range(3)])
    assert admin_client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200
    res = admin_client.post(f"/api/admin/students/{sid}/face/delete")
    assert res.get_json()["success"]
    assert not database.student_has_face(sid)

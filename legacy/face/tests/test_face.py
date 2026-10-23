import os

import pytest

from utils.camera import MockCamera, create_camera
from utils.face import Face, FaceIndex, quality_issues
from utils.liveness import HeadTurnChallenge

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "face")


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


# ---- FaceIndex (synthetic vectors, no numpy needed) ----


def _index(rows, threshold=0.5):
    idx = FaceIndex(_dist, threshold)
    idx.load(rows)
    return idx


def test_index_nearest_student_wins():
    idx = _index([(1, [0.0, 0.0]), (1, [0.1, 0.0]), (2, [1.0, 1.0])])
    match = idx.identify([0.05, 0.0])
    assert match.student_id == 1
    assert match.distance == pytest.approx(0.05)


def test_index_over_threshold_is_unknown():
    idx = _index([(1, [0.0, 0.0])])
    assert idx.identify([2.0, 0.0]) is None
    assert idx.identify_detail([2.0, 0.0]) == (None, False)


def test_index_ambiguous_when_second_student_close():
    idx = _index([(1, [0.0, 0.0]), (2, [0.04, 0.0])])
    assert idx.identify_detail([0.0, 0.0]) == (None, True)
    # Same student twice is not ambiguous.
    idx = _index([(1, [0.0, 0.0]), (1, [0.04, 0.0])])
    assert idx.identify([0.0, 0.0]).student_id == 1


def test_index_second_student_far_is_not_ambiguous():
    idx = _index([(1, [0.0, 0.0]), (2, [0.3, 0.0])])
    assert idx.identify([0.0, 0.0]).student_id == 1


def test_index_empty_and_reload():
    idx = FaceIndex(_dist, 0.5)
    assert not idx.loaded
    assert idx.identify([0.0]) is None
    idx.load([(7, [0.0])])
    assert idx.loaded and len(idx) == 1
    idx.load([])
    assert idx.identify([0.0]) is None


# ---- HeadTurnChallenge ----


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _lm(yaw):
    # right eye x=40, left eye x=60 (eye distance 20); nose offset = yaw * 20
    return [(40, 50), (60, 50), (50 + yaw * 20, 70), (42, 90), (58, 90)]


def test_head_turn_left_needs_frontal_first():
    clock = FakeClock()
    ch = HeadTurnChallenge("left", clock)
    assert ch.update(_lm(-0.5)) == "pending"  # already turned: no frontal yet
    assert ch.update(_lm(0.0)) == "pending"
    assert ch.update(_lm(-0.1)) == "pending"
    assert ch.update(_lm(-0.4)) == "passed"
    assert ch.update(_lm(0.0)) == "passed"  # sticky


def test_head_turn_wrong_direction_does_not_pass():
    ch = HeadTurnChallenge("right", FakeClock())
    ch.update(_lm(0.0))
    assert ch.update(_lm(-0.6)) == "pending"
    assert ch.update(_lm(0.6)) == "passed"


def test_head_turn_timeout():
    clock = FakeClock()
    ch = HeadTurnChallenge("left", clock, timeout=6.0)
    ch.update(_lm(0.0))
    clock.t = 6.5
    assert ch.update(_lm(-0.6)) == "timeout"
    assert ch.update(_lm(-0.6)) == "timeout"


def test_head_turn_no_face_frames_are_ignored():
    ch = HeadTurnChallenge("left", FakeClock())
    assert ch.update(None) == "pending"
    with pytest.raises(ValueError):
        HeadTurnChallenge("up")


# ---- quality_issues (needs cv2) ----


def _face(box):
    return Face(box, None, 1.0)


def test_quality_no_and_multiple_faces():
    assert quality_issues(None, []) == ["no_face"]
    assert quality_issues(None, [_face((0, 0, 1, 1)), _face((0, 0, 1, 1))]) == [
        "multiple_faces"
    ]


def test_quality_blank_is_blurry_noise_is_sharp():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    blank = np.full((480, 640, 3), 128, np.uint8)
    face = _face((200, 100, 200, 200))
    assert quality_issues(blank, [face]) == ["blurry"]
    noise = np.random.RandomState(0).randint(0, 255, (480, 640, 3)).astype(np.uint8)
    assert quality_issues(noise, [face]) == []
    assert quality_issues(noise, [_face((200, 100, 80, 80))]) == ["too_small"]


# ---- cameras ----


def test_mock_camera_cycles_and_none_without_frames():
    cam = MockCamera()
    assert cam.read() is None
    np = pytest.importorskip("numpy")
    a, b = np.zeros((2, 2, 3), np.uint8), np.ones((2, 2, 3), np.uint8)
    cam.set_frames([a, b])
    assert cam.read().sum() == 0
    assert cam.read().sum() == 12
    assert cam.read().sum() == 0


def test_create_camera_disabled_is_mock():
    assert isinstance(create_camera(False), MockCamera)


# ---- real models: skipped unless cv2 and the model files are present ----


def _need_models(*files):
    pytest.importorskip("cv2")
    pytest.importorskip("numpy")
    for f in files:
        if not os.path.isfile(os.path.join(MODEL_DIR, f)):
            pytest.skip(f"{f} not downloaded")


def test_yunet_blank_frame_has_no_face():
    _need_models(
        "face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"
    )
    import numpy as np

    from utils.face import YuNetSFaceEngine

    engine = YuNetSFaceEngine(MODEL_DIR)
    assert engine.detect(np.full((480, 640, 3), 128, np.uint8)) == []
    a = np.array([1, 0], np.float32)
    assert engine.distance(a, a) == pytest.approx(0.0)


def test_liveness_loads_and_scores_synthetic_crop():
    _need_models("MiniFASNetV2.onnx", "MiniFASNetV1SE.onnx")
    import numpy as np

    from utils.liveness import PassiveLiveness

    live = PassiveLiveness(MODEL_DIR)
    assert live.input_size == 80
    frame = np.full((480, 640, 3), 128, np.uint8)
    is_live, score = live.check(frame, Face((200, 100, 200, 200), None, 1.0))
    assert isinstance(is_live, bool) and 0.0 <= score <= 1.0


def test_liveness_missing_models_fail_closed(tmp_path):
    pytest.importorskip("cv2")
    from utils.liveness import LivenessUnavailable, PassiveLiveness

    with pytest.raises(LivenessUnavailable):
        PassiveLiveness(str(tmp_path))


def test_engine_missing_models_raise(tmp_path):
    pytest.importorskip("cv2")
    from utils.face import FaceModelsMissing, YuNetSFaceEngine

    with pytest.raises(FaceModelsMissing):
        YuNetSFaceEngine(str(tmp_path))


# ---- Blink ----


def test_eye_aspect_ratio_open_vs_closed():
    from utils.liveness import eye_aspect_ratio

    open_eye = [(0, 0), (3, -2), (7, -2), (10, 0), (7, 2), (3, 2)]
    closed = [(0, 0), (3, -0.3), (7, -0.3), (10, 0), (7, 0.3), (3, 0.3)]
    assert eye_aspect_ratio(open_eye) == pytest.approx(0.4)
    assert eye_aspect_ratio(closed) == pytest.approx(0.06)


def _blink_run(values, **kw):
    from utils.liveness import BlinkChallenge

    clock = FakeClock()
    ch = BlinkChallenge(clock, **kw)
    for v in values:
        clock.t += 0.033
        ch.update(v)
    return ch


def test_blink_passes_on_one_blink():
    ch = _blink_run([0.3] * 10 + [0.1, 0.08, 0.1] + [0.3] * 3)
    assert ch.state == "passed" and ch.blinks == 1


def test_blink_steady_photo_never_passes():
    ch = _blink_run([0.3, 0.29, 0.31] * 30)
    assert ch.state == "pending" and ch.blinks == 0


def test_blink_long_closure_is_not_a_blink():
    ch = _blink_run([0.3] * 10 + [0.1] * 20 + [0.3] * 3)
    assert ch.blinks == 0


def test_blink_times_out():
    ch = _blink_run([0.3] * 300, timeout=2.0)
    assert ch.state == "timeout"

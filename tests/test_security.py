"""Synthetic evidence and debounce checks; no real camera or student data."""
from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from utils.security import EvidenceStore, SecurityService, frame_condition


@pytest.fixture
def frame():
    np = pytest.importorskip("numpy")
    return np.indices((64, 64)).sum(axis=0).astype('uint8') * 2


@pytest.fixture
def service(tmp_path, frame):
    camera = Mock()
    camera.status.return_value = {"running": True, "frame_age": 0.01}
    camera.read.return_value = frame
    return SecurityService(camera, Mock(), tmp_path / "security", enabled=True,
                           debounce_seconds=5, recovery_seconds=3)


def settle(service, now):
    service.sample(now)
    service.sample(now + 6)


def test_conditions_are_conservative(frame):
    np = pytest.importorskip("numpy")
    assert frame_condition(None) == "unavailable"
    assert frame_condition(np.zeros((64, 64, 3), dtype='uint8')) == 'suspected_obstruction'
    assert frame_condition(np.full((64, 64, 3), 200, dtype='uint8')) == 'suspected_obstruction'
    assert frame_condition(frame) == 'healthy'


def test_debounce_recovery_ack_and_no_beep_storm(service, frame):
    service.camera.read.return_value = None
    service.sample(0)
    service.sample(4)
    service.reader.beep.assert_not_called()
    service.sample(5)
    service.reader.beep.assert_called_once()
    event = service.store.events()[0]
    assert event['kind'] == 'camera_unavailable'
    service.store.acknowledge(event['event_id'])
    service.sample(20)
    service.reader.beep.assert_called_once()
    service.camera.read.return_value = frame
    service.sample(21)
    service.sample(23)
    assert service.condition == 'unavailable'
    service.sample(24)
    recovered = service.store.get(event['event_id'])
    assert recovered['recovered_at']
    assert recovered['acknowledged_at']
    service.camera.read.return_value = None
    settle(service, 30)
    assert service.reader.beep.call_count == 2


def test_restart_reuses_incident_without_beep(service):
    service.camera.read.return_value = None
    settle(service, 0)
    restarted = SecurityService(service.camera, Mock(), service.store.directory, enabled=True)
    settle(restarted, 20)
    restarted.reader.beep.assert_not_called()
    assert len(restarted.store.events()) == 1


def test_restart_healthy_resolves_persisted_incident(service, frame):
    service.camera.read.return_value = None
    settle(service, 0)
    service.camera.read.return_value = frame
    restarted = SecurityService(service.camera, Mock(), service.store.directory, enabled=True)
    settle(restarted, 20)
    assert restarted.store.events()[0]['recovered_at']
    assert restarted.condition == 'healthy'


def test_stale_frame_detected_as_unavailable(service):
    service.camera.status.return_value['frame_age'] = 30
    settle(service, 0)
    assert service.condition == 'unavailable'
    assert service.store.events()[0]['photo_status'] == 'camera_unavailable'


def test_transient_bad_image_does_not_raise_alarm(service):
    service.camera.read.return_value = None
    service.sample(0)
    service.sample(4)
    service.camera.read.return_value = Mock()
    service.camera.status.return_value['frame_age'] = 20
    service.sample(4.5)
    assert service.store.events() == []


def test_photo_budget_preserves_existing_files(tmp_path):
    store = EvidenceStore(tmp_path / 'security', max_storage_bytes=5)
    first = {'event_id': 'a' * 32, 'started_at': '2026-01-01', 'photo_status': 'pending'}
    store.save(first)
    store.add_photo(first, b'jpeg')
    second = {'event_id': 'b' * 32, 'started_at': '2026-01-02', 'photo_status': 'pending'}
    store.save(second)
    store.add_photo(second, b'jpeg')
    assert store.photo_path(first['event_id']).read_bytes() == b'jpeg'
    assert store.get(second['event_id'])['photo_status'] == 'storage_full'
    assert store.photo_path('../outside') is None
    assert store.directory.stat().st_mode & 0o777 == 0o700
    assert (store.directory / ('a' * 32 + '.json')).stat().st_mode & 0o777 == 0o600


def test_tool_alarm_is_queued_and_snapshot_copied_off_encoding_path(service):
    service.record_tool_alarm({'alarm_id': '12', 'tool_id': '4', 'tool_name': 'Dummy'})
    assert not service.store.directory.exists()
    event, snapshot = service._queue.get_nowait()
    assert event['alarm_id'] == '12'
    assert snapshot is service.camera.read.return_value
    service.camera.jpeg.assert_not_called()


def test_capture_failure_retains_metadata(service, monkeypatch):
    cv2 = pytest.importorskip('cv2')
    monkeypatch.setattr(cv2, 'imencode', Mock(side_effect=ValueError('synthetic')))
    event = service._event('tool_alarm', alarm_id='1')
    service._capture(event, service.camera.read())
    assert service.store.get(event['event_id'])['photo_status'] == 'capture_failed'


def test_successful_capture(service):
    pytest.importorskip('cv2')
    event = service._event('tool_alarm', alarm_id='1')
    service._capture(event, service.camera.read())
    path = service.store.photo_path(event['event_id'])
    assert path.read_bytes().startswith(b'\xff\xd8')


def test_disabled_monitor_does_not_touch_storage(tmp_path):
    monitor = SecurityService(Mock(), Mock(), tmp_path / 'unused', enabled=False)
    monitor.sample(100)
    assert not monitor.store.directory.exists()


def test_corrupt_record_does_not_break_history(tmp_path):
    store = EvidenceStore(tmp_path / 'security')
    store._prepare()
    (store.directory / ('c' * 32 + '.json')).write_text('{')
    assert store.events() == []


def test_camera_read_rejects_stale_frame(monkeypatch, frame):
    from utils.camera import OpenCVCamera

    camera = OpenCVCamera()
    camera._frame = frame
    camera._frame_time = 10
    monkeypatch.setattr('utils.camera.time.monotonic', lambda: 14)
    assert camera.read() is None
    monkeypatch.setattr('utils.camera.time.monotonic', lambda: 11)
    assert camera.read() is not None


def test_private_routes_require_admin_and_ack_does_not_clear_incident(tmp_path):
    from functools import wraps

    from flask import Flask, jsonify, session

    from routes.security_routes import create_security_blueprint

    app = Flask(__name__)
    app.secret_key = 'synthetic-test-only'
    service = SecurityService(Mock(), Mock(), tmp_path / 'security')
    event = service._event('camera_unavailable')
    service.store.save(event)
    service.store.add_photo(event, b'\xff\xd8\xffsynthetic')

    def admin_required(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if not session.get('admin'):
                return jsonify(success=False), 401
            return function(*args, **kwargs)
        return wrapper

    database = Mock()
    database.get_alarm_history.return_value = []
    app.register_blueprint(create_security_blueprint(service, database, admin_required))
    client = app.test_client()
    root = '/api/admin/security'
    photo = root + '/events/' + event['event_id'] + '/photo'
    ack = root + '/events/' + event['event_id'] + '/ack'
    for url in (root, photo):
        assert client.get(url).status_code == 401
    assert client.post(ack).status_code == 401
    with client.session_transaction() as browser_session:
        browser_session['admin'] = True
    assert client.get(root).json['events'][0]['event_id'] == event['event_id']
    response = client.get(photo)
    assert response.status_code == 200
    assert 'no-store' in response.headers['Cache-Control']
    assert client.post(ack).json['success']
    saved = service.store.get(event['event_id'])
    assert saved['acknowledged_at']
    assert saved['recovered_at'] is None
    assert client.get(root + '/events/' + 'z' * 32 + '/photo').status_code == 404
    assert json.loads((service.store.directory / (event['event_id'] + '.json')).read_text())


def test_storage_failure_does_not_suppress_beep_or_retry(service, monkeypatch):
    service.camera.read.return_value = None
    original_save = service.store.save
    failed_save = Mock(side_effect=OSError('synthetic disk full'))
    monkeypatch.setattr(service.store, 'save', failed_save)
    settle(service, 0)
    service.reader.beep.assert_called_once()
    assert service.condition == 'unavailable'
    assert service.storage_error
    service.sample(10)
    service.reader.beep.assert_called_once()
    assert failed_save.call_count >= 2
    monkeypatch.setattr(service.store, 'save', original_save)
    service.sample(11)
    assert service.storage_error is None
    assert len(service.store.events()) == 1
    service.reader.beep.assert_called_once()


@pytest.mark.parametrize('encoding_fails', [False, True])
def test_ack_during_encoding_is_preserved(service, monkeypatch, encoding_fails):
    cv2 = pytest.importorskip('cv2')
    event = service._event('tool_alarm', alarm_id='1')
    original_encode = cv2.imencode

    def encode_and_ack(*args, **kwargs):
        assert service.store.acknowledge(event['event_id'])
        if encoding_fails:
            raise ValueError('synthetic encoding failure')
        return original_encode(*args, **kwargs)

    monkeypatch.setattr(cv2, 'imencode', encode_and_ack)
    service._capture(event, service.camera.read())
    saved = service.store.get(event['event_id'])
    assert saved['acknowledged_at']
    assert saved['photo_status'] == ('capture_failed' if encoding_fails else 'captured')


def test_stale_recovery_save_preserves_ack_under_store_lock(service):
    event = service._event('camera_unavailable')
    service.store.save(event)
    assert event['acknowledged_at'] is None
    assert service.store.acknowledge(event['event_id'])
    event['recovered_at'] = '2026-01-01T00:00:00Z'
    service.store.save(event)
    saved = service.store.get(event['event_id'])
    assert saved['acknowledged_at']
    assert saved['recovered_at']


def test_cover_that_lets_light_through_is_seen_by_lost_edges():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from utils.security import ObstructionDetector

    rng = np.random.default_rng(0)
    scene = (rng.integers(0, 2, (12, 16)) * 200).astype("uint8")
    scene = np.kron(scene, np.ones((40, 40), dtype="uint8"))  # 480x640 checker scene
    detector = ObstructionDetector()
    for _ in range(3):
        assert detector.condition(scene) == "healthy"
    # A bright, slightly uneven cover (paper/hand with light behind it).
    cover = np.clip(120 + rng.normal(0, 12, scene.shape), 0, 255).astype("uint8")
    cover = __import__("cv2").GaussianBlur(cover, (31, 31), 0)
    assert detector.condition(cover) == "suspected_obstruction"
    # A person in front hides part of the scene but adds edges: still healthy.
    person = scene.copy()
    person[120:360, 200:440] = 90
    person[200:210, 220:420] = 250
    assert detector.condition(person) == "healthy"


def test_covered_camera_beeps_seven_times(service):
    np = pytest.importorskip("numpy")
    service.camera.read.return_value = np.zeros((64, 64, 3), dtype="uint8")
    settle(service, 0)
    service.reader.beep.assert_called_once_with(active=2, silent=2, times=7)

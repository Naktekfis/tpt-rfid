import time

import pytest

from tests.test_vx6336 import EPC_A, EPC_B, inventory_data, response_frame
from utils import vx6336
from utils.rfid_reader import (
    RFIDReaderMock,
    ScanDebouncer,
    VX6336Reader,
    create_rfid_reader,
)


class FakeSerial:
    """Answers each command with the next scripted list of response frames."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.written = []
        self._out = b""
        self.closed = False

    @property
    def in_waiting(self):
        return len(self._out)

    def reset_input_buffer(self):
        self._out = b""

    def write(self, data):
        self.written.append(bytes(data))
        if self.replies:
            self._out += b"".join(self.replies.pop(0))

    def read(self, n):
        chunk, self._out = self._out[:n], self._out[n:]
        return chunk

    def close(self):
        self.closed = True


def inv(*epcs, status=0x01):
    return response_frame(0x01, status, inventory_data(*epcs))


NO_TAG = response_frame(0x01, vx6336.STATUS_NO_TAG)
BEEP_OK = response_frame(0x35, 0x00)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_debouncer_reports_once_per_presence():
    clock = Clock()
    d = ScanDebouncer(absent_timeout=2.0, clock=clock)
    assert d.update([EPC_A]) == [EPC_A]
    clock.t = 1.0
    assert d.update([EPC_A]) == []
    clock.t = 2.5  # still within 2 s of the last sighting at t=1
    assert d.update([EPC_A, EPC_B]) == [EPC_B]
    clock.t = 5.0  # both gone long enough
    assert d.update([]) == []
    assert d.update([EPC_A]) == [EPC_A]


def make_reader(replies):
    reader = VX6336Reader(port="fake", absent_timeout=10)
    reader.response_timeout = 0.2
    return reader, FakeSerial(replies)


def test_poll_reports_new_epc_and_debounces():
    reader, ser = make_reader([[inv(EPC_A)], [inv(EPC_A)], [NO_TAG]])
    assert reader.poll_once(ser) == [EPC_A]
    assert reader.get_current_uid() == EPC_A
    assert ser.written[0] == vx6336.inventory_command()
    assert reader.poll_once(ser) == []
    assert reader.poll_once(ser) == []


def test_clear_does_not_rereport_tag_still_on_reader():
    """Student card left on the reader must not be taken as the tool tag."""
    reader, ser = make_reader([[inv(EPC_A)], [inv(EPC_A)], [inv(EPC_A, EPC_B)]])
    reader.poll_once(ser)
    reader.clear()
    reader.poll_once(ser)
    assert reader.get_current_uid() is None
    reader.poll_once(ser)
    assert reader.get_current_uid() == EPC_B


def test_multi_frame_inventory_collected():
    reader, ser = make_reader([[inv(EPC_A, status=0x03), inv(EPC_B, status=0x01)]])
    assert reader.poll_once(ser) == [EPC_A, EPC_B]


def test_no_reply_times_out_cleanly():
    reader, ser = make_reader([])
    assert reader.poll_once(ser) == []
    assert reader.diagnostics()["no_response_total"] == 1


def test_round_diagnostics_separate_serial_and_listener_delay(monkeypatch):
    clock = Clock()
    monkeypatch.setattr("utils.rfid_reader.time.monotonic", clock)
    reader, ser = make_reader([[inv(EPC_A)], [inv(EPC_A)]])
    transact = reader._transact

    def measured_transact(*args):
        responses = transact(*args)
        clock.t += 0.025
        return responses

    def slow_listener(epcs):
        clock.t += 0.3

    monkeypatch.setattr(reader, "_transact", measured_transact)
    reader.add_round_listener(slow_listener)
    reader.poll_once(ser)
    reader.poll_once(ser)
    diagnostics = reader.diagnostics()
    assert diagnostics["inventory"]["mean_ms"] == 25
    assert diagnostics["listeners"]["mean_ms"] == 300
    assert diagnostics["total"]["mean_ms"] == 325
    assert diagnostics["round_hz"] == 3.077
    assert diagnostics["round_errors_total"] == 0
    assert EPC_A not in str(diagnostics)


def test_round_diagnostics_are_bounded_and_count_errors(monkeypatch):
    reader, ser = make_reader([[NO_TAG]] * 125)
    for _ in range(125):
        reader.poll_once(ser)
    diagnostics = reader.diagnostics()
    assert diagnostics["rounds_total"] == 125
    assert diagnostics["inventory"]["samples"] == 120

    def disconnected(*args):
        raise OSError("serial disconnected")

    monkeypatch.setattr(reader, "_transact", disconnected)
    with pytest.raises(OSError):
        reader.poll_once(ser)
    assert reader.diagnostics()["round_errors_total"] == 1
    assert reader.diagnostics()["rounds_total"] == 126


@pytest.mark.parametrize(
    "failure",
    [
        [],
        [response_frame(0x01, 0xFF)],
        [inv(EPC_B, status=0x03)],
        [inv(EPC_B, status=0x02)],
        [response_frame(0x01, 0x01)],
    ],
)
def test_failed_or_partial_inventory_does_not_advance_presence(failure, monkeypatch):
    from utils.presence import PresenceMonitor

    clock = Clock()
    reader, ser = make_reader([[inv(EPC_A)], failure, [NO_TAG]])
    reader.response_timeout = 0
    monitor = PresenceMonitor(missing_after=5, clock=clock)
    events = []
    reader.add_round_listener(lambda epcs: events.extend(monitor.update(epcs)))
    # Script the transaction without waiting on the real monotonic clock.
    replies = [
        [vx6336.parse_response(frame) for frame in frames]
        for frames in [[inv(EPC_A)], failure, [NO_TAG]]
    ]
    monkeypatch.setattr(reader, "_transact", lambda *args: replies.pop(0))
    reader.poll_once(ser)
    clock.t = 10
    reader.poll_once(ser)
    assert [event.kind for event in events] == ["new"]
    assert monitor.snapshot()[EPC_A]["state"] == "present"
    assert reader.diagnostics()["skipped_presence_rounds_total"] == 1
    reader.poll_once(ser)
    assert [event.kind for event in events] == ["new", "left"]


def test_thread_reads_info_then_polls_and_survives_missing_port():
    info = response_frame(0x21, 0x00, bytes((3, 1, 0x0C, 2, 0x4E, 0, 0x1A, 3)))
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("no such port")
        return FakeSerial([[info], [BEEP_OK], [inv(EPC_A)]])

    reader = VX6336Reader(port="fake", retry_delay=0.01, serial_factory=factory)
    reader.start()
    try:
        deadline = time.monotonic() + 3
        while reader.get_current_uid() is None and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        reader.stop()
    assert reader.get_current_uid() == EPC_A
    assert reader.reader_info.scan_time == 3
    assert len(attempts) >= 2


def test_connect_reads_beep_mode_without_changing_settings():
    info = response_frame(0x21, 0x00, bytes((3, 1, 0x0C, 2, 0x4E, 0, 0x1A, 3)))
    ser = FakeSerial([[info], [BEEP_OK], [NO_TAG]])
    reader = VX6336Reader(port="fake", retry_delay=0.01, serial_factory=lambda: ser)
    reader.start()
    try:
        deadline = time.monotonic() + 3
        while len(ser.written) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        reader.stop()
    assert ser.written[0] == vx6336.reader_info_command()
    assert ser.written[1] == vx6336.beep_mode_command(0x00)
    assert ser.written[2] == vx6336.inventory_command()
    assert all(command[2] in (0x21, 0x35, 0x01) for command in ser.written)
    assert all(command[3] == 0x00 for command in ser.written if command[2] == 0x35)


def test_round_listener_gets_every_round_and_survives_errors():
    reader, ser = make_reader([[inv(EPC_A, EPC_B)], [NO_TAG]])
    rounds = []

    def boom(epcs):
        raise RuntimeError("listener bug")

    reader.add_round_listener(boom)
    reader.add_round_listener(rounds.append)
    reader.poll_once(ser)
    reader.poll_once(ser)
    assert rounds == [[EPC_A, EPC_B], []]
    assert reader.diagnostics()["listener_errors_total"] == 2


def test_completed_empty_inventory_is_a_valid_presence_round():
    reader, ser = make_reader([[inv()]])
    rounds = []
    reader.add_round_listener(rounds.append)
    reader.poll_once(ser)
    assert rounds == [[]]
    assert reader.diagnostics()["skipped_presence_rounds_total"] == 0


def test_uhf_diagnostics_endpoint_requires_admin_and_returns_aggregates(client):
    denied = client.get(
        "/api/admin/diagnostics/uhf", headers={"Accept": "application/json"}
    )
    assert denied.status_code == 401
    with client.session_transaction() as session:
        session["admin_logged_in"] = True
    response = client.get("/api/admin/diagnostics/uhf")
    assert response.status_code == 200
    data = response.get_json()
    assert data["reader"]["mode"] == "mock"
    assert "missing_after_s" in data["presence"]
    assert "sighting_gap" in data["presence"]
    assert "unknown_epcs" not in data["presence"]


def test_beep_is_queued_and_sent_between_rounds():
    reader, ser = make_reader([[response_frame(0x33, 0x00)], [NO_TAG]])
    reader.beep(2, 2, 3)
    assert ser.written == []
    reader.poll_once(ser)
    assert ser.written[0] == vx6336.buzzer_command(2, 2, 3)
    assert ser.written[1] == vx6336.inventory_command()


def test_mock_set_present_emits_rounds_and_stops():
    reader = RFIDReaderMock()
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader._round_thread is None
    reader.set_present([EPC_A])
    try:
        deadline = time.monotonic() + 3
        while not rounds and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        reader.stop()
    assert rounds[0] == [EPC_A]
    reader.beep()


def test_factory_returns_mock_by_default():
    reader = create_rfid_reader(enabled=False, port="/dev/null")
    assert isinstance(reader, RFIDReaderMock)
    reader.simulate_scan("ABC")
    assert reader.get_current_uid() == "ABC"
    reader.clear()
    assert reader.get_current_uid() is None


def test_rfid_status_endpoint(client):
    data = client.get("/api/rfid/status").get_json()
    assert data == {"success": True, "mode": "mock"}


def test_check_rfid_returns_reported_uid(client):
    import app as app_module

    app_module.rfid_reader.simulate_scan(EPC_A)
    try:
        assert client.get("/api/check_rfid").get_json()["uid"] == EPC_A
    finally:
        app_module.rfid_reader.clear()


def test_check_rfid_reports_disconnected_reader(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        app_module.rfid_reader, "status", lambda: {"mode": "vx6336", "connected": False}
    )
    assert client.get("/api/check_rfid").get_json()["reader_connected"] is False


def test_buzzer_backlog_interleaves_with_inventory_in_fifo_order():
    beep_ok = response_frame(0x33, 0x00)
    reader, ser = make_reader(
        [[beep_ok], [inv(EPC_A)], [beep_ok], [inv(EPC_B)], [beep_ok], [NO_TAG]]
    )
    patterns = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    rounds = []
    reader.add_round_listener(rounds.append)
    for pattern in patterns:
        reader.beep(*pattern)

    assert reader.poll_once(ser) == [EPC_A]
    assert ser.written == [
        vx6336.buzzer_command(*patterns[0]),
        vx6336.inventory_command(),
    ]
    assert reader.poll_once(ser) == [EPC_B]
    assert ser.written[2:] == [
        vx6336.buzzer_command(*patterns[1]),
        vx6336.inventory_command(),
    ]
    reader.poll_once(ser)
    assert ser.written[4:] == [
        vx6336.buzzer_command(*patterns[2]),
        vx6336.inventory_command(),
    ]
    assert reader._commands.empty()
    assert rounds == [[EPC_A], [EPC_B], []]


def test_buzzer_backlog_delays_inventory_by_only_one_transaction(monkeypatch):
    clock = Clock()
    monkeypatch.setattr("utils.rfid_reader.time.monotonic", clock)
    reader, ser = make_reader([[response_frame(0x33, 0x00)], [inv(EPC_A)]])
    transact = reader._transact
    inventory_started = []

    def slow_buzzer_transaction(serial, command, expect_cmd):
        if expect_cmd == vx6336.CMD_INVENTORY:
            inventory_started.append(clock.t)
        responses = transact(serial, command, expect_cmd)
        if expect_cmd == vx6336.CMD_ACOUSTO_OPTIC:
            clock.t += 0.15
        return responses

    monkeypatch.setattr(reader, "_transact", slow_buzzer_transaction)
    for _ in range(100):
        reader.beep()

    assert reader.poll_once(ser) == [EPC_A]
    assert inventory_started == [0.15]
    assert reader._commands.qsize() == 99
    assert reader.diagnostics()["queued_commands"]["mean_ms"] == 150
    buzzer = reader.diagnostics()["buzzer"]
    assert buzzer["enqueued_total"] == 100
    assert buzzer["dequeued_total"] == 1
    assert buzzer["write_calls_total"] == buzzer["write_returns_total"] == 1
    assert buzzer["responses_total"] == buzzer["success_responses_total"] == 1
    assert buzzer["timings"]["transaction"]["mean_ms"] == 150


def test_buzzer_diagnostics_distinguish_timeout_and_keep_no_identifiers():
    reader, ser = make_reader([[]])
    reader.beep()
    reader._send_queued(ser)
    diagnostics = reader.diagnostics()["buzzer"]
    assert diagnostics["enqueued_total"] == diagnostics["dequeued_total"] == 1
    assert diagnostics["write_calls_total"] == diagnostics["write_returns_total"] == 1
    assert diagnostics["no_response_total"] == 1
    assert diagnostics["responses_total"] == 0
    assert "epc" not in str(diagnostics).lower()


def test_buzzer_diagnostics_count_dequeue_blocked_by_recovery(monkeypatch):
    reader, ser = make_reader([])
    reader.beep()
    monkeypatch.setattr(reader, "_recover_pending", lambda serial: False)
    reader._send_queued(ser)
    diagnostics = reader.diagnostics()["buzzer"]
    assert diagnostics["dequeued_total"] == 1
    assert diagnostics["dequeued_without_write_total"] == 1
    assert diagnostics["write_calls_total"] == 0

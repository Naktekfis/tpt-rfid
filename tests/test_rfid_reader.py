import time

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


def test_thread_reads_info_then_polls_and_survives_missing_port():
    info = response_frame(0x21, 0x00, bytes((3, 1, 0x0C, 2, 0x4E, 0, 0x1A, 3)))
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("no such port")
        return FakeSerial([[info], [inv(EPC_A)]])

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

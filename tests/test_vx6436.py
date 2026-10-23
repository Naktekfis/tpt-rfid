"""Synthetic protocol fixtures, not recordings from a VX6436 device."""

from __future__ import annotations

import pytest

from tests.test_rfid_reader import FakeSerial
from tests.test_vx6336 import EPC_A, EPC_B, response_frame
from utils import vx6436
from utils.rfid_reader import RFIDReaderMock, VX6336Reader, create_rfid_reader
from utils.vx6436_reader import VX6436Reader


class Transport(FakeSerial):
    def write(self, data):
        super().write(data)
        return len(data)


def inv(*epcs, status=1):
    data = bytes((1, len(epcs)))
    for epc in epcs:
        raw = bytes.fromhex(epc)
        data += bytes((len(raw),)) + raw + b"\xb0"
    return response_frame(1, status, data)


def make_reader(replies):
    reader = VX6436Reader()
    reader.response_timeout = 0.002
    return reader, Transport(replies)


def test_documented_minimal_request_and_frame_crc():
    # Calculated from manual §3; synthetic, not a hardware capture.
    assert vx6436.inventory_command() == bytes.fromhex("0600010400AC36")
    assert vx6436.reader_info_command() == bytes.fromhex("040021D96A")


@pytest.mark.parametrize("cmd", [3, 4, 5, 6, 0x22, 0x25, 0x28, 0x2F, 0x33, 0x35, 0x40])
def test_no_writes_or_configuration_builders(cmd):
    with pytest.raises(ValueError):
        vx6436.build_command(cmd)


@pytest.mark.parametrize("data", [b"", b"\x10\x00", b"\x04\x04", b"\x04\x00\x00"])
def test_inventory_refuses_unsupported_fields(data):
    with pytest.raises(ValueError):
        vx6436.build_command(1, data)


def test_factory_profiles_and_hardware_lock(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Hardware must never be opened")

    monkeypatch.setattr("serial.Serial", forbidden)
    assert isinstance(create_rfid_reader(enabled=True), VX6336Reader)
    reader = create_rfid_reader(enabled=True, model="vx6436")
    assert isinstance(reader, VX6436Reader)
    assert reader.status()["transport"] == "blocked"
    assert reader.status()["connected"] is False
    with pytest.raises(RuntimeError, match="not validated"):
        reader.start()
    assert reader._thread is None
    reader.beep()
    reader.stop()
    for enabled in (True, False):
        with pytest.raises(ValueError, match="Unknown RFID"):
            create_rfid_reader(enabled=enabled, model="typo")


def test_disabled_vx6436_supports_app_mock_contract():
    mock = create_rfid_reader(model="vx6436", scan_duration=12)
    assert isinstance(mock, RFIDReaderMock)
    assert mock.scan_duration == 12
    mock.simulate_scan(EPC_A)
    assert mock.get_current_uid() == EPC_A
    mock.clear()
    assert mock.get_current_uid() is None
    import threading

    done = threading.Event()
    rounds = []

    def on_round(epcs):
        rounds.append(epcs)
        done.set()

    mock.add_round_listener(on_round)
    try:
        mock.set_present([EPC_A, EPC_B])
        assert done.wait(1)
        assert rounds[-1] == sorted([EPC_A, EPC_B])
    finally:
        mock.stop()


def test_multiframe_inventory_and_debounce_preserve_epcs():
    reader, ser = make_reader([[inv(EPC_A, status=3), inv(EPC_B)], [inv(EPC_A)]])
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(ser) == [EPC_A, EPC_B]
    assert rounds == [[EPC_A, EPC_B]]
    reader.clear()
    assert reader.poll_once(ser) == []
    assert rounds[-1] == [EPC_A]
    assert reader.get_current_uid() is None
    assert ser.written == [vx6436.inventory_command()] * 2
    tags = vx6436.inventory_tags(vx6436.FrameSplitter().feed(inv(EPC_A))[0])
    assert tags == [vx6436.Tag(EPC_A, 0xB0)]


@pytest.mark.parametrize(
    "frames",
    [
        [],
        [inv(EPC_A, status=3)],
        [inv(status=2)],
        [inv(status=4)],
        [response_frame(1, 0xF9)],
        [response_frame(1, 0)],
        [inv(EPC_A, status=3), response_frame(1, 0xFB)],
    ],
)
def test_failures_and_partial_rounds_never_emit_absence(frames):
    reader, ser = make_reader([frames])
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(ser) == []
    assert rounds == []
    assert reader.diagnostics()["skipped_presence_rounds_total"] == 1


@pytest.mark.parametrize("frame", [inv(), response_frame(1, 0xFB)])
def test_complete_empty_round_is_emitted(frame):
    reader, ser = make_reader([[frame]])
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(ser) == []
    assert rounds == [[]]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00\x00",
        b"\x01\x01",
        b"\x01\x00\xaa",
        b"\x01\x01\x02\xaa\xbb",
        b"\x01\x01\x00\xb0",
    ],
)
def test_malformed_inventory_never_emits(data):
    reader, ser = make_reader([[response_frame(1, 1, data)]])
    rounds = []
    reader.add_round_listener(rounds.append)
    with pytest.raises(vx6436.ProtocolError):
        reader.poll_once(ser)
    assert rounds == []


def test_bad_crc_and_wrong_address_never_emit():
    raw = bytearray(inv(EPC_A))
    raw[-1] ^= 0xFF
    reader, ser = make_reader(
        [[bytes(raw), inv()], [response_frame(1, 1, b"\x01\x00", addr=1)]]
    )
    rounds = []
    reader.add_round_listener(rounds.append)
    with pytest.raises(vx6436.ProtocolError):
        reader.poll_once(ser)
    reader.poll_once(ser)
    assert rounds == []


INFO = bytes.fromhex("01140F0213401A0A01000000")


def test_reader_info_has_vx6436_specific_layout():
    info = vx6436.parse_reader_info(
        vx6436.FrameSplitter().feed(response_frame(0x21, 0, INFO))[0]
    )
    assert info.reader_type == 0x0F
    assert info.power == 26 and info.scan_time == 10
    for data in (INFO[:8], INFO[:2] + b"\xd1" + INFO[3:]):
        with pytest.raises(vx6436.ProtocolError):
            vx6436.parse_reader_info(
                vx6436.FrameSplitter().feed(response_frame(0x21, 0, data))[0]
            )


def test_injected_transport_startup_only_reads_and_has_one_owner():
    reader = None

    class StoppingTransport(Transport):
        def write(self, data):
            result = super().write(data)
            if len(self.written) == 3:
                reader._stop.set()
            return result

    ser = StoppingTransport([[response_frame(0x21, 0, INFO)], [inv(EPC_A)]])
    opens = []

    def factory():
        opens.append(True)
        return ser

    reader = VX6436Reader(serial_factory=factory)
    reader._run()
    assert len(opens) == 1 and ser.closed
    assert [frame[2] for frame in ser.written] == [0x21, 0x01, 0x01]
    assert reader.get_current_uid() == EPC_A
    assert reader.connected is False
    assert reader.status()["buzzer_supported"] is False

from __future__ import annotations

import threading

import pytest

from utils.nfc_reader import (
    NFCReaderMock,
    PN532Reader,
    create_nfc_reader,
    normalize_uid,
    parse_target,
)

UID = "04A1B2C3"


@pytest.mark.parametrize(
    "uid", [UID.lower(), bytes.fromhex(UID), bytearray.fromhex(UID)]
)
def test_normalize_uid(uid):
    assert normalize_uid(uid) == UID


@pytest.mark.parametrize("size", [4, 7, 10])
def test_all_iso14443a_uid_lengths(size):
    assert normalize_uid(bytes(range(size))) == bytes(range(size)).hex().upper()


@pytest.mark.parametrize(
    "uid", [None, 123, "", "00", "ZZ123456", "04:A1:B2:C3", "0" * 24]
)
def test_invalid_uid_is_rejected_without_disclosing_it(uid):
    with pytest.raises(ValueError, match="NFC UID"):
        normalize_uid(uid)


def test_debounce_tolerates_missed_read_and_retap_after_absence():
    now = [0.0]
    reader = NFCReaderMock(absent_timeout=1, clock=lambda: now[0])
    assert reader.set_present(UID)["sequence"] == 1
    now[0] = 0.3
    reader.set_present(None)
    now[0] = 0.5
    assert reader.set_present(UID) is None
    now[0] = 1.4
    assert reader.set_present(UID) is None
    now[0] = 2.5
    assert reader.set_present(UID)["sequence"] == 2


def test_explicit_mock_taps_and_sequence_cursor_return_independent_events():
    reader = create_nfc_reader()
    assert reader.latest_event() is None
    assert reader.simulate_scan(UID)["sequence"] == 1
    event = reader.latest_event()
    event["uid"] = "tampered"
    assert reader.latest_event()["uid"] == UID
    assert reader.latest_event(after_sequence=1) is None
    assert reader.simulate_scan(UID)["sequence"] == 2
    assert reader.status() == {
        "mode": "mock",
        "connected": True,
        "sequence": 2,
        "firmware": None,
    }


def test_listener_failure_and_mutation_do_not_break_other_consumers(caplog):
    reader = NFCReaderMock()
    received = []

    def broken(event):
        event["uid"] = "changed"
        raise ValueError(UID)

    reader.add_listener(broken)
    reader.add_listener(received.append)
    reader.simulate_scan(UID)
    assert received[0]["uid"] == UID
    assert reader.latest_event()["uid"] == UID
    assert UID not in caplog.text


def test_thread_reconnects_configures_sam_and_closes_bus_without_logging_uid(caplog):
    attempts = []
    buses = []
    received = threading.Event()

    class Bus:
        closed = False

        def deinit(self):
            self.closed = True

    class Device:
        firmware_version = (0x32, 1, 6, 7)
        ready = False

        def SAM_configuration(self):
            self.ready = True

        def call_function(self, command, params, response_length, timeout):
            assert self.ready
            assert timeout == 0.05 and command == 0x4A
            # Targets, tg, ATQA, SAK, UID length, UID, ATS.
            return bytes.fromhex("0101" + "0004" + "28" + "04" + UID + "0C788071")

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError(UID)
        bus = Bus()
        buses.append(bus)
        return Device(), bus

    reader = PN532Reader(device_factory=factory, retry_delay=0.01, poll_timeout=0.05)
    reader.add_listener(lambda event: received.set())
    reader.start()
    try:
        assert received.wait(2)
        assert reader.status()["connected"]
        assert reader.status()["firmware"] == (0x32, 1, 6, 7)
        assert reader.latest_event()["uid"] == UID
        assert reader.latest_event()["card"] == {
            "atqa": "0004",
            "sak": 0x28,
            "ats": "0C788071",
        }
    finally:
        reader.stop()
    assert not reader.status()["connected"]
    assert all(bus.closed for bus in buses)
    assert len(attempts) >= 2
    assert UID not in caplog.text


def test_real_reader_disallows_mock_injection_and_factory_has_no_side_effect():
    calls = []
    reader = create_nfc_reader(enabled=True, device_factory=lambda: calls.append(1))
    assert calls == []
    with pytest.raises(RuntimeError, match="disabled"):
        reader.simulate_scan(UID)
    assert not reader.status()["connected"]


def test_parse_target_handles_empty_and_truncated_answers():
    assert parse_target(None) == (None, None)
    assert parse_target(bytes([0])) == (None, None)
    assert parse_target(bytes.fromhex("0101000428040102")) == (None, None)

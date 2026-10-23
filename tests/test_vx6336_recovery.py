"""Busy-reader recovery with a virtual clock; no port or real-time waiting."""

from __future__ import annotations

import pytest

from scripts.vx6336_latency_bench import VirtualClock
from tests.test_rfid_reader import inv, NO_TAG
from tests.test_vx6336 import EPC_A, EPC_B, response_frame
from utils import rfid_reader, vx6336


def info(scan_time=255):
    return response_frame(0x21, 0, bytes((2, 32, 0xD1, 0, 0x13, 0x40, 13, scan_time)))


class TimedSerial:
    """Future device replies survive a host buffer reset, as on real hardware."""

    def __init__(self, clock, exchanges):
        self.clock = clock
        self.exchanges = list(exchanges)
        self.pending = []
        self.written = []
        self.resets = []
        self.on_read = lambda: None
        self.closed = False

    def reset_input_buffer(self):
        now = self.clock.monotonic()
        self.resets.append(now)
        self.pending = [(at, data) for at, data in self.pending if at > now]

    def write(self, command):
        self.written.append((self.clock.monotonic(), command[2]))
        expected, replies = self.exchanges.pop(0)
        assert command[2] == expected
        for delay, data in replies:
            self.pending.append((self.clock.monotonic() + delay, data))
        self.pending.sort(key=lambda item: item[0])

    @property
    def in_waiting(self):
        if self.pending and self.pending[0][0] <= self.clock.monotonic():
            return len(self.pending[0][1])
        return 0

    def read(self, size):
        self.on_read()
        now = self.clock.monotonic()
        if not self.pending or self.pending[0][0] > now + 0.05:
            self.clock.advance(0.05)
            return b""
        at, data = self.pending.pop(0)
        self.clock.advance(max(0, at - now))
        if data[size:]:
            self.pending.insert(0, (at, data[size:]))
        return data[:size]

    def close(self):
        self.closed = True


def setup(monkeypatch, exchanges):
    clock = VirtualClock()
    monkeypatch.setattr(rfid_reader, "time", clock)
    reader = rfid_reader.VX6336Reader(port="fake")
    return reader, TimedSerial(clock, exchanges), clock


def test_unknown_scantime_accepts_inventory_at_25_5_seconds(monkeypatch):
    reader, serial, clock = setup(monkeypatch, [(1, [(25.5, inv(EPC_A))])])
    assert reader.response_timeout == 26
    assert reader.poll_once(serial) == [EPC_A]
    assert clock.monotonic() == pytest.approx(25.5)
    assert reader.diagnostics()["transaction_timeouts_total"] == 0


def test_lost_startup_info_retries_after_guard_before_beep_or_inventory(monkeypatch):
    reader, serial, clock = setup(
        monkeypatch,
        [
            (0x21, [(20, NO_TAG)]),  # Previous owner's inventory, info was lost busy.
            (0x21, [(0.01, info())]),
            (0x35, [(0.01, response_frame(0x35, 0))]),
            (1, [(25.5, inv(EPC_A))]),
        ],
    )
    reader._read_info(serial)
    assert serial.written[1][0] >= 27.5
    reader._read_beep_mode(serial)
    assert reader.response_timeout == 26
    assert reader.poll_once(serial) == [EPC_A]
    assert [cmd for _, cmd in serial.written] == [0x21, 0x21, 0x35, 1]
    assert reader.diagnostics()["recovery_expirations_total"] == 1


def test_persistently_missing_info_never_starts_inventory(monkeypatch):
    reader, serial, _ = setup(monkeypatch, [(0x21, []), (0x21, [])])
    reader._stop.wait = lambda _: reader._stop.set()
    reader._serial_factory = lambda: serial
    reader._run()
    assert [cmd for _, cmd in serial.written] == [0x21, 0x21]
    assert serial.closed
    assert not reader.connected
    assert reader.reader_info is None
    assert reader.response_timeout == 26


@pytest.mark.parametrize("fragmented", [False, True])
def test_late_terminal_is_drained_without_presence_or_buzzer_writes(
    monkeypatch, fragmented
):
    terminal = inv(EPC_B)
    replies = [(0.05, inv(EPC_A, status=3))]
    if fragmented:
        replies += [(0.15, terminal[:4]), (0.5, terminal[4:])]
    else:
        replies += [(0.5, terminal)]
    reader, serial, _ = setup(
        monkeypatch,
        [
            (1, replies),
            (0x33, [(0.01, response_frame(0x33, 0))]),
            (1, [(0.01, NO_TAG)]),
        ],
    )
    reader.response_timeout = 0.2
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(serial) == []
    assert rounds == []
    reader.beep()
    reader.poll_once(serial)
    assert rounds == [[]]  # Neither recovered EPC is published.
    assert serial.written[1][0] == pytest.approx(0.5)
    assert serial.resets[1] == pytest.approx(0.5)
    diag = reader.diagnostics()
    assert diag["recovery_terminals_total"] == 1
    assert diag["recovery_expirations_total"] == 0
    assert diag["first_epc"]["samples"] == 1
    assert diag["epc_to_terminal"]["samples"] == 0


def test_missing_terminal_requires_info_ack_before_next_inventory(monkeypatch):
    reader, serial, _ = setup(
        monkeypatch,
        [
            (1, []),
            (0x21, [(0.01, info(3))]),
            (1, [(0.01, inv(EPC_B))]),
        ],
    )
    reader.response_timeout = 0.2
    reader.poll_once(serial)
    assert reader.poll_once(serial) == [EPC_B]
    assert serial.written[1][0] >= 26.2
    assert [cmd for _, cmd in serial.written] == [1, 0x21, 1]
    assert not reader.diagnostics()["needs_sync"]


def test_recovery_without_info_ack_withholds_next_inventory(monkeypatch):
    reader, serial, _ = setup(monkeypatch, [(1, []), (0x21, []), (0x21, [])])
    reader.response_timeout = 0.2
    reader.poll_once(serial)
    with pytest.raises(OSError, match="inventory withheld"):
        reader.poll_once(serial)
    assert [cmd for _, cmd in serial.written] == [1, 0x21, 0x21]


@pytest.mark.parametrize("phase", ["startup", "recovery"])
def test_stop_sends_no_followup_command(monkeypatch, phase):
    first_command = 0x21 if phase == "startup" else 1
    reader, serial, clock = setup(monkeypatch, [(first_command, [])])
    if phase == "startup":
        serial.on_read = reader._stop.set
        reader._read_info(serial)
        reader._read_beep_mode(serial)
    else:
        reader.response_timeout = 0.2
        reader.poll_once(serial)
        reader.beep()
        serial.on_read = reader._stop.set
        started = clock.monotonic()
        reader.poll_once(serial)
        assert clock.monotonic() - started <= 0.051
    assert [cmd for _, cmd in serial.written] == [first_command]


def test_reconnect_resets_old_info_and_short_timeout(monkeypatch):
    reader, serial, _ = setup(monkeypatch, [(0x21, []), (0x21, [])])
    reader.reader_info = vx6336.parse_reader_info(vx6336.parse_response(info(3)))
    reader.response_timeout = 0.8
    reader._serial_factory = lambda: serial
    reader._stop.wait = lambda _: reader._stop.set()
    reader._run()
    assert reader.reader_info is None
    assert reader.response_timeout == 26
    assert [cmd for _, cmd in serial.written] == [0x21, 0x21]


def test_wrong_address_cannot_finish_transaction_or_recovery(monkeypatch):
    wrong = response_frame(1, 1, b"\0", addr=1)
    reader, serial, _ = setup(
        monkeypatch,
        [(1, [(0.05, wrong), (0.4, wrong), (0.6, NO_TAG)]), (1, [(0.01, inv(EPC_A))])],
    )
    reader.response_timeout = 0.2
    assert reader.poll_once(serial) == []
    assert reader.poll_once(serial) == [EPC_A]
    assert serial.written[1][0] == pytest.approx(0.6)


def test_late_info_is_drained_then_retried_with_a_fresh_response(monkeypatch):
    reader, serial, _ = setup(
        monkeypatch,
        [
            (0x21, [(2, info(3))]),
            (0x21, [(0.01, info(255))]),
        ],
    )
    reader._read_info(serial)
    assert serial.written == [(0, 0x21), (2, 0x21)]
    assert reader.reader_info.scan_time == 255
    assert reader.response_timeout == 26
    assert reader.diagnostics()["recovery_terminals_total"] == 1


def test_recovery_survives_port_error_and_a_new_serial_connection(monkeypatch):
    reader, old_serial, clock = setup(monkeypatch, [(1, [])])
    reader.response_timeout = 0.2

    def unplugged():
        raise OSError("synthetic unplug")

    old_serial.on_read = unplugged
    with pytest.raises(OSError, match="synthetic unplug"):
        reader.poll_once(old_serial)
    replacement = TimedSerial(
        clock,
        [
            (0x21, [(0.01, info(255))]),
            (0x35, [(0.01, response_frame(0x35, 0))]),
            (1, [(0.01, inv(EPC_A))]),
        ],
    )
    reader._serial_factory = lambda: replacement
    reader.add_round_listener(lambda _: reader._stop.set())
    reader._run()
    assert replacement.written[0][0] >= 26.2
    assert [cmd for _, cmd in replacement.written] == [0x21, 0x35, 1]
    assert reader.reader_info.scan_time == 255
    assert replacement.closed


def test_inventory_continuation_in_recovery_does_not_release_busy_gate(monkeypatch):
    reader, serial, _ = setup(
        monkeypatch,
        [
            (1, [(0.4, inv(EPC_A, status=3)), (0.8, NO_TAG)]),
            (1, [(0.01, inv(EPC_B))]),
        ],
    )
    reader.response_timeout = 0.2
    reader.poll_once(serial)
    assert reader.poll_once(serial) == [EPC_B]
    assert serial.written[1][0] == pytest.approx(0.8)

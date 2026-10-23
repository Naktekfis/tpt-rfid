"""Synthetic serial timing obeys pyserial 3.5 size/timeout semantics."""

from __future__ import annotations

import pytest

from tests.test_rfid_reader import NO_TAG, inv
from tests.test_vx6336 import EPC_A, EPC_B, response_frame
from utils import vx6336
from utils.rfid_reader import VX6336Reader


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ScheduledSerial:
    """A read waits for its requested size, or until its timeout expires."""

    timeout = 0.05

    def __init__(self, clock, deliveries):
        self.clock = clock
        self.deliveries = deliveries
        self.pending = []
        self.buffer = bytearray()
        self.read_sizes = []

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self, command):
        self.pending = [
            (self.clock.now + delay, data) for delay, data in self.deliveries
        ]
        return len(command)

    def _receive(self):
        while self.pending and self.pending[0][0] <= self.clock.now:
            _, data = self.pending.pop(0)
            self.buffer.extend(data)

    @property
    def in_waiting(self):
        self._receive()
        return len(self.buffer)

    def read(self, size):
        self.read_sizes.append(size)
        deadline = self.clock.now + self.timeout
        self._receive()
        while len(self.buffer) < size:
            if not self.pending or self.pending[0][0] > deadline:
                self.clock.now = deadline
                break
            self.clock.now = self.pending[0][0]
            self._receive()
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


def make_reader(monkeypatch, deliveries):
    clock = Clock()
    monkeypatch.setattr("utils.rfid_reader.time.monotonic", clock)
    reader = VX6336Reader(port="synthetic")
    reader.response_timeout = 0.12
    return reader, ScheduledSerial(clock, deliveries), clock


def test_existing_read_strategy_has_no_fifty_ms_floor(monkeypatch):
    reader, serial, clock = make_reader(monkeypatch, [(0.004, inv(EPC_A))])
    assert reader.poll_once(serial) == [EPC_A]
    assert clock.now == pytest.approx(0.004)
    assert serial.read_sizes[0] == 1
    assert reader.diagnostics()["first_epc"]["last_ms"] == 4.0

    # A fixed 256-byte request would wait for all 50 ms despite a valid frame.
    serial.write(vx6336.inventory_command())
    started = clock.now
    assert serial.read(256) == inv(EPC_A)
    assert clock.now - started == pytest.approx(0.05)


def test_fragmented_multiframe_inventory_has_no_added_timeout(monkeypatch):
    first = inv(EPC_A, status=vx6336.STATUS_INVENTORY_MORE)
    last = inv(EPC_B)
    reader, serial, clock = make_reader(
        monkeypatch,
        [(0.002, first[:3]), (0.004, first[3:]), (0.007, last[:1]), (0.009, last[1:])],
    )
    assert reader.poll_once(serial) == [EPC_A, EPC_B]
    assert clock.now == pytest.approx(0.009)
    result = reader.diagnostics()
    assert result["response_status_counts_total"] == {"0x01": 1, "0x03": 1}
    assert result["terminal_status_counts_total"] == {"0x01": 1}
    assert result["rejected_rounds_with_epcs_total"] == 0


def test_silence_blocks_until_deadline_without_busy_spin(monkeypatch):
    reader, serial, clock = make_reader(monkeypatch, [])
    assert reader.poll_once(serial) == []
    assert 0.12 <= clock.now < 0.17
    assert len(serial.read_sizes) == 3
    assert reader.diagnostics()["no_response_total"] == 1
    assert reader.diagnostics()["terminal_status_counts_total"] == {}


@pytest.mark.parametrize("empty_frame", [NO_TAG, inv()])
def test_accepted_empty_rounds_are_counted(monkeypatch, empty_frame):
    reader, serial, _ = make_reader(monkeypatch, [(0.004, empty_frame)])
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(serial) == []
    assert rounds == [[]]
    assert reader.diagnostics()["accepted_empty_rounds_total"] == 1
    assert reader.diagnostics()["skipped_presence_rounds_total"] == 0


@pytest.mark.parametrize(
    "frame",
    [
        inv(EPC_A, status=vx6336.STATUS_INVENTORY_MORE),
        inv(EPC_A, status=vx6336.STATUS_INVENTORY_TIMEOUT),
        inv(EPC_A, status=vx6336.STATUS_INVENTORY_BUFFER_FULL),
    ],
)
def test_rejected_rounds_with_payload_are_counted_without_publishing(
    monkeypatch, frame
):
    reader, serial, _ = make_reader(monkeypatch, [(0.004, frame)])
    rounds = []
    reader.add_round_listener(rounds.append)
    assert reader.poll_once(serial) == []
    assert rounds == []
    result = reader.diagnostics()
    assert result["rejected_rounds_with_epcs_total"] == 1
    assert result["accepted_empty_rounds_total"] == 0
    assert result["skipped_presence_rounds_total"] == 1
    assert EPC_A not in str(result)


def test_malformed_rejected_payload_does_not_break_diagnostics(monkeypatch):
    malformed = response_frame(
        vx6336.CMD_INVENTORY, vx6336.STATUS_INVENTORY_TIMEOUT, b"\x01"
    )
    reader, serial, _ = make_reader(monkeypatch, [(0.004, malformed)])
    assert reader.poll_once(serial) == []
    assert reader.diagnostics()["rejected_rounds_with_epcs_total"] == 0
    assert reader.diagnostics()["terminal_status_counts_total"] == {"0x02": 1}

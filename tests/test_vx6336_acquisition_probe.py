"""Synthetic serial/clock tests; no application startup or physical device."""

from __future__ import annotations

import importlib.util
import json
import io
import subprocess
import sys
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "acquisition_probe",
    Path(__file__).resolve().parents[1] / "scripts/vx6336_acquisition_probe.py",
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
EPC = "E28068940000401A2C141084"


def test_standalone_import_has_no_app_package_config_or_serial_startup():
    path = Path(__file__).resolve().parents[1] / "scripts/vx6336_acquisition_probe.py"
    code = (
        "import runpy, sys; runpy.run_path(sys.argv[1], run_name='offline_probe'); "
        "assert not {'app', 'config', 'utils', 'serial'} & set(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code, str(path)], check=True)


def frame(cmd=1, status=1, data=None):
    if data is None:
        data = bytes((1, 12)) + bytes.fromhex(EPC)
    body = bytes((len(data) + 5, 0, cmd, status)) + data
    crc = probe.protocol.crc16(body)
    return body + bytes((crc & 255, crc >> 8))


class FakeSerial:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.now = 0.0
        self.writes = []

    @property
    def in_waiting(self):
        return 1

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def read(self, size):
        self.now += 0.01
        return self.chunks.pop(0) if self.chunks else b""

    def clock(self):
        return self.now


@pytest.mark.parametrize(
    "cmd,expected", [(1, "040001db4b"), (15, "04000fa5a2"), (33, "040021d96a")]
)
def test_exact_allowlisted_commands(cmd, expected):
    data = bytes((2, 32, 0xD1, 1, 0x13, 0x40, 13, 255)) if cmd == 33 else None
    port = FakeSerial([frame(cmd, 0 if cmd == 33 else 1, data)])
    result = probe.transact(port, cmd, 0.1, clock=port.clock)
    assert port.writes == [bytes.fromhex(expected)]
    assert result.scan_time == 255 if cmd == 33 else result.complete


@pytest.mark.parametrize("cmd", [0x25, 0x33, 0x35, 0x04, 0x05, 0x2F])
def test_settings_tag_writes_buzzer_all_refused(cmd):
    port = FakeSerial([])
    with pytest.raises(ValueError):
        probe.transact(port, cmd, clock=port.clock)
    assert port.writes == []


def test_split_frame_and_more_terminal_preserve_first_arrival():
    first = frame(status=3)
    port = FakeSerial([first[:3], first[3:], b"", frame(data=b"\x00")])
    result = probe.transact(port, 1, 0.1, clock=port.clock)
    assert result.complete and result.statuses == (3, 1)
    assert result.hits == ((0.02, EPC),)
    assert result.end == 0.04
    assert len(port.writes) == 1


@pytest.mark.parametrize(
    "chunks,expected_hits", [([], 0), ([frame()[:8]], 0), ([frame(status=3)], 1)]
)
def test_timeout_empty_partial_bytes_and_missing_terminal(chunks, expected_hits):
    port = FakeSerial(chunks)
    result = probe.transact(port, 1, 0.05, clock=port.clock)
    assert not result.complete
    assert len(result.hits) == expected_hits
    assert len(port.writes) == 1
    assert result.received_bytes == sum(map(len, chunks))
    diagnostic = probe.round_diagnostic(result)
    assert "terminal_lengkap=False" in diagnostic
    assert EPC not in diagnostic


def test_crc_corruption_is_visible_not_silently_valid():
    damaged = bytearray(frame())
    damaged[-1] ^= 1
    port = FakeSerial([bytes(damaged), frame(data=b"\x00")])
    result = probe.transact(port, 1, 0.1, clock=port.clock)
    assert result.damaged_bytes and not result.hits


@pytest.mark.parametrize(
    "reply",
    [
        frame(15),
        frame(status=0xFF),
        frame(data=b"\x01\x0c\xab"),
        frame(data=b"\x01\x00"),
    ],
)
def test_unexpected_or_malformed_response_stops(reply):
    port = FakeSerial([reply])
    with pytest.raises(probe.ProbeFault):
        probe.transact(port, 1, 0.1, clock=port.clock)
    assert len(port.writes) == 1


def test_short_write_stops_without_reading():
    port = FakeSerial([])
    port.write = lambda _: 0
    with pytest.raises(probe.ProbeFault):
        probe.transact(port, 1, 0.1, clock=port.clock)
    assert port.now == 0


def test_marked_window_includes_leading_trailing_silence_and_failed_attempts():
    rounds = [
        probe.Round(9, 11, ((11, EPC),), (1,), True, 0),
        probe.Round(11, 13, (), (0xFB,), True, 0),
        probe.Round(13, 18, ((18, EPC),), (1,), True, 0),
        probe.Round(18, 21, ((21, EPC),), (1,), True, 0),
    ]
    result = probe.summarize(rounds, 10, 10, 1, 20, 1)
    assert result["first_hit_ms"] == 1000
    assert (
        result["read_rate"] == 0.5
    )  # two hit rounds / four, including start/end crossings
    assert result["longest_silence_s"] == 7
    assert not result["censored"]
    missed = probe.summarize([], 10, 10, 1, 20, 2)
    assert missed["censored"] and missed["first_hit_ms"] is None
    assert missed["longest_silence_s"] == 10
    report = probe.aggregate([result, missed])[0]
    assert report["failed_acquisitions"] == 1
    assert report["first_hit_median_ms_successes_only"] == 1000
    assert EPC not in json.dumps([result, missed, report])


def test_multiple_tags_and_incomplete_trials_excluded_from_comparison():
    r = probe.Round(10, 12, ((11, EPC), (12, "ABCD")), (3,), False, 0)
    result = probe.summarize([r], 10, 10, 15, 5, 1)
    assert not result["single_tag_valid"]
    assert result["incomplete_rounds"] == 1
    report = probe.aggregate([result])[0]
    assert report["valid_attempts"] == 0
    assert report["failed_acquisitions"] == 0
    assert report["read_rate"] is None


def test_trial_timeout_does_not_issue_next_command(monkeypatch, capsys):
    port = FakeSerial([frame(data=b"\x00")])
    monkeypatch.setattr(probe.time, "monotonic", port.clock)
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(probe.select, "select", lambda *_: ([probe.sys.stdin], [], []))
    # First empty round completes, next baseline round times out: stop before arming.
    with pytest.raises(probe.ProbeFault):
        probe.placement_trial(port, 1, 5, 1, 10, 0.05)
    assert len(port.writes) == 2
    assert EPC not in capsys.readouterr().out


@pytest.mark.parametrize("incomplete", [False, True])
def test_live_marker_keeps_first_hit_and_emits_no_identifier(
    monkeypatch, capsys, incomplete
):
    now = [0.0]
    calls = []
    monkeypatch.setattr(probe.time, "monotonic", lambda: now[0])
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(probe.sys, "stdin", io.StringIO("\n"))
    monkeypatch.setattr(probe.select, "select", lambda *_: ([probe.sys.stdin], [], []))

    def simulated_round(port, cmd, timeout, tick=lambda: None):
        calls.append(cmd)
        start = now[0]
        tick()
        now[0] += 1
        hits = ((now[0], EPC),) if now[0] > 2 else ()
        return probe.Round(
            start, now[0], hits, (1,), not (incomplete and bool(hits)), 0
        )

    monkeypatch.setattr(probe, "transact", simulated_round)
    if incomplete:
        with pytest.raises(probe.ProbeFault):
            probe.placement_trial(None, 15, 10, 1, 10, 27)
        assert len(calls) == 3  # two baseline rounds, one partial round; no retry
    else:
        result = probe.placement_trial(None, 15, 10, 1, 10, 27)
        assert result["marker_monotonic_s"] == 2
        assert result["first_hit_ms"] == 1000
        assert result["rounds"] == 10
    output = capsys.readouterr().out
    assert "MARK 2.000000" in output
    assert EPC not in output


@pytest.mark.parametrize("clears", [True, False])
def test_baseline_warns_and_waits_for_tag_removal(monkeypatch, capsys, clears):
    now = [0.0]
    calls = []
    monkeypatch.setattr(probe.time, "monotonic", lambda: now[0])
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(probe.sys, "stdin", io.StringIO("\n"))
    monkeypatch.setattr(probe.select, "select", lambda *_: ([probe.sys.stdin], [], []))

    def simulated_round(port, cmd, timeout, tick=lambda: None):
        calls.append(cmd)
        start = now[0]
        tick()
        now[0] += 1
        baseline_hit = now[0] <= 3 or not clears
        hits = ((now[0], EPC),) if baseline_hit or now[0] > 5 else ()
        return probe.Round(start, now[0], hits, (1,), True, 0)

    monkeypatch.setattr(probe, "transact", simulated_round)
    if clears:
        result = probe.placement_trial(None, 1, 10, 1, 10, 27)
        assert result["marker_monotonic_s"] == 5
        assert result["first_hit_ms"] == 1000
    else:
        with pytest.raises(probe.ProbeFault, match="30 detik"):
            probe.placement_trial(None, 1, 10, 1, 10, 27)
        assert len(calls) == 30
    output = capsys.readouterr().out
    assert output.count("MASIH ADA TAG TERBACA") == 1
    assert EPC not in output


def test_tag_seen_during_approach_continues_and_is_not_false_first_acquisition(
    monkeypatch, capsys
):
    now = [0.0]
    monkeypatch.setattr(probe.time, "monotonic", lambda: now[0])
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(probe.sys, "stdin", io.StringIO("\n"))
    monkeypatch.setattr(
        probe.select,
        "select",
        lambda *_: ([probe.sys.stdin] if now[0] >= 4 else [], [], []),
    )

    def simulated_round(port, cmd, timeout, tick=lambda: None):
        start = now[0]
        tick()
        now[0] += 1
        hits = ((now[0], EPC),) if now[0] > 2 else ()
        return probe.Round(start, now[0], hits, (1,), True, 0)

    monkeypatch.setattr(probe, "transact", simulated_round)
    result = probe.placement_trial(None, 1, 10, 1, 10, 27)
    assert now[0] == 14
    assert result["pre_marker_detected"]
    assert result["first_hit_ms"] is None
    assert result["first_detection_relative_marker_ms"] == -1000
    assert not result["censored"]
    assert result["read_rate"] == 1
    report = probe.aggregate([result])[0]
    assert report["pre_marker_attempts"] == 1
    assert report["acquisition_valid_attempts"] == 0
    assert report["failed_acquisitions"] == 0
    assert report["first_hit_median_ms_successes_only"] is None
    output = capsys.readouterr().out
    assert "Tes tetap lanjut" in output and "SELESAI" in output
    assert EPC not in output


def test_early_hit_without_later_reads_is_not_censored_acquisition_failure():
    result = probe.summarize([], 10, 10, 1, 20, 1, pre_marker_first_hit=9)
    assert result["first_hit_ms"] is None and not result["censored"]
    assert result["longest_silence_s"] == 10
    assert probe.aggregate([result])[0]["failed_acquisitions"] == 0

"""Run with --noconftest: standalone synthetic app, no project app startup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.uhf_loss_latency_bench import run_loss_case  # noqa: E402
from scripts.vx6336_latency_bench import SYNTHETIC_EPC  # noqa: E402


@pytest.mark.parametrize(
    "name, missing_ms, pre_queue_ms, queue_ms, skipped",
    [
        ("healthy", 5062.5, 0, 0, 0),
        ("rejected_empty_02", 7062.5, 0, 0, 112),
        ("rejected_empty_04", 7062.5, 0, 0, 112),
        ("no_poll_for_8s", 8062.5, 0, 0, 0),
        ("observer_750ms", 5062.5, 750, 0, 0),
        ("tail_listener_500ms", 5062.5, 0, 500, 0),
        ("three_commands_ahead", 5062.5, 0, 375, 0),
        ("inventory_timeout", 26312.5, 0, 0, 1),
    ],
)
def test_loss_stages_are_separate(name, missing_ms, pre_queue_ms, queue_ms, skipped):
    result = run_loss_case(name)
    assert result["last_sighting_to_missing_ms"] == missing_ms
    assert result["missing_to_alarm_beep_enqueue_ms"] == pre_queue_ms
    assert result["alarm_beep_enqueue_to_write_call_ms"] == queue_ms
    assert result["skipped_presence_rounds"] == skipped
    assert result["transaction_timeouts"] == (1 if name == "inventory_timeout" else 0)
    trace = result["trace"]
    stages = [e["stage"] for e in trace]
    probe = next(e for e in trace if e["stage"] == "api_before_alarm_beep_enqueue")
    assert probe["presence"] == "missing" and probe["alarm_count"] == 1
    assert stages.index("missing_event") < stages.index("missing_committed")
    assert stages.index("missing_committed") < stages.index("alarm_committed")
    assert stages.index("alarm_committed") < stages.index("beep_enqueued")
    assert stages.index("api_after_loss_round_before_next_poll") < stages.index(
        "buzzer_write_called"
    )
    assert stages.count("buzzer_response_received") == stages.count("beep_enqueued")
    assert SYNTHETIC_EPC not in str(result)
    if name == "healthy":
        boundary = next(
            e for e in trace if e["stage"] == "api_at_exact_missing_threshold"
        )
        assert boundary["virtual_ms"] == 5000
        assert boundary["presence"] == "present" and boundary["alarm_count"] == 0
    if name == "no_poll_for_8s":
        stalled = next(e for e in trace if e["stage"] == "api_after_8s_without_round")
        assert stalled["presence"] == "present" and stalled["alarm_count"] == 0


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError):
        run_loss_case("not-a-scenario")

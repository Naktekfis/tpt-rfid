from utils.presence import PresenceMonitor


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def kinds(events):
    return [(e.kind, e.epc) for e in events]


def make():
    clock = Clock()
    return PresenceMonitor(missing_after=5.0, clock=clock), clock


def test_first_sighting_is_new_once():
    m, clock = make()
    assert kinds(m.update(["A"])) == [("new", "A")]
    clock.t = 1
    assert m.update(["A"]) == []


def test_empty_boot_round_reports_nothing():
    m, clock = make()
    assert m.update([]) == []
    clock.t = 100
    assert m.update([]) == []


def test_left_after_missing_after_and_only_once():
    m, clock = make()
    m.update(["A", "B"])
    clock.t = 5
    assert m.update(["B"]) == []  # exactly missing_after: not yet
    clock.t = 5.1
    assert kinds(m.update(["B"])) == [("left", "A")]
    clock.t = 20
    assert m.update(["B"]) == []
    assert m.snapshot()["A"]["state"] == "missing"
    assert m.snapshot()["B"]["state"] == "present"


def test_empty_rounds_advance_time():
    m, clock = make()
    m.update(["A"])
    clock.t = 6
    assert kinds(m.update([])) == [("left", "A")]


def test_back_after_missing():
    m, clock = make()
    m.update(["A"])
    clock.t = 10
    m.update([])
    clock.t = 11
    assert kinds(m.update(["A"])) == [("back", "A")]
    assert m.snapshot()["A"] == {"state": "present", "last_seen": 11}


def test_short_gap_is_not_left():
    m, clock = make()
    m.update(["A"])
    clock.t = 3
    assert m.update([]) == []
    clock.t = 4
    assert m.update(["A"]) == []


def test_duplicate_epcs_in_round():
    m, _ = make()
    assert kinds(m.update(["A", "A"])) == [("new", "A")]


def test_diagnostics_report_threshold_gaps_and_observed_departure_delay():
    monitor, clock = make()
    monitor.update(["PRIVATE_EPC"])
    clock.t = 2
    monitor.update(["PRIVATE_EPC"])
    clock.t = 8
    monitor.update([])
    diagnostics = monitor.diagnostics()
    assert diagnostics["missing_after_s"] == 5
    assert diagnostics["tracked_tags"] == 1
    assert diagnostics["present_tags"] == 0
    assert diagnostics["missing_tags"] == 1
    assert diagnostics["sighting_gap"]["max_ms"] == 2000
    assert diagnostics["departure_delay"]["max_ms"] == 6000
    assert diagnostics["oldest_sighting_age_s"] == 6
    assert "PRIVATE_EPC" not in str(diagnostics)


def test_diagnostic_gap_samples_are_bounded():
    monitor, clock = make()
    for t in range(150):
        clock.t = t
        monitor.update(["PRIVATE_EPC"])
    diagnostics = monitor.diagnostics()
    assert diagnostics["sighting_gap"]["samples"] == 120
    assert diagnostics["sighting_gap"]["mean_ms"] == 1000

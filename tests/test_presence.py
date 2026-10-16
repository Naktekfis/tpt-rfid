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

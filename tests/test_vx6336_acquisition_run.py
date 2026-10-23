"""Exercise the wrapper with fake services, serial port and probe executable."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


WRAPPER = Path(__file__).resolve().parents[1] / "scripts/vx6336_acquisition_run.sh"
FAKE = """#!/usr/bin/env python3
import os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['TRACE'], 'a') as log:
    log.write(name + ' ' + ' '.join(args) + '\\n')
if name == 'sudo':
    if args == ['-v']:
        sys.exit(0)
    os.execvp(args[0], args)
if name == 'systemctl':
    state = Path(os.environ['STATE'])
    if args[0] == 'show':
        if os.environ.get('QUERY_FAIL') == '1':
            sys.exit(1)
        print(state.read_text())
    elif args[0] == 'stop':
        if os.environ.get('STOP_FAIL') != '1':
            state.write_text('inactive')
    elif args[0] == 'start':
        if os.environ.get('START_FAIL') == '1':
            sys.exit(1)
        state.write_text('active')
    elif args[0] == 'is-active':
        print(state.read_text())
        sys.exit(0 if state.read_text() == 'active' else 3)
elif name == 'fuser':
    sys.exit(int(os.environ.get('OWNER_STATUS', '1')))
elif name == 'fake-python':
    print('SYNTHETIC PROBE')
    sys.exit(int(os.environ.get('PROBE_EXIT', '0')))
"""


def run_wrapper(tmp_path, initial, **settings):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("sudo", "systemctl", "fuser", "sleep", "fake-python"):
        path = bindir / name
        path.write_text(FAKE)
        path.chmod(0o700)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/vx6336_acquisition_probe.py").touch()
    port = tmp_path / "fake-port"
    port.touch()
    state = tmp_path / "state"
    state.write_text(initial)
    trace = tmp_path / "trace"
    env = dict(
        os.environ,
        PATH=str(bindir) + os.pathsep + os.environ["PATH"],
        STATE=str(state),
        TRACE=str(trace),
        VX6336_PROBE_PORT=str(port),
        VX6336_PROBE_PYTHON=str(bindir / "fake-python"),
        **settings,
    )
    result = subprocess.run(
        ["bash", str(WRAPPER), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, trace.read_text(), state.read_text()


@pytest.mark.parametrize("initial", ["active", "inactive"])
def test_runs_and_restores_original_service_state(tmp_path, initial):
    result, trace, state = run_wrapper(tmp_path, initial)
    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC PROBE" in result.stdout
    assert "sleep 27" in trace
    assert state == initial
    assert ("systemctl stop" in trace) == (initial == "active")
    assert ("systemctl start" in trace) == (initial == "active")
    assert len(list(tmp_path.glob("results.*"))) == 1


@pytest.mark.parametrize("initial", ["active", "inactive"])
def test_owned_port_prevents_probe(tmp_path, initial):
    result, trace, state = run_wrapper(tmp_path, initial, OWNER_STATUS="0")
    assert result.returncode == 2
    assert "fake-python " not in trace
    assert "sleep 27" not in trace
    assert state == initial


@pytest.mark.parametrize(
    "initial,settings",
    [
        ("failed", {}),
        ("activating", {}),
        ("active", {"QUERY_FAIL": "1"}),
        ("active", {"STOP_FAIL": "1"}),
        ("inactive", {"OWNER_STATUS": "2"}),
    ],
)
def test_uncertain_service_or_owner_check_prevents_probe(tmp_path, initial, settings):
    result, trace, _ = run_wrapper(tmp_path, initial, **settings)
    assert result.returncode == 2
    assert "fake-python " not in trace


def test_probe_error_still_restores_active_service(tmp_path):
    result, trace, state = run_wrapper(tmp_path, "active", PROBE_EXIT="2")
    assert result.returncode == 2
    assert "sleep 27" in trace and state == "active"


def test_recovery_error_is_visible_and_nonzero(tmp_path):
    result, _, state = run_wrapper(tmp_path, "active", START_FAIL="1")
    assert result.returncode == 2 and state == "inactive"
    assert "PEMULIHAN GAGAL" in result.stderr

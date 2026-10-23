# VX6336 timeout/busy recovery — local candidate, not deployed

## Goal and current authorization

Continue first-acquisition investigation through offline timeout/busy diagnosis
and fixes. User explicitly permits local code/tests, forbids all Jetson commands,
service changes, physical tests, reader setting changes and tag writes without
fresh permission. Do not repeat deployment or VX6436 work. Preserve all local
changes, data, probe results and backups. No commits or cleanup performed.

This supersedes the earlier deployed handoff's suggested SSH next step and its
last-known active service state. User subsequently reported last-known service
inactive. Actual current state is unknown and was NOT checked this session.

Local branch `main`, HEAD `99cc143`, heavily dirty before and after this task.
`AGENTS.md`, GATES, reader/platform/face references and deployed handoff read.
`RTK.md` referenced by user instructions was not found at repository root.

## Diagnosis and changes

Previous local driver had initial1.5 s fallback, changed only by successful
reader-info to ScanTime/10 +0.5; 255 means26 s. Missing info continued startup;
reconnect reused old info. Timeout did not retain outstanding command state;
next transaction reset input and sent immediately, risking busy command loss
and stale inventory terminal attribution.

Changed locally:

- `utils/rfid_reader.py`: unknown inventory fallback26 s; reset info/timeout at
  connection open; separate control deadline1.5 s; startup info retry once after
  recovery, then fail/reconnect if no valid info. ScanTime outside3..255 rejected.
- Pending transaction retains command, splitter and guard across timeout and
  I/O errors/reconnect. Recovery blocks new commands until matching-address
  terminal, or until extra26 s after original response deadline. Recovered
  EPCs/empty rounds never advance presence or new inventory timing. Status03
  keeps waiting. Guard expiry requires successful fresh read-only info before
  further beep/inventory. Missing info acknowledgment withholds inventory.
- Stop checked before writes and inside recovery. New identifier-free recovery
  counters/state are exposed by existing diagnostics. Startup stays read-only
  `35 00`; no config/tag commands added.
- `tests/test_vx6336_recovery.py`: 14 parameterized test cases with virtual time,
  including25.5 s inventory, lost/late/permanently missing info, late fragmented
  terminal, continuation, silence, handshake failure, address mismatch, old
  info reset, I/O reconnect, and stop during startup/recovery.
- `scripts/vx6336_latency_bench.py`: synthetic read-only info acknowledgments
  support actual recovery; no serial opener. `tests/test_vx6336_latency.py`:
  fault-case virtual dispatch changes350→26350 ms, reflecting the guard and
  immediate synthetic handshake. No physical-speed claim.
- `docs/hardware/vx6336/timeout-recovery.md`: diagnosis, behavior, limits and
  diagnostics. Existing latency doc updated for new fault timing and latest
  physical-test constraints.

Tradeoff: no-terminal inventory at maximum ScanTime can wait about52 s from
send plus info/retry overhead. Earlier matching terminal releases immediately.
Normal complete rounds have no deliberate added wait. Firmware responses must
be ordered and the serial port must have one owner. No transaction IDs exist;
arbitrary firmware delay cannot be proven safe by a guard/handshake. A reader
that permanently refuses info now stays unavailable instead of degraded polling.

## Exact verification

- Targeted: `.venv/bin/python -m pytest -q tests/test_vx6336_recovery.py tests/test_rfid_reader.py tests/test_vx6336_latency.py`
  — **52 passed in0.96 s**.
- Final full: `scripts/check.sh` — Ruff passed; **327 passed,1 skipped in9.42 s**.
- `.venv/bin/python -m py_compile app.py config.py utils/*.py routes/*.py scripts/vx6336_latency_bench.py tests/test_vx6336_recovery.py` — passed.
- `git diff --check` — passed.
- `ruff format --check utils/rfid_reader.py scripts/vx6336_latency_bench.py tests/test_vx6336_latency.py tests/test_vx6336_recovery.py` — passed.
- Independent read-only scoped review found no concrete breaking issue; did not
  rerun green checks. No Python3.8 runtime execution or physical validation claimed.

An earlier targeted run was47 passed/2 failed: the two old350 ms benchmark
expectations needed updating for the intentional26 s guard; final run above
includes corrected expectations and additional recovery cases.

## Remaining investigation

Offline fix is complete locally and NOT deployed. It does not establish that
recovery fixes physical first-acquisition delay. No new acquisition measurements.

Existing temporary Jetson probe is `/home/tpt/vx6336-acquisition.ALhJ5S/` with
`results.*` retained there. Local acquisition probe/run scripts unchanged.
Distance options are10/20/30 cm due to casing. ENTER-marker placement failed
because tags could be acquired during movement before ENTER; do not repeat it.
Repeated sightings are not first-acquisition measurements.

Any subsequent Jetson inspection, deployment, service action or physical trial
needs fresh permission; then check current service/serial ownership before
taking action. The user's later priority change below supersedes continuing
reader investigation next.

## Clarification: what causes the first-acquisition delay?

The primary physical cause is still UNKNOWN. The proven finding is a software
failure path that can worsen delay WHEN a timeout occurs: missing reader-info
left a1.5 s timeout; inventory could still be busy for up to25.5 s; another
command could be lost while busy, while its late terminal could be discarded
or attributed to the wrong round. Code and synthetic tests establish this
possibility, not that it caused the delay the user observed on hardware.

The earlier approximately50 ms live inventory timings describe repeated
sightings after a tag was already acquired, not placement-to-first-acquisition.
Distance, orientation, casing and nearby metal remain possible RF factors,
not established causes. The local timeout/recovery fix cannot yet be claimed
to solve the physical first-acquisition problem.

## Latest user direction: pause now; UI/UX after /clear

User asked to record the explanation above, defer all ongoing work now, and
prepare a kickoff message for a new session after `/clear`. The next objective
is a more mature UI/UX cleanup. No UI implementation or additional reader work
was started in this turn. All existing edits/results/backups remain preserved.

In the next session, read AGENTS/GATES and this handoff, inspect current UI
and working-tree changes, then improve the existing kiosk and admin UI/UX
locally. Focus on clear flows, visual hierarchy, consistency, readable copy,
touch interaction and loading/empty/error feedback. Infer priorities from the
actual screens before editing. Keep reader investigation/deployment paused;
do not change hardware settings, auth/security logic, or live data as part of
visual cleanup. Run relevant local checks after implementation. Do not discard
preexisting changes or revive archived face/VX6436 work.

This handoff-only update was checked with `git diff --check`; the327-pass suite
above belongs to the completed recovery implementation and was not rerun for
this documentation-only update.

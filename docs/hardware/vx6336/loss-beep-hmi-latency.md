# Local loss → reader beep → HMI diagnosis (2026-10-23)

Scope: local source and synthetic execution only. No Jetson, device/service
actions, real data, settings, commit or deployment. Existing application code,
UI work, recovery implementation and VX6436 work are preserved.

User reports all HMI pages feel slow and the sound comes from the reader.
That identifies the sound source, but does not establish whether it is the
application's queued loss alarm (`0x33`) or firmware automatic read beep.
The loss-alarm trace below is conditional on the former. Current device source,
configuration, beep mode and timings remain unknown.

## Facts verified against local code

- `utils/presence.py`: departure requires an accepted round without the tag,
  strictly more than `missing_after` since its last accepted sighting. Default
  is 5 seconds; effective device value is unknown. No independent departure
  timer runs during a reader stall. Physical removal can occur after the last
  accepted sighting, so those two origins must not be equated in real trials.
- `utils/rfid_reader.py`: incomplete, invalid, status 02 and status 04 rounds
  do not advance presence. Rejected rounds cannot prove absence.
- `utils/tool_presence.py`: outside an active borrowing session, an available
  tool's loss follows missing commit → alarm commit → evidence observer →
  beep enqueue. All events/listeners run sequentially on the reader thread.
  Multiple departures are marked in memory before per-tool processing;
  `PresenceEvent.at` is not alarm commit time.
- One FIFO buzzer command is taken before each following inventory. Command
  removal precedes recovery/write, and failed commands are not requeued.
  Queue entry, dequeue, write call, successful write return, ACK and physical
  sound onset are distinct boundaries.
- Presence and alarm commits are separate. `/api/kiosk/state` also assembles
  its fields sequentially, without an atomic revision. A changed board alone
  does not prove that a response contains the corresponding alarm.
- Before this local HMI adjustment, kiosk polled at 1 second, monitor at
  3 seconds, admin alerts at 3 seconds, and admin tool lists at 15 seconds.
  `UI.fetchJSON` has no explicit abort deadline, so polling intervals are not
  upper bounds if requests or browser scheduling stall.
- Alarm evidence normally uses a copied latest camera frame and a worker queue.
  Queue-full fallback saves synchronously, including fsync. Saturation during
  the user's observation has not been established.

## New reproducible local evidence

Run from the repository root:

```sh
.venv/bin/python scripts/uhf_loss_latency_bench.py
.venv/bin/python -m pytest --noconftest -q tests/test_uhf_loss_latency.py
```

The benchmark creates its own Flask application with SQLite **in memory**, one
synthetic tool, an idle real Kiosk and real driver/presence/database/GET route.
It never starts a reader thread or opens serial, and does not import app.py or
config.py. The fake serial supports inventory/info and synthetic buzzer ACKs.
The observer is a test callback, not the camera/security pipeline.

Time advances only for injected waits; real DB, logging and HTTP CPU costs do
not advance that clock. HTTP host duration is separate and must not be added
to virtual measurements. Zero virtual delay means no injected delay, not zero
real execution cost. The response deadline is explicitly injected as 250 ms;
it is not the application's default 26-second inventory deadline.

All values below are **synthetic milliseconds**, not device measurements:

| Injected case | Last sighting → missing | Missing → alarm beep enqueue | Enqueue → write call |
| --- | ---: | ---: | ---: |
| Healthy, 62.5 ms complete rounds | 5062.5 | 0 | 0 |
| 112 rejected empty status 02 rounds, then complete | 7062.5 | 0 | 0 |
| 112 rejected empty status 04 rounds, then complete | 7062.5 | 0 | 0 |
| No poll for 8 seconds, then complete | 8062.5 | 0 | 0 |
| Observer adds 750 ms after alarm commit | 5062.5 | 750 | 0 |
| Following listener adds 500 ms | 5062.5 | 0 | 500 |
| Three synthetic buzzer commands ahead | 5062.5 | 0 | 375 |
| Inventory silence, recovery guard, next complete | 26312.5 | 0 | 0 |

At exactly 5000 ms the healthy case remains present. After 8 seconds without
any poll, API still reports present and no alarm. In every case the actual GET
route returns missing **and** one alarm before the application alarm beep is
enqueued. This probe is synchronous/reentrant on the test thread; it establishes
logical visibility, not concurrent SQLite or production HTTP performance.
The FIFO case injects three commands in the observer immediately before the
application beep and uses 62.5 ms ACKs and inventories. It does not reproduce
any observed backlog or assume firmware sound duration equals ACK duration.

## Local diagnostic fields added

The existing admin-only `/api/admin/diagnostics/uhf` now includes two bounded,
identifier-free sections:

- `loss`: counts accepted presence events, missing events, and application beep
  enqueues; timing summaries for event-to-handler, handler duration,
  missing-event-to-alarm-commit, alarm-commit-to-enqueue, and total
  missing-event-to-enqueue.
- `reader.buzzer`: counts enqueued/dequeued commands, serial write calls and
  returns, parsed responses split by success/error, no-response transactions,
  transactions blocked before write, and transaction errors. Timing summaries
  separate enqueue-to-dequeue, dequeue-to-write, write-to-response and
  dequeue-to-transaction completion.

Each histogram retains at most 120 values. Counters live for the process
lifetime. These timings identify software boundaries; write return and ACK do
not indicate when sound became audible. Firmware auto-read beep still has no
application timestamp.

## Local HMI adjustment

The monitor board now polls every 1 second. Admin alarm and unverified-return
state also polls every 1 second through a new admin-only
`/api/admin/kiosk/alerts` route that returns only those two lists instead of
rebuilding the full kiosk board. Admin tool/loan lists now refresh every
5 seconds (and still refresh immediately after edits). The main kiosk remains
at its existing 1-second interval. This shortens the normal poll wait; network
or API stalls remain possible. The request increase has not been measured on
the Jetson, so this change remains local and is not deployed.

Nine isolated regression tests pass for the original synthetic benchmark. The
runtime instrumentation and HMI suite passes 104 targeted tests. Together
they cover stage ordering, strict threshold,
no timer during a stall, rejected rounds, recovery, observer/listener delays,
FIFO delay, API state before write, ACK receipt and omission of EPC from output.
The standalone benchmark test uses `--noconftest` because it builds its own
synthetic app. The full repository check also passes: `scripts/check.sh` reports
339 passed and 1 skipped. Tests use the configured in-memory SQLite database.
Python 3.8 runtime validation and device validation were not performed.

## Hypotheses, still unproven on the device

1. Default departure threshold accounts for part of the perceived loss delay.
2. Accepted-round gaps/rejected rounds or recovery add delay before detection.
3. DB/locks, multiple events, evidence fallback or listeners delay beep enqueue
   or write. Source also permits failure between the two commits; that is a
   failure mode to distinguish from latency, not evidence it happened.
4. Buzzer backlog/recovery/firmware delays sound after enqueue/write.
5. Polling, API time, browser scheduling or rendering adds delay after commit.

All pages feeling slow is compatible with a shared upstream delay, and also
with shared API/resource pressure. It does not select between those hypotheses.
The local poll intervals changed; loss threshold, recovery rule and buzzer
semantics did not.

## Reviewable measurement design for a separately authorized trial

Use random trial IDs, round counters and per-trial state sequence numbers.
Do not log EPCs, student/tool identities, HTTP bodies, photos or auth material.
Use a bounded opt-in trace buffer; record dropped samples and instrumentation
cost. The design below is not installed in the running application.

| Boundary | Required observation |
| --- | --- |
| Physical action and sound | Same-clock synchronized video/audio/trigger: removal onset, final position, first audible sound; retain uncertain/censored trials |
| Inventory | Round ID, send/write return, first frame, terminal, status counts, validation/acceptance, count of EPC-bearing rejected rounds, empty accepted rounds, inter-command gap, recovery entry/exit |
| Presence | Target last accepted sighting (anonymous trial match kept only in memory), missing event and callback start/end; per-event position in round |
| Persistence | Separate presence and alarm commit start/end/success/error; trial state sequence; DB wait included |
| Evidence/listeners | Observer and each listener start/end, worker queue depth/fallback, error count |
| Buzzer | Command sequence, enqueue/dequeue/depth, recovery wait, write start/return/error, ACK/status/timeout; record dequeue-without-write explicitly |
| API | Request sequence, server entry/exit and serialization, board and alarm state sequence actually included; concurrent mixed snapshots labeled |
| Browser | Page identity, request start/response/JSON end, included sequence, DOM update, rAF proxy, hidden-tab/long-task state; dropped/overlapping/failed requests |

Measure loss intervals from both physical removal and last accepted sighting.
Distinguish removal → missing, missing → alarm commit, commit → enqueue,
enqueue → write, write → physical sound, commit → response containing that
state, and response → DOM. Never subtract browser performance.now directly
from server monotonic. Align clocks with uncertainty or use external same-clock
observation; rAF alone does not prove displayed pixels.

For before/after API probes in production, do not copy the synthetic same-thread
HTTP probe into the reader callback: that would add work to the measured path.
Use asynchronous trace correlation. Compare all three pages separately and
separate alarm banner state from admin tool-table state. Preserve failed trials
and queued-but-unsent beeps instead of selecting only successful timings.

Physical measurement, live instrumentation and any Jetson command remain outside
this session's authorization. The next safe work is local review/refinement of
this trace contract; no device permission request is necessary for that.

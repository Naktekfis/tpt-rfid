# VX6336 latency investigation

2026-10-23. No physical measurements at 20 cm have been taken in this follow-up.
The initial investigation was offline. Deployment was subsequently authorized
separately; no settings or tag writes are authorized. VX6436 hardware activation
remains outside this investigation.

## Reproduce offline

```bash
.venv/bin/python scripts/vx6336_latency_bench.py
.venv/bin/python scripts/vx6336_latency_bench.py --tools 20 --photo-kib 512
.venv/bin/python scripts/vx6336_latency_bench.py --unit-photo-kib 2048
```

Output is aggregate JSON with no EPCs. The program does not import `app.py` or
`config.py`, load `.env`, open serial, start reader threads, or connect to the
application database. It constructs a separate Flask app with SQLite `:memory:`
and synthetic tools. Only synthetic inventory 01 frames are accepted by its
transport, along with synthetic reader-info 21 replies for recovery handshakes.
All resources disappear when the process exits; no cleanup of existing
files or tables is performed.

The real frame splitter, `VX6336Reader.poll_once`, `ToolPresenceService`, database
handler, kiosk state, and GET `/api/kiosk/state` are exercised. Serial timing uses
a virtual clock. Presence CPU/database processing and HTTP test-client timings
use the host's real `perf_counter`. Do not add those clocks together or interpret
virtual dispatch time as an end-to-end physical measurement. The Flask test
client excludes TCP, browser JSON parsing, rendering and display refresh.

The cases distinguish:

| Synthetic scenario | First presence dispatch (virtual) | Meaning |
| --- | ---: | --- |
| Immediate hit | 50 ms | One complete inventory is sufficient for arrival |
| 10 empty rounds, then hit | 550 ms | Acquisition misses precede presence processing |
| 100 empty rounds, then hit | 5,050 ms | A seconds-long acquisition gap can coexist with fast processing |
| EPC at 50 ms, terminal frame at 250 ms | 250 ms | Existing driver holds sightings until the round completes |
| Partial frame, timeout, missing terminal, recovery, complete hit | 26,350 ms | Partial round does not advance presence; guard + info handshake precede next round |
| No response, timeout, recovery, complete hit | 26,350 ms | Silence requires the same guard + handshake |

These are injected test conditions, not probabilities/read rates at any distance.
The benchmark deliberately starts with a 300 ms inventory timeout, but retains
the 26 s recovery guard. The two failure cases previously dispatched at 350 ms
because the driver immediately sent again after timeout. Their new virtual
26,350 ms includes a full guard expiry and an immediate synthetic reader-info
acknowledgment; it is an intentional fault-path cost, not an RF measurement.
Production starts with a 26 s fallback and uses ScanTime + 500 ms after successful
reader-info (historical FF gives 26 s). Startup now withholds inventory when
reader-info remains unavailable. See [timeout recovery](timeout-recovery.md).

`presence_monitor_host_wall` measures pure presence logic;
`presence_service_host_wall` includes synchronous database/kiosk handling.
`presence_hit_service_host_wall` isolates rounds with the synthetic target so
empty fast rounds do not hide the arrival cost. `kiosk_get_host_wall` includes
20 actual GET requests, including the first cold request. Repeated sightings,
departure/return and multi-tool semantics also remain covered by existing reader
and presence tests.

## Instrumentation available for a future authorized run

Reader diagnostics now add bounded summaries (last 120 rounds):

- `first_frame`: command send to first complete, CRC-valid matching frame.
- `first_epc`: command send to first parsed EPC in any inventory frame.
- `epc_to_terminal`: first EPC to the final response frame, when both exist.
- Existing `inventory`, `listeners`, `queued_commands`, `total`, timeout and
  skipped-presence counters remain available.

Missing observations are excluded rather than recorded as zero. A partial round
can contain `first_epc` without an eventual terminal frame or presence update.
These measure any EPC in each round, including repeated sightings; they cannot
measure placement-to-first-acquisition for a particular physical tag. The
authenticated diagnostics route already exposes these reader summaries without
adding another serial owner. Authentication is unchanged.

For browser timing, use the kiosk URL with `?uhf_timing=1`, then inspect
`window.kioskTiming()` in the browser console. This returns bounded local-only
aggregates for schedule wait, request including JSON decode, synchronous DOM
work, and next animation-frame wait. It retains no kiosk response or identifiers
and uploads nothing. `next_frame_ms` is a frame boundary proxy, not proof of
completed paint; background tabs can throttle it. Failed requests are counted;
a request that never resolves is still a limitation of the existing fetch path.
Schedule wait is the gap between polls, not the latency of a specific tag event.
Browser timing has received a syntax check, not a physical display/paint test.

## Concrete optimizations and evidence

Implemented: board queries defer Tool, ToolType and Student photo BLOBs and use
SQLite `length(photo_data) > 0` to choose the type photo URL. The board previously
loaded those bytes on every poll. Null and empty images, borrower fields,
overdue status and untyped tools preserve their contracts, with a regression
check ensuring one query and no projected image BLOBs.

Local before/after benchmark: 20 synthetic tools sharing a type with a 512 KiB
image, six scenarios, 20 GETs each. Per-scenario mean GET time fell from
10.225–10.745 ms to 3.731–4.173 ms; p95 ranged 10.544–11.487 ms before and
3.909–6.402 ms after. These single host runs are indicative, not Jetson results.
Raw aggregate outputs for this session are `/tmp/tpt-vx6336-photo-before.json`
and `/tmp/tpt-vx6336-photo-after.json` (temporary, not durable artifacts).

Polling remains 1000 ms. The offline model uses uniformly distributed event
phases, a snapshot at request start, 20 ms request time and 5 ms DOM work:

| Poll sleep | Modeled mean event-to-DOM | Modeled maximum | Requests/s |
| --- | ---: | ---: | ---: |
| 1000 ms | 538.013 ms | 1050 ms | 0.976 |
| 500 ms | 287.763 ms | 550 ms | 1.905 |
| 250 ms | 162.638 ms | 300 ms | 3.636 |

The scheduling maximum improves by 750 ms at 250 ms polling, with higher query
load. Validate on the target before choosing a new interval, and update
`kiosk_poll_seconds` in diagnostics if it changes. Polling cannot recover RF
sightings that never occurred. The benchmark model values are explicit inputs,
not measured browser/network timing.

Additional software improvements before deployment:

- At most one FIFO buzzer command runs before each inventory. Alarm bursts no
  longer drain the entire queue ahead of acquisition. A unit test with 100 queued
  patterns and 150 ms simulated buzzer response time verifies that inventory
  waits for one command and leaves 99 queued. One slow transaction can still
  block until its response timeout; this does not solve timeout recovery.
- `get_tool_presence_info` selects only id/status/presence rather than loading
  the full Tool including its image. SQL projection and unknown-tag contracts
  are tested using a synthetic 2 MiB tool image. `--unit-photo-kib` exercises
  this path; the host before/after wall timings were noisy, so no quantitative
  speedup is claimed for this second query optimization.
- Reader startup now only reads beep mode (`35 00`), replacing the automatic
  persistent beep-off write. Existing stored mode is preserved, including when
  the service restarts or the reader reconnects. A fresh reader with beep-on
  enabled will therefore keep its current behavior until separately configured.

Other candidates, conditional on measurement:

- A large `epc_to_terminal` suggests exploring early positive sightings while
  retaining complete-round-only departure handling. Current implementation
  deliberately preserves the existing partial-round semantics.
- Large `listeners` with short inventory rounds suggests database/kiosk commit
  work reducing polling cadence. Large gaps before the first EPC suggest
  acquisition instead. Do not lower `missing_after` to speed arrival: it only
  controls departure and can cause false alarms with weak RF reception.
- Compare inventory 01 vs 0F only with one agreed test tag. Historical 0F tests
  starved weaker/other tags, so it remains unsuitable as the multi-tool default.
  The offline benchmark does not pretend to model RF differences between modes.
- No documented VX6336 Q/session fields were found in the previous manual
  review; do not transplant VX6436 inventory payloads. ScanTime, band and power
  tuning remain outside the current authorization.

## Physical experiment: authorization required before execution

First obtain specific permission for the machine/port, synthetic test tags,
temporary interruption of the application's serial ownership if needed, and
Inventory 01 / single-tag 0F plus optional reader-info 21 commands. No setting,
beep, write, lock, kill or erase commands are needed. Any Jetson action requires
separate target-device authorization. Older deployed code sends stored beep-mode
off (`35 80`) on startup; this candidate replaces that with read-only inspection.
Verify which source is installed before restarting/restoring a service. A
physical benchmark needs a dedicated no-buzzer/no-setting harness, not app startup.
Do not use the old probe's raw or per-EPC output on real identifiers.

After that authorization, prepare/review an aggregate-only physical harness
before running it; the offline benchmark cannot be pointed at a serial port.
The physical harness must allow only agreed inventory/info commands, never
call reader startup or drain buzzer commands, use the observed ScanTime for
timeouts, and have exactly one serial owner.

The subsequent ENTER-marker attempt was unreliable: tags were often acquired
while moving, before ENTER. Do not repeat that procedure or interpret repeated
sightings as first acquisition. The casing permits 10/20/30 cm; a future,
separately authorized physical test needs a reliable acquisition start trigger.

Mark placement reproducibly on a fixed jig, then measure 10/20/30 cm with the
same orientation and environment. Use at least 20 approaches per condition,
record the placement marker, first valid EPC, complete round and presence
handling. Record censored trials with no acquisition by the chosen deadline
rather than omitting them. Repeat with one tag, then representative multiple
tags using 01; compare 0F only in the single-tag condition. Report first-hit
p50/p95, misses, complete-round rate, read rate and longest gap including initial
and trailing no-read periods. Preserve settings and record aggregate counts only.

To connect acquisition to visible display, a separately authorized application
instrumentation run must correlate those events with kiosk responses and
foreground browser timing, or use a synchronized external video/placement
marker. Clock differences between browser and server must be accounted for.
The offline tools establish measurement separation and a query improvement;
they do not establish the VX6336's physical limit or justify replacing it.

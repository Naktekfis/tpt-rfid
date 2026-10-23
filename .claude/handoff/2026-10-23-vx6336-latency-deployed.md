# VX6336 latency software deployed; physical 20 cm acceptance pending

## Goal and authorization

Continue VX6336 latency investigation without repeating completed VX6436 SDK
discovery. User subsequently explicitly asked to apply current code to Jetson,
then requested SDK/software optimization with tests/unit tests and autopilot.
This supersedes the earlier deployment prohibition for this bounded deployment.

User selected discussion of tag/reader changes, asking for specific actions
first. This does NOT authorize executing setting/tag writes. Preserve all local
changes, live records, photos, configuration and existing backups. No commits,
pushes, resets or deletion. Do not activate VX6436 on hardware.

## Current state

Laptop `/home/ahmad/tpt-rfid`, branch `main`, HEAD `99cc143`, intentionally
heavily dirty. Earlier tracked/untracked changes remain preserved.
Jetson SSH `tpt@10.42.0.14`, app `/home/tpt/tpt-rfid`, Python 3.8.0.
Service active, master **13440**, sole new worker **14665** at last check;
old worker **13476** exited. Re-read PIDs before future actions.

Deployment directory `/home/tpt/tpt-vx6336-latency-20261023/`:

- `candidate/`: 95 source/assets/test files, staged separately without `.env`,
  live DB, images of users/tools or stored evidence.
- `install-plan.json`, `installed-manifest.json`: exact 14-file before/after
  source hashes. All 14 live hashes verified after installation.
- `source-backup-ffdn8ce6/source-before.tar`: valid code-only backup, private
  directory/files. No existing backups changed, no DB/config backup copied.
- `source-backup/`: preserved earlier source snapshot from a preflight attempt
  which failed before touching source/processes; do not confuse it with the
  installation's selected rollback directory.
- `postdeploy-health.json`, `postdeploy-timing-unit.json` and
  `offline-benchmark.json`: identifier-free evidence retained on-device.

Installed 14 files: `app.py`, `config.py`, `static/js/kiosk.js`,
`utils/database_handler.py`, `utils/rfid_diagnostics.py`, `utils/rfid_reader.py`,
`utils/vx6436.py`, `utils/vx6436_reader.py`, `tests/test_rfid_reader.py`,
`tests/test_vx6336_latency.py`, `tests/test_vx6436.py`,
`scripts/vx6336_latency_bench.py`, `docs/hardware/vx6336/latency-benchmark.md`,
`docs/hardware/vx6436/README.md`.

Existing changed runtime source matched the prior stage4 manifest. Kiosk JS
was absent from that manifest; its remote-to-candidate diff was inspected and
contained only the new opt-in timing instrumentation. All other runtime files
matched local code. No dependencies, unit, environment or schema were changed.

## Implemented behavior

- Reader timing adds command-to-first-frame, command-to-first-EPC and
  first-EPC-to-terminal summaries. Bounded, identifier-free, missing observations
  excluded. Complete-round-only presence semantics preserved.
- Reader startup/reconnect now only READS beep mode (`35 00`), replacing its
  automatic persistent beep-off write (`35 80`). This change was necessary to
  restart while preserving the user's no-reader-setting constraint.
- One FIFO queued buzzer command maximum before each inventory. Alarm bursts
  cannot drain indefinitely ahead of acquisition. No coalescing/drop; one slow
  command can still block to response timeout and queue size remains unbounded.
- Board queries defer photo BLOBs; type photo presence uses SQL length > 0.
  Null/empty images, borrower/overdue data and untyped tools preserve contracts.
- Tool presence lookup projects only id/status/presence, avoiding tool photo
  BLOBs in the arrival/departure processing path.
- Kiosk URL `?uhf_timing=1` exposes local `window.kioskTiming()` aggregates:
  scheduling gap, request/JSON, synchronous DOM and animation-frame boundary.
  No payload/identifier retention or upload. Cadence remains **1000 ms**.
- Offline benchmark uses synthetic serial frames through actual driver,
  presence service, SQLite in-memory and kiosk GET; no app/config import or
  serial opener. Supports type-photo and unit-photo sizes. Virtual serial timing
  is explicitly separated from real host CPU/HTTP timing.
- VX6436 SDK-derived codec/candidate is now present on Jetson as source only.
  Hardware startup guard remains intact, production active reader is VX6336.

## Verification

- Final local full pytest: **273 passed, 1 skipped in 7.49 s**; Ruff passed.
- Final Jetson staging full pytest with mock hardware/RAM DB:
  **273 passed, 1 skipped in 30.13 s** on Python 3.8.0.
- Earlier staging attempt: 269 passed, 1 skipped, 1 failed because fonts were
  omitted from staging. Added fonts/assets; next 270-test run passed. Final
  candidate adds three meaningful tests and passes as above.
- Python compilation and Node kiosk JS syntax passed; `git diff --check` passed.
- Independent read-only review found no breaking issue in timing, query,
  read-only startup, queue changes or installer. No browser paint test claimed.
- Mock backlog test: 100 buzzer requests with simulated 150 ms per reply delay
  inventory by one 150 ms command, leaving 99 pending; FIFO/interleaving verified.
- Host board benchmark, 20 tools / shared type image 512 KiB: per-scenario GET
  means **10.225–10.745 ms before**, **3.731–4.173 ms after**. Unit-photo presence
  timings were noisy; no quantitative speedup claimed for that second query.
- New passive live aggregate sample: **19.789 rounds/s**, inventory mean
  **50.193 ms**, p95 **57.787 ms**; first EPC mean **50.051 ms**, p95 **57.640 ms**;
  EPC-to-terminal **0 ms** in 120 observed samples; listeners mean **0.234 ms**,
  p95 **0.290 ms**. At 1186 total rounds: zero round errors, no-responses,
  incomplete responses, listener errors or skipped-presence rounds.
- Passive placement/distance was uncontrolled; these are ongoing repeated
  sightings, NOT placement-to-first-acquisition or 20 cm acceptance results.
- Postinstall health: NFC connected; VX6336 connected on `/dev/rfid-reader`,
  reported ScanTime **25500 ms** unchanged; camera opened/running, frame age
  **0.034 s**; kiosk HTTP 200; served kiosk JS hash matches installed candidate.
  Systemd `NRestarts=0`; exactly one new Gunicorn worker.

Installer: SIGSTOP master, SIGTERM sole worker, wait exit/zombie before code
replacement, atomic source writes, verify checksums, SIGCONT master in finally.
Initial installer used unsupported `/proc/.../children` on old Jetson kernel and
stopped BEFORE signals/source writes. Replaced discovery with `pgrep -P`; retry
completed successfully, preserving the first code snapshot.

Journal note: worker stdout is attributed to inherited master stream, so
`journalctl _PID=14665` returned no UHF aggregates. Unit filtering and selecting
only JSON summaries with new `first_epc` field returned the correct new samples.
Never dump full logs or kiosk state payloads; these can contain identifiers.

## Remaining work and boundaries

1. User needs a hard refresh of kiosk browser to load new JS. Backend source
   and instrumentation are already active. No automated browser control used.
2. Physical 5/10/15/20 cm marked-placement test remains unperformed. Need an
   agreed test tag, single serial owner, aggregate-only harness and precise
   physical-test authorization. Use first-hit/misses/gaps with censored trials;
   compare 01 vs 0F only for a single tag, retain 01 for multi-tool coverage.
3. Reader/tag modification proposals were explained: 01/0F comparison is
   read-only; ScanTime 25 only if blocking rounds measured, with approved value
   and restore steps; band/power require compatible specs and specific approved
   values. EPC rewrite 04 changes DB identity and is not an initial latency test.
   No writing, kill, lock, erase, frequency/power/ScanTime changes authorized.
4. Potential future bounded software work: explicit timeout/busy recovery for
   missing reader-info/late terminal responses. Current 1.5 s fallback before
   reader info can be too short for unknown 25.5 s ScanTime. Do not blindly shorten
   serial timeout or invent VX6436 Q/session payloads for VX6336.
5. Do not conclude hardware replacement from current timing. Current live
   inventory tail/listener timing is short, but first physical RF acquisition
   near 20 cm is still unmeasured.

Rollback source only, never restore DB over subsequent transactions. Old backed-up
reader source automatically writes beep-off on restart: any rollback must retain
the new read-only startup behavior or obtain explicit setting-write permission.

Next safe command: read-only service/device health over SSH, then prepare the
bounded physical benchmark or timeout-recovery mock work. Deployment is complete;
do not repeat it or change .env/reader model just because VX6436 source exists.

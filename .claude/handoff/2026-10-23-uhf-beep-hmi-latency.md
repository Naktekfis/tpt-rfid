# UHF acquisition, delayed alarm beep, and slower HMI — local diagnosis

## Goal, latest feedback, and authorization

Initial question: why does UHF take time to acquire the first tool tag while
NFC feels smooth? Latest user feedback broadens the investigation:

- HMI updates for tool changes/theft also feel slow.
- The audible beep itself is delayed; HMI updates arrive even later than beep.
- These are qualitative observations, not synchronized timings. The exact HMI
  page and whether the sound is the application alarm or automatic read beep
  have NOT been established. Explanations of alarm timing below are conditional
  on it being the tool-loss alarm.

User requested this handoff for the next session. Continue LOCAL diagnosis and
prepare a reviewable measurement design before any device permission request.
No authorization for Jetson access, service actions, deployment, reader/tag
settings or writes, auth changes, or real student data. No commit/deploy.
Preserve every pre-existing change, data file, test result and backup. UI cleanup
is complete locally: do not repeat it. Do not repeat VX6436 work or activate face.

Read AGENTS.md, .claude/knowledge/GATES.md, and these predecessor handoffs:
- 2026-10-23-ui-cleanup-and-rfid-next.md
- 2026-10-23-vx6336-offline-recovery.md

This handoff adds beep/HMI observations; it does not authorize hardware work.
RTK.md remains absent at repo root. Platform/reader/face references were read.

## Verified local state and work performed

Branch main, HEAD 99cc143, heavily dirty tracked/untracked tree. All existing
changes predate this analysis; no application/source modifications in this
session. Only this new handoff is added to the repo. No app startup, serial
open, SSH, real database access, secret reads, service changes or commits.

Inspected current reader, presence, kiosk, API, browser polling, security alarm
observer and camera snapshot paths. Ran existing offline synthetic benchmark
and additional synthetic status scenarios. No full suite rerun: previous green
results remain in predecessor handoffs and are not new verification here.

## Facts from current source

### Acquisition and presence

- utils/rfid_reader.py poll_once emits rounds only after an accepted complete
  terminal (00/01/FB) and payload validation. Status 03 waits for terminal.
- EPCs can already have arrived in frames ending with status 02 (reader scan
  time exhausted) or 04 (buffer full), but those rounds do NOT update presence.
  This is current deliberate complete-round-only behavior; do not call it a
  proven bug or change it without considering departure/false-alarm semantics.
- Reader status 02 is different from a HOST response timeout/recovery.
- PresenceMonitor.update emits new/back on the first accepted round containing
  the tag. RFID_ABSENT_TIMEOUT/debouncer does not gate this listener path.
- missing_after applies to departure only. config.py default RFID_MISSING_AFTER
  is 5 seconds, ENV OVERRIDABLE. Effective device value is UNKNOWN. Departure
  requires a subsequent accepted complete round with the tag absent, strictly
  beyond the threshold since its last sighting. Reader stalls/invalid rounds
  can delay this; there is no independent departure timer.
- The 10-second last_seen persistence interval does not defer new/back/missing
  transitions. DB/kiosk handling is synchronous on the reader thread.

### Alarm beep path (conditional on tool-loss alarm)

For a known available tool without an active session handling the departure:
accepted absent round -> missing event -> commit presence=missing -> create and
commit alarm -> alarm_observer -> reader.beep queues command -> reader finishes
remaining round/listeners -> later poll_once sends at most one FIFO queued
buzzer command before inventory.

- Alarm is committed BEFORE beep is queued; HMI need not await beep completion.
- Queueing is not physical sound onset. Queue backlog, remaining listener work,
  serial ownership/recovery and firmware can affect command/sound delay, but
  their costs during the reported incident are unmeasured.
- security.record_tool_alarm normally copies the latest camera frame and queues
  evidence work; encoding and disk I/O normally run off the reader thread.
  Queue-full fallback calls store.save synchronously (including fsync). This
  is a conditional possible delay, NOT evidence of saturation in the incident.
- ALARM_GRACE_SECONDS default 30 is retrospective alarm-to-borrow attribution
  after NFC identification, NOT a 30-second wait before raising the alarm.
- Automatic firmware beep-on-read is a distinct sound path. Historical beep
  mode was off; current physical mode and deployed source were not checked.

### HMI/API

- /api/kiosk/state assembles kiosk state, board, alarms and unverified returns.
- static/js/kiosk.js: next request 1000 ms after prior request/render completes.
- static/js/monitor.js: next request 3000 ms after prior completion.
- static/js/admin_monitor.js: alarm/return state at 3000 ms setInterval;
  tools/type lists separately at 15000 ms, with overlap guards.
- Thus admin alarm and tool table can temporarily disagree from polling alone.
- UI.fetchJSON has no explicit abort deadline. An unresolved request can hold
  the kiosk chain or admin overlap guard; no evidence this happened physically.
- With default missing threshold and healthy rounds, roughly 5 seconds from
  last sighting plus processing/polling can explain slow loss notification.
  This is a CODE MODEL, not a current-device measurement or guaranteed bound.
- Beep then HMI is compatible with polling. Long extra delay still requires
  API/browser timing; do not attribute all of it to polling without measurement.

### Existing instrumentation limits

- first_epc starts at inventory command send, not physical placement; means ANY
  EPC, including repeats. It is not target-specific first acquisition.
- Aggregate diagnostics retain at most 120 rounds and do not correlate a
  placement, target, presence change, API response and browser render.
- kioskTiming opt-in aggregates request+JSON, scheduling, DOM and rAF proxy.
  Scheduling gap is not per-event latency; rAF is not proof of displayed pixels.
- NFC identifies via separate PN532/I2C -> NFCService -> kiosk path, sharing
  downstream kiosk polling. Smooth NFC does not validate UHF RF/serial health.

## Evidence and hypotheses

Historical reports: fast kiosk at 2–3 cm; about 5 seconds near 10 cm; later
reported worse at about 20 cm. Uncontrolled geometry and timings. Earlier
passive logs: ~50 ms inventory, ~0.25 ms listeners, no faults in those samples.
These were repeated sightings, not placement-to-first-acquisition, and not
necessarily simultaneous with the delay. An older handoff concluded RF was
the cause too strongly; that is NOT established by these observations.

Candidate explanations remain separate:
1. Many empty rounds before any EPC (RF/geometry/tag compatibility/firmware).
2. EPC received but accepted complete round delayed or skipped (03/02/04).
3. Tool departure debounce and accepted-round cadence before alarm.
4. Callback/DB/buzzer queue/serial delay before sound.
5. API/polling/browser delay after state is already committed.

Timeout/recovery is a demonstrated software failure path with a local candidate
fix, NOT a proven physical root cause or validated solution. Current device and
service state remain UNKNOWN. Do not reuse old handoff PIDs/status.

Primary web sources checked this session:
- https://electron.id/produk/hw-vx6336/ — desktop tap reader, effective 0–20 cm,
  built-in antenna, 0–13 dBm. No guarantee of consistent reads for every tag at
  20 cm. No power/settings change justified.
- https://nidsolutions.freshdesk.com/support/solutions/articles/60001287026-writing-uhf-rfid-tags-practical-tips
  — orientation/polarization, material, tag and environment affect read links.
  General mechanism only; installed antenna polarization/tag mounting unknown.
Gen2 session persistence was researched but VX6336 internal session/search mode
is not established; do not transplant another reader's configuration commands.

## Exact new offline verification and retained artifacts

Existing benchmark command executed successfully via subprocess:
`.venv/bin/python scripts/vx6336_latency_bench.py`
Separate Flask app, synthetic tools, SQLite in memory, fake serial, virtual
serial clock. No app.py/config/.env or real serial opener. Host HTTP test client
excludes TCP/browser/display. Virtual and host timings must not be added.

New aggregate JSON (private temp file, existing results untouched):
`/tmp/tpt-vx6336-local-diagnosis-ez9q_967.json`

Virtual first presence dispatch:
- immediate 50 ms
- ten empty rounds then hit 550 ms
- hundred empty rounds then hit 5050 ms
- first EPC 50 ms, terminal 250 ms -> dispatch 250 ms
- partial_then_complete / no_response_then_complete -> 26350 ms each

Retained `/tmp/tpt-vx6336-latency.json` still has 350 ms for the two fault cases;
it predates recovery behavior. Preserve it; do not cite as current-code timing.

Additional inline Python imported run_case/frame/SYNTHETIC_EPC from the existing
benchmark and injected three sets of 101 rounds. Successful exit, saved:
`/tmp/tpt-vx6336-status-diagnosis-9t3ngy3f.json`

| Injected sequence | Rounds containing EPC | Skipped presence rounds | First dispatch |
| --- | ---: | ---: | ---: |
| 100 empty, then 01 hit | 1 | 0 | 5050 ms |
| 100 EPC hits status 02, then 01 hit | 101 | 100 | 5050 ms |
| 100 EPC hits status 04, then 01 hit | 101 | 100 | 5050 ms |

These prove distinct code paths can yield identical visible delays, NOT their
frequency or occurrence on hardware. No formal new test files or source edits.
Temp artifacts may disappear after reboot; verify before relying on them.

## Next work in priority order

1. Resolve measurement labels: which HMI page is observed, tool arrival versus
   departure, application alarm beep versus firmware read beep. Ask a concise
   clarification while continuing independent local work if useful.
2. Prepare identifier-free local instrumentation and synthetic verification
   for the three separate intervals: removal/last sighting -> missing event;
   missing event/alarm commit -> buzzer queue/write; committed state -> API
   response containing that change -> DOM/display. Not implemented yet.
   Include accepted empty rounds, EPC-bearing rejected rounds, per-status counts,
   inter-command gaps, listener costs, queue depth and recovery flags. Do not
   lower missing_after or alter buzzer/alarm semantics merely to hide delay.
3. Correlate by synthetic trial/round/state revision rather than EPC/person
   identifiers. Browser/server clocks require alignment or same-clock external
   observation; do not subtract performance.now from server monotonic directly.
4. For acquisition design, reject old ENTER-at-arrival procedure: tags were
   acquired while approaching before the marker. Use auditable synchronized
   video/trigger with BOTH motion onset and arrival at fixed jig position.
   Keep detections during approach, including negative offsets to arrival;
   never relabel the next repeat as first acquisition. No improvised shielding
   or RF reset is a proven trigger. Host EPC receive time includes firmware,
   serial/USB and scheduling; cannot isolate internal RF time unaided.
5. Future separately authorized trials: one agreed test tag, Inventory 01,
   fixed geometry/orientation, 10/20/30 cm (30 beyond documented range), initial
   target 20 trials/condition. Retain censored misses, early hits, all statuses.
   Separate multi-tag work and optional single-tag 0F comparison; 0F historically
   starved other tags and is not a multi-tool replacement.
6. Only after a concrete reviewed local design, request precise missing device
   authorization if proceeding. Any Jetson command, service interruption,
   live instrumentation/deployment or physical trial still needs approval.
   Check fresh service/serial ownership only AFTER that approval.

Relevant paths: utils/{rfid_reader,presence,tool_presence,kiosk,rfid_diagnostics,
security,camera,database_handler}.py; routes/kiosk_routes.py;
static/js/{kiosk,monitor,admin_monitor,ui}.js;
scripts/vx6336_latency_bench.py; tests/test_vx6336_latency.py;
docs/hardware/vx6336/{acquisition-probe,latency-benchmark,timeout-recovery}.md.

Next safe command: `git status --short`, then read this handoff and inspect
current source for the first unfinished local measurement step. No SSH or app
startup against default data. Full source tests were not rerun for this handoff.

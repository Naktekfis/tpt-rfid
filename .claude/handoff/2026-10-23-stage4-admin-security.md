# Stage 4 — admin split, camera evidence, UHF diagnosis

## Goal and user decisions

Continue `.claude/handoff/2026-10-23-nfc-stage3-operational.md` without redoing
NFC registration, tisu deletion, or earlier deployment. User explicitly accepts
the upper-right kiosk panel: preserve it. Preserve local edits, all data and
backups; no card writes or further deletion. Deployment and physical testing
remain authorized. User confirmed kiosk idle and all tools back before install.

Physical feedback this session: NFC tap and borrow/return session succeeded
postrestart. UHF response around 5 seconds at ~10 cm, including reapproach.
After new deployment user says all displays appear, but response is still slow;
clarified slow part is approaching the UHF, not necessarily admin screen polling.
User then confirmed **Kiosk; at 2–3 cm it becomes fast**. This points to
distance/orientation acquisition reliability near 10 cm rather than a fixed
software delay. No settings changed; advise tag facing antenna at 2–3 cm.
Reliable detection at 10 cm is not established.

## Git and deployment

Laptop `/home/ahmad/tpt-rfid`, branch `main`, HEAD `99cc143`, intentionally dirty.
Existing changes and untracked files preserved; no commit/push/reset/clean.
Jetson SSH `tpt@10.42.0.14`, app `/home/tpt/tpt-rfid`.
Current Gunicorn master 4567, sole worker 11212 at latest sample; re-read PIDs.
Systemd active, `NRestarts=0`. No reboot/cold-start test this session.
`RTK.md` remains absent; actual gates `.claude/knowledge/GATES.md`.

New changes installed: 26 allowlisted files, SHA256 checked in staging and live.
Manifest `/home/tpt/tpt-stage4-manifest.json`; candidate tar alongside it;
staging `/home/tpt/tpt-stage4-candidate` includes runtime source/static/tests,
no production `.env` or database. Staging tests force RAM DB and mock hardware.
No dependency, environment, live unit, or schema change.

Install used SIGSTOP master, SIGTERM sole worker, verify worker exit, backup,
atomic file replacement, SIGCONT master in finally. No concurrent device owner.
Initial install attempt used system Python 3.6 and stopped BEFORE source copies:
SQLite `.backup()` unavailable. Master resumed, replacement worker 11072 healthy.
Retry used app `.venv/bin/python` 3.8, replaced 11072 with 11212 successfully.

## Changes

- `/admin/monitor` now Monitor Alat; separate `/admin/students` with contacts,
  NFC binding state, active/overdue/no-card filters, per-loan due dates and
  confirmed reminder actions. History remains recap. No email sent by agent.
- Admin can edit unit display name/category and rename a whole type/current
  unit names; transaction snapshots, EPCs and borrowing state preserved.
  No delete/archive action. Existing admin/CSRF/PIN boundaries reused unchanged.
- New `/admin/security`: alarm evidence and camera incident/recovery history,
  explicit acknowledgement, private authenticated JPEG serving with no-store.
- `utils/security.py`: frame copied at alarm event; encoding/writes queued
  off the serial thread. Private JSON/JPEG under `instance/security`, directory
  700/files 600, atomic writes. Default photo budget 200 MiB stops new captures
  without deleting any older file. Failure status persists where disk permits.
  No face recognition or identity claims.
- Camera dark/flat-frame heuristic labelled suspected obstruction/poor light,
  unavailable/stale separately. 5 s fault debounce, 3 s healthy recovery;
  single buzzer pattern per incident. Stable incident/ack survives worker
  restart. Acknowledgement is merged under store lock so encoding/recovery
  cannot overwrite it. Storage failure does not suppress camera beep; retry
  state remains and error is shown in admin UI.
- Camera `read()` rejects frames older than 3 s.
- `ToolPresenceService.alarm_observer` isolates capture failures from alarm/beep.
- UHF inventory errors, silence, malformed/partial inventories no longer emit
  false empty rounds to presence. Complete valid empty inventory still proves
  departure. No hardware settings or presence/debounce defaults tuned.
- Bounded identifier-free reader timing (120 samples) and aggregate presence
  gaps through authenticated `/api/admin/diagnostics/uhf`. Reader logs aggregate
  `UHF timing {json}` every 30 seconds for safe live diagnosis. No EPC in these
  summaries. Normal older scan logging is unchanged.

## Verification

- Laptop `scripts/check.sh`: Ruff passed; **221 passed, 1 skipped in 6.94s**.
- Jetson staged app Python 3.8 full pytest: **221 passed, 1 skipped in 27.20s**.
- Python compile of app/config/utils/routes passed on laptop and staged Jetson.
- Node syntax checks all 3 changed admin scripts passed; admin agent also ran
  synthetic DOM edit/filter/cancel-email interaction checks. No browser screenshot.
- Independent security review found two issues (storage suppressing camera beep,
  concurrent acknowledgement lost); both fixed with synthetic regression tests.
  Security targeted suite now 18 passed; full suites above include these fixes.
- First staging collection lacked `deploy/jetson/backup_db.py` dependency;
  copying existing deploy source to staging fixed collection. No production change.
- New diagnostic test initially assumed default threshold 5; laptop config is
  overridden, so test now injects 4.25 and verifies reporting effective threshold.
- Live 26/26 hashes matched; SQLite quick_check=ok; foreign_key_check 0 issues.
  Schema unchanged. At immediate postinstall snapshot all counts unchanged:
  students, NFC cards, face embeddings, tool types, tools, transactions, alarms.
- Seven postinstall samples over 30 seconds: NFC/UHF connected, camera frames
  fresh 0.0069–0.0340 s. All five tools present, no unknown tools/open alarms
  at that sample. Protected new HTML pages redirect to admin login and APIs
  return 401 without session.
- Live timing logs: ~18.8–20.6 rounds/s, inventory mean 48.1–52.8 ms,
  p95 58.4–60.9 ms, listeners mean 0.24–0.25 ms, queued commands ~0.036 ms;
  zero no-response, partial, listener, or skipped-round errors in first samples.
  ScanTime 25500 ms remains configured; it is NOT actual measured round duration.
- Later a naturally occurring tool alarm produced `photo_status=captured`.
  No security error logs at that check. This is actual postdeploy capture evidence;
  no image content/student data was printed or downloaded. Later operational
  alarm/transaction counts may legitimately change; don't expect frozen counts.
- Camera physical acceptance PASSED: user reports beep/photo/recovery after
  closing and reopening lens. A later read-only check found 35 camera-suspected
  obstruction records, each with captured photo and recovered_at (healthy); no
  raw image was read/downloaded. This reconciles the earlier check that ran
  before the records were written.

## Backup / rollback

Keep older stage2 and stage3 backups intact. New VALID backup:
`/home/tpt/nfc-backups/20261023-stage4-admin-security-v2/` (700) contains
`before-stage4.db` (600, quick_check=ok), `source-before.tar` (600), and
`baseline.json` (600). Restore only needed source files under a stopped worker,
then resume master; newly added unused source can remain during rollback.
Do not restore entire DB over later sessions/registrations or delete evidence.

`/home/tpt/nfc-backups/20261023-stage4-admin-security/` is the INCOMPLETE first
attempt, preserved: baseline plus an empty/unfinished database file. Do not use
it as a valid SQLite backup. Private evidence stays on the Jetson under
`/home/tpt/tpt-rfid/instance/security`; never put it into Git or static assets.

## Remaining work

1. Physical comparison complete: user confirmed Kiosk is fast at 2–3 cm.
   Keep tag facing antenna close for reliable acquisition. If reliable 10 cm
   rack coverage is required, investigate tag orientation/metal placement and
   antenna/hardware coverage; software threshold tuning cannot improve RF capture.
2. Camera close/reopen acceptance passed by user and persisted records. If the
   user reports false alerts, review threshold calibration using synthetic tests
   and aggregate samples; do not remove accumulated private evidence.
3. If perceived lag is only admin list, current poll remains 15 s tools/students,
   3 s alarms, 5 s security. Consider event-driven/shorter bounded polling,
   but don't change unrelated UI after user clarified UHF as the slow part.
4. Physical edit dialogs/reminder discovery acceptance; no actual reminder send
   authorized by this task. Existing binding/photo/reboot/long soak scenarios
   from stage3 remain unclaimed. Initial NFC I2C cold-start concern remains open.
5. Storage limits: metadata append-only (no retention deletion authorized), queued
   frames lost on abrupt kill, heuristic cannot prove intentional camera cover.

Next safe command: SSH device health and aggregate `UHF timing` log filtering
with remote Python (Jetson lacks `rg`); never dump full logs/student payloads.

Final user report: `Ya, beep/foto/pemulihan berhasil`. Camera-specific event
photos and recovery were subsequently verified in private metadata. NFC session,
admin destinations, UHF close-range test and actual tool-alarm photo accepted.

## Stage 5 — UHF range/throughput redesign (discovery)

User asks to make UHF read farther and faster. Physical benchmark already
reported: kiosk reads quickly at 2–3 cm, roughly 5 seconds near 10 cm. Installed
loop measures 18.8–20.6 valid inventory rounds/s (50 ms average, ~60 ms p95),
with ~0.25 ms listeners and no timeouts/partial rounds. Thus app loop is not the
5 s bottleneck; tag RF acquisition is intermittent at 10 cm.

Primary vendor specs (Electron product pages, checked 2026-10-23): current
HW-VX6336 is a desktop reader with built-in antenna, effective 0–20 cm and
0–13 dBm. Raising its power past the observed maximum is unavailable. A useful
nearby target is HW-VX6436: USB/RS232, published 0–100 cm, adjustable 1–26 dBm,
and >50 tags/s anti-collision. A much longer HW-VX6330K publishes 6–8 m and
would likely overshoot a workshop rack, risking unrelated tag reads. The exact
VX6436 command compatibility with our existing VX6336 driver has not been
source-verified/tested on hardware; vendor calls some other HW-VX63 protocols
similar, which is insufficient evidence to silently deploy a guessed adapter.

Do not change installed reader power via command 0x2F: it is a persistent,
gated setting and current desktop output is already max. Never write tags.
Indonesia's Komdigi rules list 920–923 MHz as SRD and device use must meet the
technical operating requirements; procure only a properly certified/configured
regional model and honor its EIRP limit. Don't set a high advertised conducted
power without accounting for antenna gain/EIRP.

User selected a useful range of about 1 m for the rack (2026-10-23). The vendor
page for HW-VX6436 confirms USB/RS232, adjustable 1–26 dBm, 0–100 cm and a
published anti-collision rate above 50 tags/s. It links an SDK, but the linked
cloud download is inaccessible to the web research tool; no VX6436 serial
command protocol was verified in public documentation during this pass. Do not
assume its commands match VX6336.

Next step: obtain and inspect the official VX6436 SDK/protocol and validate it
against a candidate physical unit. Test the same existing EPC tags at measured
distances/orientations, per-tag acquisition rate, false reads outside the rack,
reader-info/inventory/beep behavior, and a properly certified Indonesian
regional configuration with compliant EIRP. Only then implement/enable a
model-specific driver profile behind the existing factory, with one serial
owner. No code-only tuning can make the installed VX6336 reliably read at 1 m;
no tag writes or current reader config commands are authorized. Existing
data/cards remain untouched.

# NFC — stage 1 complete; stage 2 deployment next

## Read this first

This is the latest checkpoint. It supersedes hardware-blocker and deployment
status in `2026-10-23-nfc-implementation.md`; consult that longer handoff only
for diagnosis details. Do not restart completed discovery, setup or tests.

User wants stages with Markdown handoff and an opening prompt at each boundary,
so they can `/clear` and resume. Finish one stage, record exact state, then return
only the next opening prompt. Communicate concisely in Indonesian.

## Goal, decisions and authorization

- NFC PN532 I²C 0x24 for student registration AND borrow/return kiosk sessions.
- UHF HW-VX6336 remains separate for tool presence.
- Face/liveness/CV benchmark archived in `legacy/face/`; retain existing DB face
  embeddings, photos, old student RFID bindings and downloaded models.
- Camera remains for tool photos. Alarm documentation/tamper detection is future
  work, with controller hardware/protocol still undecided.
- Preserve all local changes and existing data. No card writes or data deletion.
- User explicitly authorized deployment and staged Jetson tests for this work,
  with backup/rollback before replacing the running app. Do not re-ask for that
  same authorization; check live state before acting. Never expose secrets or
  real student records. Tests use synthetic data.

## Git and sources

- Laptop `/home/ahmad/tpt-rfid`, branch main, HEAD99cc143. No commit/push.
- Preexisting user changes preserved: AGENTS.md, CONTEXT.md, .agents/, .codex/,
  Scanner.zip and previous handoffs. AGENTS/CONTEXT now also reflect new code.
- NFC source implementation is uncommitted. Review `git status --short` for the
  full tree; deleted face files have counterparts in `legacy/face/`.
- `RTK.md` referenced by instructions was not found.
- Active changes: `utils/nfc_reader.py`, `nfc_service.py`, `kiosk.py`,
  `routes/nfc_routes.py`, `camera_routes.py`, app/config/models/database,
  NFC register/kiosk/admin UI, optional requirements and Jetson installer.
- Dedicated additive `student_nfc_cards` table (StudentNFCCard), unique student
  and UID, FK. Old Student.rfid_uid is untouched. Kiosk uses get_student_by_nfc.
- Registration uses fresh browser-owned capture token,120s, server-held UID,
  single consumption, stale-event rejection, token-checked cancellation.
  Admin may bind an NFC-unbound existing student. Card replacements unsupported.
- Active sessions ignore other taps; borrow/return/late alarm behavior retained.

## Completed verification — do not repeat without a reason

- Laptop `scripts/check.sh`: Ruff green, **172 passed, 1 skipped** (archived CV).
- Jetson Python3.8 staging: **172 passed, 1 skipped**, compilation green.
- Python compilation, JS syntax, Jinja parsing, diff whitespace green.
- Synthetic UI registration/admin-binding harness passed.
- Additive-schema test preserves old RFID UID, photo and face embedding.
- Independent review findings fixed: old UHF binding conflict and installer
  NFC mock default. Follow-up review found no further blockers.
- Browser visual inspection remains pending.

## Hardware failure resolved sufficiently to proceed

Before cold start, SAME original proven script/venv failed I2C timeout110;
read-only native status `i2ctransfer -y 1 r1@0x24` also timed out. Correct bus1,
100kHz, no competing reader process. I2C runtime woke for transactions. Desktop
sleep was not established as cause. No pinmux/kernel/GPIO changes made.

User performed full cold start. Verified uptime~1min and boot ID
`bbe0c651-2492-4ccf-85ad-0c0f72de2327`. After cold start:

1. Staging `scripts/nfc_probe.py --duration45`: connected, firmware(50,1,6,7),
   10 detections, UID length4. User confirmed they performed multiple taps.
2. Staging `scripts/nfc_acceptance.py`: ALL PASS on real PN532, RAM SQLite,
   synthetic student/tool, mock UHF, actual CSRF enabled. Physical first tap
   registered synthetic student; next tap opened correct session; UHF rounds
   exercised borrow,return and protected end/summary. Readers stopped and RAM
   database disposed; no production registration or card write.

Cold start restored communication; exact root cause remains unproven. If issue
recurs, consult previous handoff rather than reinstalling libraries blindly.
No test NFC processes remain at checkpoint.

## Device and staging

- SSH `tpt@10.42.0.14`, hostname tpt-desktop. App `/home/tpt/tpt-rfid`.
- Production Git clean at99cc143, old face app still running. Production source,
  environment, venv and database have NOT been replaced/changed for NFC.
- Service tpt-rfid active; Gunicorn master4567, single worker7562 at checkpoint
  (re-read PIDs). Camera enabled/open, UHF connected `/dev/rfid-reader`.
- Device app venv Python3.8; pip25.0.1. PN532/Blinka not installed there yet.
- Proven separate `/home/tpt/pn532-test-venv`: Blinka9.1.0, PN5322.4.9,
  busdevice5.2.17, Jetson.GPIO2.0.17. Do not replace it or copy its broken freeze.
- Hardware tests invoked app venv with
  `PYTHONPATH=/home/tpt/pn532-test-venv/lib/python3.8/site-packages`.
- `/home/tpt/nfc-stage-20261023-v2`: tested code,172tests + real acceptance pass.
- **Latest deployment candidate:** `/home/tpt/nfc-stage-final/`, extracted from
  `/tmp/tpt-nfc-final.tar.gz` (laptop archive also `/tmp/tpt-nfc-final.tar.gz`).
  Includes `nfc-release-manifest.json`:126 source files with SHA256 and14 retired
  source paths. Latest small changes vs testedv2: UHF disconnect banner fix,
  docs, archive script root paths and comments; functional NFC flow unchanged.
- Candidate excludes data/config secrets, AGENTS/CONTEXT and unrelated user files.

## Verified private backup and rollback

**Latest:** `/home/tpt/nfc-backups/20261023T031856/` on Jetson ONLY:
- code.tar (deployed clean99cc143);164entries verified, extracted in code-check/,
  original app.py compiled successfully.
- database.db: SQLite online backup including WAL; quick_check=ok.
- .env: private mode600, never printed/exported.
- runtime.tar.gz: uploaded photos/models preserved.
- venv.tar.gz:87MB,7117entries fully scanned, expected .venv/bin/python verified.
- verified.txt records verification. Parent directory mode700; archives private.

Older backup025719 includes saved desktop-power.json. It is superseded for app
rollback by031856. Desktop idle300s changed to0, AC sleep actionnothing,
idle-dimfalse; screen-lock auth unchanged. X11 s off/-dpms/force on applied before
cold start (session-local). Persistent GSettings survived restart.

Rollback before/after deployment: restore code/config and restart app; leave live
SQLite and the additive NFC table intact to preserve newer transactions. Snapshot
DB is disaster recovery only, never routine rollback. Restore venv from backup if
package installation causes a failure while the service is stopped.
See `deploy/jetson/NFC_ROLLOUT.md`; its example025719 path is historical—use031856.

`sudo -n true` required a password before reboot. Do not request/store a password.
Use authorized service-user Gunicorn single-worker recycle if appropriate:
SIGTERM the worker, master replaces it AFTER exit. Do not HUP overlapping workers
that share hardware. Re-read process structure and verify old owner exited.

## Stage 2 — bounded deployment

1. Recheck laptop Git, device SSH/Git, service, one worker, no NFC test owner.
2. Verify latest staged manifest hashes and backup artifacts. Backups already
   prepared; refresh only if live state changed materially.
3. Install `requirements-nfc.txt` into app venv (not yet done); check dependency
   compatibility and imports. Preserve other package versions when possible.
4. Update only NFC_READER_ENABLED=true in existing env without printing secrets.
5. Copy reviewed candidate files; retire ONLY manifest-listed old source files,
   which are archived in shipped legacy/face/. Preserve .git,instance,uploads,
   models,secrets and unrelated files. No rsync delete over data directories.
6. Recycle single service worker without overlapping hardware ownership. First
   startup adds student_nfc_cards via create_all; no existing tables altered.
7. Check `/api/devices/status`: PN532 connected, UHF connected, camera open.
   Check kiosk/register/admin routes and absence of active face/CV routes.
   Do not print `/api/kiosk/state` with real student data to logs.
8. Roll back code/config if health fails; retain live data. Record exact state and
   next task in a NEW concise handoff. Return only opening prompt for stage3.

## Stage 3 — operational verification

With user at kiosk, verify real registration/account binding as appropriate,
session safety, UHF tool departures/returns, camera tool capture, admin flow,
startup/restart reliability and visual UI. Use synthetic/RAM data for automated
tests; coordinate real records through intended user workflow. Alarm evidence /
camera tamper and controller integration remain later scope.

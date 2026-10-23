# NFC — stage 2 deployment complete; stage 3 operational verification next

## Read first / authorization

This supersedes the **not deployed** status in `2026-10-23-nfc-stage1-complete.md`
and the older implementation handoff. Stage 1 implementation, laptop checks,
Python 3.8 tests and real PN532 registration/session acceptance already passed.
Do not restart that work. User wants one stage per session, a Markdown handoff,
and **only the next opening prompt** in the final response, in Indonesian.

- Deployment and staged Jetson testing remain authorized. No data deletion or
  card writes. Preserve local changes, old RFID bindings, photos, face embeddings,
  downloaded models and transactions. Never print secrets or student records.
- PN532 is for student identity; separate UHF reader is for tool presence.
- Use synthetic/RAM data for automated tests. Real registration/account binding
  belongs to the intended UI workflow with the user at the kiosk.
- `RTK.md` is still absent. `.Codex/knowledge/GATES.md` referenced by the generic
  safety skill is absent; current project gates are `.claude/knowledge/GATES.md`.

## Git / deployed source

- Laptop `/home/ahmad/tpt-rfid`: branch `main`, HEAD `99cc143`; implementation
  remains uncommitted. Preexisting AGENTS/CONTEXT, `.agents/`, `.codex/`, Scanner.zip
  and handoffs preserved. This stage only added this handoff locally.
- SSH `tpt@10.42.0.14`, hostname `tpt-desktop`, app `/home/tpt/tpt-rfid`.
- Jetson was clean at `99cc143` before deployment. Now intentionally dirty with
  the NFC candidate changes; HEAD unchanged. No commit/push/reset/clean performed.
- Candidate `/home/tpt/nfc-stage-final/nfc-release-manifest.json`: **126 source
  files, 14 retired paths**. Every SHA256 matched both laptop and staging before
  deployment, then matched production afterward. Retired paths have counterparts
  in shipped `legacy/face/`. Only those old source paths were removed.
- `.git`, `instance/`, uploads, models and unrelated files preserved. No broad
  rsync deletion. Candidate excludes laptop agent setup and unrelated user files.

## Deployment completed (2026-10-23, ~03:25 WIB)

1. Reverified full code/runtime/venv archive readability, private config mode 600,
   and backup SQLite `quick_check=ok` in backup `20261023T031856`.
2. Installed candidate `requirements-nfc.txt` into the **app** `.venv` Python 3.8:
   Blinka 9.1.0, PN532 2.4.9, busdevice 5.2.17, PlatformDetect 3.89.1,
   Jetson.GPIO 2.0.17, plus resolved dependencies. All **45** previously installed
   package versions preserved; typing-extensions remains 4.13.2. `pip check` green.
   Proven `/home/tpt/pn532-test-venv` untouched; production needs no PYTHONPATH hack.
3. Final candidate tested using updated app venv in staging:
   `cd /home/tpt/nfc-stage-final && /home/tpt/tpt-rfid/.venv/bin/python -m pytest -q`
   → **172 passed, 1 skipped in 20.37s**. `py_compile app.py config.py utils/*.py
   routes/*.py` passed. Fixtures force RAM DB and all hardware mocks.
4. Suspended Gunicorn master 4567 with SIGSTOP, sent SIGTERM to sole old worker
   7562, verified it exited before copying anything. Made an additional private
   SQLite online backup while no app worker was running. Copied manifest files,
   retired allowlisted sources and atomically updated only `NFC_READER_ENABLED`
   to true in the existing `.env`. Resumed master with SIGCONT afterward.
   No overlapping reader owners or sudo/service-unit changes.
5. Master spawned sole replacement worker **9028**. Running installed systemd
   unit still has SupplementaryGroups `dialout video`; inherited account groups
   include `i2c` and `gpio`, verified in process status. Shipped service template
   now lists those groups too, but live systemd unit was not rewritten.

## Verification after deployment

- `tpt-rfid` active, Gunicorn master **4567**, one worker **9028** at checkpoint
  (~03:28 WIB). Re-read PIDs next session. No NFC test process owns the reader.
- Boot ID unchanged: `bbe0c651-2492-4ccf-85ad-0c0f72de2327`.
- `/api/devices/status`: PN532 connected, firmware `[50,1,6,7]`; UHF VX6336
  connected on `/dev/rfid-reader`; real camera index 0 open/running with fresh
  frames (~0.01s). **Seven samples over 30 seconds all passed** after initialization.
- Initial health check before PN532 initialization completed showed disconnected;
  it connected within the next checks. Kernel showed transient I2C timeout/no-ACK
  around initialization. No driver/pinmux/kernel/power changes were made. This is
  not evidence of a permanent fix for the earlier cold-start issue; restart and
  longer-term reliability remain stage 3 work. NFC sequence advanced 4→6 during
  the sampling window; no UID or live kiosk/student payload was printed. This
  alone does not establish operational acceptance.
- Public `/`, `/mahasiswa`, `/kiosk`, `/daftar`, `/admin/login`: HTTP 200.
  Kiosk/register/login have CSRF meta tokens; register renders NFC UI without
  face API references. HTML requests to `/admin`, `/admin/monitor`,
  `/admin/input_tool`, `/admin/history` redirect to `/admin/login`.
- Removed `/cv/`, `/cv/live`, `/cv/face-rec`, `/api/face/identify` redirect to `/`
  through the existing global 404 handler. Expect **302**, not HTTP 404.
  An unauthenticated `/admin` request without HTML Accept returns 401 as designed.
- Production SQLite `quick_check=ok`. Compared existing table SQL and rows to
  the immediate pre-deploy snapshot without printing contents: all schemas and
  stored data preserved, except expected ongoing `tools.last_seen_at/updated_at`
  from real UHF polling. **Only new table is empty `student_nfc_cards`.** Students,
  tool types, face embeddings, transactions and alarm events unchanged.
- Environment comparison verified only NFC setting changed. All deployed hashes
  and all 14 retired-source absences verified. No real registration, record
  deletion, card write, email or destructive migration performed in stage 2.

## Backups / rollback (private on Jetson only)

Use `/home/tpt/nfc-backups/20261023T031856/`, **not** the historical 025719 example
in `deploy/jetson/NFC_ROLLOUT.md`. Parent private mode 700; never export backups.

- `code.tar`: old clean 99cc143, 164 entries; extraction already verified.
- `.env`: old configuration, mode 600; never printed.
- `database.db`: original online snapshot, quick_check OK.
- `runtime.tar.gz`: photos/models, 8 entries, fully read again.
- `venv.tar.gz`: original full app venv, 7117 entries, fully read again.
- Added `pip-before-stage2.txt`: previous 45 package versions.
- Added `stage2-pre-deploy.db`: immediate online snapshot after old worker exit,
  mode 600; used for preservation comparison.
- Added `deployed-manifest.json`: exact deployed candidate manifest.

Routine rollback restores backed-up **code and configuration**, then restarts the
single worker; retain live SQLite including NFC table/newer transactions. Never
overwrite live DB routinely. If dependency restore is needed, use venv archive
while app service is stopped. Privileged systemctl previously required password;
do not ask for/store a password. The authorized worker-recycle method above can
serialize code/config rollback without overlapping hardware owners. Never HUP
overlapping workers. Read current process tree before signaling.

## Stage 3 — remaining work

1. Recheck Git, process ownership and device health; app is **already deployed**.
   First read-only command:
   `ssh tpt@10.42.0.14 'systemctl is-active tpt-rfid; curl -fsS http://127.0.0.1:5000/api/devices/status'`.
2. With user physically at kiosk, inspect browser/UI and coordinate registration
   or admin binding as appropriate, NFC session safety, UHF departures/returns,
   tool-photo camera and admin flow. Do not repeat standalone PN532 probe while
   the active worker owns it. Existing account replacement remains unsupported.
3. Verify restart/startup reliability and longer operation; initial PN532 delay
   and prior cold-start failure merit observation. Refer to stage 1 and older
   implementation handoff if I2C failure returns; do not blindly reinstall libs.
4. Record exact operational results in the next Markdown handoff. Alarm evidence,
   camera tamper and undecided controller integration are later scope.

No new approval blocker at stage 2 completion. Physical actions in stage 3 need
coordination with the user; deployment/testing authorization remains in force.

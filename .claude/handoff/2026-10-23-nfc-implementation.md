# NFC implementation and device staging — 2026-10-23

## Goal and authorization

Implement NFC student registration and borrow/return sessions, archive face and
liveness, preserve camera for tool photos and UHF for presence. User authorized
staged Jetson testing/deployment with backup and rollback before replacement.
Never delete data or write cards. Alarm camera evidence/tamper detection is later
work; controller protocol remains unspecified.

User's later steering: “coba cek lagi kayanya ke-sleep deh”. Rechecked SSH and
firmware using both new code and original proven PN532 test venv. Jetson stays
awake/reachable; PN532 currently does not respond. Do not infer a sleep cause.

## Git / local work

- Branch main, HEAD 99cc143; no commit or push.
- Preserved preexisting AGENTS.md/CONTEXT.md edits, .agents/, .codex/, Scanner.zip,
  and earlier handoffs. Updated only stale project facts in AGENTS/CONTEXT after
  implementing the new active path.
- `RTK.md` referenced by user instructions is absent; search found no local copy.
- Source changes remain uncommitted. See `git status --short` and `git diff`.

## Implemented

- `utils/nfc_reader.py`: mock + PN532 I2C 0x24, optional lazy dependencies, firmware
  validation, read-only passive UID, uppercase hex normalization (4/7/10 bytes),
  held-card debounce, reconnect, stop/cleanup, thread-safe sequence events/status.
  Hardware UID is not printed/logged by the reader/probe.
- `utils/nfc_service.py`, `routes/nfc_routes.py`: fresh registration captures owned
  by a browser session, 120-second timeout, no client UID acceptance, capture token
  single use, no stale event reuse, old cancellation cannot cancel a newer token.
- `app.py`: registration uses captured card; NFC opens kiosk sessions; camera
  routes independent of face; no CV/face blueprint or frame/liveness loop active.
- `utils/kiosk.py`: NFC idle/unknown_card/session/summary; active sessions never
  switch students on another tap. Preserves presence borrowing/returns, session
  timeouts/extensions, late alarm attribution, end/cancel, return verification.
- New additive `StudentNFCCard` model/table `student_nfc_cards`: unique student,
  unique NFC UID, FK. NFC lookup is separate from legacy `Student.rfid_uid`.
  This avoids confusing UHF student EPCs with PN532 UIDs. Admin can bind any
  existing NFC-unbound student without changing their old RFID UID. Replacing
  an existing NFC binding is intentionally unsupported for this slice.
- Registration/kiosk/admin/student menu UI uses NFC. Tool camera remains.
  Algorithm code, CV routes/templates, original kiosk/UI/tests and face tooling
  preserved under `legacy/face/`. Existing biometric DB models/data retained.
- Optional `requirements-nfc.txt` pins match prior proven test venv. Camera-only
  `requirements-cv.txt`; dlib requirements archived. Installer enables NFC and
  adds i2c/gpio permissions. See `deploy/jetson/NFC_ROLLOUT.md`.
- `scripts/nfc_probe.py`: firmware/connection/count/UID-length output only.
- `scripts/nfc_acceptance.py`: real PN532 + RAM DB/synthetic student/tool data,
  active CSRF, mock UHF rounds. Two taps exercise registration, session, borrow,
  return and end. Never writes production DB/card; actual UID stays in memory.

## Verification

- Laptop `scripts/check.sh`: Ruff green; **172 passed, 1 skipped**. Skip is obsolete
  CV blueprint test (archived feature). Subsequent changes only UHF disconnect
  banner, documentation, archive script paths and comments: Ruff, compilation,
  JS syntax and diff whitespace rechecked green.
- `.venv/bin/python -m py_compile app.py config.py utils/*.py routes/*.py`: green.
- `git diff --check`: green.
- `node --check`: register/kiosk/admin_monitor/monitor scripts green.
- `/tmp/tpt-nfc-ui-check.js`: synthetic Node UI registration/admin-binding flows
  passed (ephemeral harness). Worker also tested acceptance script end-to-end
  locally using a synthetic PN532 device; real hardware acceptance remains open.
- Jetson staging Python 3.8: **172 passed, 1 skipped**; compilation green.
- Synthetic schema-upgrade test preserves legacy UID, photo and face embedding
  while adding/binding the NFC table.
- Independent read-only review: initial two findings fixed (legacy UHF binding
  conflict, installer mock default); follow-up found no additional blockers.
- Browser visual inspection on Jetson remains untested.

## Jetson state and backup

- SSH `tpt@10.42.0.14`, hostname tpt-desktop, eth0 UP. `/dev/i2c-1` and
  `/dev/ttyUSB0` present. Service `tpt-rfid` active, one Gunicorn master/worker,
  deployed HEAD 99cc143; initial Git tree clean.
- Old active device status: camera enabled/open; UHF connected via
  `/dev/rfid-reader`. Production app code/config/DB/venv NOT replaced or changed.
- Private backup **/home/tpt/nfc-backups/20261023T025719/**:
  `code.tar` from clean deployed HEAD; `database.db` via SQLite online backup,
  quick_check=ok (WAL included); `.env` mode600; `runtime.tar.gz` photos/models.
  Directory mode700, DB mode600. No contents exported or printed. Venv not
  backed up yet because dependency installation/deployment has not begun.
- Backup helper on device `/tmp/tpt-nfc-backup.py` (ephemeral). It copied config
  privately as authorized backup; do not print its contents or real records.
- Staging **/home/tpt/nfc-stage-20261023-v2/** from
  `/tmp/tpt-nfc-stage-v2.tar.gz`: latest functional NFC implementation and tests,
  full Python3.8 suite passed. Small later local edits (UHF banner, docs, archive
  tool paths/comments) need syncing before any deployment.
- Initial staging `/home/tpt/nfc-stage-20261023/` also exists; superseded by v2.
- App venv lacks Adafruit PN532/Blinka; prior isolated
  `/home/tpt/pn532-test-venv` remains untouched. Staging probe used:
  `PYTHONPATH=/home/tpt/pn532-test-venv/lib/python3.8/site-packages`
  `/home/tpt/tpt-rfid/.venv/bin/python scripts/nfc_probe.py --duration 45`.
- `sudo -n true` reported password required. Interactive systemd stop/start needs
  local sudo or an approved interactive path; user already authorized deployment,
  so do not ask for deployment permission again. Never request/store password.

## Hardware blocker / remaining work

1. **PN532 does not answer I2C 0x24 now.** New probe returned ValueError/RuntimeError
   during init, no connected status or detections. Targeted
   `i2cdetect -y -r 1 0x24 0x24` displayed `--`. Direct firmware check using ORIGINAL
   proven `/home/tpt/pn532-test-venv` also timed out, ending with
   `ValueError: No I2C device at address: 0x24`. SSH/up-time remained normal.
   User was asked to check module power/SDA/SCL/I2C switches and safely power-cycle
   the module. Await physical readiness; do not redo previous installation or
   suggest MFRC522/SPI. All test reader processes have ended.
2. Once user says module ready, run ONE targeted probe, no competing I2C reader
   processes. Verify firmware 0x32 v1.6, then count two taps with removal >=2s.
3. Sync final local code into new staging; run `scripts/nfc_acceptance.py` with
   actual PN532 + synthetic RAM data, announce both tap prompts. Existing live
   app has no PN532 owner, so no service stop is needed for acceptance.
4. Before production change, refresh backup if needed, snapshot app venv before
   optional dependency install, and validate/extract the backup archive.
5. Install optional NFC requirements into production venv; preserve other config
   while adding NFC_READER_ENABLED=true. Follow NFC_ROLLOUT.md. Database change
   is only additive create_all for student_nfc_cards; never overwrite/delete
   existing data or restore stale DB during routine rollback.
6. Restart one worker/service without overlapping hardware owners; verify real
   NFC, real UHF presence and tool camera; inspect UI in kiosk browser.
7. Record exact final state/results here or a subsequent handoff. No commit/push
   unless requested.

Routine rollback restores code/config and restarts old app, leaving live database
and added table intact. Database snapshot is disaster recovery only, to avoid
losing transactions after backup. Concrete commands are in NFC_ROLLOUT.md.

## Follow-up: exact previous-session replay

User asked why prior session succeeded and requested the prior method be checked.
Verified actual historical log (not only handoff):
`/home/ahmad/.codex/sessions/2026/10/22/rollout-2026-10-22T23-50-29-01a16485-72e4-7340-934d-3bfe33f3c698.jsonl`.
Relevant original commands/output around lines 735–852; real UID was redacted
before output during investigation. Original sequence:

- Targeted bus1 probe found 24.
- Created Python3.8 `/home/tpt/pn532-test-venv`; installed PN532/Blinka.
- First launch failed `No module named Jetson`; installed Jetson.GPIO2.0.17 and
  busdevice5.2.17, then launched:
  `/home/tpt/pn532-test-venv/bin/python -u /home/tpt/pn532-test.py`.
- Actual log at 2026-10-22T19:40:17Z reports firmware chip0x32 v1.6 and READY;
  19:40:41Z reports repeated card UID detections of length4.
- Test was stopped explicitly with SIGINT before handoff.

Compared current device script with original `/tmp/tpt-pn532-test.py`:
identical SHA256 `5487e04887c988d394070aa8e835a37f7b7b409d8c2294e1f557f17d3947d549`.
Current original-venv versions remain Blinka9.1.0, PN5322.4.9, busdevice5.2.17,
Jetson.GPIO2.0.17.

Replayed the EXACT original script/venv, with UID output suppression and live I2C
runtime-status monitoring via `/tmp/tpt-replay-pn532.py` on laptop/device.
Observed `suspended -> active -> suspended`; original script failed before
firmware with kernel TimeoutError110 and `No I2C device at address: 0x24`.
Thus the controller *does* wake for access; idle runtime suspended alone is not
proof of the cause. Kernel logs confirm tegra-i2c7000c400 transfer timeouts0x24.
Original script and installed polling path do not call `power_down()`; cleanup
only deinitializes bus. Cause remains unresolved (module/bus state, physical
power/wiring, or controller condition); do not assert screen sleep or broken
module as established. Next useful step is safe module power-cycle/physical
check and same-script replay, rather than reinstalling tested libraries.

## Follow-up: repeated desktop screen sleep

User reported Jetson sleeping again. SSH, uptime, desktop session and tpt-rfid
service were active; no suspend-service event found. Desktop settings showed
`org.gnome.desktop.session idle-delay=uint32 300`, AC sleep action `suspend` with
AC timeout0, idle-dim=true. This establishes a five-minute desktop idle timer,
not whole-system suspend or the cause of PN532 failure.

Saved those three original GSettings values privately on Jetson in
`/home/tpt/nfc-backups/20261023T025719/desktop-power.json` (mode600), then set:
- org.gnome.desktop.session idle-delay: uint32 0
- org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type: nothing
- org.gnome.settings-daemon.plugins.power idle-dim: false

Applied successfully through user's existing session D-Bus. Also successfully
ran `xset s off`, `xset -dpms`, and `xset dpms force on` against the existing X11
session, requesting display wake. These X11 settings are session-local; exact
prior X11 timers were not persisted, and logout/login restores desktop defaults.
Lock-screen authentication setting was not changed.
To roll back GSettings, read only this dedicated non-secret JSON and invoke
`gsettings set <schema> <key> <value>` for each saved record using
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus as tpt, then logout/login
for normal desktop/X11 policy. No production app code/config/database change.
PN532 communication recovery has NOT been established by this desktop change.

User requested another check after disabling desktop sleep. At device03:06:55,
SSH and service remained active, idle-delay0 and AC sleep actionnothing verified.
Replayed original script/venv again: I2C runtime suspended->active->suspended,
TimeoutError110 and No I2C device at0x24; exit1. Desktop keep-awake did not restore
PN532 communication. No firmware/card detection, deployment still pending.

## Troubleshooting plan after user confirms no cold start

User asked for troubleshooting; confirmed PN532 LED is on and no power-cycle has
been performed yet. Main verified no users of /dev/i2c-1 at pre-test check;
Blinka9.1.0 jetson_nano board maps SDA/SCL to GEN2 I2C / bus1; device-tree clock
is100000Hz. One native read-only status transaction
`timeout 15s i2ctransfer -y 1 r1@0x24` failed with Connection timed out (exit1),
with same kernel timeout dump. Thus failure persists without Python/library's
zero-length probe. No pinmux/GPIO/controller settings were changed.

Read-only source research:
- NVIDIA staff confirms Nano clock-stretch support and controller reinit after
  timeout; a thread with matching dump reports SCL held low. This is a hypothesis
  to discriminate, not a measurement of this board:
  https://forums.developer.nvidia.com/t/i2c-issue-timeout-error-messages/187257
- NXP PN532 manual describes readable busy status RDY0 and ordinary wake-up
  stretching under2ms: https://www.nxp.com/docs/en/user-guide/141520.pdf
- PN5322.4.9 reset toggles hardware only with a wired reset pin. Four-wire original
  test calls bus.deinit at exit, with no physical module reset:
  https://raw.githubusercontent.com/adafruit/Adafruit_CircuitPython_PN532/2.4.9/adafruit_pn532/adafruit_pn532.py

User has been instructed: save desktop work, orderly Shut Down via Jetson UI,
then remove power until Jetson AND PN532 LEDs are off, reconnect and boot without
changing SDA/SCL. Async readiness question pending. Do not remotely power off
without coordinating; physical re-power requires user. All NFC probes stopped.
Once user confirms boot completed, verify uptime/boot state, ensure one reader
owner, run ONE firmware probe. If restored, run hardware acceptance/two taps.
If still failing after verified cold start, inspect wiring/mode with power off;
measure module supply and idle SDA/SCL with meter/analyzer if available. Do not
keep repeating identical failed probes or reinstall tested dependencies.

## Superseded checkpoint

Hardware blocker resolved after user cold start; real NFC registration/session
acceptance passed. Latest verified backup includes venv, production unchanged.
Continue from `2026-10-23-nfc-stage1-complete.md`, not earlier blocker steps.
User requested handoff per stage with only next opening prompt returned.

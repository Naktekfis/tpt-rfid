# Alarm confirm delay + presence worker — deployed to Jetson

## Goal and user decisions
User reported short/insensitive UHF range and kiosk delay, worse on "kecolongan"
(tool-loss alarm). User declined per-distance measurements and chose option A:
software fixes without measuring first. User authorized SSH/deploy (2026-10-23).

## Change
- `utils/tool_presence.py`: an unborrowed tool that leaves the field now waits
  `alarm_confirm_seconds` before alarm/beep/photo; if it is read again first, the
  alarm is dropped. A session started during the wait borrows the tool instead.
  `background=True` moves DB/kiosk/alarm handling to one worker thread; the reader
  thread only runs `PresenceMonitor.update`. `stop()` ends the worker and makes
  later rounds run inline (tests rely on this via `tests/conftest.py`).
- `config.py` `RFID_ALARM_CONFIRM_SECONDS` (default 5, then 2, now 0); `app.py` wires it,
  `background=True`, and `presence_service.stop()` in cleanup.
- `RFID_MISSING_AFTER` deliberately NOT raised: it also sets how fast an in-session
  borrow is registered. Jetson effective value is 1.5 s (no `.env` override).
- Laptop only: `alarms_cancelled_total` counter in `LossDiagnostics`, README/.env.example rows.

## Jetson state
- `tpt@10.42.0.14` (via laptop USB ethernet `enx002432b4d00b`, 10.42.0.1; must be UP).
- Live tree differs from laptop: laptop has undeployed work (VX6336 timeout/recovery in
  `utils/rfid_reader.py`, `LossDiagnostics`, UI cleanup). A Jetson-specific
  `tool_presence.py` (live version + this change only) was installed: 5 files
  `app.py config.py utils/tool_presence.py tests/conftest.py tests/test_tool_presence.py`.
- Backup: `~/tpt-alarm-confirm-20261023/backup/source-before.tar`; staging `candidate/`.
  Rollback: untar backup in `~/tpt-rfid`, then `kill -HUP <gunicorn MainPID>`.
- Reloaded with HUP: master 4815, new worker 9283, ActiveState active, NRestarts 0,
  `/api/rfid/status` 200, ~18.5 rounds/s, no listener/round errors after reload.
- The auto-mode classifier blocks remote writes from the agent; the user ran the
  write/reload commands via `!`. Read-only SSH works from the agent.

## Update 2026-10-24: confirm delay lowered to 2 s
User asked for 2 s. Jetson `.env` now has `RFID_ALARM_CONFIRM_SECONDS=2` (backup
`~/tpt-alarm-confirm-20261023/backup/env-before-2s`); reloaded with HUP, new worker
9866, active, NRestarts 0, health 200, ~20 rounds/s, no round errors. Laptop
default also 2 (config.py, app.py, .env.example, README). Alarm now fires about
3.5 s after the last read (1.5 s missing + 2 s confirm).

## Update 2026-10-24: confirm delay set to 0 s
User then chose 0 s (the 1.5 s `RFID_MISSING_AFTER` is enough delay). Jetson `.env`
`RFID_ALARM_CONFIRM_SECONDS=0` (backup `env-before-0s`), reloaded, active, health 200.
Laptop default also 0. Alarm timing is back to pre-change (1.5 s after last read);
only the off-reader-thread worker remains in effect. Returns were never affected.

## Verification
- Laptop `scripts/check.sh`: Ruff OK, 356 passed, 1 skipped (before a small `stop()`
  race fix; after it, targeted 46 passed + Ruff).
- Jetson staging pytest: 276 passed, 1 skipped, 1 failed `test_kiosk.py::test_timeout_summary_idle`
  — pre-existing: live `utils/kiosk.py` has `SUMMARY_SECONDS = 5.0` but live
  `tests/test_kiosk.py` still expects 8 s. Unrelated to this change.

## Remaining
1. User feedback on false alarms / delay in real use; tune `RFID_ALARM_CONFIRM_SECONDS`
   via Jetson `.env` (edge-of-field gaps of 2–10 s were seen in old probe data).
2. Fix the stale Jetson `tests/test_kiosk.py`.
3. Range itself is a VX6336 hardware limit (0–20 cm, 13 dBm max); software cannot extend it.
4. Undeployed laptop work (timeout/recovery, diagnostics, UI) still needs its own deploy decision.

## Update 2026-10-24: full laptop code deployed
User asked to deploy everything. Laptop `scripts/check.sh` 356 passed, 1 skipped;
Jetson staging `~/tpt-full-deploy-20261024/candidate` on Python 3.8: 356 passed,
1 skipped. Installed 47 files with rsync `--backup` (replaced files in
`~/tpt-full-deploy-20261024/backup/`, list in `installed-files.txt`; excludes in
`excludes`, `migrations/` not deployed). Rollback: `rsync -a backup/ ~/tpt-rfid/`
(new files from the list must be removed by hand), then HUP. After HUP: worker
10974, active, NRestarts 0, health/kiosk 200, devices: reader vx6336, NFC pn532 and
camera connected, ~20.8 rounds/s, 0 round errors, 0 no-response, no tracebacks.
Laptop and Jetson code now match (rsync -c dry-run: 0 differences outside excludes).
The VX6336 timeout/recovery fix and UI cleanup are now live. Kiosk Chromium was
started before the deploy and must be reloaded to pick up new JS/CSS (no cache busting).

## Update 2026-10-24: back to 2 s (alarm flapping)
User reported the red alarm not clearing after a quick return and noisy beeps.
Jetson DB (read-only) showed the server closes alarms 0.7–1.6 s after return, but a
freshly returned tag re-alarmed every few seconds (missing 1.5 s → alarm → read →
closed → repeat). Not a JS/HMI render delay (kiosk.js hides the overlay on the same
poll that updates the board). Set `RFID_ALARM_CONFIRM_SECONDS=2` on Jetson `.env`
(backup `~/tpt-full-deploy-20261024/env-before-2s`) and as laptop default; reloaded,
active, health 200. Kiosk browser still needs Ctrl+Shift+R for the deployed UI.

## Update 2026-10-24: mouse-move-to-refresh kiosk
User: kiosk sometimes only updates after moving the mouse (same open item as
`2026-10-23-overall-hmi-rfid-latency-deployed.md`). At check time Chromium was NOT
running on the Jetson (active window was gnome-terminal), so live flags could not be
read. Added `--disable-background-timer-throttling --disable-renderer-backgrounding
--disable-backgrounding-occluded-windows` to `deploy/jetson/kiosk.sh` and installed it
on the Jetson (backup `~/tpt-full-deploy-20261024/kiosk.sh.before`). Takes effect on
the next kiosk launch. Unverified fix; if it persists, next hypothesis is GPU/compositor
paint stall (try `--disable-gpu-compositing`) or `unclutter -root`.

## Update 2026-10-24: tile before alarm; mouse issue round 2
- User: tile turned red before the alarm. Cause: `left` set presence `missing` at
  1.5 s while the alarm waited 2 s more. Now an available tool pending confirmation
  stays `present` until the alarm fires (`_fire_due_alarms` sets `missing`); session
  borrows still mark `missing` at once. 2 tests added. Laptop check 358 passed,
  1 skipped; Jetson staging 358 passed, 1 skipped; installed (backup
  `~/tpt-full-deploy-20261024/backup-tile/`), HUP, active, health 200.
- Mouse issue persisted with the anti-throttling flags (Chromium confirmed running
  with them), so throttling is ruled out. Added `--disable-gpu-compositing` to
  `kiosk.sh`, installed and relaunched Chromium on DISPLAY=:0 (confirmed flag, window
  active). Unverified by user yet. Next if it persists: `--disable-gpu`, then remove
  `unclutter -root`. Note: `pkill -f chromium-browser` over ssh kills the ssh shell
  itself; use `pgrep -x chromium-browse`.

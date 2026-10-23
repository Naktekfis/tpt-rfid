# NFC stage 3 — operational checkpoint and next-stage scope

## Goal, decisions, authorization

Read `AGENTS.md` and stage 2 handoff first. Deployment is already complete; do
not repeat NFC implementation or dependency installation. User is at the kiosk.
User confirmed new-account registration works (`udh oke sebenarnya`) and NFC
card detection is very good. Do not describe this as complete acceptance of all
borrow/return, binding, camera, admin, or restart scenarios.

Deployment/testing remains authorized. Preserve local edits, old identity data,
photos, face embeddings, models, and transactions. No card writes. No general
data deletion permission. **Narrow exception explicitly approved this session:**
delete item `tisu`, its one physical unit, and its two related alarm records after
private backup. This exception has been executed; do not repeat it.

User wants work triaged between immediate changes and handoff, then a Markdown
handoff and only an Indonesian opening prompt for the next stage in final chat.
`RTK.md` and generic safety skill's `.Codex/knowledge/GATES.md` remain absent;
actual gates are `.claude/knowledge/GATES.md`.

## Git and running device

- Laptop `/home/ahmad/tpt-rfid`: `main`, HEAD `99cc143`, many existing uncommitted
  NFC and agent-setup changes preserved. This stage edits only
  `static/css/kiosk.css` and adds this handoff. No commit/push/reset/clean.
- SSH `tpt@10.42.0.14`; production `/home/tpt/tpt-rfid`, same branch/HEAD,
  intentionally dirty NFC deployment preserved.
- At checkpoint systemd active, Gunicorn master **4567**, sole new worker
  **10305**, `NRestarts=0`. Re-read PIDs before signaling. Systemd restart count
  does not count worker replacement.
- Boot ID remains `bbe0c651-2492-4ccf-85ad-0c0f72de2327`: no reboot/cold-start
  verification occurred. Live systemd unit, venv, and `.env` unchanged this stage.

## Executed and verified

1. Read-only health and ownership verification: one app worker. Seven samples
   over 30 seconds before restart: PN532 and UHF connected, camera running,
   frame ages 0.008–0.033 s. No standalone PN532 probe while app owns hardware.
2. User tested new-account registration successfully and praised NFC detection.
   User later confirmed kiosk idle, registration finished, and tools back in rack
   before restart. Server state was also asserted idle immediately before stop.
3. Panel-right CSS: compact transaction rows and 3rem thumbnails scoped to
   `.session-lists`; cap transaction area at 38%, allow overflow scrolling;
   reduce outer padding to extend usable area toward bottom; rack grid fills
   remaining height and scrolls while preserving five-column tile design.
   Idle screen and alarm styles were not changed by this stage.
4. Prepared private stage-3 backup directory and prior deployed CSS. Suspended
   master with SIGSTOP, SIGTERM sole old worker **9028**, waited for exit/zombie,
   then performed database/CSS changes. Always resumed master in `finally`.
   No overlapping hardware owners. An initial attempt failed before any signals
   because Jetson lacks `/proc/<pid>/task/<pid>/children`; use
   `ps --ppid <master> -o pid=` on this kernel.
5. Created SQLite online backup with file mode 600, `quick_check=ok` while worker
   stopped. Under `BEGIN IMMEDIATE` and `foreign_keys=ON`, reasserted exact scope:
   ToolType id 6 name `tisu`; sole Tool id 6/type 6 available; zero transactions;
   exactly two alarms. Deleted exactly those 2 alarms, 1 unit, and 1 type.
   Checked table-count deltas and `foreign_key_check` empty / `quick_check=ok`
   before commit. Students, NFC cards, face embeddings, transactions counts
   unchanged. No other deletion, no schema change. Old worker's presence cache
   removed naturally through replacement.
6. Installed only candidate CSS atomically. Seven samples over 30 seconds after
   worker replacement: PN532 connected firmware `[50,1,6,7]`, UHF connected,
   camera running with frame ages 0.010–0.034 s. NFC sequence stayed zero in this
   window: connection health is **not proof of a post-restart physical tap**.
7. HTTP-served CSS SHA256 matches laptop:
   `bd145e17a8fc6d33b53607ba4660204ff32aeae5d6c2a2c11f579b747dd90421`.
8. `git diff --check` passed. `.venv/bin/python -m pytest -q tests/test_pages.py`
   → **20 passed, 1 skipped in 0.47s**. No Python implementation changed, so
   stage 2's full suite was not rerun. No browser screenshot or automated layout
   check was performed; kiosk visual acceptance is still awaiting user feedback.

## Backup and rollback

Original deployment backup remains `/home/tpt/nfc-backups/20261023T031856/`;
see stage 2 handoff for contents. Do not use obsolete 025719 rollout example.

New `/home/tpt/nfc-backups/20261023-stage3-operational/` mode 700 contains:

- `before-tisu-delete.db` mode 600: valid online snapshot immediately before the
  explicitly approved deletion, after user registration. Keep private on Jetson.
- `kiosk.css.before`: prior deployed CSS.
- `kiosk.css.candidate`: installed stage-3 CSS.

CSS rollback can restore only `kiosk.css.before` to production CSS and refresh
browser. Do not reset the repo or restore whole database routinely. If tisu must
be recovered, reconcile and selectively restore its exact type/unit/alarm rows
from snapshot under a stopped worker; do not overwrite later registrations or
transactions. Old deployment code/config rollback remains as in stage 2.

## User feedback and next-stage priorities

1. **Admin navigation/management:** split tool monitor and student monitor into
   separate menu destinations. History should remain a log/recap. Add practical
   tool editing/removal and richer student monitoring. Design deletion/archive
   semantics around historical transaction/alarm foreign keys; the tisu exception
   does not authorize deleting other records. Current admin API has tool creation,
   unit creation and photo update, but no tool edit/delete operation.
2. **Email discoverability:** existing `Kirim pengingat` remains in
   `/admin/monitor` tool/loan table, only when `status == borrowed` and
   `borrower_email` exists. `app.py` `/api/admin/tools_status` requests email;
   `/api/admin/send_warning_email` still uses Flask-Mail. Export email is also
   in history. No email was sent, credentials inspected, or SMTP success verified.
   Make this action discoverable in the separated admin screens.
3. **UHF responsiveness:** user reports slow response. Verified source defaults:
   `RFID_MISSING_AFTER=5.0` governs absence, kiosk poll `POLL_MS=1000`, admin
   lists `LIST_MS=15000`, admin alarm poll `STATE_MS=3000`.
   `RFID_ABSENT_TIMEOUT=2.5` is scan debounce, not presence departure threshold;
   `LAST_SEEN_WRITE_INTERVAL=10` throttles persistence, not inventory reads.
   Effective environment override was not inspected. Reader status ScanTime
   25500 ms is **not measured inventory latency**; stage 2/reference notes show
   much faster ordinary rounds. Measure departures/returns and stationary-tag
   gaps with realistic rack/tag placement before tuning. No reader settings or
   timing changed this stage. Do not start a second hardware owner for stats.
4. **Security evidence (requested, unimplemented):** capture a camera photo for
   every alarm and expose evidence/time/tool/resolution in an admin security
   view. User also wants an audible alarm if camera is covered. Existing
   AlarmEvent stores no image; `ToolPresenceService` only persists event/beeps.
   Design camera evidence storage and retention, capture failure handling,
   obstruction thresholds and debounce, distinction from low light/disconnection,
   and recovery/acknowledgement. A frame is evidence, not verified identity;
   no need to reactivate archived face recognition. Use mock/synthetic tests.

## Acceptance still pending

Asked user to refresh Ctrl+Shift+R, tap registered card after restart, evaluate
compact right panel, perform one borrow/return, finish session, and inspect admin
camera preview and reminder button (without sending email). Response pending at
this checkpoint. Do not claim these passed without a subsequent response.

Existing-account admin binding, actual tool-photo capture/storage, admin login/
logout operational acceptance, held-card/busy-session behavior, repeated worker
restart, full service start, reboot/cold-start and longer soak remain unverified
in this stage. New-account registration alone passed by user report. Prior
PN532 I2C cold-start issue is unresolved as a reliability question.

Next read-only command:

```bash
ssh tpt@10.42.0.14 'systemctl is-active tpt-rfid; curl -fsS http://127.0.0.1:5000/api/devices/status'
```

Continue from outstanding physical-test feedback; then prioritize admin split
and management. Preserve all existing deployment/local work and backups.

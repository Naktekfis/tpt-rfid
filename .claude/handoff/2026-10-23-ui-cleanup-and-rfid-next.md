# UI cleanup complete locally; UHF first-acquisition question remains open

## User decisions and boundaries

User requested local kiosk/admin UI cleanup with frontend-design, preserving
the heavily dirty tree, existing data, test results and backups. This work is
complete locally; no commit or deployment. Latest request: write this handoff
and a next-session opening message, retaining the question: why does tool RFID
have first-acquisition delay while NFC identification feels smooth?

This request does NOT authorize device work. No Jetson access, service changes,
reader settings, tag writes, authentication changes, or real student data access.
Do not repeat VX6436 work or reactivate archived face features. Preserve all
existing changes/results/backups. Read AGENTS.md and .claude/knowledge/GATES.md.
RTK.md referenced by instructions was not found at repo root.

## Git state

Branch main, HEAD 99cc143, heavily dirty before and after UI work. Many modified,
deleted and untracked files predate this session. Do not reset, clean, or assume
the whole diff belongs to UI cleanup. No commits made.

## Completed UI changes

- Retained local Source Sans 3, ITB blue, dark kiosk instruction area and simple
  rule-based visual language. No external asset dependency added.
- static/css/ui.css: readable root size (16px floor), dynamic viewport height,
  minimum 44px controls, persistent loading-error component, reduced-motion rule.
- static/css/pages.css: responsive topbar, forms, tool layout and public board;
  touch-sized small controls/link buttons; table scroll regions; consistent admin
  navigation and table headers. Alarm/return queues sit side by side on wide
  screens. Removed duplicate navigation on tool/student monitor pages; primary
  add-tool action now lives in the tool-monitor heading.
- templates/app_base.html: shared admin navigation with active-page indication.
- templates/kiosk.html + static/css/kiosk.css: three-step instructions, responsive
  idle/session/alarm layouts, flexible rack grids, more room for transactions,
  wrapping long names, and touch-sized registration link.
- static/js/ui.js: shared persistent loadNotice(message, retry), deduplicated
  announcements, accessible horizontal table wrappers on page templates.
- static/js/kiosk.js: API success:false now triggers outage feedback; initial
  loading replaced on failure; stale data retained; identical-data recovery clears
  banner. Deduplicated device banners; session buttons show busy text/state.
  Unit status marks now have accessible labels.
- static/js/monitor.js: handles success:false, persistent outage banner, initial
  failure message and recovery with unchanged data. static/js/board.js adds
  accessible unit labels.
- static/js/admin_monitor.js, admin_students.js, admin_history.js and respective
  templates: persistent failures near affected data, retry controls, retained
  stale data, meaningful initial failure/empty copy. Monitor/student loading
  guarded against overlapping polls. History versioning ignores older responses
  after a later filter request. Basic Indonesian copy cleaned in admin menu/history.

API endpoints, payload contracts, CSRF, authentication and backend/hardware logic
were preserved. register.js and other earlier dirty files were not edited here.

## Verification and artifacts

- Full check:
  PYTHONPATH=/tmp/tpt-ui-preview/noenv SECURITY_STORAGE_DIR=/tmp/tpt-ui-preview/test-security scripts/check.sh
  Ruff passed; 327 passed, 1 skipped in 10.07s.
- After final template adjustments, same isolated environment with
  .venv/bin/python -m pytest -q tests/test_pages.py
  yielded 20 passed, 1 skipped in 0.49s.
- node --check passed for ui.js, kiosk.js, monitor.js, board.js,
  admin_monitor.js, admin_students.js, admin_history.js.
- git diff --check passed.
- Independent read-only source review found no concrete new breaking issue.
- Final browser harness: node /tmp/tpt-ui-preview/check.cjs, exit 0.
  Eight screens at widths 360/768/1366px; no document/body horizontal overflow,
  no visible .btn/.input/.linkbtn below 44px height, no page JS errors.
  Checked unknown card/session/summary, full/compact alarm at desktop/mobile,
  initial failure, stale-data retention, identical-data recovery, admin retry,
  search empty results, native edit dialog and preserved edit payload, session
  end request and busy state. Synthetic API responses only.

The browser preview was a separate Flask/Jinja renderer, NOT app.py; it did not
import the real app or open its database. Latest preview enables template auto
reload. Server was stopped after validation. Test-only sitecustomize.py disables
dotenv.load_dotenv to avoid repository secret reads; SECURITY_STORAGE_DIR is
isolated. Tests use the existing in-memory DB and mock hardware fixtures.

Temporary artifacts (may not survive reboot; verify existence):
/tmp/tpt-ui-preview/{server.py,check.cjs,browser-check.log,results.json}
and screenshots kiosk-desktop.png, kiosk-mobile.png, admin-desktop.png,
kiosk-session.png, kiosk-summary.png, kiosk-unknown_card.png,
alarm-{idle,session}-{1366,360}.png. Harness npm dependency is outside repo.
Browser evidence is synthetic; no physical kiosk/reader validation claimed.

## RFID question: known facts versus hypotheses

Read .claude/handoff/2026-10-23-vx6336-offline-recovery.md for the preceding
diagnosis and exact recovery changes. Its final instruction to START UI cleanup
is superseded by the completed work above. Its hardware limits remain in force.

NFC identification (PN532 over I2C) and tool UHF inventory (USB HW-VX6336) are
different reader/service paths. Smooth NFC does not establish that the UHF
reader, serial transaction, presence processing or board display is timely.
Do not infer a specific RF/firmware/software cause from that comparison alone.

The primary cause of the observed physical first-acquisition delay remains
UNKNOWN. A software failure path was established locally: missing reader info
could leave the old 1.5s timeout while inventory could still run up to 25.5s,
allowing a later command to be lost while busy or a late terminal misattributed.
Timeout/busy recovery is fixed and tested LOCALLY, NOT deployed. It is not proof
that this path caused the observed delay, nor that the fix solves it physically.
The previous roughly 50ms inventory observations were repeated sightings after
acquisition, not placement-to-first-acquisition measurements. Distance,
orientation, casing and metal remain hypotheses. Current Jetson/service state
was not checked; do not trust an older handoff's service state.

## Next work, in order

1. Start with the user's unresolved RFID-versus-NFC question. Inspect local
   current code and retained non-personal results; do not repeat completed UI
   work or completed recovery implementation. Before reader/platform code work,
   read TARGET_PLATFORM.md, RFID_VX6336.md and FACE_MODELS.md per AGENTS.md.
2. Map UHF latency stages separately: placement to first EPC response, response
   to listener/presence/session update, API response, browser render. Compare NFC
   only to identify different stages, not as a benchmark proving UHF RF health.
   Establish what existing evidence can and cannot distinguish. Do not present
   nominal timeout/guard bounds as measured physical delay.
3. Prepare a concrete measurement approach that separates first acquisition
   from repeated sightings. The earlier ENTER placement marker was invalid:
   tags could be acquired during movement before ENTER. Do not repeat that
   procedure or re-measure repeated sightings as first acquisition.
4. Any Jetson inspection, deployment, service action or physical trial still
   requires fresh explicit user permission. Prepare local analysis/test changes
   or a reviewable measurement proposal first; never assume handoff authorizes
   hardware access. After authorization, verify current service/serial owner.

No external blocker for local analysis. Device validation is approval-gated.
No claim of Python 3.8 runtime validation added in the UI session.

First safe next command:
git status --short
Then read the recovery handoff/relevant local knowledge and inspect current
UHF/NFC pipelines within the boundaries above. No SSH or deployment command.

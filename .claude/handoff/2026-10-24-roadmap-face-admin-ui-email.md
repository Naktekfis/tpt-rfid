# Roadmap: face admin login, admin-only UI, alarm timeout, email reminders, logos, GitHub deploy

Written 2026-10-24 from the user's request to collect the next big batch of work.
Nothing in this file is implemented yet. Previous state: see
`2026-10-23-alarm-confirm-deployed.md` (Jetson == laptop code, nothing committed).

## User requests (their words, paraphrased)
1. Reuse the archived face system as **admin login** ("sayang ngga kepake").
2. **Drop the student pages**; keep the admin pages, with the improved UI.
3. Face **enrollment mechanism** is not designed yet (user has no idea yet).
4. Later, **wrap it as a real app** once everything else is done.
5. **Deploy via GitHub** from now on so deploys are recorded. Past manual deploys stay as
   they are (no need to reconstruct them).
6. UI **outside the kiosk session screen is still ugly**: redo it with the same approach
   as the earlier UI cleanup (frontend-design + `ui-review` agent, synthetic preview).
7. Alarm page/overlay must **not stay on forever**: add a timeout.
8. **Gmail reminders**: an automatic email when a borrow is **over 2 days**, plus a manual
   message the admin can send.
9. **TF and ITB logos** in the corners of the kiosk session page.

## Facts checked in the code (2026-10-24)
- Face code is archived in `legacy/face/` (`utils/face.py`, `face_service.py`,
  `liveness.py`, `cv_handler.py`, `routes/face_routes.py`, `cv_routes.py`, templates,
  tests, `scripts/face_bench.py`, `fetch_face_models.py`). Models are still in
  `models/face/` (YuNet detector, SFace recognizer, MiniFASNet V1SE/V2 liveness).
  `FaceEmbedding` model and stored embeddings are still in `utils/models.py`/the DB.
  `.claude/knowledge/FACE_MODELS.md` must be read first. CV deps: `requirements-cv.txt`;
  camera already runs on the Jetson (`CAMERA_ENABLED`, `utils/camera.py`).
- Admin login today: PIN (`ADMIN_PIN_HASH`, default `133133` when unset — the Jetson
  logs "using the default admin PIN", so the device runs on the default PIN).
- Student-facing pages in `app.py`: `/` landing, `/mahasiswa` welcome, `/daftar`
  (`/register`) NFC registration, `/monitor` public board, `/kiosk`. Admin pages:
  `/admin`, `/admin/login`, `/admin/monitor`, `/admin/input_tool`, `/admin/history`,
  `/admin/export_history`, `/admin/students`, `/admin/security`.
- Email: Flask-Mail on `smtp.gmail.com` (`app.py:62`). Manual warning email exists:
  `POST /api/admin/send_warning_email` (`app.py:734`), used by `admin_monitor.js` and
  `admin_students.js`. **No automatic/scheduled email exists.** `Transaction.is_overdue`
  uses `due_at`. Mail credentials live in `.env` (gated: do not read/print them).
  `deploy/jetson/` already has a systemd timer pattern (`tpt-rfid-backup.timer`).
- Alarm overlay: `kiosk.js` `renderAlarm` shows it while `get_open_alarms()` is non-empty;
  alarms close only on return ("returned") or admin PIN acknowledge. No timeout.
- Logos exist: `static/assets/Logo_Teknik_Fisika.jpg`, `Logo_Institut_Teknologi_Bandung.png`.
- GitHub: `origin https://github.com/Naktekfis/tpt-rfid.git`, `.github/` has only a PR
  template. Laptop working tree is heavily dirty and **uncommitted**; HEAD `99cc143`.
  Jetson `~/tpt-rfid` is a git checkout at `99cc143` with files copied over by rsync,
  so its tree is dirty too (content equals the laptop as of 2026-10-24).

## User answers (2026-10-24) — these supersede the questions below
- A1 Remove **`/mahasiswa` (welcome) and `/` landing** only, because the UX changes.
  `/daftar` and `/monitor` stay unless the user says otherwise.
- A2 **Face is the main admin login, PIN is the fallback.** Several admins, each with
  their own face.
- A3 Enrollment proposal accepted (admin logs in, "Daftarkan wajah", N frames +
  liveness, stored per admin; re-enroll/delete there). Extra task: **research a stronger
  anti-spoofing method that still runs on the Jetson Nano 4GB (JetPack 4.6.1, Py 3.8,
  CPU/old CUDA)** before building. Current archive uses MiniFASNet V1SE/V2 (passive,
  Silent-Face). Things to compare, not decided: MiniFASNet ensemble tuning, adding an
  active challenge (blink / head turn) on top of passive, other light FAS models with
  ONNX/TensorRT export; measure fps on the device.
- A4 Alarm: add **a timeout and a manual "exit/close" button** on the alarm overlay.
  Purpose: the kiosk must become usable again for others to borrow, whether the alarm is
  real theft or a bug. Duration not given — pick a sensible default (e.g. 60–120 s) in
  config and confirm with the user. Keep the alarm record visible to admin after timeout.
- A5 Email: send **once when the borrow becomes due, and once when it is 2 days past
  due** (`due_at`). Nothing more. Keep the manual admin message.
- A6 App wrapper: later, undecided.
- A7 Deploy: approved going through GitHub. The real goal: **Claude Code can deploy to the
  Jetson by itself.** In this session the auto-mode classifier blocked remote writes
  ("Remote Shell Writes", "Blind Apply"), so the user had to run them via `!`. Plan: one
  reviewed script (`scripts/deploy_jetson.sh <tag>`: push/tag check → ssh → device
  `deploy/jetson/update.sh` that fetches the tag, backs up, runs pytest in staging,
  installs, HUPs, health-checks, rolls back on failure) plus a project permission allow
  rule for exactly that script in `.claude/settings.json` (use `update-config` skill).
  Pushing still needs the user's OK per GATES unless they grant it durably.
- Mouse issue: **fixed** by `--disable-gpu-compositing` (user confirmed 2026-10-24).
  Commit `deploy/jetson/kiosk.sh` with the baseline.

## Open questions for the user (original list; see answers above)
- Q1 Which "page mahasiswa" goes: only `/mahasiswa` + `/` landing, or also `/daftar`
  (NFC card registration) and `/monitor` (public board)? Who registers new students'
  NFC cards afterwards — admin only?
- Q2 Face login: replace the PIN, or face + PIN (2 factors), or face with PIN fallback?
  One admin or several (each with own face)?
- Q3 Face enrollment: proposal — an admin already logged in (PIN) opens
  "Daftarkan wajah", camera captures N frames with liveness, stores embeddings tied to
  that admin; re-enroll/delete from the same page. Confirm.
- Q4 Alarm timeout: how long (e.g. 2–5 min)? After the timeout: hide the overlay but keep
  the alarm open in admin, or close it as "timeout"? Does the buzzer stop too?
- Q5 Auto email: "lewat 2 hari" counted from borrow time, or from `due_at`? Send once,
  or repeat daily? Which sender account (needs Gmail app password in `.env`)?
- Q6 "App beneran": PWA/fullscreen on the Jetson, desktop wrapper (Electron/Tauri), or
  Android? Decide later; not now.
- Q7 GitHub deploy: Jetson pulls a tag/branch (`git pull` + reload script), or a GitHub
  Actions self-hosted runner on the Jetson? Recommendation: tagged releases + a
  `deploy/jetson/update.sh` run on the device (simple, recorded by git tags).

## Proposed order
0. **Baseline commit + GitHub deploy path** (needs user OK; gated: push, device):
   commit the current laptop tree as Naktekfis (no Co-Authored-By, see memory), push
   to `origin/main`, tag it. On the Jetson, align the checkout to that commit without
   touching `.env`, `instance/`, `uploads/`, security storage; then write
   `deploy/jetson/update.sh` (fetch tag → backup changed files → pytest in staging →
   install → HUP → health check) and use it for every later deploy.
1. **Quick wins**: logos on the kiosk session page (#9); alarm overlay timeout (#7, after Q4).
2. **Email** (#8, after Q5): scheduled job (systemd timer or in-app thread) that finds
   overdue borrows and sends once per borrow (store "reminded_at" to avoid repeats);
   keep and tidy the manual send in admin. Test with a mock mailer; never print creds.
3. **Admin-only restructure** (#2, after Q1): remove student pages/routes/templates/JS
   and their tests; redirect `/` to `/kiosk` or `/admin`.
4. **Admin UI redesign** (#6): every non-session page on `app_base.html`; same process as
   the 2026-10-23 UI cleanup (`ui-review` inventory → implement → synthetic browser check
   at 360/768/1366 px).
5. **Face admin login + enrollment** (#1, #3, after Q2/Q3): bring back only what is needed
   from `legacy/face/` behind a Mock/Real factory; liveness on; auth change is gated
   (GATES.md: auth logic) — review with `test-review` before deploy.
6. **App wrapper** (#4, after Q6), last.

## Still open from before
- (Resolved) mouse-move repaint: `--disable-gpu-compositing` fixed it, user confirmed.
- Jetson uses the default admin PIN (`ADMIN_PIN_HASH` unset). Set one with
  `scripts/set_admin_pin.py` (gated: auth/secrets) — relevant to #1.
- UHF range is a VX6336 hardware limit (0–20 cm).

## Next session: start here
1. Read this file, `AGENTS.md`, `.claude/knowledge/GATES.md`; `git status --short`.
2. Step 0: ask the user once for the baseline commit + push (identity Naktekfis, no
   Co-Authored-By), then build `deploy/jetson/update.sh` + `scripts/deploy_jetson.sh`
   and the narrow permission rule, and deploy the baseline tag with it.
3. Then step 1 (logos + alarm timeout/exit button), step 2 (due / due+2d emails),
   step 3 (remove `/mahasiswa` and `/` landing), step 4 (admin UI), step 5 (face login:
   start with the anti-spoofing research on Jetson-capable models), step 6 later.
Jetson: `tpt@10.42.0.14` over laptop USB ethernet; read-only SSH works from the agent.

## Progress 2026-10-24 (later session)
- Step 0 DONE. Baseline `dbf1606` tagged `v2026.10.24`, pushed. Deploy tooling
  `deploy/jetson/update.sh` + `scripts/deploy_jetson.sh` + allow rule in
  `.claude/settings.json`; fixed for the Jetson's git 2.17. Deployed `v2026.10.24.2`
  (`be05128`) with it: staging 358 passed/1 skipped (64 s), DB+code backup in
  `~/tpt-deploys/20261024-010629-v2026.10.24.2/`, HUP, master 4648, NRestarts 0,
  camera/pn532/vx6336 connected, Jetson tree clean (detached at the tag).
- User approved push + deploy without asking for the rest of this roadmap.
- `Scanner.zip` left out and git-ignored (user choice).
- Laptop `.env` has placeholder SECRET_KEY/MAIL_PASSWORD (values equal .env.example):
  the email step needs a real Gmail app password in the Jetson `.env` (gated).
- Step 1 DONE, deployed `v2026.10.24.3` (`93bdf26`). Alarm overlay hides after
  `ALARM_OVERLAY_SECONDS` (user chose 30 s) or on "Tutup"; the alarm stays open for admin
  and the board still shows the tool as hilang. The UHF buzzer only beeps once per alarm,
  so there is nothing to stop. TF + ITB logos in the bottom-right corner of the session
  screen. Checked with headless Chrome at 1440x810 on mock hardware. Jetson: staging
  360 passed/1 skipped, healthy, NRestarts 0, reader/NFC/camera connected.
- Dev-server tip: the laptop `.env` enables the real reader; for demos run with
  `RFID_READER_ENABLED=false NFC_READER_ENABLED=false CAMERA_ENABLED=false` and a scratch
  `DATABASE_URL`.
- Step 2 CODE DONE, deployed `v2026.10.24.4` (`f857f28`), reminders OFF.
  `utils/loan_reminders.py` + table `loan_reminders` + `scripts/loan_reminders.py`
  (dry-run counts). Jetson dry run 2026-10-24: due=0 overdue=0. Jetson `.env` has no
  MAIL_USERNAME/MAIL_PASSWORD/LOAN_REMINDERS_ENABLED yet: the user adds them (Gmail
  app password), then `kill -HUP $(systemctl show -p MainPID --value tpt-rfid)`; log
  should say "Loan reminder emails on". Manual admin email unchanged.
- Next: step 3 (remove `/mahasiswa` and `/` landing).

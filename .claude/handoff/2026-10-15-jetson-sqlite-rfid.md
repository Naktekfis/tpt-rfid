# Handoff: move tpt-rfid to Jetson Nano + SQLite + USB UHF reader

Written 2026-10-15 by the previous session. Branch `cvtest`. Start by reading this file, then `AGENTS.md` (auto-loaded), `.claude/knowledge/TARGET_PLATFORM.md`, and `.claude/knowledge/RFID_VX6336.md`.

## Goal (user's words, condensed)
The app will run on a **Jetson Nano 4GB (P3450, JetPack 4.6.1, Ubuntu 18.04, aarch64)** with a local **SQLite** database and the **HW-VX6336 USB UHF reader** from `RFID HW/`. It should end up as a light app (web app in a kiosk browser; Electron/Tauri only if needed). **Priority: make it functionally correct first. UI/UX comes later.** There are no tests yet, and the user wants a sensible testing setup. Big scope/design refactors are expected; it is the user's personal repo, so breaking changes are fine.

## Decided (do not reopen)
- Target is the Jetson Nano 4GB above, not Orin Nano (confirmed by the user).
- Database: SQLite file, local. Rationale: one device, one app, low write volume, 4 GB RAM, trivial backup. Setup rules: WAL + `busy_timeout` + `synchronous=NORMAL` (set via a SQLAlchemy `connect` event), one gunicorn worker (threads OK), periodic `.backup` copies (microSD + power loss is the main risk). System SQLite on 18.04 is 3.22 (no `RETURNING`/`DROP COLUMN`), so Alembic needs `render_as_batch=True`. Later: move student photos from BLOB to files. Revisit Postgres only if several kiosks need to share data.
- Reader: USB HW-VX6336 for now. The ESP32/MQTT path stays behind its mock and is not extended.
- Existing PostgreSQL data is dummy: start SQLite empty and use `seed_database.py` for sample data. No migration needed.
- Commits: the agent setup and the user's earlier code edits go in **separate commits**, done later when the user asks.
- Reader: talk to the serial protocol directly with `pyserial`. The vendor SDKs are Windows-only.
- `RFID HW/` stays local and gitignored. The PDFs are copied to `docs/hardware/vx6336/`.
- Agent setup comes from `~/agent-kit` (generic). Project facts go in `AGENTS.md` and `.claude/knowledge/`.

## State at handoff
- (Outdated: agent setup is now committed in 115e672.) **Not committed**: the whole agent setup (`CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `.claude/`, `.mcp.json`, `.github/`, `pyproject.toml`, `scripts/agent_format_hook.sh`, `.gitignore` additions, `docs/hardware/`), **plus the user's own earlier uncommitted edits** to `app.py`, `routes/cv_routes.py`, `setup.sh`, `static/js/scan.js`, `templates/cv_*.html`, `tpt-rfid-installer.sh`, `utils/helpers.py`. Ask the user how to split those into commits; do not lump them together.
- `ruff check .` shows 21 issues (mostly unused imports). `py_compile` passes.

## Known problems (from the audit)
1. Flask-Limiter defaults (200/day, 50/hour per IP, in-memory) also apply to `cv_bp`. `/cv/stats` is polled every 1 s (`templates/cv_live.html:224`) and match checks run every 0.8 s (`templates/cv_face_rec.html:282`), so the pages likely get 429s within a minute. A kiosk is a single IP, so normal pages are at risk too. Not reproduced yet.
2. `cookies.txt` and `raspi _access.txt` are tracked in git (likely credentials). They need `git rm --cached` and the user should rotate whatever is in them. **Gated: ask first.**
3. `start-app.sh` expects `venv/`; the repo uses `.venv/`.
4. `migrations/` is gitignored, so Alembic history is not versioned.
5. `face-recognition` is in the main `requirements.txt` although the code treats CV as optional. It cannot be installed casually on the Jetson.
6. Bare `except:` at `app.py:917` and `app.py:1232`.
7. Python 3.8 breakers: `utils/cv_handler.py:63` (`list[str]`) and `:165` (`str | None`).
8. `file-baru/` duplicates the CV files and can be deleted.
9. `~/.config/autostart/tpt-rfid-kiosk.desktop` points to `/home/ahmad/tpt-rfid-kiosk.sh`, which does not exist.

## Proposed plan (each step its own small commit; tests from step 1 on)
1. **[DONE 79524b8]** Run `scripts/check.sh` (29 tests pass; ruff covers only `tests/` until step 3 fixes the 21 old issues). Behaviour the tests record as-is: a non-JSON body to `/api/scan_student` returns 500 (the other scan/borrow/return routes probably do too); `admin_required` returns a 302 only when the request accepts HTML, otherwise 401; `.venv` was missing Flask-WTF, now installed. Original step text: **Test baseline.** Use pytest + Flask test client against SQLite in-memory: set `DATABASE_URL=sqlite://` before importing `app`, and disable CSRF/limiter in test config. Start with characterization tests for the current behaviour: register student, scan student, scan tool, borrow, return, tools status, admin login. Add a `scripts/check.sh` that runs `ruff check --target-version py38` + pytest, and put it in AGENTS.md "Commands". `app.py` builds everything at import time; if that blocks testing, the first refactor is an app factory (`create_app(config)`) in its own commit with no behaviour change.
2. **[DONE 4b1adbf, e7c199c]** SQLite is the default (`instance/tpt_rfid.db`), pragmas are set in `utils/database_handler.py`, tables are created with `create_all` in `DatabaseHandler.init_app` (Alembic is out for now; Flask-Migrate is still imported in app.py), and psycopg2 is removed from requirements. The concurrent double-borrow bug is fixed with a conditional UPDATE. Left over: the local `.env` still sets a postgresql DATABASE_URL (the user must change it); README, setup.sh and the installer still describe Postgres. Original step text: **SQLite switch.** Default `DATABASE_URL` to `sqlite:///<instance>/tpt_rfid.db`. `ilike` and `with_for_update()` in `utils/database_handler.py` compile fine on SQLite (with_for_update is ignored); the borrow/return race then depends on SQLite's write lock, so add a test. Drop `psycopg2-binary` from the default requirements. Decide whether to keep Alembic (and un-ignore `migrations/`) or use `create_all`.
3. **[DONE 817c47a, 9db5b9e]** Tests pass on CPython 3.8.20 (`PY38=<python> scripts/check.sh`). Flask-WTF is pinned to 1.2.1 because 1.2.2 needs Python 3.9 or newer. `requirements-cv.txt` is split out. Left over: 10 ruff issues in app.py and 1 in utils/helpers.py, which `check.sh` excludes (TEMP) until the user's edits are committed. setup.sh, the installer and the README pip lines still need to mention requirements-cv. Original step text: **Python 3.8 compatibility + requirements split**: `requirements.txt` (core), `requirements-cv.txt` (opencv/face-recognition/psutil), and the existing `requirements-mqtt.txt`. Fix item 7. CI-like check: `ruff check --target-version py38`.
4. **Reader driver.** Add a pure protocol module (frame build/parse, CRC, inventory response parsing) with unit tests using the vectors in `RFID_VX6336.md`. Add a serial reader thread behind a Mock/Real factory, with debounce. Feed scans into the same path that `/api/scan_*` and MQTT use now. **Open question for the user/hardware team:** are student cards UHF too (same reader), or is there a second reader?
5. **Fix audit items 1, 3, 6.**
6. **Device bring-up** (gated: the user runs it or approves it): run the checks in `TARGET_PLATFORM.md`, set up the Python 3.8 venv, a udev rule for the reader, a systemd service for Flask, and a kiosk browser autostart (fix item 9). Record the real device output in `TARGET_PLATFORM.md`.
7. Later: UI/UX pass (`/ui-audit` first), CV on device, and the ESP32/MQTT path (keep or drop?).

## Questions to raise with the user
- Student cards: UHF on the same reader, or something else? (User has not decided yet as of 2026-10-15; design the reader so it just reports EPCs, and let the app decide what they are.)

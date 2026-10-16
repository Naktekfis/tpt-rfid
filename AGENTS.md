# AGENTS.md

> Snapshot of the current state (2026-10). Scope, design, and features are due for large refactors; update or delete lines here as they stop being true.

## Repo Shape
- tpt-rfid is a kiosk web app for borrowing workshop tools (Lab Fabrikasi Teknik Fisika ITB): students are identified by face (USB webcam, YuNet + SFace, head-turn liveness), tools carry UHF tags that one USB HW-VX6336 reader polls continuously (presence; a tool leaving with no session raises an alarm). Flask 3 + Flask-SQLAlchemy on SQLite (`instance/tpt_rfid.db`, tables via `create_all`), Jinja + hand-written CSS (`static/css/tokens.css`, `ui.css`, `pages.css`, `kiosk.css`; self-hosted Source Sans 3, no CDN) + vanilla JS. Plain monitor + mouse + USB keyboard. Plan and status: `.claude/handoff/2026-10-16-face-presence-plan.md`.
- **Target**: NVIDIA Jetson Nano 4GB (JetPack 4.6.1, Ubuntu 18.04, Python 3.8). Read `.claude/knowledge/TARGET_PLATFORM.md`, `RFID_VX6336.md`, `FACE_MODELS.md` before touching platform, reader or face code.
- `app.py` builds the app at import time (config, Mail, CSRF, limiter, DB, reader, camera, face service, presence service, kiosk) and still holds the page routes and the old `/api/*` routes. New logic goes in `utils/` + blueprints in `routes/` (factories `create_*_blueprint(...)` that get their dependencies from app.py).
- `utils/`: `models.py` (Student, ToolType, Tool, Transaction, AlarmEvent, FaceEmbedding), `database_handler.py` (all queries), `vx6336.py` + `rfid_reader.py` (protocol, mock/real reader, round listeners, queued buzzer), `presence.py` + `tool_presence.py` (present/missing, alarms, unverified returns), `camera.py`, `face.py` + `liveness.py` + `face_service.py`, `kiosk.py` (`Kiosk` state machine + `KioskLoop`), `helpers.py`. `cv_handler.py` + `routes/cv_routes.py` are the old experimental `/cv` benchmark (CSRF-exempt).
- `templates/kiosk_base.html` / `app_base.html` are the bases; `templates/<page>.html` pairs with `static/js/<page>.js`. `deploy/jetson/` holds the bring-up (`install.sh` with `DRY_RUN=1`). `models/face/` (ONNX, gitignored) comes from `scripts/fetch_face_models.py`.

## Commands
- Run (dev): `.venv/bin/python app.py` (port 5000). `start-app.sh` uses `.venv/` if present, else `venv/` (the installer's).
- Quick check after Python edits: `ruff check .` and `.venv/bin/python -m py_compile app.py config.py utils/*.py routes/*.py`
- Tests: .venv/bin/python -m pytest -q (tests/, SQLite in-memory, CSRF+limiter off). Full check: scripts/check.sh; `PY38=<py38 python> scripts/check.sh` also runs tests on 3.8.

## Code Direction
- New logic goes in `utils/` modules or a blueprint under `routes/`, not into `app.py`.
- Keep hardware and network behind the Mock/Real factories so the app runs without the reader or a camera.
- Code must run on Python 3.8 (the target's floor); ruff targets py38 via `pyproject.toml` and flags missing `from __future__ import annotations` (FA).
- Catch the narrowest exception you can; broad catches only at request and background-thread boundaries, and they must log.

## Runtime Gotchas
- `RFID_READER_ENABLED` and `CAMERA_ENABLED` default to false (mocks). In development `/debug/presence?epcs=` and `/debug/kiosk/identify?student_id=` drive the kiosk (`scripts/kiosk_demo.sh`). The admin PIN hash comes from `.env` `ADMIN_PIN_HASH` (`scripts/set_admin_pin.py`); without it the default PIN `133133` (`config.DEFAULT_ADMIN_PIN`) is used.
- CSRF is on for all POSTs except `cv_bp`; JS must send the token.
- The rate limiter is in-memory and per IP with no global default (a kiosk is one IP that polls every second); only routes with an explicit `@limiter.limit` are limited.
- `face_recognition` (dlib) is imported lazily because it takes seconds to load; CV deps are optional.
- Timestamps are stored in UTC and shown in WIB through `utils/helpers.py`.

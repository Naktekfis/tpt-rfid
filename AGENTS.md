# AGENTS.md

> Snapshot of the current state (2026-10). Scope, design, and features are due for large refactors; update or delete lines here as they stop being true.

## Repo Shape
- tpt-rfid is a touchscreen kiosk web app for borrowing workshop tools with RFID cards (Lab Fabrikasi Teknik Fisika ITB). Flask 3 + Flask-SQLAlchemy on SQLite (default `instance/tpt_rfid.db`, tables via `create_all`; Postgres via DATABASE_URL still possible), Jinja templates with Tailwind and vanilla JS, ESP32 RFID readers over MQTT. Development runs on a laptop.
- **Moving to** (decided 2026-10-15): an NVIDIA Jetson Nano 4GB (JetPack 4.6.1, Ubuntu 18.04) as the target, and a USB HW-VX6336 UHF reader read directly over serial. Read `.claude/knowledge/TARGET_PLATFORM.md` and `RFID_VX6336.md` before touching platform or reader code. Active plan: `.claude/handoff/`.
- `app.py` is a monolith: it builds the app at import time (config, Mail, CSRF, rate limiter, DB, MQTT/WebSocket clients) and holds every page and `/api/*` route. `config.py` (`get_config()`) reads `.env`.
- `utils/`: `models.py` (`Student`, `Tool`, `Transaction`; student photos are stored as bytes in the DB), `database_handler.py` (`DatabaseHandler`, all queries), `mqtt_client.py` / `websocket_handler.py` (Mock and Real classes behind `create_*` factories), `vx6336.py` (pure reader protocol: frames, CRC, inventory parsing), `rfid_reader.py` (`RFIDReaderMock` / `VX6336Reader` serial thread with debounce behind `create_rfid_reader`; pages poll its current UID via `/api/check_rfid`, `RFID_READER_ENABLED`/`RFID_READER_PORT` in `.env`), `helpers.py` (validation, WIB time helpers), `cv_handler.py` (camera + face recognition).
- `routes/cv_routes.py` is the only blueprint (`cv_bp`, `/cv`): the experimental CV benchmark on branch `cvtest`. It is registered only if its imports succeed, and it is CSRF-exempt.
- `templates/<page>.html` pairs with `static/js/<page>.js`. `deploy/jetson/` holds the Jetson bring-up (`install.sh` with `DRY_RUN=1`, systemd units, udev rule, kiosk autostart, `backup_db.py`); `docs/` holds older deployment/MQTT/ESP32 guides; `scripts/` holds Mosquitto and DB shell tooling. `migrations/` (Alembic) exists locally but is gitignored.

## Commands
- Run (dev): `.venv/bin/python app.py` (port 5000). `start-app.sh` uses `.venv/` if present, else `venv/` (the installer's).
- Quick check after Python edits: `ruff check .` and `.venv/bin/python -m py_compile app.py config.py utils/*.py routes/*.py`
- Tests: .venv/bin/python -m pytest -q (tests/, SQLite in-memory, CSRF+limiter off). Full check: scripts/check.sh; `PY38=<py38 python> scripts/check.sh` also runs tests on 3.8. scripts/test_mqtt_*.{py,sh} are manual broker checks.

## Code Direction
- New logic goes in `utils/` modules or a blueprint under `routes/`, not into `app.py`.
- Keep hardware and network behind the Mock/Real factories so the app runs without an ESP32, broker, or camera.
- Code must run on Python 3.8 (the target's floor); ruff targets py38 via `pyproject.toml` and flags missing `from __future__ import annotations` (FA).
- Catch the narrowest exception you can; broad catches only at request/MQTT callback boundaries, and they must log.

## Runtime Gotchas
- `MQTT_ENABLED` / `WEBSOCKET_ENABLED` default to false, which selects the mock classes; MQTT needs `requirements-mqtt.txt`.
- CSRF is on for all POSTs except `cv_bp`; JS must send the token.
- The rate limiter is in-memory and per IP with no global default (a kiosk is one IP that polls every second); only routes with an explicit `@limiter.limit` are limited.
- `face_recognition` (dlib) is imported lazily because it takes seconds to load; CV deps are optional.
- Timestamps are stored in UTC and shown in WIB through `utils/helpers.py`.

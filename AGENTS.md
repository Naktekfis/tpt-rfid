# AGENTS.md

> Snapshot of the current state (2026-10). Scope, design, and features are due for large refactors; update or delete lines here as they stop being true.

## Repo Shape
- tpt-rfid is a kiosk web app for borrowing workshop tools (Lab Fabrikasi Teknik Fisika ITB): students register and open borrow/return sessions with NFC cards (PN532 I²C at 0x24); UHF tags on tools are monitored continuously by a separate USB HW-VX6336. Flask 3 + Flask-SQLAlchemy on SQLite (`instance/tpt_rfid.db`, additive tables via `create_all`), Jinja + hand-written CSS and vanilla JS. USB camera remains for tool photos; alarm documentation and camera tamper detection are future work. Admin face login (YuNet + SFace, passive liveness `utils/liveness.py` default anti-spoof-mn3, kiosk screen only, PIN fallback) lives in `utils/admin_face.py` + `routes/admin_face_routes.py`, off unless `FACE_LOGIN_ENABLED`; the old student face identification and the CV benchmark stay archived under `legacy/face/`. Device rollout status is in the newest NFC handoff.
- **Target**: NVIDIA Jetson Nano 4GB (JetPack 4.6.1, Ubuntu 18.04, Python 3.8). Read `.claude/knowledge/TARGET_PLATFORM.md`, `RFID_VX6336.md`, `FACE_MODELS.md` before touching platform, reader or face code.
- `app.py` builds the app at import time (config, Mail, CSRF, limiter, DB, UHF reader, camera, NFC service, presence service, kiosk) and still holds the page routes and the old `/api/*` routes. New logic goes in `utils/` + blueprints in `routes/` (factories `create_*_blueprint(...)` that get their dependencies from app.py).
- `utils/`: `models.py` (Student, ToolType, Tool, Transaction, AlarmEvent, FaceEmbedding, StudentNFCCard), `database_handler.py` (all queries), `vx6336.py` + `rfid_reader.py` (protocol, mock/real reader, round listeners, queued buzzer), `presence.py` + `tool_presence.py` (present/missing, alarms, unverified returns), `camera.py`, `nfc_reader.py` + `nfc_service.py`, `kiosk.py` (`Kiosk` session state machine), `helpers.py`.
- `templates/kiosk_base.html` / `app_base.html` are the bases; `templates/<page>.html` pairs with `static/js/<page>.js`. `deploy/jetson/` holds the bring-up (`install.sh` with `DRY_RUN=1`). Existing face models under `models/face/` and stored face data remain untouched; archived tooling is under `legacy/face/scripts/`.

## Commands
- Run (dev): `.venv/bin/python app.py` (port 5000). `start-app.sh` uses `.venv/` if present, else `venv/` (the installer's).
- Quick check after Python edits: `ruff check .` and `.venv/bin/python -m py_compile app.py config.py utils/*.py routes/*.py`
- Deploy: commit, `git tag -a vYYYY.MM.DD[.N]`, push main + tag, then `scripts/deploy_jetson.sh <tag>` (runs the tag's `deploy/jetson/update.sh` on the Jetson: staging pytest, backup to `~/tpt-deploys/`, checkout, HUP, health check, rollback). Never rsync code to the device.
- Tests: .venv/bin/python -m pytest -q (tests/, SQLite in-memory, CSRF+limiter off). Full check: scripts/check.sh; `PY38=<py38 python> scripts/check.sh` also runs tests on 3.8.

## Code Direction
- New logic goes in `utils/` modules or a blueprint under `routes/`, not into `app.py`.
- Keep hardware and network behind the Mock/Real factories so the app runs without the reader or a camera.
- Code must run on Python 3.8 (the target's floor); ruff targets py38 via `pyproject.toml` and flags missing `from __future__ import annotations` (FA).
- Catch the narrowest exception you can; broad catches only at request and background-thread boundaries, and they must log.

## Runtime Gotchas
- `NFC_READER_ENABLED`, `RFID_READER_ENABLED` and `CAMERA_ENABLED` default to false (mocks). In development `/debug/presence?epcs=` and `/debug/kiosk/identify?student_id=` drive the kiosk (`scripts/kiosk_demo.sh`). The admin PIN hash comes from `.env` `ADMIN_PIN_HASH` (`scripts/set_admin_pin.py`); without it the default PIN `133133` (`config.DEFAULT_ADMIN_PIN`) is used.
- CSRF is on for POSTs; JS must send the token. NFC registration uses a fresh, browser-owned capture token (120 seconds), never a client-supplied UID. Existing accounts can bind NFC via admin; replacements are not supported.
- The rate limiter is in-memory and per IP with no global default (a kiosk is one IP that polls every second); only routes with an explicit `@limiter.limit` are limited.
- Optional PN532 dependencies: `requirements-nfc.txt`; optional camera dependencies: `requirements-cv.txt`. `student_nfc_cards` stores NFC bindings separately; legacy RFID UIDs, photos and face embeddings are preserved.
- Timestamps are stored in UTC and shown in WIB through `utils/helpers.py`.

## Working in this repo
- Use the checked-out code and pinned dependency versions as the source of truth. For unfamiliar APIs, consult official documentation for those versions; `.claude/knowledge/REFERENCE_POLICY.md` has the full source order.
- Read `.claude/knowledge/GATES.md` before work involving secrets, real student data, destructive database operations, deployment, auth, or RFID hardware commands. Apply its approval boundaries in light of authorization already given by the user.
- `.claude/knowledge/` and `.claude/handoff/` are project references to read as needed. Claude Code slash commands do not automatically apply in Codex.
- Run the relevant checks listed above after edits. Format changed files with the project's existing tools.
- This is the user's personal repo and broad scope, design, and feature refactors are expected. Keep project guidance lean and update or remove stale statements as the code changes.
- Before committing, respect the repository's configured Git identity. Do not add AI co-author trailers unless the user asks for them.

## Agent workflow
- The main agent owns scope, integration, risk decisions, and the final report. For bounded work that benefits from delegation, use the matching project agent in `.codex/agents/`: `explore-plan` for discovery and planning, `build-bugfix` for implementation or diagnosis, `test-review` for independent diff review, `ui-review` for UI inventory or review, `docs-knowledge` for agent setup and project knowledge, `deep-analysis` for uncertain architecture or root causes, and `quick-scan` for mechanical searches or log summaries.
- Model roles: Claude Opus-like high-judgment work maps approximately to `gpt-6-astra` (`deep-analysis`); Sonnet-like general implementation and review maps to `gpt-6.1-sol` (the project default and five agents above); Haiku-like mechanical searches and log summaries maps to `gpt-6-luna` (`quick-scan`). Choose the stronger model only when the task calls for it; these are workload equivalents, not exact model equivalents.
- Keep small, already understood changes inline. Delegate only when the separate context or independent review is useful. Give the agent a narrow task, established decisions, relevant paths, limits, checks, and expected concise report.
- Treat `explore-plan`, `test-review`, and `ui-review` as read-only roles. A Codex subagent inherits the main session's permissions, so the role instruction does not enforce a separate read-only sandbox.
- For routine review, inspect the diff for behavior-breaking issues and avoid rerunning checks already reported green. Run the full check once near completion when the change warrants it; report the commands and results.
- Use the Claude-style brief when delegating: Task; Decided; Where; Cause/context; Limits; Verify; Report. Pass established findings so the agent does not rediscover them. Keep the returned report concise, without a pasted diff.
- For explicit workflows, use Codex skills: `$tpt-plan`, `$tpt-reference`, `$tpt-review`, `$tpt-ui-audit`, and `$tpt-evidence`. Codex's built-in `/plan` and `/review` are different commands.

## Handoff
- Keep handoffs in `.claude/handoff/` so Claude Code and Codex share the same project history. Read the relevant newest handoff only when resuming that work; check its claims against the current code and Git state. A dated handoff is a snapshot, not a standing instruction.
- When switching sessions or models with unfinished work, or when context is too long to carry reliably, write `YYYY-MM-DD-<topic>.md` with: goal and user decisions; current branch and working-tree state; completed changes and exact verification results; remaining work in priority order; open blockers or required approvals; relevant paths and next command. Mark older claims that were superseded.
- After writing a handoff, continue the authorized task when practical. On resume, read the handoff, verify the current state, and pick up at the first unfinished step. Do not restart completed work.
- Keep durable project rules in `AGENTS.md` and domain terms in `CONTEXT.md`. Treat native agent memories as recall aids; verify them against these files and current code before acting.

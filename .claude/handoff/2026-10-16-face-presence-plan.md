# Handoff: face identity + tool presence monitoring (new UX)

Written 2026-10-16. Branch `cvtest`, last commit `bd89163`, tree clean, nothing pushed. Start by reading this file, then `AGENTS.md` (auto-loaded), `.claude/knowledge/RFID_VX6336.md`, and `.claude/knowledge/TARGET_PLATFORM.md`. The older handoff `2026-10-15-jetson-sqlite-rfid.md` still holds the Jetson bring-up plan (step 6, not run yet) and the parked UI audit list. Where they disagree, this file wins.

This is a **plan, not built**. Nothing below is implemented yet. Phase 0 needs answers from the user before code is written.

## The new concept (user, 2026-10-16, condensed)
- Students are identified by **face**, not by a card. KTM uses a different scanner and is out of scope; do not work on it.
- Students **register their face first** (self-service at the kiosk) before they can take tools.
- The UHF reader **continuously sees every tagged tool** (presence: "is this tool here or not"; exact position is not needed).
- When a tool leaves the reader's range **without an identified student**, an **alarm** sounds.
- This replaces the current UX ("tap card, tap tool, confirm"). `/scan` and `/register` will be rewritten; the H1-H6 hardening in `a96c9f2` applies to the old flow only.

## Decided (do not reopen)
- Identification is **1:N**: the student just looks at the camera. The kiosk shows "Halo, <name> (<NIM>)" with a "Bukan saya" button. No NIM typing per transaction.
- Registration happens **at the kiosk, by the student**. It needs a keyboard for name/NIM/email/phone (on-screen keyboard still an open question, see B2 in the old handoff).
- Camera: **USB webcam** (`/dev/video0`, OpenCV `VideoCapture`). Keep it behind a Mock/Real factory like the reader.
- The VX6336 reads tags fine on the laptop (`scripts/rfid_probe.py`, findings in `RFID_VX6336.md`). The driver in `utils/rfid_reader.py` works end to end (`/api/rfid/status` connected, `/api/check_rfid` returns EPCs).

## Blocker to raise first: reader range
The HW-VX6336 is a **desk reader: built-in antenna, 13 dBm max, 0-20 cm**. It can watch a small tray of tools lying on it, not a cabinet or a wall. Presence monitoring of a real tool area needs a **fixed UHF reader with external antennas** (typically 4 ports, 26-30 dBm, circular-polarized antennas, several metres). Antennas also give rough zones (which antenna saw the tag); there is no true position. Ask the user:
1. How big is the tool area (one shelf, a cabinet, a room)? How many tools?
2. Is buying a fixed reader + antennas possible? Until then, build and test everything against the VX6336 with tools on a tray within 20 cm.
3. Design the presence code against an interface (`inventory round -> set of EPCs`), so swapping the reader means a new driver module only. Many cheap fixed readers speak a close relative of this protocol family; check before writing a new one.

Other physics to plan for: UHF misses reads (orientation, bodies, other tags), and tags on **metal tools need on-metal tags**. So "missing" must mean "not seen for N seconds", never "missing from one round". The VX6336 inventory reply carries no RSSI.

## Target flows
**Idle (kiosk home):** live tool board (present / borrowed / missing) and a "Lihat ke kamera untuk mulai" prompt. The camera runs face detection at low rate. Unknown face → "Wajah belum terdaftar" + button to register.

**Take tools:** face identified → confirm screen (name, NIM, photo, "Bukan saya") → **session opens** (e.g. 60 s, extended while tools are moving) → student takes tools; each tool that goes missing during the session is recorded as borrowed by that student and appears live on screen → session ends by button, timeout, or face leaving. Summary screen.

**Return tools:** put the tool back in range. When the reader sees it again it is auto-returned (closes the open transaction). No face needed. *Open question:* require a face on return to log who returned it?

**Alarm:** a tool goes missing with no open session → alarm: full-screen red overlay listing the tool(s), sound in the kiosk browser, record an `AlarmEvent`. Stops when the tool comes back or an admin acknowledges with the PIN. *Open question:* is browser audio enough, or a physical buzzer/siren (reader buzzer `0x33` is weak and its data layout is unverified, gated; a USB/GPIO siren on the Jetson is another option)?

**Register:** consent screen (biometric data, see Risks) → form (name, NIM, email, phone) → face capture: 3-5 frames, slight head turns, quality checks (one face, large enough, sharp) → store embeddings + one frame as the profile photo → test recognition once → done. Reject a face that already matches another student. Remove the old photo file picker and the RFID tap.

## Architecture
New logic goes in `utils/` and a blueprint under `routes/` (AGENTS.md rule), not `app.py`.
- `utils/presence.py`: `PresenceMonitor` fed by inventory rounds; per-EPC `last_seen`; state PRESENT / MISSING with `RFID_MISSING_AFTER` seconds (start ~5 s, tune on hardware); emits events `tool_left(epc)` / `tool_back(epc)`. Unknown EPCs are listed for admin registration. Pure logic with an injectable clock, fully unit-tested. `VX6336Reader` today reports only *new arrivals* through `ScanDebouncer`; the monitor needs the **full set per round**, so add a callback/queue of raw rounds alongside the debouncer.
- `utils/face.py` (replaces the benchmark parts of `utils/cv_handler.py`): `FaceEngine` with `detect`, `embed`, `identify(embedding) -> (student_id, distance) | None`, cached in memory (all students' embeddings as one array, reloaded on registration). Threshold starting at 0.5 for dlib; tune with real faces. `CameraMock` / `UsbCamera` behind a factory, `CAMERA_ENABLED`, `CAMERA_INDEX` in `.env`.
- `utils/session.py`: the kiosk state machine (idle → identified → session open → summary; alarm overlays any state). One session at a time. Decides "borrow vs alarm" when `tool_left` arrives. All DB writes go through `DatabaseHandler`.
- Frontend gets state by polling a single `GET /api/kiosk/state` (~1 s, same pattern as today) or by SSE. Polling is simpler and matches the current code; a camera MJPEG stream (`generate_recognition_frames` already exists) can show the preview.
- Engine choice (verify, do not assume): dlib/`face_recognition` must be compiled on the Jetson (slow, memory-hungry; CUDA build possible). Alternative that avoids dlib: OpenCV's **YuNet** (`cv2.FaceDetectorYN`) + **SFace** (`cv2.FaceRecognizerSF`), ONNX models, opencv >= 4.5.4. Benchmark both on the laptop first, then on the Jetson; pick by speed and accuracy. Store which engine/model produced each embedding, since embeddings are not comparable across engines.

## Data model changes (SQLite, `create_all` today)
- `Student.rfid_uid`: make nullable now (drop later). `photo_data` stays as the profile photo for now.
- New `FaceEmbedding(id, student_id FK, engine, vector BLOB float32, created_at)`, several per student.
- `Tool`: add `presence` (present/missing), `last_seen_at`. `rfid_uid` stays the EPC (24 hex chars, uppercase).
- `Transaction`: borrow created by the session (student from face). Add `returned_by` nullable if returns get a face.
- New `AlarmEvent(id, tool_id, started_at, ended_at, ended_by: 'returned'|'admin', note)`.
- The dev DB is dummy data, so recreating `instance/tpt_rfid.db` is fine. Real data on the Jetson needs a migration plan (Alembic with `render_as_batch=True`, see the old handoff). Deleting the DB file is gated: ask first.

## Phases (each its own commit(s); scripts/check.sh green at each)
0. **Answers + hardware test** (no app code): user answers the open questions. Extend `scripts/rfid_probe.py` with a `--stats` mode: per-EPC read rate and longest gap over N minutes with tools lying still. This measures the miss rate that sets `RFID_MISSING_AFTER`.
1. **Presence backend**: `utils/presence.py`, raw-round callback in `VX6336Reader`, mock reader that can simulate a set of present tags (`/debug/presence?epcs=...`), `Tool.presence`, `AlarmEvent`. Tests with fake clock and FakeSerial.
2. **Face backend**: engine benchmark (dlib vs YuNet/SFace) on the laptop webcam; `utils/face.py`, `FaceEmbedding`, camera factory + mock; enroll and identify APIs. Tests with stored fixture embeddings (no camera in CI).
3. **Session logic**: `utils/session.py`, `/api/kiosk/state`, borrow on `tool_left` during a session, auto-return on `tool_back`, alarm otherwise, admin acknowledge (PIN). Tests for every transition.
4. **UI rewrite**: idle board, identify/confirm, session screen, alarm overlay, self-registration with face capture, admin views (alarm log, unknown EPCs → register tool, delete a student's face data). Fold in still-valid audit items: B1 (Tailwind/fonts from CDN must be bundled for an offline kiosk), M1 language, M3/M5 touch sizes, M6 sticky hover, M7 admin link on the public page, L1 pinch zoom, L3 innerHTML. Remove the old card/tap flow.
5. **Jetson**: camera + engine on the device (step 6 of the old handoff first), performance with `tegrastats`, `install.sh` for CV deps.

## Risks and open questions
- **Spoofing**: a photo of a student's face fools plain face recognition. v1 has no liveness check; say so to the user. Options later: blink/head-turn challenge, IR/depth camera.
- **Biometric data and privacy**: under Indonesia's UU PDP (UU 27/2022), biometric data is specific personal data. Get explicit consent at registration, explain the purpose, let admin delete a student's face data, keep embeddings local (no cloud). Do not use real student faces in tests or commit them.
- **Two people at the kiosk**: identify only the largest/closest face; the confirm screen ("Bukan saya") covers mistakes.
- **A student walks off without a session**: that is exactly the alarm case. A student who forgot to scan their face must come back. Decide whether identifying after the alarm converts it to a borrow (recommend: yes, within a short window, logged).
- **Returns by someone else**: auto-return does not know who returned the tool. Fine for v1 unless the user wants accountability.
- Open questions for the user: tool area size and count; fixed reader purchase; alarm hardware; session length; face on return; what happens to the old RFID student cards and `seed_database.py` (switch seed to tools with EPC-like UIDs + students without cards); idle timeouts; screen size and on-screen keyboard (old handoff); whether the device is always online (email alerts).

## Useful facts from this session
- Reader on the laptop: CH340 `1a86:7523` on `/dev/ttyUSB0`. Ubuntu's `brltty` steals it (`apt remove brltty`; `install.sh` now does this). The user must be in `dialout`; run the app from a shell that has the group (`newgrp dialout` or re-login). The agent's shell can use `sg dialout -c "..."`.
- Read-only probe: `.venv/bin/python scripts/rfid_probe.py /dev/ttyUSB0 --raw` (stop the app first; one process per port). Allowed reader commands without asking: Inventory `0x01`/`0x0F`, Get Reader Info `0x21`, Set ScanTime `0x25`, buzzer/LED `0x33` (see GATES.md).
- Existing CV code: `utils/cv_handler.py` (`CVCamera`, 1:1 reference capture, HOG detection, thresholds 0.50/0.55/0.60, MJPEG generators, system stats) and `routes/cv_routes.py` (`/cv` benchmark pages, CSRF-exempt). `requirements-cv.txt` (opencv-python, face-recognition, psutil). Not installed in the laptop `.venv`; no `/dev/video*` was present on 2026-10-16 (webcam not plugged in or not checked).
- `.env` is the user's; the agent has never read it. The user once lost `.env.example` from the tree (restored in `bd89163`).
- Admin PIN: `scripts/set_admin_pin.py`; the old PIN 133133 is in git history and must not be reused.

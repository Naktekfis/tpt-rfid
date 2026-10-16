# Handoff: face identity + tool presence monitoring (new UX)

Written 2026-10-16, updated the same day after the phase 0 reader tests (commit `7be4956`). Branch `cvtest`, nothing pushed. Start by reading this file, then `AGENTS.md` (auto-loaded), `.claude/knowledge/RFID_VX6336.md`, and `.claude/knowledge/TARGET_PLATFORM.md`. The older handoff `2026-10-15-jetson-sqlite-rfid.md` still holds the Jetson bring-up plan (step 6, not run yet) and the parked UI audit list. Where they disagree, this file wins.

Phase 0 is mostly done (reader facts below). **Phase 1 is done** (a6cf58a, 9ffe11f; 93 tests). **Next:** phase 2 (face backend), and phase 0 (b)/(c)/(d) whenever the user has all tags and a USB webcam ready; (b)/(c) only tune `RFID_MISSING_AFTER` (default 5 s).

## The new concept (user, 2026-10-16, condensed)
- Students are identified by **face**, not by a card. KTM uses a different scanner and is out of scope; do not work on it.
- Students **register their face first** (self-service at the kiosk) before they can take tools.
- The UHF reader **continuously sees every tagged tool** (presence: "is this tool here or not"; position is not needed).
- When a tool leaves the reader's range **without an identified student**, an **alarm** sounds.
- Returning a tool also needs **face verification**.
- Registering a tool needs a **photo of the tool** (display only, not used for recognition).
- Loan period: **2 days**.
- Inventory: **5 tool types, 3-5 units each** (about 15-25 tags in the field at once).
- This replaces the current UX ("tap card, tap tool, confirm"). `/scan` and `/register` will be rewritten; the H1-H6 hardening in `a96c9f2` applies to the old flow only.

## Decided (do not reopen)
- Identification is **1:N**: the student just looks at the camera. The kiosk shows "Halo, <name> (<NIM>)" with a "Bukan saya" button. No NIM typing per transaction.
- Student registration happens **at the kiosk, by the student**. It needs a keyboard for name/NIM/email/phone (on-screen keyboard still open, see B2 in the old handoff).
- Camera: **USB webcam** (`/dev/video0`, OpenCV `VideoCapture`). Behind a Mock/Real factory like the reader.
- **Reader range: assume it is enough** (user, 2026-10-16). Do not block on buying a fixed reader. Background, in case it comes back: the HW-VX6336 is a desk reader (built-in antenna, 13 dBm max, 0-20 cm); a tool cabinet would normally need a fixed reader with external antennas. Keep the presence code behind an interface (`inventory round -> set of EPCs`) so a different reader means a new driver module only.
- **Alarm sound: the reader's own buzzer** via `0x33`, plus an on-screen alarm. Beep-on-read is switched off with `0x35` (see Phase 0 results), so continuous polling is silent.
- **Face photos are fine to store** (user: "foto wajah aman aja"). Still add a short consent line at registration and an admin "delete face data" action; that is cheap and matches UU PDP (UU 27/2022, biometric = specific personal data).
- **Liveness is wanted** (user asked to research it). See "Liveness" below.
- The UI needs a **full redesign**, not polish: the user finds it inconsistent and "too generic AI". Phase 4 starts with a design direction (tokens, type scale, components, tone) agreed with the user before building screens.
- The VX6336 reads tags on the laptop (`scripts/rfid_probe.py`, findings in `RFID_VX6336.md`). The driver in `utils/rfid_reader.py` works end to end (`/api/rfid/status` connected, `/api/check_rfid` returns EPCs).

## Two clocks, do not mix them
- **Kiosk session**: the short window after a face is identified (start ~60 s, extended while tools move, ended by button, timeout, or the face leaving). Tools that leave or come back during it are attributed to that student.
- **Loan period**: 2 days from borrow. After that the transaction is overdue (existing overdue/warning-email logic in `utils/database_handler.py` / `app.py` must be checked and switched to 2 days; it may count hours today).

## Target flows
**Idle (kiosk home):** live tool board grouped by type (present / borrowed by whom / missing) and a "Lihat ke kamera untuk mulai" prompt. The camera runs face detection at low rate. Unknown face → "Wajah belum terdaftar" + button to register.

**Take tools:** face identified + liveness passed → confirm screen (name, NIM, photo, "Bukan saya") → kiosk session opens → each tool that goes missing during the session becomes a borrow by that student (due in 2 days) and appears live on screen → session ends. Summary screen.

**Return tools:** face identified + liveness → kiosk session → put tools back in range; each tool that reappears during the session closes that student's open transaction. Edge cases to decide with the user (recommendation in brackets):
- A tool reappears **without a session** → it is physically back, so no alarm; mark the transaction "kembali, belum diverifikasi" and show it on the idle board until someone verifies by face [recommended].
- A student returns a tool **borrowed by someone else** → record who returned it; allow it [recommended], or reject.

**Alarm:** a tool goes missing with no open session → reader buzzer + full-screen red overlay listing the tool(s) + `AlarmEvent`. Stops when the tool comes back, or an admin acknowledges with the PIN. If the student identifies within a short grace window (e.g. 30 s) after the alarm, convert it to a borrow and log it [recommended].

**Register student:** consent line → form (name, NIM, email, phone) → face capture: 3-5 frames with slight head turns, quality checks (one face, large enough, sharp) + liveness → store embeddings + one frame as profile photo → test recognition once → done. Reject a face that already matches another student. Remove the old file picker and the RFID tap.

**Register tool (admin, PIN):** pick or create the tool type → put the tag on the reader (the new, unknown EPC is picked up automatically; the admin view lists unknown EPCs in the field) → take the tool photo with the webcam (or upload) → save. Photo is display only.

## Liveness (research 2026-10-16; verify before relying on it)
Recommendation: **passive model + one active challenge**, both on CPU.
1. **Passive: MiniFASNet from Silent-Face-Anti-Spoofing** (MiniVision, Apache-2.0). Two small models (MiniFASNetV2 + MiniFASNetV1SE, ~4 MB total, <10 ms on CPU per a downstream project) run on the face cropped at 2.7x and 4.0x scale; average the softmax "real" score. Downstream users report ~0.76 for real faces vs ~0.01 for a printed-photo spoof. Weak against 3D masks (irrelevant here). ONNX exports exist in downstream projects; check whether `cv2.dnn` runs them (else `onnxruntime`, check aarch64 + py3.8 wheels). Sources: https://www.mintlify.com/shubham0204/OnDevice-Face-Recognition-Android/advanced/face-spoof-detection and LocalAI's insightface backend (antispoofing commit).
2. **Active: blink or head turn.** Blink = eye aspect ratio (Soukupová & Čech 2016) on 68-point dlib landmarks: EAR drops near zero during a blink; typical threshold ~0.2-0.3 over >=2-3 consecutive frames (https://pyimagesearch.com/2017/04/24/eye-blink-detection-opencv-python-dlib/). Needs dense landmarks: dlib 68-point or MediaPipe Face Mesh. YuNet gives only 5 points, enough for a **head-turn** check (nose offset relative to the eyes) but not for EAR.
3. Heavier options (later only): YOLOv8n real/fake classifier reported ~20 FPS on a Jetson Nano but on a self-collected dataset (ijcsrr.org 2026 paper); CASO-PAD (arXiv 2602.18965, benchmarked on Orin Nano, code not checked). Hardware option: IR/depth camera.
Fail closed: if the liveness models are missing, identification refuses with a clear error, it does not silently pass.

## Phase 0 results (2026-10-16)
Details and raw frames are in `.claude/knowledge/RFID_VX6336.md`; this is the summary.
- **Buzzer, solved in software.** The firmware beeps on every `0x01` round that sees a tag (would beep nonstop under presence polling). Not fixable with documented commands (`0x33 0,0,0` does nothing). Fix: undocumented **`0x35` Set Beep Mode** from the UHFReader09-family SDK (https://github.com/klks/UHFReader): `00` read, `80` off, `81` on (factory). Our reader is now **off**; the mode **survives unplugging**; `0x33` **still beeps** on command (user heard both). `0x35` with these three values is allowed (user, 2026-10-16: GATES.md, `SAFE_COMMANDS`).
- **`0x0F` is not an option for presence**: it does not beep, but it keeps reporting one tag (two equally close tags: `0x01` 82.5% / 75%, `0x0F` only one of them in 30 s). Presence polls with `0x01`.
- **Read rates, `0x01`**: one still tag 82%, longest gap 0.07 s; 2-3 tags 55-83%, gaps 0.13-0.37 s; a tag at the edge of the field drops to a few % with gaps of 2-10 s. ~30-40 rounds/s, 23 ms empty / ~30 ms with tags. `RFID_MISSING_AFTER` 2-3 s looks safe for well-placed tags; confirm with the full set.
- **Probe** (`scripts/rfid_probe.py`): `--stats --duration S --quiet` (per-EPC rate, longest gap, tags/frames per round), `--single` (`0x0F`), `--beep A,S,N`, `--beep-mode read|off|on`.
- **Webcam**: no USB webcam yet. `/dev/video0` = laptop RGB camera, `/dev/video2` = laptop **IR** camera (liveness experiments only, not the target).
- **Still open**: (b) all ~15-25 tags at once: does one round report all of them, and does the multi-frame `0x03` path work; (c) 5-minute `--stats` with everything lying still; (d) USB webcam.
- **Phase 1 consequence**: the reader driver sends `35 80` on every connect (a replacement reader ships with beep on), and `0x33` for the alarm pattern.

## Architecture
New logic goes in `utils/` and a blueprint under `routes/` (AGENTS.md rule), not `app.py`.
- `utils/presence.py`: `PresenceMonitor` fed by inventory rounds; per-EPC `last_seen`; state PRESENT / MISSING after `RFID_MISSING_AFTER` seconds (start ~5 s, tune with phase 0 data); events `tool_left(epc)` / `tool_back(epc)`; unknown EPCs listed for tool registration. Pure logic with an injectable clock, fully unit-tested. `VX6336Reader` today reports only *new arrivals* through `ScanDebouncer`; the monitor needs the **full set per round**, so add a raw-round callback alongside the debouncer. With ~20 tags the reader will use multi-frame replies (status `0x03`); that path is coded but untested on hardware.
- `utils/face.py` (replaces the benchmark parts of `utils/cv_handler.py`): `FaceEngine` with `detect`, `embed`, `identify(embedding) -> (student_id, distance) | None` over an in-memory array of all embeddings (reloaded on registration), plus `utils/liveness.py`. Camera behind a factory: `CAMERA_ENABLED`, `CAMERA_INDEX` in `.env`; a mock camera for dev/tests.
- Engine choice (benchmark, do not assume): dlib/`face_recognition` (68 landmarks give blink detection for free; must be compiled on the Jetson, slow and memory-hungry) vs OpenCV **YuNet + SFace** (`cv2.FaceDetectorYN` / `cv2.FaceRecognizerSF`, ONNX, opencv >= 4.5.4, no dlib build; head-turn instead of blink). Store the engine name with each embedding; embeddings are not comparable across engines.
- `utils/session.py`: kiosk state machine (idle → identified → session → summary; alarm overlays any state). One session at a time. Decides borrow / return / alarm on presence events. DB writes through `DatabaseHandler`.
- Frontend polls one `GET /api/kiosk/state` (~1 s, same pattern as today). Camera preview via the existing MJPEG generator pattern.

## Data model changes (SQLite, `create_all` today)
- `Student.rfid_uid`: make nullable now (drop later). `photo_data` = profile photo from the face capture.
- New `FaceEmbedding(id, student_id FK, engine, vector BLOB float32, created_at)`, several per student.
- New `ToolType(id, name, photo)` for the 5 types; `Tool` becomes one physical unit: `type_id`, `unit_no`, `rfid_uid` (EPC, 24 hex uppercase), `photo` (optional, falls back to the type photo), `presence`, `last_seen_at`.
- `Transaction`: `due_at` (= borrow + 2 days), `returned_by` (student), `return_verified` (bool) for the unverified-return case.
- New `AlarmEvent(id, tool_id, started_at, ended_at, ended_by: 'returned'|'admin'|'late_identify', student_id nullable)`.
- The dev DB is dummy data; recreating `instance/tpt_rfid.db` is fine but deleting it is gated, so ask first. Real data on the Jetson needs a migration plan (Alembic with `render_as_batch=True`, see the old handoff). Rewrite `seed_database.py`: 5 types × 3-5 units with EPC-like UIDs, students without cards.

## Phases (each its own commit(s); scripts/check.sh green at each)
0. **Hardware facts, no app code.** (a) Buzzer: **done**, see Phase 0 results. (c) probe `--stats`: **done** (tool built, full-set run still open). Open: (b) Put all ~15-25 tags in the field: does one inventory round report all of them (multi-frame `0x03`)? (c) Extend `scripts/rfid_probe.py` with `--stats`: per-EPC read rate and longest gap over N minutes with tools lying still; this sets `RFID_MISSING_AFTER`. (d) Plug in the webcam, check `/dev/video0`.
1. **[DONE a6cf58a, 9ffe11f]** `utils/presence.py` (`PresenceMonitor`), `utils/tool_presence.py` (`ToolPresenceService`: presence to DB, alarm only for an `available` tool leaving, closed on return or admin ack), `routes/presence_routes.py` (`GET /api/presence`, `POST /api/alarms/<id>/ack`), `/debug/presence`, new models, seed with 5 types / 20 units, dev DB recreated. Known gap: a tool not seen since boot keeps its last stored `presence`. Original: **Presence backend**: `utils/presence.py`, raw-round callback, `35 80` on connect, mock reader that simulates a set of present tags (`/debug/presence?epcs=...`), `ToolType`/`Tool` changes, `AlarmEvent`, buzzer-on-alarm (behind the reader factory). Tests with a fake clock and FakeSerial.
2. **Face backend**: engine benchmark on the laptop webcam (dlib vs YuNet/SFace) and liveness (MiniFASNet + blink or head turn); `utils/face.py`, `utils/liveness.py`, `FaceEmbedding`, camera factory + mock; enroll and identify APIs. Tests with fixture embeddings (no camera in CI; never commit real faces).
3. **Session logic**: `utils/session.py`, `/api/kiosk/state`, borrow and verified return during a session, unverified return, alarm + grace window, 2-day due date and overdue, admin acknowledge (PIN). A test for every transition.
4. **UI redesign**: agree a design direction with the user first (not generic: real typography, a deliberate palette, touch-first sizes, Indonesian copy throughout), then: idle board, identify/confirm, session screen, alarm overlay, student self-registration with face capture, tool registration with photo, admin views (alarm log, unknown EPCs, delete face data). Bundle Tailwind/fonts locally (B1, offline kiosk). Fold in the still-valid audit items from the old handoff (M1, M3, M5, M6, M7, L1, L3). Remove the old card/tap flow.
5. **Jetson**: bring-up (step 6 of the old handoff), camera + engine + liveness on the device, `tegrastats`, `install.sh` for CV deps.

## Open questions for the user
- Unverified return and returning someone else's tool: OK with the recommendations above?
- Alarm grace window for a student who forgot to scan first: OK?
- Kiosk session length (start 60 s)?
- Screen size and on-screen keyboard; is the device always online (email alerts)? (from the old handoff)

## Useful facts from this session
- Reader on the laptop: CH340 `1a86:7523` on `/dev/ttyUSB0`. Ubuntu's `brltty` steals it (`apt remove brltty`; `install.sh` now does this). The user must be in `dialout`; run the app from a shell that has the group (`newgrp dialout` or re-login). The agent's shell can use `sg dialout -c "..."`.
- Probe: `.venv/bin/python scripts/rfid_probe.py /dev/ttyUSB0 --raw` (stop the app first; one process per port; read-only except `--beep-mode off|on`). Allowed reader commands without asking: Inventory `0x01`/`0x0F`, Get Reader Info `0x21`, Set ScanTime `0x25`, buzzer/LED `0x33`, Set Beep Mode `0x35` with `00`/`80`/`81` only (GATES.md). No-tag rounds answer in ~23 ms with status `0x01`, `Num=0`.
- Existing CV code: `utils/cv_handler.py` (`CVCamera`, 1:1 reference capture, HOG detection, thresholds 0.50/0.55/0.60, MJPEG generators, system stats) and `routes/cv_routes.py` (`/cv` benchmark pages, CSRF-exempt). `requirements-cv.txt` (opencv-python, face-recognition, psutil), not installed in the laptop `.venv`.
- `.env` is the user's; the agent has never read it. `.env.example` once went missing from the tree (restored in `bd89163`).
- Admin PIN: default `133133` (user decision 2026-10-16, `config.DEFAULT_ADMIN_PIN`); `scripts/set_admin_pin.py` overrides it via `ADMIN_PIN_HASH`.

## Decisions 2026-10-16 (later the same day)
- **Liveness research stopped (user).** Gate = head-turn in both directions, random order (yaw 0.25). Bench numbers: genuine reached -0.26/+0.33; a phone photo reached -0.28 one way but only +0.06 the other, so one direction alone is not enough. MiniFASNet (yakhyo weights) scored phone photos 1.00 like real faces (verified identical in onnxruntime, OpenCV 4.14 and 5.0, preprocessing matches Silent-Face): logged only, not a gate. Blink (EAR, dlib 68 points) counted 7 real blinks but also 9 fake ones on a tilted phone photo; code kept in `utils/liveness.py`, unused. Bench: `scripts/face_bench.py --challenge|--blink --show [--spoof]`.
- **Engine: YuNet + SFace.** Genuine distance median 0.15 / max 0.19 vs threshold 0.637; detect 17 ms. dlib HOG missed 22/30 frames with head movement and is 11x slower. Impostor distances not measured yet (needs a second person). The blur threshold (60) rejected 11/30 laptop-camera frames; tune with the `sharpness` numbers from the bench.
- Phase 3 answers: unverified return = recommended; returning someone else's tool allowed and recorded; 30 s alarm grace converts to a borrow; session 60 s, +30 s per tool event.
- Phase 4 answers: **plain monitor + mouse** (not touch), **physical USB keyboard** (no on-screen keyboard), style **clean institutional** (white, ITB blue, calm/formal). Lock face enroll: only for a student without face data, otherwise admin PIN (user approved the auth change).

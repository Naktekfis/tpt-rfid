# Handoff: face identity + tool presence monitoring (new UX)

Written 2026-10-16. Branch `cvtest`, nothing pushed. Start by reading this file, then `AGENTS.md` (auto-loaded), `.claude/knowledge/RFID_VX6336.md`, and `.claude/knowledge/TARGET_PLATFORM.md`. The older handoff `2026-10-15-jetson-sqlite-rfid.md` still holds the Jetson bring-up plan (step 6, not run yet) and the parked UI audit list. Where they disagree, this file wins.

This is a **plan, not built**. Nothing below is implemented yet. Start with phase 0.

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
- **Alarm sound: the reader's own buzzer** (user: the reader beeps when it detects). Plus an on-screen alarm. See "Buzzer" below; it changes how polling works.
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

## Phase 0 progress (2026-10-16)
- Done: `0x33` layout read (one-shot `ActiveT, SilentT, Times`, 50 ms units, no stored mode; the manual has no beep-on-read switch). `vx6336.buzzer_command()` and test added. Probe has `--beep A,S,N`, `--duration`, `--stats`, `--quiet`. The reader answered a `--beep 2,2,2` with status `0x00`.
- Webcam: no USB webcam yet. `/dev/video0` = laptop built-in RGB camera, `/dev/video2` = laptop **IR** camera (useful for liveness experiments only, not the target).
- **Reader beeps on every read with a tag** (user confirmed, continuous polling, one tag). Continuous presence polling with this reader = constant beeping. `0x33 0,0,0` tried: still beeps. Decision pending with the user (options: undocumented beep-off command, gated; disconnect the buzzer physically and alarm via Jetson speaker; different reader).
- **`0x0F` (Inventory Single) does not beep** (user confirmed). If repeated `0x0F` rounds see every tag in a multi-tag field often enough, presence can poll with `0x0F` silently and keep `0x33` for the alarm. 2-tag test: `0x0F` saw only the strong tag in 30 s; `0x01` saw both (96.7% / 11%, so the second tag was weak anyway). Retest with two equally close tags: `0x01` 82.5% / 75%, `0x0F` only one tag in 30 s. `0x0F` is ruled out for presence; presence uses `0x01`.
- **Solved in software: undocumented `0x35` Set Beep Mode** (found via github.com/klks/UHFReader). `35 00` reads (factory `01` = on), `35 80` = beep off, `35 81` = restore. After `35 80`, `0x01` polling is silent and `0x33` still beeps on command (user confirmed both). The original plan stands: silent polling, reader buzzer for alarms. The mode survives unplugging (checked). `0x35` (values `00`/`80`/`81` only) is now allowed (user, 2026-10-16) and in `SAFE_COMMANDS`; probe `--beep-mode`. Phase 1: the reader driver sends `35 80` on connect, so a replacement reader with the factory setting stays quiet. `0x0F`, one still tag: 99.7%, gap 0.05 s.
- One still tag (`0x01`): read rate 82%, longest gap 0.07 s (an earlier run with the tag being moved: 36%, 2.02 s). `RFID_MISSING_AFTER` of 2-3 s looks safe; confirm with all tags.
- Still open: did the `--beep 2,2,2` test sound? (b) multi-tag round, (c) still-tag `--stats` run.

## Buzzer: check this first in phase 0
The user says the reader beeps when it detects a tag. With continuous inventory polling and ~20 tags always in range, a beep-on-read reader would **beep constantly**. Phase 0 must find out:
- Does it beep on every inventory round with tags, or only in some mode? (Our probe ran several seconds with tags present; ask the user whether it beeped the whole time.)
- Command `0x33` (acousto-optic control, in GATES.md's allowed list) layout: read `docs/hardware/vx6336/communication-protocol-v1.2.pdf` before sending anything. Goal: no beep during normal polling, beep pattern on alarm. If `0x33` only sets a persistent mode, write down how to restore the factory setting before changing it, and tell the user.
- If the buzzer cannot be controlled, fallback: speaker on the Jetson (browser audio) for the alarm.

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
0. **Hardware facts, no app code.** (a) Buzzer behaviour and `0x33` layout (above). (b) Put all ~15-25 tags in the field: does one inventory round report all of them (multi-frame `0x03`)? (c) Extend `scripts/rfid_probe.py` with `--stats`: per-EPC read rate and longest gap over N minutes with tools lying still; this sets `RFID_MISSING_AFTER`. (d) Plug in the webcam, check `/dev/video0`.
1. **Presence backend**: `utils/presence.py`, raw-round callback, mock reader that simulates a set of present tags (`/debug/presence?epcs=...`), `ToolType`/`Tool` changes, `AlarmEvent`, buzzer-on-alarm (behind the reader factory). Tests with a fake clock and FakeSerial.
2. **Face backend**: engine benchmark on the laptop webcam (dlib vs YuNet/SFace) and liveness (MiniFASNet + blink or head turn); `utils/face.py`, `utils/liveness.py`, `FaceEmbedding`, camera factory + mock; enroll and identify APIs. Tests with fixture embeddings (no camera in CI; never commit real faces).
3. **Session logic**: `utils/session.py`, `/api/kiosk/state`, borrow and verified return during a session, unverified return, alarm + grace window, 2-day due date and overdue, admin acknowledge (PIN). A test for every transition.
4. **UI redesign**: agree a design direction with the user first (not generic: real typography, a deliberate palette, touch-first sizes, Indonesian copy throughout), then: idle board, identify/confirm, session screen, alarm overlay, student self-registration with face capture, tool registration with photo, admin views (alarm log, unknown EPCs, delete face data). Bundle Tailwind/fonts locally (B1, offline kiosk). Fold in the still-valid audit items from the old handoff (M1, M3, M5, M6, M7, L1, L3). Remove the old card/tap flow.
5. **Jetson**: bring-up (step 6 of the old handoff), camera + engine + liveness on the device, `tegrastats`, `install.sh` for CV deps.

## Open questions for the user
- Did the reader beep the whole time during the probe test with tags lying on it?
- Unverified return and returning someone else's tool: OK with the recommendations above?
- Alarm grace window for a student who forgot to scan first: OK?
- Kiosk session length (start 60 s)?
- Screen size and on-screen keyboard; is the device always online (email alerts)? (from the old handoff)

## Useful facts from this session
- Reader on the laptop: CH340 `1a86:7523` on `/dev/ttyUSB0`. Ubuntu's `brltty` steals it (`apt remove brltty`; `install.sh` now does this). The user must be in `dialout`; run the app from a shell that has the group (`newgrp dialout` or re-login). The agent's shell can use `sg dialout -c "..."`.
- Read-only probe: `.venv/bin/python scripts/rfid_probe.py /dev/ttyUSB0 --raw` (stop the app first; one process per port). Allowed reader commands without asking: Inventory `0x01`/`0x0F`, Get Reader Info `0x21`, Set ScanTime `0x25`, buzzer/LED `0x33` (GATES.md). No-tag rounds answer in ~23 ms with status `0x01`, `Num=0`.
- Existing CV code: `utils/cv_handler.py` (`CVCamera`, 1:1 reference capture, HOG detection, thresholds 0.50/0.55/0.60, MJPEG generators, system stats) and `routes/cv_routes.py` (`/cv` benchmark pages, CSRF-exempt). `requirements-cv.txt` (opencv-python, face-recognition, psutil), not installed in the laptop `.venv`. No `/dev/video*` on 2026-10-16.
- `.env` is the user's; the agent has never read it. `.env.example` once went missing from the tree (restored in `bd89163`).
- Admin PIN: default `133133` (user decision 2026-10-16, `config.DEFAULT_ADMIN_PIN`); `scripts/set_admin_pin.py` overrides it via `ADMIN_PIN_HASH`.

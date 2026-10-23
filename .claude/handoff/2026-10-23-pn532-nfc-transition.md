# PN532 test and NFC transition — 2026-10-23

## Goal and user decisions

- User wants a major change from face identification to NFC cards. Confirmed
  that cards serve BOTH student registration and opening borrow/return sessions.
- Preserve face recognition/liveness code under `legacy/` for possible future
  use; remove it from the active application path. This is requested direction,
  NOT an implemented change.
- Keep camera independent of face algorithms: photograph tools during tool
  registration, capture evidence of unauthorized tool departures, and later
  detect covered/disconnected cameras as input to an alarm/controller.
- Controller hardware/protocol and camera-obstruction policy are undecided.
- User requested handoff before implementation. No application overhaul started.
- Communicate in Indonesian. Do not repeat already completed hardware setup.

## Git / workspace

- Branch `main`, HEAD `99cc143`.
- Existing changes: modified `AGENTS.md`, `CONTEXT.md`; untracked `.agents/`,
  `.codex/`, `.claude/handoff/2026-10-22-memory-handoff-test.md`, `Scanner.zip`.
  Preserve these. This handoff is newly added. No commit or push performed.
- No app source, dependencies, database, or service deployment changed for NFC.
- `AGENTS.md` / `CONTEXT.md` still describe the face-based app; update them when
  the new behavior is actually implemented, rather than treating it as done.

## Jetson connection — solved

- SSH works with the existing laptop SSH key: `ssh tpt@10.42.0.14`.
- Hostname `tpt-desktop`, Ubuntu 18.04.6, aarch64; device-tree compatible:
  `nvidia,p3449-0000-b00+p3448-0000-b00` (Nano B01).
- Direct Ethernet from Jetson through a USB Ethernet adapter on laptop.
- OLD adapter `enx9c69d36844fa`: intermittent disappearing/carrier loss.
  Existing profile `jetson-share` uses IPv4 shared; autoconnect was enabled.
- WORKING replacement adapter `enx002432b4d00b`: created profile
  `jetson-share-usb`, IPv4 shared, IPv6 ignore, autoconnect yes. Laptop gets
  `10.42.0.1/24`; DHCP assigned Jetson `10.42.0.14/24`.
- Multiple successful SSH checks and reader tests confirmed connectivity.
  On resume verify live status, since addresses/link availability can change.
- Earlier `172.17.0.1` was Docker, not the useful SSH address. Do not redo that
  troubleshooting or change SSH port (22).
- Claude's earlier successful SSH setup is recorded in local history:
  `/home/ahmad/.claude/projects/-home-ahmad-tpt-rfid/80c05538-bc78-4727-9656-1bc618f42d57.jsonl`
  around lines 2041–2148. History is evidence, not fresh authorization.

## Reader identity / wiring — corrected and tested

- User initially called it MFRC522. Photo, supplied code, and actual firmware
  response establish that the connected reader is PN532 (red NFC Module V3
  style board), using I2C. Supersedes earlier MFRC522/SPI suggestions.
- User-confirmed wiring: SDA physical pin 3, SCL physical pin 5, VCC 3V3,
  GND to GND. Exact ground pin and 3V3 pin were not specified (do not claim
  a measured/confirmed pin 1/17 or a particular ground pin).
- Read-only targeted probe `i2cdetect -y -r 1 0x24 0x24` found `24`.
- Firmware test succeeded: `FIRMWARE: chip=0x32 version=1.6`.
- User tapped their card; multiple reads returned the same 4-byte UID.
  Do not copy the actual UID into fixtures or durable docs; use synthetic UIDs.
- No card writes, authentication, sector reads, or student registration done.
- Reader works without SPI. Prior observation: SPI device-tree nodes exist,
  but no driver binding or `/dev/spidev*`; irrelevant to this I2C reader.
- System has Jetson.GPIO 2.0.17; `tpt` belongs to gpio/i2c/dialout groups.
  No GPIO output/pinmux changes were made.

## Test artifacts installed on Jetson

- Separate Python 3.8 venv: `/home/tpt/pn532-test-venv`.
- Test script: `/home/tpt/pn532-test.py` (also staged locally as
  `/tmp/tpt-pn532-test.py`; /tmp is not durable).
- Uses `busio.I2C(board.SCL, board.SDA)` and `PN532_I2C(..., address=0x24)`,
  checks firmware, runs `SAM_configuration()`, polls UID with 0.5 s timeout.
  Exits after 5 minutes; deinitializes I2C. Suppresses repeats until card is
  absent (brief missed reads can still produce repeated detections).
- Test reader was explicitly stopped with SIGINT when preparing this handoff;
  subsequent process check found no matching reader process.
- Key installed versions: Adafruit-Blinka 9.1.0,
  adafruit-circuitpython-pn532 2.4.9, busdevice 5.2.17,
  platformdetect 3.89.1, Jetson.GPIO 2.0.17, typing-extensions 4.13.2.
- Old venv pip/setuptools lacked wheel and produced build warnings before
  falling back to successful setup.py installs. `pip freeze` includes
  `UNKNOWN==0.0.0` (sysv_ipc metadata issue) and `pkg-resources==0.0.0`.
  Do not blindly copy freeze into production requirements. Resolve packaging
  cleanly and verify Python 3.8 compatibility when integrating.
- App venv `/home/tpt/tpt-rfid/.venv` was only inspected, not modified.
- Local `/home/ahmad/tpt-rfid/Scanner.zip` contains ONLY `Scanner.py` (1209
  bytes); no venv. Source uses Adafruit PN532 I2C at 0x24. Archive was read
  directly, not extracted/executed. Its prompt suggesting smartphone reading
  is not proof that arbitrary phones will expose a usable stable UID.

## Current-code integration findings

- `utils/models.py`: Student already has nullable unique `rfid_uid` and face
  relationships. Confirm current DB contents/schema before planning migration;
  do not access student data or drop existing face data just to archive code.
- `utils/kiosk.py`: session/presence logic currently mixed with face/liveness
  and frame processing. Replace identity source while preserving authorized
  borrowing/return attribution, session timing, and late identification logic.
- `app.py`: creates face service/camera/kiosk and starts frame loop; self
  registration `/api/register` is followed by face enrollment.
- `routes/face_routes.py`: `/camera/stream` is inside the face blueprint.
  Move generic camera route out BEFORE retiring that blueprint.
- `routes/admin_routes.py` already supports tool-type photo capture through
  `/api/admin/tool_types/<type_id>/photo/capture` using `camera.jpeg()`.
  `static/js/input_tool.js` already exposes capture/upload and camera preview.
- `utils/camera.py` already has MockCamera/OpenCVCamera factories; retain and
  reuse it rather than moving camera into legacy.
- Face-specific UI: `templates/register.html`, `static/js/register.js`, kiosk
  page/JS and admin student face state will need inspection and revision.

## Next steps (not yet implemented)

1. Verify working tree and SSH, then bound the NFC implementation against the
   current code. Confirm any remaining UX decisions (card replacement, unknown
   cards, repeated taps / session switching), without re-asking whether NFC
   serves both registration and sessions: user already confirmed yes.
2. Add mock/real PN532 reader abstraction and normalize UID representation;
   handle duplicate taps and disconnected hardware. Keep NFC identity separate
   from UHF tool EPC/presence. Registration must not overwrite another student's
   existing card binding.
3. Separate generic camera routes/service from face dependencies; switch
   registration and kiosk identity to cards, preserve tool session behavior.
4. Archive face/liveness/experimental face assets under `legacy/` coherently,
   preserving reusable code and existing DB data. Decide test/dependency/config
   changes as part of the bounded refactor.
5. Add meaningful synthetic tests; run repo checks per AGENTS.md. Only then
   prepare and validate device deployment within user-authorized scope.
6. Subsequent scope: camera alarm snapshots; obstruction/disconnection events;
   controller interface once hardware/protocol/behavior are established.

## Context limits / verification

- Gemini share: https://share.gemini.google/PciLkAGxYPEN redirects to
  https://gemini.google.com/share/c1bffaf6c2da . Only title "Panduan GPIO Jetson
  Nano Python C++" and sign-in shell were accessible. Full conversation was
  NOT read. Browser accessibility also failed. Do not invent decisions from it.
- Verified: archive content, live hardware identity/config, I2C address,
  PN532 firmware, repeated UID reads, SSH and installed test versions.
- No repository application tests run: no application code changed.
- User authorized isolated library installation and card reading. This does
  not imply permission to write cards, destroy DB data, or deploy the overhaul.

Next commands:
```bash
git status --short
ssh -o BatchMode=yes -o ConnectTimeout=5 tpt@10.42.0.14 'hostname; ip -4 -br address show eth0'
```

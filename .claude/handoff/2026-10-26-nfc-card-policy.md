# NFC card policy (KTM only, one exempt card) — 2026-10-26

## Goal and user decisions
- Only KTM chips may register or open a kiosk session. Other cards: "Kartunya bukan KTM, silakan daftar menggunakan KTM".
- One personal card (an e-money card, "kartu 4") is treated as a normal KTM but only for NIM 13323018 (the user's own). Any other NIM: "Kartu rusak". No admin access (user chose "mahasiswa biasa").
- Card UID and the NIM are stored only as HMAC-SHA256 digests keyed by a secret pepper in `.env` (an 8-digit NIM falls to a plain hash). NIM only, not name.

## Measured on the Jetson PN532 (read-only, service stopped, 2026-10-26)
| Card | UID | ATQA | SAK | ATS |
|---|---|---|---|---|
| KTM (3 cards, identical) | 4 B | 0004 | 0x28 | 0D78007003990200D103042201 |
| e-money | 4 B | 0004 | 0x28 | 0C788071024D49464152452B |
| Flazz BCA | 4 B | 0004 | 0x28 | 137880720280318066B1840C016E0183009000 |
| Istanbulkart (DESFire) | 7 B | 0344 | 0x20 | 067577810280 |
ATQA+SAK do not separate them; the full ATS does. Only 3 KTMs (same batch) were sampled, so an older KTM with another chip would be refused (`KTM_PROFILES` in `utils/nfc_policy.py`, or `NFC_CARD_POLICY=false` to switch the filter off).

## Changed (working tree, NOT committed, NOT deployed)
- `utils/nfc_policy.py` (new): `CardPolicy` (`check_tap`, `check_student`, `is_special`, `digest`).
- `utils/nfc_reader.py`: reads via InListPassiveTarget with a 48-byte buffer (`parse_target`), events carry `card` {atqa, sak, ats}. **Bug fixed:** the library's default 19-byte buffer truncated ISO-DEP answers (UID + ATS, 22-23 B), so every KTM failed the frame checksum and the old `read_passive_target` path probably could not read KTMs at all.
- `utils/nfc_service.py`: refuses bad taps at capture (`rejection()`) and at the kiosk (`Kiosk.reject_card()` → unknown-card screen).
- `app.py` registration, `database_handler.bind_student_nfc(policy=)`, `routes/nfc_routes.py` (`rejected` field), `static/js/register.js` shows the message, `config.py` (`NFC_CARD_POLICY`, `NFC_POLICY_PEPPER`, `NFC_SPECIAL_UID_HMAC`, `NFC_SPECIAL_NIM_HMAC`).
- `scripts/set_special_card.py` (new): taps the card, asks the NIM with getpass, writes the three `.env` values, prints nothing sensitive.
- Tests: `tests/test_nfc_policy.py` (new), `tests/test_nfc_reader.py` updated. Full suite: 417 passed, 2 skipped; `ruff check .` clean; py_compile clean.

## Remaining, in order (all on the live device: needs user approval per GATES)
1. Commit, `git tag -a vYYYY.MM.DD`, push, `scripts/deploy_jetson.sh <tag>` (Naktekfis identity, no Co-Authored-By per the commit-identity memory).
2. On the Jetson: stop the service (`ssh -t tpt@10.42.0.14 'sudo systemctl stop tpt-rfid'`), run `.venv/bin/python scripts/set_special_card.py`, tap the e-money card, type the NIM, start the service again. **Until this is done the e-money card is refused, including for the already registered NIM.**
3. In the kiosk: tap a KTM (opens a session), the e-money card (opens the session for 13323018 only), Flazz/Istanbulkart (unknown-card screen). In registration check the new messages.
4. Students already bound to a non-KTM card are locked out at the kiosk by the policy; check `student_nfc_cards` (no UIDs printed) if anyone reports it.

## Blockers / risks
- **PN532 I²C link is intermittent** (loose wire/power): "No I2C device at address 0x24" / "Failed to detect the PN532" most runs; it also hung `i2cdetect` once (uninterruptible wait in `tegra_i2c_xfer_msg`, cleared after a few minutes). Fix the wiring (solder SDA/SCL/VCC/GND, check the I²C mode switch) before trusting NFC at the kiosk.
- The kiosk service was left **stopped** by the probing; check `systemctl is-active tpt-rfid`.
- The UID is not authenticated: anyone who copies the exempt card's UID with an emulator is accepted as NIM 13323018.
- Probe script `/tmp/nfc_sak.py` on the Jetson (and the scratchpad copy) prints ATQA/SAK/ATS with the UID masked; the Jetson copy disappears on reboot.

## Parked
- HW-VX6330K SDK read (protocol is the UHFReader18 family; `0x35` there is Set WorkMode, so the VX6336 beep-mode code must never be sent to it; it needs RS232/RS485/TCP, 6-8 m range). See the conversation; nothing implemented.

## Update 2026-10-26 (later): v2026.10.26 and v2026.10.26.1 are deployed; revisions below are in the working tree, NOT committed or deployed
- Second KTM batch profile (ATS `0D7800A10257694C4C20230307`) and the refusal log line (chip type only) shipped in v2026.10.26.1.
- Admin page `/admin/cards` (`templates/admin_cards.html`, `static/js/admin_cards.js`, routes in `routes/nfc_routes.py`): table `nfc_card_exceptions` keeps HMAC digests only. kind `ktm` = real KTM the chip check rejects (any NIM may use it); kind `other` = non-KTM card tied to one NIM (else "Kartu rusak"). Needs `NFC_POLICY_PEPPER` (already on the Jetson). `CardPolicy.lookup` reads the table.
- Register page: no subtitle, step cues (check on finished steps, next step filled), live NIM-taken check (`/api/register/nim`).
- Kiosk: "Anda pinjam" merged into "dipinjam"; session shows a log (newest first, WIB time per row); rack photos/tiles/marks about 20% larger.
- Checks: ruff clean, 422 passed, 2 skipped. Not yet looked at on a real screen (1360x768 layout).

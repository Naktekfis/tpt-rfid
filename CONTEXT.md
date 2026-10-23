# tpt-rfid Domain Language

Shared domain memory for Claude Code and Codex. Verify against the current code;
session progress belongs in `.claude/handoff/`, and working rules in `AGENTS.md`.

**Student**:
A registered borrower with name, NIM, email, phone, optional photo, and optional legacy RFID UID. NFC cards support kiosk identification; existing face embeddings are retained as legacy data.
_Avoid_: user, member

**Tool**:
A physical workshop unit with its own RFID tag; its loan status is `available` or `borrowed`.
_Avoid_: item, asset

**Transaction**:
One borrow of one Tool by one Student, closed when the Tool is returned. Keeps copies of the student and tool names.
_Avoid_: loan record, history entry

**RFID UID**:
The tag identifier read by the USB UHF reader (EPC as uppercase hex). Students retain a legacy optional RFID UID; the kiosk uses a separate PN532 NFC card binding.
_Avoid_: card number, tag ID

**Admin**:
Lab staff signed in with the admin PIN; can see borrowers, add tools, export history, and send reminder emails.

- **Tool type (`ToolType`)**: a category of tools; distinct from an individual physical unit (`Tool`).
- **EPC**: the UHF tag identifier used to track a physical tool through the reader.
- **Presence**: whether the reader currently sees a tool; distinct from its loan transaction status.
- **Kiosk session**: a short window attributing tool movements to an identified student; distinct from the loan period and the admin login session.
- **Unverified return**: a tool has physically returned, but its return still needs NFC borrower verification or admin verification (`Transaction.return_verified`).
- **Returned by**: the student recorded as returning a tool (`returned_by_id`), who may differ from the borrower.
- **Alarm grace window**: time during which late identification can attribute an alarmed tool departure to a student.

Sources: `utils/models.py`, `utils/kiosk.py`, `config.py` and the shared NFC handoffs dated 2026-10-23.

- **NFC card (`StudentNFCCard`)**: one PN532-readable ISO14443A UID (4, 7 or 10 bytes, uppercase hex) bound to one student in `student_nfc_cards`; distinct from the legacy student RFID UID and tool EPC.

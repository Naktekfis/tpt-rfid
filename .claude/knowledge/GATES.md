# Gates

Stop and confirm with the user before any of these. A `test-review` pass is not approval.

## Always
- Reading, printing, copying, or committing secrets: `.env*`, keys, tokens, cookies, credential files.
- Using real personal or customer data (tests use synthetic data).
- Destructive data operations: dropping/truncating tables, deleting records in bulk, irreversible migrations.
- Deploying, or changing anything on a live/production machine.
- Force-pushing, rewriting history, or deleting branches.

## Project-specific
- Anything that reads or exports real student data (names, NIM, email, phone, photos, face encodings).
- Admin PIN or session/auth logic, CSRF exemptions, and rate-limit changes.
- Running migrations or schema changes against a database that holds real data.
- Running anything on the target device (Jetson Nano; installer, systemd, apt, deploy).
- Sending any RFID reader command other than Inventory `0x01`/`0x0F`, Get Reader Info `0x21`, Set ScanTime `0x25`, buzzer/LED `0x33`, or Set Beep Mode `0x35` with data `0x00`/`0x80`/`0x81` only (tag writes, kill, lock, and reader config can be permanent; see `RFID_VX6336.md`).

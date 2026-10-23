# NFC rollout and rollback

Use one Gunicorn worker. PN532 and UHF each have a single hardware owner.
Test in a separate staging directory first; do not run two PN532 processes.

1. Run `scripts/check.sh` on the laptop. In Jetson staging, run the same synthetic
   suite with its Python 3.8 interpreter and all hardware disabled by fixtures.
2. Run `scripts/nfc_probe.py` using the verified NFC dependencies. Confirm firmware
   chip 0x32, connection and repeated tap detection without printing actual UIDs.
3. Run `scripts/nfc_acceptance.py` on Jetson. It uses an in-memory SQLite database,
   synthetic student/tool data, real NFC and mock UHF. Follow its two tap prompts.
4. Before replacing live code, make a private, timestamped backup outside the app
   directory: Git tracked code (`git archive HEAD` if the device checkout is clean),
   SQLite using `deploy/jetson/backup_db.py` (online backup includes WAL), runtime
   configuration, and the app venv before dependency installation. Do not print
   config contents or export the backups from the device. Check SQLite backup
   `PRAGMA quick_check` and test archive extraction before continuing.
5. Install `requirements-nfc.txt` into the app venv. Set only
   `NFC_READER_ENABLED=true` in the existing environment file, preserving all
   other settings. Preserve `instance/`, uploads, models and all existing rows.
6. Copy reviewed code from staging. Retire old face modules/routes/UI into the
   shipped `legacy/face/` archive. The only database addition is
   `student_nfc_cards`; `create_all()` does not rewrite existing tables.
7. Restart the app through systemd. When privileged restart is unavailable,
   the service user can terminate the single Gunicorn worker with SIGTERM;
   its master replaces it after exit. Verify worker count and no overlapping
   reader ownership; do not use HUP to overlap workers sharing the hardware.
8. Check `/api/devices/status`, `/kiosk`, `/daftar`, camera/tool capture and UHF
   presence. Register real students only through their intended workflow.

## Rollback

Stop the new worker before changing code. Restore the backed-up tracked code and
runtime config, then restart the single worker. Leave the new NFC table in place:
old code ignores it, and keeping it avoids losing registrations made after rollout.
Do **not** overwrite the live database with the snapshot during routine rollback:
it could discard later loans/returns. The SQLite snapshot is disaster recovery
only; compare and reconcile post-backup transactions before restoring it.

If dependencies caused the failure, restore the backed-up app venv while the
service is stopped. Never start both old and new apps against the same readers.
Keep the deployment directory and exact commands/results in the handoff.

For the prepared device backup, routine code/config rollback commands are:

```bash
sudo systemctl stop tpt-rfid
cd /home/tpt/tpt-rfid
tar -xf /home/tpt/nfc-backups/20261023T025719/code.tar -C /home/tpt/tpt-rfid
install -m 600 /home/tpt/nfc-backups/20261023T025719/.env /home/tpt/tpt-rfid/.env
sudo systemctl start tpt-rfid
curl -fsS http://127.0.0.1:5000/api/devices/status
```

These commands restore application code/config, leaving the current SQLite file,
photos and added NFC bindings intact. The device currently requires interactive
sudo authentication for systemd changes; never send or store the sudo password
in this repository. No production replacement has occurred as of this backup.

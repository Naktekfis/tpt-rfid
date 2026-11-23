# Jetson Nano bring-up

Files for running tpt-rfid on the Jetson Nano 4GB (JetPack 4.6.x, Ubuntu 18.04). Background: `.claude/knowledge/TARGET_PLATFORM.md`. `setup.sh` in the repo root is the laptop dev setup; the old Raspberry Pi + Postgres installer was removed (see git history before this commit).

| File | Installed to | Does |
|---|---|---|
| `install.sh` | — | Runs everything below. `DRY_RUN=1` prints the commands and renders the files to `build/jetson-dry-run/` |
| `99-tpt-rfid-reader.rules` | `/etc/udev/rules.d/` | Readers → `/dev/rfid-reader-1` (also `/dev/rfid-reader`) and `/dev/rfid-reader-2` by USB port, group `dialout` |
| `tpt-rfid.service` | `/etc/systemd/system/` | gunicorn, 1 worker, 4 threads, binds `127.0.0.1:5000` |
| `tpt-rfid-backup.{service,timer}` | `/etc/systemd/system/` | Daily 03:00 SQLite backup via `backup_db.py`, keeps 14 |
| `kiosk.sh` + `tpt-rfid-kiosk.desktop` | `~/.config/autostart/` | Waits for the app, then opens Chromium (or Firefox) in kiosk mode |

## Steps
1. Run the device checks in `TARGET_PLATFORM.md` and record their output there.
2. `git clone` the repo onto the device, then `cd tpt-rfid && DRY_RUN=1 deploy/jetson/install.sh` and read what it would do.
3. `deploy/jetson/install.sh`, then log out and back in (or reboot).
4. `curl -s 127.0.0.1:5000/api/devices/status` should show the reader connected and the camera open. The kiosk browser opens `/kiosk`; register a student card via `/daftar` (set `NFC_READER_ENABLED=true` for PN532 I²C), register tools via Admin › Input Alat.

## Not verified yet (check on the device)
- `python3.8` / `python3.8-venv` are installable from the 18.04 apt repos, and every pin in `requirements.txt` installs on aarch64 + 3.8.
- Both readers use a CH340 (`1a86:7523`) with no serial number, so the udev rule names them by USB port path; moving a cable means updating `KERNELS==` in the rule. install.sh removes `brltty`, which otherwise steals the CH340.
- That the browser keeps the admin session over `http://127.0.0.1`. `FLASK_ENV=production` sets `SESSION_COOKIE_SECURE=True`. Recent Chromium and Firefox accept Secure cookies on localhost, but older builds may not. If admin login does not stick, this is why.
- That `chromium-browser` exists on the JetPack image, and that the autostart works under its desktop (GNOME/Unity).
- Backups go to `instance/backups` on the same microSD by default. That protects against a corrupted database, not a dead card. Set `TPT_RFID_BACKUP_DIR` in the backup service to a USB stick for that.

## NFC transition

See [NFC_ROLLOUT.md](NFC_ROLLOUT.md) for staging, backup, acceptance and rollback. The NFC binding table is additive; old RFID UIDs and biometric data are retained. Real NFC support is optional on laptops and enabled explicitly on the Jetson.

## Remote admin (Cloudflare Tunnel + Access)

ITB blocks Tailscale, ZeroTier and ngrok; Cloudflare Tunnel passes (ports 443 and 7844).

- URL: `https://admin.labfabrikasi-itb.my.id` (domain at Hostinger, DNS on Cloudflare).
- Jetson: `/usr/local/bin/cloudflared` 2026.10.7, systemd service `cloudflared` from `sudo cloudflared service install <token>` (token from Cloudflare: Networking > Tunnels > tpt-jetson). Gunicorn stays on `127.0.0.1:5000`.
- Route: tunnel `tpt-jetson`, published application `admin` -> `http://localhost:5000`.
- Access: Zero Trust application on `admin.labfabrikasi-itb.my.id`, Allow policy `admin-lab` on listed emails, One-time PIN login. Create or change Access before any new route, or the route is public.
- The app treats a loopback request with `X-Forwarded-For` (cloudflared adds it) as remote: face login stays kiosk-only, logout goes to `/admin/login` (`utils/helpers.is_kiosk_request`).
- Off: `sudo systemctl stop cloudflared` (disable to keep it off after reboot). The Jetson's internet currently comes through the dev laptop (`10.42.0.1`).

# 2026-11-24 Remote admin: tunnel, remote face login, PC reader, UI rework next

## Goal and user decisions
- Admin pages usable from a PC and a phone outside the kiosk. ITB blocks Tailscale, ZeroTier and ngrok; Cloudflare works.
- Remote face login: an alternative to the PIN. Enrolment allowed from both the kiosk and remote devices (user's choice).
- Remote face liveness uses minifas_se; the kiosk keeps mn3.
- Tags can be registered from a VX6336 plugged into the admin PC (Web Serial). Tested in the browser by the user on another PC (not yet reported back).
- NEXT (asked 2026-11-24): rework the remote admin UI. On PC it should feel like a complete website/client with ITB identity; on phone like a native app. Keep the design D theme (tokens.css, Source Sans 3, square corners, hairlines, ITB blue). Kiosk out of scope. Use ui-review for the spec, then build-bugfix.

## State
- Branch main, clean after v2026.11.24.5 (all pushed and deployed).
- Tags today: .4 (remote liveness minifas_se), .5 (Web Serial PC reader). Earlier today .1 (manifest crossorigin + README tunnel), .2 (remote face login), .3 (remote quality gate); v2026.11.23.4 (`is_kiosk_request`).
- Jetson: cloudflared 2026.10.7 runs as a systemd service (tunnel `tpt-jetson`, route `admin.labfabrikasi-itb.my.id` -> `http://localhost:5000`, Access policy `admin-lab` with email OTP). Setup is in `deploy/jetson/README.md`.
- Jetson .env: `RFID_READER_PORTS=/dev/rfid-reader-1` (reader 2 unplugged for PC testing; the two-reader line is kept as a comment, and a `.env.bak-*` copy exists). Restore it and restart `tpt-rfid` when reader 2 returns.
- Jetson sudo password: the one in `~/.config/tpt-rfid/jetson-sudo` is wrong (an update was blocked). The user gave the right one in chat.

## Verified
- scripts/check.sh: 444 passed, 2 skipped.
- node --test tests/js/vx6336_serial.test.js: 4 pass.
- tests/js/hmi_polling.test.js already failed before today: its `window` stub has no `addEventListener`.
- Remote face login was tested on the user's phone: passes after the minifas_se switch ("udh oke iguess"). No spoof test yet.

## Open
1. UI rework (above).
2. `/camera/stream` needs no admin session (anyone past Access can view it), and each viewer holds one of 4 gunicorn threads.
3. PIN rate limit: every remote request arrives from 127.0.0.1, so the kiosk and the remote share it.
4. The tool photo on input_tool uses the kiosk camera; remotely, use upload (or a device camera later).
5. A missing child reader in multi-reader mode is not handled (utils/rfid_reader.py:705).
6. The Jetson's internet comes through the dev laptop (10.42.0.1).

## Update 2026-11-24 later: UI rework (local commits, NOT deployed)
- Local commits on main ahead of origin: 3b9c8b6 (PC reader diagnostics), 66f3d70 (admin shell: site nav, phone tab bar, card tables, dashboard, split login), 6eb3458 (admin follows the kiosk look, back button), f901439 (white logos, `static/assets/*_white.png`), e99e35e and b15faac (labels: kicker "ADMIN", phone brand "Lab Fabrikasi · TF ITB", dashboard title "Admin").
- Deploying all of it needs the user's "deploy": push main, tag `v2026.11.24.6`, `scripts/deploy_jetson.sh`.
- The user's verdict: the kiosk and PC are OK. Phone still feels like "a web page squeezed in" (font not native, long scroll). Next: research native mobile patterns (explore-plan running), build phone variants B (native patterns with Source Sans 3) and C (system font), switchable with `?variant=` and scoped to the phone media query, then show an A/B/C comparison as an Artifact (not a local gallery).
- Screenshot gallery script: /tmp/claude-1000/-home-ahmad-tpt-rfid/01a1cabe-6637-4f12-a6d2-1c2ca55ee0be/scratchpad/shots.sh (demo on :8765, 16 pages x 4 sizes).
- PC reader (Web Serial): the user reports no port shows in the browser chooser. Waiting for the PC's OS and browser; the driver and permission checklist was given.
- Jetson .env is still single-reader (reader 2 unplugged).

## End of day 2026-11-24 (supersedes the "local commits, NOT deployed" notes above)
- Deployed v2026.11.24.8 (cc31c25) on the Jetson; tests 466 passed there. Tag v2026.11.24.6 exists on origin, points at 3b9c8b6, and was never deployed (an interrupted command); left as is.
- Live: kiosk-style admin shell, phone variant B as the default (`?variant=a` still shows the old phone layout; delete it once the user confirms), dashboard order (hero with a "perlu tindakan" CTA, menu, stats, Perangkat), /admin/register with card-exception options (/admin/cards redirects there), remote registration photo from the device camera (optional for a remote admin), /admin/nfc-test, admin phone Web NFC capture, and the kiosk chip lock (`nfc_card_profiles`, Reset sidik kartu).
- Vercel demo (https://tpt-rfid-demo.vercel.app) was rebuilt from cc31c25 by the ui-demo workflow.
- A/B review page (Artifact): https://claude.ai/artifact/SQiB2nHTq9LQMPQtGn85x5.
- NOT verified on hardware (the user said to treat it as done):
  - No kiosk NFC tap since the deploy, so `nfc_card_profiles` was still empty and the 4 bound cards were unchanged.
  - The chip lock compares ATQA/SAK/ATS exactly. If real KTMs get refused, loosen it to ATQA+SAK.
  - Phone registration of a new KTM, then completing it at the kiosk, was not seen in the DB.
- Jetson .env is still single-reader (reader 2 at the PC). Tool 24 kept alarming at the edge of reader 1 (04:12-04:15 WIB).
- PC Web Serial: the port does not show in the browser chooser; waiting for the PC's OS and browser.
- Later the same day: reader 2 is back on the Jetson (.env restored to two readers; both connected). The user reports the PC USB reader works. Variant A is retired in code: admin pages always set data-variant=b (local commit; deploy pending approval).

"""
Choose the one exempt NFC card and the one NIM it may be registered to.

Stop the app first (it owns the PN532), run this, tap the card when asked, type
the NIM, then start the app again. Only HMAC digests go into .env
(NFC_POLICY_PEPPER, NFC_SPECIAL_UID_HMAC, NFC_SPECIAL_NIM_HMAC); the UID and NIM
are never printed or stored. Re-running replaces the previous choice and keeps
the existing pepper.

  .venv/bin/python scripts/set_special_card.py [path/to/.env]
"""

from __future__ import annotations

import getpass
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.set_admin_pin import set_env_value  # noqa: E402
from utils.nfc_policy import CardPolicy  # noqa: E402
from utils.nfc_reader import (  # noqa: E402
    _CMD_IN_LIST_PASSIVE_TARGET,
    _TARGET_RESPONSE_LENGTH,
    PN532Reader,
    normalize_uid,
    parse_target,
)

TIMEOUT = 40.0


def read_uid() -> str:
    device, bus = PN532Reader._open_device()
    try:
        device.SAM_configuration()
        end = time.monotonic() + TIMEOUT
        while time.monotonic() < end:
            try:
                response = device.call_function(
                    _CMD_IN_LIST_PASSIVE_TARGET,
                    params=[0x01, 0x00],
                    response_length=_TARGET_RESPONSE_LENGTH,
                    timeout=0.5,
                )
            except RuntimeError:
                continue
            uid, _card = parse_target(response)
            if uid:
                return normalize_uid(uid)
    finally:
        bus.deinit()
    raise SystemExit("No card read in {:.0f} s.".format(TIMEOUT))


def existing_pepper(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("NFC_POLICY_PEPPER="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def main() -> int:
    env_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / ".env"
    )
    nim = getpass.getpass("NIM allowed for this card: ").strip()
    if not nim.isdigit():
        print("NIM must be digits only.", file=sys.stderr)
        return 1
    print("Tap the card on the reader...", flush=True)
    uid = read_uid()

    text = env_path.read_text() if env_path.exists() else ""
    pepper = existing_pepper(text) or secrets.token_hex(32)
    policy = CardPolicy(pepper=pepper)
    for key, value in (
        ("NFC_POLICY_PEPPER", pepper),
        ("NFC_SPECIAL_UID_HMAC", policy.digest("uid", uid)),
        ("NFC_SPECIAL_NIM_HMAC", policy.digest("nim", nim)),
    ):
        text = set_env_value(text, key, value)
    env_path.write_text(text)
    os.chmod(env_path, 0o600)
    print("Saved the digests to {}. Start the app again.".format(env_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

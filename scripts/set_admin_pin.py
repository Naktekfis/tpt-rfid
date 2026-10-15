"""
Set the admin PIN: asks for it twice, stores only its hash as
ADMIN_PIN_HASH in .env (created if missing). Restart the app afterwards.

  .venv/bin/python scripts/set_admin_pin.py [path/to/.env]
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

MIN_LENGTH = 6
KEY = "ADMIN_PIN_HASH"


def set_env_value(text: str, key: str, value: str) -> str:
    """Replace or append `key='value'` in .env text. Single quotes stop
    python-dotenv from expanding the `$` in werkzeug hashes."""
    line = f"{key}='{value}'"
    out, found = [], False
    for existing in text.splitlines():
        if existing.strip().startswith(f"{key}="):
            if not found:
                out.append(line)
                found = True
            continue
        out.append(existing)
    if not found:
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / ".env"
    pin = getpass.getpass("New admin PIN: ")
    if len(pin) < MIN_LENGTH:
        print(f"PIN must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat PIN: ") != pin:
        print("PINs do not match.", file=sys.stderr)
        return 1

    text = env_path.read_text() if env_path.exists() else ""
    env_path.write_text(set_env_value(text, KEY, generate_password_hash(pin)))
    os.chmod(env_path, 0o600)
    print(f"Saved {KEY} to {env_path}. Restart the app to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

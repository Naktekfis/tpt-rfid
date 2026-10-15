"""
Copy the SQLite database with SQLite's online backup API (safe while the app
runs, WAL included), check the copy, and keep the newest N copies.

Run by tpt-rfid-backup.timer. Env:
  TPT_RFID_BACKUP_DIR   where copies go (default <repo>/instance/backups;
                        point it at a USB stick to survive a dead microSD)
  TPT_RFID_BACKUP_KEEP  copies to keep (default 14)
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[2]
PREFIX = "tpt_rfid-"


def db_path_from_uri(uri: str) -> Optional[Path]:
    """File path of a sqlite:/// URI, or None for anything else."""
    if not uri.startswith("sqlite:///"):
        return None
    path = uri[len("sqlite:///") :]
    return Path(path) if path else None


def backup(
    src: Path, dest_dir: Path, keep: int, now: Optional[datetime] = None
) -> Path:
    if not src.is_file():
        raise FileNotFoundError(f"Database not found: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{PREFIX}{stamp}.db"

    source = sqlite3.connect(str(src))
    target = sqlite3.connect(str(dest))
    try:
        source.backup(target)
        result = target.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        target.close()
        source.close()
    if result != "ok":
        dest.unlink()
        raise RuntimeError(f"Backup failed quick_check: {result}")

    prune(dest_dir, keep)
    return dest


def prune(dest_dir: Path, keep: int) -> List[Path]:
    copies = sorted(dest_dir.glob(f"{PREFIX}*.db"))
    old = copies[:-keep] if keep > 0 else []
    for path in old:
        path.unlink()
    return old


def main() -> int:
    sys.path.insert(0, str(REPO))
    from config import Config  # reads .env

    src = db_path_from_uri(Config.SQLALCHEMY_DATABASE_URI)
    if src is None:
        print(
            "backup_db: DATABASE_URL is not a SQLite file, nothing to do",
            file=sys.stderr,
        )
        return 1
    dest_dir = Path(
        os.getenv("TPT_RFID_BACKUP_DIR", str(REPO / "instance" / "backups"))
    )
    keep = int(os.getenv("TPT_RFID_BACKUP_KEEP", "14"))
    dest = backup(src, dest_dir, keep)
    print(f"backup_db: wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

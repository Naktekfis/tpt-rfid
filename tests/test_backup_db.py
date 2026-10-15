import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "jetson"))
import backup_db  # noqa: E402


def make_db(path):
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    return con  # kept open: the row may still sit in the WAL


def test_backup_copies_wal_data_and_prunes(tmp_path):
    src = tmp_path / "tpt_rfid.db"
    con = make_db(src)
    dest_dir = tmp_path / "backups"
    for day in range(1, 5):
        out = backup_db.backup(src, dest_dir, keep=2, now=datetime(2026, 10, day))
    con.close()

    copies = sorted(p.name for p in dest_dir.iterdir())
    assert copies == ["tpt_rfid-20261003-000000.db", "tpt_rfid-20261004-000000.db"]
    assert sqlite3.connect(str(out)).execute("SELECT x FROM t").fetchone() == (42,)


def test_db_path_from_uri():
    assert backup_db.db_path_from_uri("sqlite:////var/x.db") == Path("/var/x.db")
    assert backup_db.db_path_from_uri("sqlite://") is None
    assert backup_db.db_path_from_uri("postgresql://u@h/db") is None

import threading

from flask import Flask
from sqlalchemy import text

from utils.database_handler import DatabaseHandler
from utils.models import Student, Tool, Transaction, db


def _make_app(path):
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(path)
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    return flask_app


def test_pragmas_active(tmp_path):
    flask_app = _make_app(tmp_path / "pragma.db")
    handler = DatabaseHandler(flask_app)
    with flask_app.app_context():
        conn = db.session.connection()
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL
        db.session.remove()
        db.engine.dispose()
    assert handler is not None


def test_concurrent_borrow_single_winner(tmp_path):
    rounds = 25
    flask_app = _make_app(tmp_path / "race.db")
    handler = DatabaseHandler(flask_app)
    with flask_app.app_context():
        s1 = Student(
            name="A", nim="11111111", email="a@x.com", phone="081", rfid_uid="S1"
        )
        s2 = Student(
            name="B", nim="22222222", email="b@x.com", phone="082", rfid_uid="S2"
        )
        tools = [
            Tool(name="T%d" % n, rfid_uid="T%d" % n, category="Hand Tools")
            for n in range(rounds)
        ]
        db.session.add_all([s1, s2] + tools)
        db.session.commit()
        student_ids = [s1.id, s2.id]
        tool_ids = [t.id for t in tools]
        db.session.remove()

    def worker(student_id, tool_id, barrier):
        with flask_app.app_context():
            barrier.wait()
            try:
                handler.borrow_tool_atomic(student_id, tool_id)
            except Exception:  # noqa: BLE001 - losing the race is expected
                pass
            finally:
                db.session.remove()

    for tool_id in tool_ids:
        barrier = threading.Barrier(2)
        threads = [
            threading.Thread(target=worker, args=(sid, tool_id, barrier))
            for sid in student_ids
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    with flask_app.app_context():
        counts = [
            Transaction.query.filter_by(tool_id=tid, status="borrowed").count()
            for tid in tool_ids
        ]
        db.session.remove()
        db.engine.dispose()
    assert all(c == 1 for c in counts), counts

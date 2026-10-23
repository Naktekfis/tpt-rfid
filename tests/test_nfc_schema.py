"""The additive NFC table must preserve legacy identities and biometric data."""

from flask import Flask

from utils.database_handler import DatabaseHandler
from utils.models import Student, StudentNFCCard, FaceEmbedding, db


def test_additive_nfc_table_preserves_old_rows(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(tmp_path / "legacy.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.metadata.create_all(
            db.engine,
            tables=[
                table
                for table in db.metadata.sorted_tables
                if table.name != "student_nfc_cards"
            ],
        )
        student = Student(
            name="Synthetic",
            nim="12345678",
            email="test@example.com",
            phone="080000000",
            rfid_uid="E20000112233445566778899",
            photo_data=b"synthetic photo",
        )
        db.session.add(student)
        db.session.flush()
        sid = student.id
        db.session.add(
            FaceEmbedding(student_id=sid, engine="synthetic", vector=b"old embedding")
        )
        db.session.commit()
        handler = DatabaseHandler()
        handler.create_tables(app)
        handler.bind_student_nfc(sid, "01020304")
        assert db.session.get(Student, sid).rfid_uid == "E20000112233445566778899"
        assert db.session.get(Student, sid).photo_data == b"synthetic photo"
        assert FaceEmbedding.query.one().vector == b"old embedding"
        assert StudentNFCCard.query.one().student_id == sid
        # The previous app can continue reading its old tables after rollback.
        assert handler.get_student_by_uid("E20000112233445566778899")[
            "student_id"
        ] == str(sid)
        db.session.remove()
        db.engine.dispose()

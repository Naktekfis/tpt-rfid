"""
SQLAlchemy models for the RFID Workshop Tool Monitoring System
"""

from datetime import datetime, timedelta
from flask import current_app
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# Import timezone helpers (will be available after helpers.py is loaded)
def _get_utc_to_wib():
    """Lazy import to avoid circular dependency"""
    try:
        from .helpers import utc_to_wib

        return utc_to_wib
    except ImportError:
        # Fallback if helpers not available yet
        return lambda x: x


class Student(db.Model):
    """Student model - represents registered students with RFID cards"""

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    nim = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    rfid_uid = db.Column(db.String(100), unique=True, nullable=True, index=True)
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_mimetype = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    transactions = db.relationship(
        "Transaction",
        backref="student",
        lazy="dynamic",
        foreign_keys="Transaction.student_id",
    )
    face_embeddings = db.relationship(
        "FaceEmbedding",
        backref="student",
        lazy="dynamic",
        foreign_keys="FaceEmbedding.student_id",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_photo=False):
        """Convert model to dictionary"""
        data = {
            "student_id": str(self.id),
            "name": self.name,
            "nim": self.nim,
            "email": self.email,
            "phone": self.phone,
            "rfid_uid": self.rfid_uid,
            "photo_url": f"/api/student/{self.id}/photo" if self.photo_data else "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return data

    def __repr__(self):
        return f"<Student {self.nim} - {self.name}>"


class StudentNFCCard(db.Model):
    """Dedicated NFC identity; old Student.rfid_uid values remain untouched."""

    __tablename__ = "student_nfc_cards"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, unique=True
    )
    uid = db.Column(db.String(20), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class FaceEmbedding(db.Model):
    """One face embedding of a student (float32 bytes), per face engine."""

    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    engine = db.Column(db.String(32), nullable=False, index=True)
    vector = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ToolType(db.Model):
    """A kind of tool (e.g. "Obeng"); each physical unit is a Tool."""

    __tablename__ = "tool_types"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_mimetype = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tools = db.relationship("Tool", backref="tool_type", lazy="dynamic")

    def to_dict(self):
        return {
            "type_id": str(self.id),
            "name": self.name,
            "photo_url": f"/api/tool_type/{self.id}/photo" if self.photo_data else "",
            "created_at": self.created_at,
        }

    def __repr__(self):
        return f"<ToolType {self.name}>"


class Tool(db.Model):
    """Tool model - represents workshop tools with RFID tags"""

    __tablename__ = "tools"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    rfid_uid = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, default="Uncategorized")
    status = db.Column(db.String(20), nullable=False, default="available", index=True)
    type_id = db.Column(db.Integer, db.ForeignKey("tool_types.id"), nullable=True)
    unit_no = db.Column(db.Integer, nullable=True)
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_mimetype = db.Column(db.String(50), nullable=True)
    # unknown | present | missing: whether the tag is in the reader field
    presence = db.Column(db.String(10), nullable=False, default="unknown")
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    transactions = db.relationship("Transaction", backref="tool", lazy="dynamic")

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "tool_id": str(self.id),
            "name": self.name,
            "rfid_uid": self.rfid_uid,
            "category": self.category,
            "status": self.status,
            "type_id": str(self.type_id) if self.type_id else None,
            "unit_no": self.unit_no,
            "photo_url": f"/api/tool/{self.id}/photo" if self.photo_data else "",
            "presence": self.presence,
            "last_seen_at": self.last_seen_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return f"<Tool {self.name} ({self.status})>"


class Transaction(db.Model):
    """Transaction model - represents borrow/return transactions"""

    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    student_name = db.Column(db.String(200), nullable=False)
    tool_id = db.Column(
        db.Integer, db.ForeignKey("tools.id"), nullable=False, index=True
    )
    tool_name = db.Column(db.String(200), nullable=False)
    borrow_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    return_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="borrowed", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_at = db.Column(db.DateTime, nullable=True)
    returned_by_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    return_verified = db.Column(db.Boolean, nullable=False, default=True)

    # Composite index for common queries
    __table_args__ = (
        db.Index(
            "ix_transactions_student_tool_status", "student_id", "tool_id", "status"
        ),
        db.Index("ix_transactions_tool_status", "tool_id", "status"),
    )

    @property
    def effective_due_at(self):
        """due_at, or borrow_time + LOAN_DAYS for old rows without one (UTC)."""
        if self.due_at is not None:
            return self.due_at
        try:
            days = current_app.config.get("LOAN_DAYS", 2)
        except RuntimeError:  # no app context
            days = 2
        return self.borrow_time + timedelta(days=days)

    def is_overdue(self, now=None):
        """A borrowed transaction is overdue once now > due_at."""
        if self.status != "borrowed":
            return False
        return (now or datetime.utcnow()) > self.effective_due_at

    def to_dict(self):
        """Convert model to dictionary with WIB timezone conversion"""
        utc_to_wib = _get_utc_to_wib()
        return {
            "transaction_id": str(self.id),
            "student_id": str(self.student_id),
            "student_name": self.student_name,
            "tool_id": str(self.tool_id),
            "tool_name": self.tool_name,
            # Convert timestamps from UTC to WIB
            "borrow_time": utc_to_wib(self.borrow_time),
            "return_time": utc_to_wib(self.return_time) if self.return_time else None,
            "status": self.status,
            "created_at": utc_to_wib(self.created_at),
            "due_at": utc_to_wib(self.effective_due_at),
            "is_overdue": self.is_overdue(),
            "returned_by_id": str(self.returned_by_id) if self.returned_by_id else None,
            "return_verified": self.return_verified,
        }

    def __repr__(self):
        return f"<Transaction {self.id} - {self.status}>"


class AlarmEvent(db.Model):
    """A tool left the reader field while it was not borrowed."""

    __tablename__ = "alarm_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tool_id = db.Column(
        db.Integer, db.ForeignKey("tools.id"), nullable=False, index=True
    )
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    # returned | admin | late_identify
    ended_by = db.Column(db.String(20), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)

    tool = db.relationship("Tool", backref="alarm_events")

    def to_dict(self):
        utc_to_wib = _get_utc_to_wib()
        return {
            "alarm_id": str(self.id),
            "tool_id": str(self.tool_id),
            "tool_name": self.tool.name if self.tool else None,
            "started_at": utc_to_wib(self.started_at),
            "ended_at": utc_to_wib(self.ended_at) if self.ended_at else None,
            "ended_by": self.ended_by,
            "student_id": str(self.student_id) if self.student_id else None,
        }

    def __repr__(self):
        return f"<AlarmEvent {self.id} tool={self.tool_id}>"

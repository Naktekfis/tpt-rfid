"""
SQLAlchemy models for the RFID Workshop Tool Monitoring System
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Student(db.Model):
    """Student model - represents registered students with RFID cards"""

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    nim = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    rfid_uid = db.Column(db.String(100), unique=True, nullable=False, index=True)
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_mimetype = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    transactions = db.relationship("Transaction", backref="student", lazy="dynamic")

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


class Tool(db.Model):
    """Tool model - represents workshop tools with RFID tags"""

    __tablename__ = "tools"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    rfid_uid = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, default="Uncategorized")
    status = db.Column(db.String(20), nullable=False, default="available", index=True)
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

    # Composite index for common queries
    __table_args__ = (
        db.Index(
            "ix_transactions_student_tool_status", "student_id", "tool_id", "status"
        ),
        db.Index("ix_transactions_tool_status", "tool_id", "status"),
    )

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "transaction_id": str(self.id),
            "student_id": str(self.student_id),
            "student_name": self.student_name,
            "tool_id": str(self.tool_id),
            "tool_name": self.tool_name,
            "borrow_time": self.borrow_time,
            "return_time": self.return_time,
            "status": self.status,
            "created_at": self.created_at,
        }

    def __repr__(self):
        return f"<Transaction {self.id} - {self.status}>"

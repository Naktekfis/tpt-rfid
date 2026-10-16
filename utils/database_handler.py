"""
Database handler for RFID Workshop Tool Monitoring System
Handles all database operations using SQLAlchemy
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from flask import current_app
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .models import (
    db,
    Student,
    Tool,
    ToolType,
    Transaction,
    AlarmEvent,
    FaceEmbedding,
)
from .helpers import utc_to_wib

logger = logging.getLogger(__name__)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Apply SQLite pragmas on every new connection (no-op for other DBs)."""
    if not isinstance(dbapi_conn, sqlite3.Connection):
        return
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class DatabaseHandler:
    """Handler for database operations via SQLAlchemy"""

    def __init__(self, app=None):
        """Initialize database handler, optionally with a Flask app"""
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app (for factory pattern support)"""
        db.init_app(app)
        with app.app_context():
            db.create_all()
        logger.info("Database handler initialized")

    def create_tables(self, app):
        """Create all tables (also called on startup by init_app)"""
        with app.app_context():
            db.create_all()
        logger.info("Database tables created")

    # ==================== Student Operations ====================

    def create_student(self, data: Dict) -> Dict:
        """
        Create a new student in the database

        Args:
            data (dict): Student data including name, nim, email, phone, rfid_uid

        Returns:
            dict: Created student data with ID
        """
        try:
            student = Student(
                name=data["name"],
                nim=data["nim"],
                email=data["email"],
                phone=data["phone"],
                rfid_uid=data.get("rfid_uid"),
            )
            db.session.add(student)
            db.session.commit()

            result = student.to_dict()
            logger.info(
                f"Created student: {student.name[:3]}*** (NIM: ***{student.nim[-4:]})"
            )
            return result

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating student: {str(e)}")
            raise

    def get_student_by_uid(self, rfid_uid: str) -> Optional[Dict]:
        """
        Get student by RFID UID

        Args:
            rfid_uid (str): RFID card UID

        Returns:
            dict or None: Student data if found, None otherwise
        """
        try:
            student = Student.query.filter_by(rfid_uid=rfid_uid).first()

            if student:
                logger.info(f"Found student by UID {rfid_uid}: {student.name[:3]}***")
                return student.to_dict()

            logger.warning(f"No student found with UID: {rfid_uid}")
            return None

        except Exception as e:
            logger.error(f"Error getting student by UID: {str(e)}")
            raise

    def get_student_by_nim(self, nim: str) -> Optional[Dict]:
        """
        Get student by NIM (for validation during registration)

        Args:
            nim (str): Student NIM

        Returns:
            dict or None: Student data if found, None otherwise
        """
        try:
            student = Student.query.filter_by(nim=nim).first()

            if student:
                return student.to_dict()

            return None

        except Exception as e:
            logger.error(f"Error getting student by NIM: {str(e)}")
            raise

    def get_student_by_id(self, student_id: str) -> Optional[Dict]:
        """
        Get student by ID

        Args:
            student_id (str): Student ID

        Returns:
            dict or None: Student data if found, None otherwise
        """
        try:
            student = db.session.get(Student, int(student_id))
            if student:
                return student.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting student by ID: {str(e)}")
            raise

    def update_student_photo(self, student_id: str, photo_data: bytes, mimetype: str):
        """
        Update a student's photo (stored as binary in database)

        Args:
            student_id (str): Student ID
            photo_data (bytes): Binary photo data
            mimetype (str): MIME type of the photo (e.g. 'image/jpeg')
        """
        try:
            student = db.session.get(Student, int(student_id))
            if student:
                student.photo_data = photo_data
                student.photo_mimetype = mimetype
                db.session.commit()
                logger.info(f"Updated photo for student {student_id}")
            else:
                raise ValueError(f"Student {student_id} not found")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating student photo: {str(e)}")
            raise

    def get_student_photo(self, student_id: str) -> Optional[tuple]:
        """
        Get student photo binary data

        Args:
            student_id (str): Student ID

        Returns:
            tuple or None: (photo_data, mimetype) if found, None otherwise
        """
        try:
            student = db.session.get(Student, int(student_id))
            if student and student.photo_data:
                return (student.photo_data, student.photo_mimetype)
            return None
        except Exception as e:
            logger.error(f"Error getting student photo: {str(e)}")
            raise

    # ==================== Face Data ====================

    def add_face_embeddings(
        self,
        student_id: int,
        engine: str,
        vectors: List[bytes],
        replace: bool = False,
    ) -> int:
        """Store float32 embedding bytes; replace=True drops this student's
        embeddings of the same engine first. Returns how many were stored."""
        try:
            if db.session.get(Student, int(student_id)) is None:
                raise ValueError(f"Student {student_id} not found")
            if replace:
                FaceEmbedding.query.filter_by(
                    student_id=int(student_id), engine=engine
                ).delete()
            for vec in vectors:
                db.session.add(
                    FaceEmbedding(student_id=int(student_id), engine=engine, vector=vec)
                )
            db.session.commit()
            return len(vectors)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding face embeddings: {str(e)}")
            raise

    def get_face_embeddings(self, engine: str) -> List[tuple]:
        """[(student_id, vector bytes)] for one engine."""
        rows = FaceEmbedding.query.filter_by(engine=engine).all()
        return [(r.student_id, bytes(r.vector)) for r in rows]

    def delete_face_data(self, student_id: int) -> bool:
        """Delete all embeddings and the profile photo. False if no such student."""
        try:
            student = db.session.get(Student, int(student_id))
            if student is None:
                return False
            FaceEmbedding.query.filter_by(student_id=student.id).delete()
            student.photo_data = None
            student.photo_mimetype = None
            db.session.commit()
            logger.info(f"Deleted face data for student {student_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting face data: {str(e)}")
            raise

    def student_has_face(self, student_id: int) -> bool:
        return (
            FaceEmbedding.query.filter_by(student_id=int(student_id)).first()
            is not None
        )

    # ==================== Tool Operations ====================

    def create_tool(self, data: Dict) -> Dict:
        """
        Create a new tool in the database

        Args:
            data (dict): Tool data including name, rfid_uid, category

        Returns:
            dict: Created tool data with ID
        """
        try:
            tool = Tool(
                name=data["name"],
                rfid_uid=data["rfid_uid"],
                category=data.get("category", "Uncategorized"),
                status=data.get("status", "available"),
                type_id=data.get("type_id"),
                unit_no=data.get("unit_no"),
            )
            db.session.add(tool)
            db.session.commit()

            result = tool.to_dict()
            logger.info(f"Created tool: {tool.name} (UID: {tool.rfid_uid})")
            return result

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating tool: {str(e)}")
            raise

    def get_tool_by_uid(self, rfid_uid: str) -> Optional[Dict]:
        """
        Get tool by RFID UID

        Args:
            rfid_uid (str): RFID tag UID

        Returns:
            dict or None: Tool data if found, None otherwise
        """
        try:
            tool = Tool.query.filter_by(rfid_uid=rfid_uid).first()

            if tool:
                logger.info(f"Found tool by UID {rfid_uid}: {tool.name}")
                return tool.to_dict()

            logger.warning(f"No tool found with UID: {rfid_uid}")
            return None

        except Exception as e:
            logger.error(f"Error getting tool by UID: {str(e)}")
            raise

    def get_tool_by_name(self, name: str) -> Optional[Dict]:
        """
        Get tool by name (case-insensitive)

        Args:
            name (str): Tool name

        Returns:
            dict or None: Tool data if found, None otherwise
        """
        try:
            tool = Tool.query.filter(Tool.name.ilike(name)).first()

            if tool:
                logger.info(f"Found tool by name: {tool.name}")
                return tool.to_dict()

            return None

        except Exception as e:
            logger.error(f"Error getting tool by name: {str(e)}")
            raise

    def update_tool_status(self, tool_id: str, status: str):
        """
        Update tool status (available/borrowed)

        Args:
            tool_id (str): Tool ID
            status (str): New status ('available' or 'borrowed')
        """
        try:
            tool = db.session.get(Tool, int(tool_id))
            if tool:
                tool.status = status
                db.session.commit()
                logger.info(f"Updated tool {tool_id} status to: {status}")
            else:
                raise ValueError(f"Tool {tool_id} not found")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating tool status: {str(e)}")
            raise

    # ==================== Presence / Alarm Operations ====================

    def create_tool_type(self, name: str) -> Dict:
        try:
            tool_type = ToolType(name=name)
            db.session.add(tool_type)
            db.session.commit()
            return tool_type.to_dict()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating tool type: {str(e)}")
            raise

    def get_tool_presence_info(self, rfid_uid: str) -> Optional[Dict]:
        """id, status, presence of the tool with this tag, or None if unknown."""
        tool = Tool.query.filter_by(rfid_uid=rfid_uid).first()
        if tool is None:
            return None
        return {"id": tool.id, "status": tool.status, "presence": tool.presence}

    def set_tool_presence(
        self, tool_id: int, presence: str, last_seen_at: Optional[datetime] = None
    ) -> None:
        try:
            values = {"presence": presence}
            if last_seen_at is not None:
                values["last_seen_at"] = last_seen_at
            db.session.execute(
                db.update(Tool).where(Tool.id == tool_id).values(**values)
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def open_alarm_for_tool(self, tool_id: int) -> Optional[AlarmEvent]:
        return AlarmEvent.query.filter_by(tool_id=tool_id, ended_at=None).first()

    def create_alarm(self, tool_id: int) -> Dict:
        try:
            alarm = AlarmEvent(tool_id=tool_id)
            db.session.add(alarm)
            db.session.commit()
            return alarm.to_dict()
        except Exception:
            db.session.rollback()
            raise

    def close_alarms_for_tool(self, tool_id: int, ended_by: str) -> int:
        """Close every open alarm of a tool; returns how many were closed."""
        try:
            closed = db.session.execute(
                db.update(AlarmEvent)
                .where(AlarmEvent.tool_id == tool_id, AlarmEvent.ended_at.is_(None))
                .values(ended_at=datetime.utcnow(), ended_by=ended_by)
            ).rowcount
            db.session.commit()
            return closed
        except Exception:
            db.session.rollback()
            raise

    def get_open_alarms(self) -> List[Dict]:
        alarms = (
            AlarmEvent.query.filter_by(ended_at=None)
            .order_by(AlarmEvent.started_at)
            .all()
        )
        return [a.to_dict() for a in alarms]

    def acknowledge_alarm(self, alarm_id: int, ended_by: str = "admin") -> bool:
        """Close one open alarm; False if it does not exist or is already closed."""
        try:
            closed = db.session.execute(
                db.update(AlarmEvent)
                .where(AlarmEvent.id == alarm_id, AlarmEvent.ended_at.is_(None))
                .values(ended_at=datetime.utcnow(), ended_by=ended_by)
            ).rowcount
            db.session.commit()
            return closed == 1
        except Exception:
            db.session.rollback()
            raise

    def get_tools_presence(self) -> List[Dict]:
        return [t.to_dict() for t in Tool.query.order_by(Tool.name).all()]

    @staticmethod
    def _loan_period() -> timedelta:
        return timedelta(days=current_app.config.get("LOAN_DAYS", 2))

    # ==================== Transaction Operations ====================

    def create_transaction(self, data: Dict) -> Dict:
        """
        Create a transaction record (borrow or return)

        Args:
            data (dict): Transaction data

        Returns:
            dict: Created transaction data with ID
        """
        try:
            borrow_time = data.get("borrow_time", datetime.utcnow())
            transaction = Transaction(
                student_id=int(data["student_id"]),
                student_name=data["student_name"],
                tool_id=int(data["tool_id"]),
                tool_name=data["tool_name"],
                borrow_time=borrow_time,
                due_at=borrow_time + self._loan_period(),
                return_time=data.get("return_time"),
                status=data.get("status", "borrowed"),
            )
            db.session.add(transaction)
            db.session.commit()

            result = transaction.to_dict()
            logger.info(
                f"Created transaction: {transaction.status} - "
                f"Student: {transaction.student_name[:3]}***, Tool: {transaction.tool_name}"
            )
            return result

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating transaction: {str(e)}")
            raise

    def get_recent_transactions(self, limit: int = 5) -> List[Dict]:
        """
        Get recent transactions ordered by creation time

        Args:
            limit (int): Maximum number of transactions to return

        Returns:
            list: List of recent transaction dicts
        """
        try:
            transactions = (
                Transaction.query.order_by(Transaction.created_at.desc())
                .limit(limit)
                .all()
            )

            result = [t.to_dict() for t in transactions]
            logger.info(f"Retrieved {len(result)} recent transactions")
            return result

        except Exception as e:
            logger.error(f"Error getting recent transactions: {str(e)}")
            raise

    def get_active_borrow(self, student_id: str, tool_id: str) -> Optional[Dict]:
        """
        Check if there's an active borrow transaction for a student-tool pair

        Args:
            student_id (str): Student ID
            tool_id (str): Tool ID

        Returns:
            dict or None: Active borrow transaction if found, None otherwise
        """
        try:
            transaction = Transaction.query.filter_by(
                student_id=int(student_id), tool_id=int(tool_id), status="borrowed"
            ).first()

            if transaction:
                return transaction.to_dict()

            return None

        except Exception as e:
            logger.error(f"Error checking active borrow: {str(e)}")
            raise

    def update_transaction_return(self, transaction_id: str):
        """
        Update transaction to mark tool as returned

        Args:
            transaction_id (str): Transaction ID
        """
        try:
            transaction = db.session.get(Transaction, int(transaction_id))
            if transaction:
                transaction.return_time = datetime.utcnow()
                transaction.status = "returned"
                db.session.commit()
                logger.info(f"Updated transaction {transaction_id} to returned")
            else:
                raise ValueError(f"Transaction {transaction_id} not found")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating transaction return: {str(e)}")
            raise

    def get_all_tools(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        """
        Get all tools from database, with optional pagination.

        Args:
            limit (int, optional): Max number of tools to return. None = all.
            offset (int): Number of tools to skip (for pagination). Default 0.

        Returns:
            list: List of tool dicts
        """
        try:
            query = Tool.query.order_by(Tool.name)

            if offset > 0:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)

            tools = query.all()
            result = [t.to_dict() for t in tools]
            logger.info(f"Retrieved {len(result)} tools")
            return result

        except Exception as e:
            logger.error(f"Error getting all tools: {str(e)}")
            raise

    def get_active_transaction_by_tool(self, tool_id: str) -> Optional[Dict]:
        """
        Get active transaction for a specific tool

        Args:
            tool_id (str): Tool ID

        Returns:
            dict or None: Active transaction if found
        """
        try:
            transaction = Transaction.query.filter_by(
                tool_id=int(tool_id), status="borrowed"
            ).first()

            if transaction:
                return transaction.to_dict()

            return None

        except Exception as e:
            logger.error(f"Error getting active transaction by tool: {str(e)}")
            raise

    # ==================== Atomic Borrow/Return Operations ====================

    def borrow_tool_atomic(self, student_id: str, tool_id: str) -> Dict:
        """
        Atomically borrow a tool using a database transaction.
        Reads tool status and student data, validates, creates transaction,
        and updates tool status -- all within one atomic transaction.

        Args:
            student_id (str): Student ID
            tool_id (str): Tool ID

        Returns:
            dict: Created transaction data with ID

        Raises:
            ValueError: If student/tool not found, tool not available, or already borrowed
        """
        try:
            # Use SELECT ... FOR UPDATE to lock the tool row
            student = db.session.get(Student, int(student_id))
            tool = db.session.execute(
                db.select(Tool).filter_by(id=int(tool_id)).with_for_update()
            ).scalar_one_or_none()

            if not student:
                raise ValueError("Data mahasiswa tidak ditemukan")
            if not tool:
                raise ValueError("Data tool tidak ditemukan")

            if tool.status != "available":
                raise ValueError("Tool sedang dipinjam")

            # Check for existing active borrow (same student + tool)
            existing = Transaction.query.filter_by(
                student_id=int(student_id), tool_id=int(tool_id), status="borrowed"
            ).first()
            if existing:
                raise ValueError("Anda sudah meminjam tool ini")

            # Claim the tool with a conditional UPDATE. SQLite ignores FOR UPDATE,
            # so this WHERE clause is what stops two concurrent borrows.
            claimed = db.session.execute(
                db.update(Tool)
                .where(Tool.id == tool.id, Tool.status == "available")
                .values(status="borrowed")
                .execution_options(synchronize_session=False)
            ).rowcount
            if claimed != 1:
                raise ValueError("Tool sedang dipinjam")

            # All checks passed -- create transaction
            now = datetime.utcnow()
            transaction = Transaction(
                student_id=student.id,
                student_name=student.name,
                tool_id=tool.id,
                tool_name=tool.name,
                borrow_time=now,
                due_at=now + self._loan_period(),
                return_time=None,
                status="borrowed",
            )
            db.session.add(transaction)
            db.session.commit()

            result = transaction.to_dict()
            logger.info(f"Atomic borrow: Student {student_id} borrowed tool {tool_id}")
            return result

        except ValueError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in atomic borrow: {str(e)}")
            raise

    def return_tool_atomic(self, student_id: str, tool_id: str) -> Dict:
        """
        Atomically return a tool using a database transaction.
        Finds active borrow, marks it returned, and sets tool available.

        Args:
            student_id (str): Student ID
            tool_id (str): Tool ID

        Returns:
            dict: Updated transaction info

        Raises:
            ValueError: If no active borrow found
        """
        try:
            # Lock the tool row for update
            tool = db.session.execute(
                db.select(Tool).filter_by(id=int(tool_id)).with_for_update()
            ).scalar_one_or_none()

            # Find active borrow transaction
            borrow_txn = Transaction.query.filter_by(
                student_id=int(student_id), tool_id=int(tool_id), status="borrowed"
            ).first()

            if not borrow_txn:
                other = Transaction.query.filter_by(
                    tool_id=int(tool_id), status="borrowed"
                ).first()
                if other:
                    raise ValueError(
                        "Alat ini dipinjam mahasiswa lain. "
                        "Hanya peminjam yang bisa mengembalikan."
                    )
                raise ValueError("Alat ini tidak sedang dipinjam")

            # Update transaction to returned
            borrow_txn.return_time = datetime.utcnow()
            borrow_txn.status = "returned"

            # Update tool status to available
            if tool:
                tool.status = "available"

            db.session.commit()

            result = {"transaction_id": str(borrow_txn.id), "status": "returned"}
            logger.info(f"Atomic return: Student {student_id} returned tool {tool_id}")
            return result

        except ValueError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in atomic return: {str(e)}")
            raise

    # ==================== Kiosk session operations ====================

    def close_borrow(
        self, tool_id: int, returned_by_id: Optional[int], verified: bool
    ) -> Optional[Dict]:
        """Close the open borrow of a tool, whoever returns it. None if the
        tool has no open borrow. Unlike return_tool_atomic this does not
        require the returner to be the borrower."""
        try:
            tool = db.session.execute(
                db.select(Tool).filter_by(id=int(tool_id)).with_for_update()
            ).scalar_one_or_none()
            txn = Transaction.query.filter_by(
                tool_id=int(tool_id), status="borrowed"
            ).first()
            if tool is None or txn is None:
                db.session.rollback()
                return None
            txn.return_time = datetime.utcnow()
            txn.status = "returned"
            txn.returned_by_id = returned_by_id
            txn.return_verified = verified
            tool.status = "available"
            db.session.commit()
            logger.info(
                f"Close borrow: tool {tool_id} by {returned_by_id} verified={verified}"
            )
            return txn.to_dict()
        except Exception:
            db.session.rollback()
            raise

    def get_unverified_returns(self) -> List[Dict]:
        rows = (
            Transaction.query.filter_by(status="returned", return_verified=False)
            .order_by(Transaction.return_time)
            .all()
        )
        return [
            {
                "transaction_id": str(t.id),
                "tool_id": str(t.tool_id),
                "tool_name": t.tool_name,
                "borrower_id": str(t.student_id),
                "borrower_name": t.student_name,
                "return_time": utc_to_wib(t.return_time).isoformat()
                if t.return_time
                else None,
            }
            for t in rows
        ]

    def verify_return(self, transaction_id: int) -> bool:
        """Admin: mark an unverified return as verified. False if there is none."""
        try:
            n = db.session.execute(
                db.update(Transaction)
                .where(
                    Transaction.id == transaction_id,
                    Transaction.status == "returned",
                    Transaction.return_verified.is_(False),
                )
                .values(return_verified=True)
            ).rowcount
            db.session.commit()
            return n == 1
        except Exception:
            db.session.rollback()
            raise

    def verify_returns_by_borrower(self, student_id: int) -> int:
        """A student's own unverified returns count as verified by them."""
        try:
            n = db.session.execute(
                db.update(Transaction)
                .where(
                    Transaction.student_id == int(student_id),
                    Transaction.status == "returned",
                    Transaction.return_verified.is_(False),
                )
                .values(return_verified=True, returned_by_id=int(student_id))
            ).rowcount
            db.session.commit()
            return n
        except Exception:
            db.session.rollback()
            raise

    def convert_recent_alarms_to_borrows(
        self, student_id: int, grace_seconds: float
    ) -> List[Dict]:
        """Open alarms that started within the grace window become borrows by
        the student (alarm ended_by='late_identify'). Returns the transactions."""
        cutoff = datetime.utcnow() - timedelta(seconds=grace_seconds)
        alarms = (
            AlarmEvent.query.filter(
                AlarmEvent.ended_at.is_(None), AlarmEvent.started_at >= cutoff
            )
            .order_by(AlarmEvent.started_at)
            .all()
        )
        converted = []
        for alarm_id, tool_id in [(a.id, a.tool_id) for a in alarms]:
            try:
                txn = self.borrow_tool_atomic(str(student_id), str(tool_id))
            except ValueError:
                continue  # tool no longer available: leave the alarm alone
            try:
                db.session.execute(
                    db.update(AlarmEvent)
                    .where(AlarmEvent.id == alarm_id, AlarmEvent.ended_at.is_(None))
                    .values(
                        ended_at=datetime.utcnow(),
                        ended_by="late_identify",
                        student_id=int(student_id),
                    )
                )
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            converted.append(txn)
        return converted

    def get_board(self) -> List[Dict]:
        """Tools grouped by type for the kiosk board, with borrower and
        overdue info taken from the open transaction's due_at."""
        now = datetime.utcnow()
        rows = (
            db.session.query(Tool, ToolType, Transaction, Student)
            .outerjoin(ToolType, ToolType.id == Tool.type_id)
            .outerjoin(
                Transaction,
                db.and_(Transaction.tool_id == Tool.id, Transaction.status == "borrowed"),
            )
            .outerjoin(Student, Student.id == Transaction.student_id)
            .all()
        )
        groups: Dict[object, Dict] = {}
        for tool, ttype, txn, student in rows:
            key = ttype.id if ttype else None
            group = groups.setdefault(
                key,
                {
                    "type_id": str(ttype.id) if ttype else None,
                    "type_name": ttype.name if ttype else "Lainnya",
                    "photo_url": ttype.to_dict()["photo_url"] if ttype else "",
                    "units": [],
                },
            )
            due = txn.effective_due_at if txn else None
            group["units"].append(
                {
                    "tool_id": str(tool.id),
                    "name": tool.name,
                    "unit_no": tool.unit_no,
                    "presence": tool.presence,
                    "status": tool.status,
                    "borrower_name": txn.student_name if txn else None,
                    "borrower_nim": student.nim if student else None,
                    "due_at": utc_to_wib(due).isoformat() if due else None,
                    "is_overdue": bool(txn and txn.is_overdue(now)),
                }
            )
        for group in groups.values():
            group["units"].sort(key=lambda u: (u["unit_no"] or 0, u["name"]))
        return sorted(groups.values(), key=lambda g: g["type_name"].lower())

    # ==================== Monitor / Batch Operations ====================

    def get_all_tools_with_borrowers(
        self,
        include_email: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Get all tools with borrower info using efficient JOINs.

        Args:
            include_email (bool): If True, include borrower email and photo info (admin view)
            limit (int, optional): Max tools to return. None = all.
            offset (int): Number of tools to skip. Default 0.

        Returns:
            list: List of tool dicts with borrower info attached
        """
        try:
            # Build query with LEFT JOIN to get active transactions and student info
            query = (
                db.session.query(Tool, Transaction, Student)
                .outerjoin(
                    Transaction,
                    db.and_(
                        Transaction.tool_id == Tool.id, Transaction.status == "borrowed"
                    ),
                )
                .outerjoin(Student, Student.id == Transaction.student_id)
                .order_by(Tool.name)
            )

            if offset > 0:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)

            rows = query.all()

            tools = []
            for tool, txn, student in rows:
                tool_dict = tool.to_dict()

                tool_dict["borrower_name"] = None
                tool_dict["borrower_nim"] = None
                tool_dict["borrow_time"] = None
                tool_dict["due_at"] = None
                tool_dict["is_overdue"] = False

                if include_email:
                    tool_dict["borrower_email"] = None
                    tool_dict["borrower_photo_url"] = None

                if txn and student:
                    tool_dict["borrower_name"] = txn.student_name
                    # Convert borrow_time from UTC to WIB
                    tool_dict["borrow_time"] = utc_to_wib(txn.borrow_time)
                    tool_dict["due_at"] = utc_to_wib(txn.effective_due_at)
                    tool_dict["is_overdue"] = txn.is_overdue()

                    if student:
                        tool_dict["borrower_nim"] = student.nim
                        if include_email:
                            tool_dict["borrower_email"] = student.email
                            tool_dict["borrower_photo_url"] = (
                                f"/api/student/{student.id}/photo"
                                if student.photo_data
                                else ""
                            )

                tools.append(tool_dict)

            logger.info(f"Retrieved {len(tools)} tools with borrower info")
            return tools

        except Exception as e:
            logger.error(f"Error getting tools with borrowers: {str(e)}")
            raise

    def get_transactions_filtered(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get filtered transactions for admin history and export.

        Args:
            start_date (datetime, optional): Start date filter (inclusive)
            end_date (datetime, optional): End date filter (inclusive)

        Returns:
            list: List of transaction dicts with student and tool info
                  (timestamps converted to WIB timezone)
        """
        try:
            # Build query with JOINs to get student and tool info
            query = (
                db.session.query(
                    Transaction.id,
                    Transaction.student_name,
                    Transaction.tool_name,
                    Transaction.borrow_time,
                    Transaction.return_time,
                    Transaction.status,
                    Student.nim.label("student_nim"),
                    Tool.category.label("tool_category"),
                )
                .join(Student, Student.id == Transaction.student_id)
                .join(Tool, Tool.id == Transaction.tool_id)
            )

            # Apply date filters if provided
            if start_date:
                query = query.filter(Transaction.borrow_time >= start_date)
            if end_date:
                query = query.filter(Transaction.borrow_time <= end_date)

            # Order by borrow time descending (newest first)
            query = query.order_by(Transaction.borrow_time.desc())

            results = query.all()

            # Convert to list of dicts with timezone conversion
            transactions = []
            for row in results:
                transactions.append(
                    {
                        "id": row.id,
                        "student_name": row.student_name,
                        "student_nim": row.student_nim,
                        "tool_name": row.tool_name,
                        "tool_category": row.tool_category,
                        # Convert UTC timestamps to WIB for display
                        "borrow_time": utc_to_wib(row.borrow_time),
                        "return_time": utc_to_wib(row.return_time)
                        if row.return_time
                        else None,
                        "status": row.status,
                    }
                )

            logger.info(
                f"Retrieved {len(transactions)} filtered transactions "
                f"(start: {start_date}, end: {end_date})"
            )
            return transactions

        except Exception as e:
            logger.error(f"Error getting filtered transactions: {str(e)}")
            raise

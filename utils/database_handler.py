"""
PostgreSQL database handler for RFID Workshop Tool Monitoring System
Handles all database operations using SQLAlchemy
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from .models import db, Student, Tool, Transaction

logger = logging.getLogger(__name__)


class DatabaseHandler:
    """Handler for PostgreSQL database operations via SQLAlchemy"""

    def __init__(self, app=None):
        """Initialize database handler, optionally with a Flask app"""
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app (for factory pattern support)"""
        db.init_app(app)
        logger.info("PostgreSQL database handler initialized")

    def create_tables(self, app):
        """Create all tables (use flask db upgrade in production instead)"""
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
                rfid_uid=data["rfid_uid"],
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
            transaction = Transaction(
                student_id=int(data["student_id"]),
                student_name=data["student_name"],
                tool_id=int(data["tool_id"]),
                tool_name=data["tool_name"],
                borrow_time=data.get("borrow_time", datetime.utcnow()),
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

            # All checks passed -- create transaction and update tool
            now = datetime.utcnow()
            transaction = Transaction(
                student_id=student.id,
                student_name=student.name,
                tool_id=tool.id,
                tool_name=tool.name,
                borrow_time=now,
                return_time=None,
                status="borrowed",
            )
            tool.status = "borrowed"

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
                raise ValueError("Tidak ada peminjaman aktif untuk tool ini")

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

                if include_email:
                    tool_dict["borrower_email"] = None
                    tool_dict["borrower_photo_url"] = None

                if txn and student:
                    tool_dict["borrower_name"] = txn.student_name
                    tool_dict["borrow_time"] = txn.borrow_time

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

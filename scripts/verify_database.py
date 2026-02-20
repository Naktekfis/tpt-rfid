#!/usr/bin/env python3
"""
TPT-RFID Database Verification Script
Verifies data integrity after migration
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Import database models
from utils.models import db, Student, Tool, Transaction
from config import get_config


# Colors for terminal output
class Colors:
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")


def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.NC}")


def print_warning(message):
    print(f"{Colors.YELLOW}⚠  {message}{Colors.NC}")


def print_info(message):
    print(f"{Colors.BLUE}{message}{Colors.NC}")


def verify_database():
    """Main verification function"""

    print_info("=" * 50)
    print_info("  TPT-RFID Database Verification")
    print_info("=" * 50)
    print()

    # Create Flask app context
    from flask import Flask

    app = Flask(__name__)
    app.config.from_object(get_config())
    db.init_app(app)

    errors = []
    warnings = []

    with app.app_context():
        # Test 1: Database connection
        print_info("Test 1: Database Connection")
        try:
            db.session.execute(db.text("SELECT 1"))
            print_success("Database connection successful")
        except Exception as e:
            print_error(f"Database connection failed: {e}")
            return False
        print()

        # Test 2: Table existence
        print_info("Test 2: Table Existence")
        tables = ["students", "tools", "transactions", "alembic_version"]
        for table in tables:
            try:
                result = db.session.execute(db.text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print_success(f"Table '{table}' exists ({count} records)")
            except Exception as e:
                print_error(f"Table '{table}' missing or inaccessible: {e}")
                errors.append(f"Missing table: {table}")
        print()

        # Test 3: Record counts
        print_info("Test 3: Record Counts")
        try:
            student_count = db.session.query(Student).count()
            tool_count = db.session.query(Tool).count()
            transaction_count = db.session.query(Transaction).count()

            print_success(f"Students: {student_count}")
            print_success(f"Tools: {tool_count}")
            print_success(f"Transactions: {transaction_count}")

            if student_count == 0:
                warnings.append("No students in database")
            if tool_count == 0:
                warnings.append("No tools in database")

        except Exception as e:
            print_error(f"Failed to count records: {e}")
            errors.append("Record count failed")
        print()

        # Test 4: RFID UID Uniqueness (Students)
        print_info("Test 4: RFID UID Uniqueness (Students)")
        try:
            duplicates = db.session.execute(
                db.text("""
                SELECT rfid_uid, COUNT(*) as count 
                FROM students 
                GROUP BY rfid_uid 
                HAVING COUNT(*) > 1
            """)
            ).fetchall()

            if duplicates:
                print_error(f"Found {len(duplicates)} duplicate student RFID UIDs")
                for dup in duplicates:
                    print(f"  - UID '{dup[0]}' appears {dup[1]} times")
                errors.append("Duplicate student RFID UIDs")
            else:
                print_success("All student RFID UIDs are unique")
        except Exception as e:
            print_error(f"Failed to check student UID uniqueness: {e}")
            errors.append("Student UID check failed")
        print()

        # Test 5: RFID UID Uniqueness (Tools)
        print_info("Test 5: RFID UID Uniqueness (Tools)")
        try:
            duplicates = db.session.execute(
                db.text("""
                SELECT rfid_uid, COUNT(*) as count 
                FROM tools 
                GROUP BY rfid_uid 
                HAVING COUNT(*) > 1
            """)
            ).fetchall()

            if duplicates:
                print_error(f"Found {len(duplicates)} duplicate tool RFID UIDs")
                for dup in duplicates:
                    print(f"  - UID '{dup[0]}' appears {dup[1]} times")
                errors.append("Duplicate tool RFID UIDs")
            else:
                print_success("All tool RFID UIDs are unique")
        except Exception as e:
            print_error(f"Failed to check tool UID uniqueness: {e}")
            errors.append("Tool UID check failed")
        print()

        # Test 6: NIM Uniqueness
        print_info("Test 6: NIM Uniqueness")
        try:
            duplicates = db.session.execute(
                db.text("""
                SELECT nim, COUNT(*) as count 
                FROM students 
                GROUP BY nim 
                HAVING COUNT(*) > 1
            """)
            ).fetchall()

            if duplicates:
                print_error(f"Found {len(duplicates)} duplicate NIMs")
                for dup in duplicates:
                    print(f"  - NIM '{dup[0]}' appears {dup[1]} times")
                errors.append("Duplicate NIMs")
            else:
                print_success("All NIMs are unique")
        except Exception as e:
            print_error(f"Failed to check NIM uniqueness: {e}")
            errors.append("NIM check failed")
        print()

        # Test 7: Foreign Key Integrity (Transactions → Students)
        print_info("Test 7: Foreign Key Integrity (Transactions → Students)")
        try:
            orphaned = db.session.execute(
                db.text("""
                SELECT t.id, t.student_id 
                FROM transactions t 
                LEFT JOIN students s ON t.student_id = s.id 
                WHERE s.id IS NULL
            """)
            ).fetchall()

            if orphaned:
                print_error(
                    f"Found {len(orphaned)} transactions with invalid student_id"
                )
                errors.append("Orphaned transactions (invalid student_id)")
            else:
                print_success("All transactions have valid student_id references")
        except Exception as e:
            print_error(f"Failed to check student FK integrity: {e}")
            errors.append("Student FK check failed")
        print()

        # Test 8: Foreign Key Integrity (Transactions → Tools)
        print_info("Test 8: Foreign Key Integrity (Transactions → Tools)")
        try:
            orphaned = db.session.execute(
                db.text("""
                SELECT t.id, t.tool_id 
                FROM transactions t 
                LEFT JOIN tools tl ON t.tool_id = tl.id 
                WHERE tl.id IS NULL
            """)
            ).fetchall()

            if orphaned:
                print_error(f"Found {len(orphaned)} transactions with invalid tool_id")
                errors.append("Orphaned transactions (invalid tool_id)")
            else:
                print_success("All transactions have valid tool_id references")
        except Exception as e:
            print_error(f"Failed to check tool FK integrity: {e}")
            errors.append("Tool FK check failed")
        print()

        # Test 9: Timestamp Format Check
        print_info("Test 9: Timestamp Format Check")
        try:
            # Check if timestamps are valid datetime objects
            sample_students = db.session.query(Student).limit(5).all()
            for student in sample_students:
                if not isinstance(student.created_at, datetime):
                    print_error(
                        f"Student {student.id} has invalid created_at timestamp"
                    )
                    errors.append("Invalid timestamp format")
                    break
            else:
                print_success("Student timestamps are valid")

            sample_tools = db.session.query(Tool).limit(5).all()
            for tool in sample_tools:
                if not isinstance(tool.created_at, datetime):
                    print_error(f"Tool {tool.id} has invalid created_at timestamp")
                    errors.append("Invalid timestamp format")
                    break
            else:
                print_success("Tool timestamps are valid")

            sample_transactions = db.session.query(Transaction).limit(5).all()
            for txn in sample_transactions:
                if not isinstance(txn.borrow_time, datetime):
                    print_error(f"Transaction {txn.id} has invalid borrow_time")
                    errors.append("Invalid timestamp format")
                    break
            else:
                print_success("Transaction timestamps are valid")
        except Exception as e:
            print_error(f"Failed to check timestamps: {e}")
            errors.append("Timestamp check failed")
        print()

        # Test 10: Data Completeness (Required Fields)
        print_info("Test 10: Data Completeness")
        try:
            # Check for NULL in required fields
            null_students = db.session.execute(
                db.text("""
                SELECT COUNT(*) FROM students 
                WHERE name IS NULL OR nim IS NULL OR rfid_uid IS NULL
            """)
            ).scalar()

            if null_students > 0:
                print_error(f"Found {null_students} students with NULL required fields")
                errors.append("Incomplete student data")
            else:
                print_success("All students have complete required fields")

            null_tools = db.session.execute(
                db.text("""
                SELECT COUNT(*) FROM tools 
                WHERE name IS NULL OR rfid_uid IS NULL OR status IS NULL
            """)
            ).scalar()

            if null_tools > 0:
                print_error(f"Found {null_tools} tools with NULL required fields")
                errors.append("Incomplete tool data")
            else:
                print_success("All tools have complete required fields")

        except Exception as e:
            print_error(f"Failed to check data completeness: {e}")
            errors.append("Data completeness check failed")
        print()

    # Summary
    print_info("=" * 50)
    print_info("  Verification Summary")
    print_info("=" * 50)
    print()

    if errors:
        print_error(f"Found {len(errors)} critical errors:")
        for error in errors:
            print(f"  • {error}")
        print()

    if warnings:
        print_warning(f"Found {len(warnings)} warnings:")
        for warning in warnings:
            print(f"  • {warning}")
        print()

    if not errors and not warnings:
        print_success("All verification tests passed!")
        print()
        return True
    elif not errors:
        print_warning("Verification passed with warnings")
        print()
        return True
    else:
        print_error("Verification failed - please fix errors above")
        print()
        return False


if __name__ == "__main__":
    success = verify_database()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Seed Database - Add Sample Data for Testing
Populates PostgreSQL database with sample students and tools
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from config import get_config
from utils import DatabaseHandler, db
from utils.models import Student, Tool


def create_app():
    """Create a minimal Flask app for database seeding"""
    app = Flask(__name__)
    app.config.from_object(get_config())
    database = DatabaseHandler(app)
    # Ensure tables exist (creates them if they don't)
    database.create_tables(app)
    return app, database


def seed_students(app, database):
    """Add sample students to database"""
    print("\n  Adding sample students...")

    students = [
        {
            "name": "Ahmad Fauzi",
            "nim": "1234567890",
            "email": "ahmad.fauzi@university.ac.id",
            "phone": "081234567890",
            "rfid_uid": "STUDENT001",
        },
        {
            "name": "Siti Nurhaliza",
            "nim": "0987654321",
            "email": "siti.nurhaliza@university.ac.id",
            "phone": "081234567891",
            "rfid_uid": "STUDENT002",
        },
        {
            "name": "Budi Santoso",
            "nim": "1122334455",
            "email": "budi.santoso@university.ac.id",
            "phone": "081234567892",
            "rfid_uid": "STUDENT003",
        },
        {
            "name": "Dewi Lestari",
            "nim": "5544332211",
            "email": "dewi.lestari@university.ac.id",
            "phone": "081234567893",
            "rfid_uid": "STUDENT004",
        },
        {
            "name": "Rizki Pratama",
            "nim": "6677889900",
            "email": "rizki.pratama@university.ac.id",
            "phone": "081234567894",
            "rfid_uid": "STUDENT005",
        },
    ]

    with app.app_context():
        # Get existing RFID UIDs to avoid duplicates
        existing_uids = set()
        try:
            existing_students = Student.query.all()
            for s in existing_students:
                existing_uids.add(s.rfid_uid)
        except Exception as e:
            print(f"  Warning: Could not check existing students: {e}")

        created_count = 0
        for student_data in students:
            try:
                if student_data["rfid_uid"] in existing_uids:
                    print(
                        f"  SKIP {student_data['name']} (UID: {student_data['rfid_uid']}) already exists"
                    )
                    continue

                student = database.create_student(student_data)
                print(
                    f"  OK   Created: {student_data['name']} (NIM: {student_data['nim']}, UID: {student_data['rfid_uid']})"
                )
                created_count += 1

            except Exception as e:
                print(f"  ERR  Error creating {student_data['name']}: {str(e)}")

        print(
            f"\n  Students: {created_count} created, {len(students) - created_count} skipped"
        )


def seed_tools(app, database):
    """Add sample tools to database"""
    print("\n  Adding sample tools...")

    tools = [
        {
            "name": "Drill Machine",
            "rfid_uid": "TOOL001",
            "category": "Power Tools",
            "status": "available",
        },
        {
            "name": "Angle Grinder",
            "rfid_uid": "TOOL002",
            "category": "Power Tools",
            "status": "available",
        },
        {
            "name": "Soldering Iron",
            "rfid_uid": "TOOL003",
            "category": "Electronics",
            "status": "available",
        },
        {
            "name": "Multimeter Digital",
            "rfid_uid": "TOOL004",
            "category": "Electronics",
            "status": "available",
        },
        {
            "name": "Circular Saw",
            "rfid_uid": "TOOL005",
            "category": "Power Tools",
            "status": "available",
        },
        {
            "name": "Oscilloscope",
            "rfid_uid": "TOOL006",
            "category": "Electronics",
            "status": "available",
        },
        {
            "name": "Impact Driver",
            "rfid_uid": "TOOL007",
            "category": "Power Tools",
            "status": "available",
        },
        {
            "name": "Hot Air Station",
            "rfid_uid": "TOOL008",
            "category": "Electronics",
            "status": "available",
        },
        {
            "name": "Belt Sander",
            "rfid_uid": "TOOL009",
            "category": "Power Tools",
            "status": "available",
        },
        {
            "name": "Wire Stripper Set",
            "rfid_uid": "TOOL010",
            "category": "Hand Tools",
            "status": "available",
        },
    ]

    with app.app_context():
        # Get existing RFID UIDs to avoid duplicates
        existing_uids = set()
        try:
            existing_tools = Tool.query.all()
            for t in existing_tools:
                existing_uids.add(t.rfid_uid)
        except Exception as e:
            print(f"  Warning: Could not check existing tools: {e}")

        created_count = 0
        for tool_data in tools:
            try:
                if tool_data["rfid_uid"] in existing_uids:
                    print(
                        f"  SKIP {tool_data['name']} (UID: {tool_data['rfid_uid']}) already exists"
                    )
                    continue

                tool = database.create_tool(tool_data)
                print(
                    f"  OK   Created: {tool_data['name']} (Category: {tool_data['category']}, UID: {tool_data['rfid_uid']})"
                )
                created_count += 1

            except Exception as e:
                print(f"  ERR  Error creating {tool_data['name']}: {str(e)}")

        print(
            f"\n  Tools: {created_count} created, {len(tools) - created_count} skipped"
        )


def main():
    """Main function to seed database"""
    print("=" * 60)
    print("RFID Workshop - Database Seeding Script")
    print("=" * 60)

    try:
        # Initialize Flask app and database
        print("\nConnecting to PostgreSQL database...")
        app, database = create_app()
        print("Connected to PostgreSQL successfully!")

        # Seed students
        seed_students(app, database)

        # Seed tools
        seed_tools(app, database)

        print("\n" + "=" * 60)
        print("Database seeding completed successfully!")
        print("=" * 60)

        print("\nSummary:")
        print("  - Students and tools have been added to PostgreSQL")
        print("  - You can now test the application with these UIDs:")
        print("\n  Student UIDs:")
        print("    - STUDENT001 (Ahmad Fauzi)")
        print("    - STUDENT002 (Siti Nurhaliza)")
        print("    - STUDENT003 (Budi Santoso)")
        print("    - STUDENT004 (Dewi Lestari)")
        print("    - STUDENT005 (Rizki Pratama)")
        print("\n  Tool UIDs:")
        print("    - TOOL001 (Drill Machine)")
        print("    - TOOL002 (Angle Grinder)")
        print("    - TOOL003 (Soldering Iron)")
        print("    - TOOL004 (Multimeter Digital)")
        print("    - TOOL005 to TOOL010 (Various tools)")

        print("\nTesting instructions:")
        print("  1. Open application: http://localhost:5000")
        print("  2. Go to 'Scan' page")
        print("  3. In browser console (F12), run:")
        print("     simulateRFID('STUDENT001')  // Scan student card")
        print("     simulateRFID('TOOL001')     // Scan tool tag")
        print("  4. Click 'Confirm Pinjam' to borrow")

    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

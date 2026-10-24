#!/usr/bin/env python3
"""
Seed Database - sample data for development.

Creates a few students (no RFID card yet) and 5 tool types with 3-5 units
each. Every unit gets an EPC-like tag UID (24 hex characters, uppercase), so
the debug route /debug/presence?epcs=<EPC>,<EPC> can simulate them.
"""

from __future__ import annotations

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask  # noqa: E402

from config import get_config  # noqa: E402
from utils import DatabaseHandler  # noqa: E402
from utils.models import Student, Tool, ToolType  # noqa: E402

STUDENTS = [
    {
        "name": "Ahmad Fauzi",
        "nim": "13320001",
        "email": "ahmad.fauzi@university.ac.id",
        "phone": "081234567890",
    },
    {
        "name": "Siti Nurhaliza",
        "nim": "13320002",
        "email": "siti.nurhaliza@university.ac.id",
        "phone": "081234567891",
    },
    {
        "name": "Budi Santoso",
        "nim": "13320003",
        "email": "budi.santoso@university.ac.id",
        "phone": "081234567892",
    },
]

# (type name, category, number of units)
TOOL_TYPES = [
    ("Bor Listrik", "Power Tools", 4),
    ("Multimeter Digital", "Electronics", 5),
    ("Solder Station", "Electronics", 3),
    ("Obeng Set", "Hand Tools", 5),
    ("Tang Potong", "Hand Tools", 3),
]


def make_epc(type_index: int, unit_no: int) -> str:
    """EPC-like UID: 24 hex characters, uppercase."""
    return f"E2000017221101{type_index:02X}{unit_no:02X}000000"


def create_app():
    """Create a minimal Flask app for database seeding"""
    app = Flask(__name__)
    app.config.from_object(get_config())
    database = DatabaseHandler(app)
    database.create_tables(app)
    return app, database


def seed_students(app, database):
    print("\n  Adding sample students...")
    created = 0
    with app.app_context():
        existing = {s.nim for s in Student.query.all()}
        for data in STUDENTS:
            if data["nim"] in existing:
                print(f"  SKIP {data['name']} already exists")
                continue
            database.create_student(data)
            print(f"  OK   Created: {data['name']} (NIM: {data['nim']})")
            created += 1
    print(f"\n  Students: {created} created, {len(STUDENTS) - created} skipped")


def seed_tools(app, database):
    print("\n  Adding tool types and units...")
    created = 0
    with app.app_context():
        existing_uids = {t.rfid_uid for t in Tool.query.all()}
        for type_index, (type_name, category, units) in enumerate(TOOL_TYPES, 1):
            tool_type = ToolType.query.filter_by(name=type_name).first()
            if tool_type is None:
                tool_type = ToolType.query.get(
                    database.create_tool_type(type_name)["type_id"]
                )
            for unit_no in range(1, units + 1):
                epc = make_epc(type_index, unit_no)
                if epc in existing_uids:
                    continue
                database.create_tool(
                    {
                        "name": f"{type_name} #{unit_no}",
                        "rfid_uid": epc,
                        "category": category,
                        "type_id": tool_type.id,
                        "unit_no": unit_no,
                    }
                )
                print(f"  OK   {type_name} #{unit_no}  {epc}")
                created += 1
    print(f"\n  Tools: {created} created")


def main():
    print("=" * 60)
    print("RFID Workshop - Database Seeding Script")
    print("=" * 60)

    try:
        app, database = create_app()
        seed_students(app, database)
        seed_tools(app, database)

        print("\n" + "=" * 60)
        print("Database seeding completed successfully!")
        print("=" * 60)
        print("\nSimulate tags with the mock reader (development):")
        print("  /debug/presence?epcs=<EPC>,<EPC>   tags in the field")
        print("  /api/presence                      presence, alarms, unknown tags")
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

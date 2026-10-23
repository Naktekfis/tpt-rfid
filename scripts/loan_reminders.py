"""
Show how many loan reminder emails would go out right now, without sending.
Counts only, no names or addresses. Read-only; does not start the readers.

  .venv/bin/python scripts/loan_reminders.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from config import get_config  # noqa: E402
from utils.loan_reminders import pending_reminders  # noqa: E402
from utils.models import db  # noqa: E402


def main() -> int:
    app = Flask(__name__)
    app.config.from_object(get_config())
    db.init_app(app)
    with app.app_context():
        if not inspect(db.engine).has_table("loan_reminders"):
            print(
                "Table loan_reminders missing: deploy the app version with reminders first."
            )
            return 1
        days = app.config.get("LOAN_OVERDUE_REMINDER_DAYS", 2)
        pending = pending_reminders(datetime.utcnow(), days)
        counts = Counter(kind for _, _, kind in pending)
        print(f"enabled: {app.config.get('LOAN_REMINDERS_ENABLED')}")
        print(f"would send now: due={counts['due']} overdue={counts['overdue']}")
        print(f"distinct students: {len({s.id for _, s, _ in pending})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

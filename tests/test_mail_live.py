"""Sends one real reminder email through the configured Gmail account.

Skipped unless MAIL_LIVE_TO is set, so normal runs and deploys never mail
anyone. Run it where .env has MAIL_USERNAME/MAIL_PASSWORD (the Jetson):

  MAIL_LIVE_TO=naktekfis@gmail.com .venv/bin/python -m pytest -q tests/test_mail_live.py
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

import pytest

from utils.loan_reminders import DUE, build_message
from utils.models import Student, Transaction

TO = os.getenv("MAIL_LIVE_TO")

pytestmark = pytest.mark.skipif(not TO, reason="set MAIL_LIVE_TO to send a real email")


def test_reminder_email_reaches_the_inbox():
    user, password = os.getenv("MAIL_USERNAME"), os.getenv("MAIL_PASSWORD")
    if not (user and password):
        pytest.fail("MAIL_USERNAME/MAIL_PASSWORD not set in .env")
    now = datetime.utcnow()
    txn = Transaction(
        tool_name="Multimeter (uji email)",
        borrow_time=now - timedelta(days=2),
        due_at=now,
    )
    subject, body = build_message(txn, Student(name="Uji Coba", email=TO), DUE, now)

    msg = EmailMessage()
    msg["Subject"] = f"[UJI] {subject}"
    msg["From"] = f"Lab Fabrikasi Teknik Fisika ITB <{user}>"
    msg["To"] = TO
    msg.set_content(body)

    server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.getenv("MAIL_PORT", "587"))
    with smtplib.SMTP(server, port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        refused = smtp.send_message(msg)
    assert refused == {}

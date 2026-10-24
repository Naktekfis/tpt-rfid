from datetime import datetime, timedelta

import pytest

from utils.loan_reminders import DUE, OVERDUE, LoanReminder, send_due_reminders
from utils.models import Transaction, db

T0 = datetime(2026, 10, 1, 3, 0)  # borrow time (UTC)
DUE_AT = T0 + timedelta(days=2)


class FakeMail:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def __call__(self, recipient, subject, body):
        if self.fail:
            raise OSError("smtp down")
        self.sent.append((recipient, subject, body))


@pytest.fixture()
def borrow(student, tool):
    txn = Transaction(
        student_id=int(student["student_id"]),
        student_name=student["name"],
        tool_id=int(tool["tool_id"]),
        tool_name=tool["name"],
        borrow_time=T0,
        due_at=DUE_AT,
        status="borrowed",
    )
    db.session.add(txn)
    db.session.commit()
    return txn


def kinds():
    return sorted(r.kind for r in LoanReminder.query.all())


def test_nothing_before_due(borrow):
    mail = FakeMail()
    assert send_due_reminders(mail, now=DUE_AT - timedelta(minutes=1)) == 0
    assert mail.sent == []


def test_due_then_overdue_each_once(borrow):
    mail = FakeMail()
    assert send_due_reminders(mail, now=DUE_AT + timedelta(minutes=5)) == 1
    assert send_due_reminders(mail, now=DUE_AT + timedelta(hours=5)) == 0
    recipient, subject, body = mail.sent[0]
    assert recipient == "budi@example.com"
    assert "Batas waktu" in subject
    assert "Obeng" in body and "03-10-2026 pukul 10:00 WIB" in body

    assert send_due_reminders(mail, now=DUE_AT + timedelta(days=2, minutes=1)) == 1
    assert send_due_reminders(mail, now=DUE_AT + timedelta(days=5)) == 0
    assert "terlambat 2 hari" in mail.sent[1][2]
    assert len(mail.sent) == 2
    assert kinds() == [DUE, OVERDUE]


def test_first_seen_long_overdue_sends_only_overdue(borrow):
    mail = FakeMail()
    assert send_due_reminders(mail, now=DUE_AT + timedelta(days=9)) == 1
    assert send_due_reminders(mail, now=DUE_AT + timedelta(days=10)) == 0
    assert kinds() == [OVERDUE]


def test_returned_borrow_gets_nothing(borrow):
    borrow.status = "returned"
    borrow.return_time = DUE_AT
    db.session.commit()
    mail = FakeMail()
    assert send_due_reminders(mail, now=DUE_AT + timedelta(days=3)) == 0


def test_failed_send_is_retried_later(borrow):
    assert send_due_reminders(FakeMail(fail=True), now=DUE_AT + timedelta(hours=1)) == 0
    assert kinds() == []
    mail = FakeMail()
    assert send_due_reminders(mail, now=DUE_AT + timedelta(hours=2)) == 1
    assert kinds() == [DUE]


def test_row_without_due_at_uses_loan_days(borrow):
    borrow.due_at = None  # old rows: borrow_time + LOAN_DAYS (2)
    db.session.commit()
    mail = FakeMail()
    assert send_due_reminders(mail, now=T0 + timedelta(days=1)) == 0
    assert send_due_reminders(mail, now=T0 + timedelta(days=2, minutes=1)) == 1


def test_sent_and_failed_reminders_are_logged_once(borrow, admin_client):
    from tests.conftest import TEST_PIN

    for hours in (1, 2):  # an outage retried every check leaves one failure row
        send_due_reminders(FakeMail(fail=True), now=DUE_AT + timedelta(hours=hours))
    send_due_reminders(FakeMail(), now=DUE_AT + timedelta(hours=3))

    assert admin_client.get("/api/admin/emails").status_code == 401
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    emails = admin_client.get("/api/admin/emails").get_json()["emails"]
    assert [(m["kind"], m["success"]) for m in emails] == [(DUE, True), (DUE, False)]
    assert emails[0]["recipient"] == "budi@example.com"
    assert emails[0]["tool_name"] == "Obeng"
    assert emails[1]["error"] == "OSError: smtp down"


def test_manual_warning_email_is_logged(admin_client, monkeypatch):
    import app as app_module
    from tests.conftest import TEST_PIN

    sent = []
    monkeypatch.setattr(app_module.mail, "send", sent.append)
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    resp = admin_client.post(
        "/api/admin/send_warning_email",
        json={
            "student_name": "Budi",
            "student_email": "budi@example.com",
            "tool_name": "Obeng",
            "borrow_date": "2026-10-01T10:00:00",
        },
    )
    assert resp.status_code == 200 and len(sent) == 1
    emails = admin_client.get("/api/admin/emails").get_json()["emails"]
    assert [(m["kind"], m["success"], m["student_name"]) for m in emails] == [
        ("manual", True, "Budi")
    ]

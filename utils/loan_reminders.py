"""
Automatic loan reminder emails.

A borrow gets at most two: "due" once it is past its due time, and "overdue"
once it is LOAN_OVERDUE_REMINDER_DAYS past due. A borrow that is already that
late when it is first seen (e.g. right after reminders are switched on) gets
only the "overdue" one. Each (transaction, kind) is claimed in loan_reminders
before sending, so a reminder is never sent twice; a failed send drops the
claim and is retried on the next check.

The mail itself goes through a `send(recipient, subject, body)` callable from
app.py, so this module does not import Flask-Mail and tests use a fake.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from utils.helpers import utc_to_wib
from utils.models import EmailLog, LoanReminder, Student, Transaction, db

logger = logging.getLogger(__name__)

DUE = "due"
OVERDUE = "overdue"

SendMail = Callable[[str, str, str], None]


def pending_reminders(
    now: datetime, overdue_days: int
) -> List[Tuple[Transaction, Student, str]]:
    """Borrowed transactions that need a reminder now, with the kind to send."""
    sent = {
        (r.transaction_id, r.kind)
        for r in db.session.query(LoanReminder.transaction_id, LoanReminder.kind)
    }
    rows = (
        db.session.query(Transaction, Student)
        .join(Student, Transaction.student_id == Student.id)
        .filter(Transaction.status == "borrowed")
        .order_by(Transaction.id)
        .all()
    )
    out = []
    for txn, student in rows:
        due = txn.effective_due_at
        if now < due:
            continue
        if now >= due + timedelta(days=overdue_days):
            kind = OVERDUE
        elif (txn.id, OVERDUE) in sent:
            continue
        else:
            kind = DUE
        if (txn.id, kind) not in sent:
            out.append((txn, student, kind))
    return out


def _wib(dt: datetime) -> str:
    return utc_to_wib(dt).strftime("%d-%m-%Y pukul %H:%M WIB")


def build_message(txn: Transaction, student: Student, kind: str, now: datetime):
    """(subject, body) in Indonesian for one reminder."""
    due = txn.effective_due_at
    if kind == DUE:
        subject = "[Lab Fabrikasi ITB] Batas waktu peminjaman alat"
        opening = (
            "Batas waktu peminjaman alat berikut sudah tiba. "
            "Mohon kembalikan alat ke Lab Fabrikasi pada jam operasional."
        )
    else:
        late_days = max(1, (now - due).days)
        subject = "[Lab Fabrikasi ITB] Alat terlambat dikembalikan"
        opening = (
            f"Alat berikut sudah terlambat {late_days} hari dari batas waktu "
            "peminjaman. Mohon segera kembalikan alat ke Lab Fabrikasi."
        )
    body = f"""Kepada Yth. {student.name},

{opening}

Nama alat: {txn.tool_name}
Dipinjam: {_wib(txn.borrow_time)}
Batas waktu: {_wib(due)}

Apabila alat sudah dikembalikan, mohon abaikan email ini. Jika ada kendala,
silakan hubungi petugas lab.

Salam,
Tim Lab Fabrikasi
Teknik Fisika ITB

---
Email ini dikirim otomatis oleh sistem peminjaman Lab Fabrikasi.
"""
    return subject, body


def log_email(
    kind: str,
    recipient: str,
    student_name: Optional[str],
    tool_name: Optional[str],
    error: Optional[BaseException] = None,
) -> None:
    """Record one reminder email (sent, or failed with `error`) for the admin.
    A failure repeating the previous one for the same email is not logged
    again, so a long outage (retried every check) leaves one row."""
    if error is not None:
        last = (
            EmailLog.query.filter_by(
                kind=kind, recipient=recipient, tool_name=tool_name
            )
            .order_by(EmailLog.id.desc())
            .first()
        )
        if last is not None and not last.success:
            return
    db.session.add(
        EmailLog(
            kind=kind,
            recipient=recipient,
            student_name=student_name,
            tool_name=tool_name,
            success=error is None,
            error=None if error is None else f"{type(error).__name__}: {error}"[:200],
        )
    )
    db.session.commit()


def email_history(limit: int = 100) -> List[dict]:
    rows = EmailLog.query.order_by(EmailLog.at.desc(), EmailLog.id.desc()).limit(limit)
    return [row.to_dict() for row in rows]


def send_due_reminders(
    send: SendMail, now: Optional[datetime] = None, overdue_days: int = 2
) -> int:
    """Send every reminder that is due now; returns how many went out.
    Needs an app context. Stops at the first mail failure (usually bad
    credentials or no network) and leaves the rest for the next check."""
    now = now or datetime.utcnow()
    sent = 0
    for txn, student, kind in pending_reminders(now, overdue_days):
        claim = LoanReminder(transaction_id=txn.id, kind=kind)
        db.session.add(claim)
        try:
            db.session.commit()
        except IntegrityError:  # claimed elsewhere meanwhile
            db.session.rollback()
            continue
        subject, body = build_message(txn, student, kind, now)
        try:
            send(student.email, subject, body)
        except (
            Exception
        ) as exc:  # SMTP/network errors vary; drop the claim, retry later
            logger.exception("Loan reminder %s for transaction %s failed", kind, txn.id)
            db.session.delete(claim)
            db.session.commit()
            log_email(kind, student.email, student.name, txn.tool_name, exc)
            break
        claim.sent_at = datetime.utcnow()
        db.session.commit()
        log_email(kind, student.email, student.name, txn.tool_name)
        sent += 1
        logger.info("Loan reminder %s sent for transaction %s", kind, txn.id)
    return sent


class LoanReminderService:
    """Background thread that runs send_due_reminders every `interval` s."""

    def __init__(
        self, app, send: SendMail, interval: float = 300, overdue_days: int = 2
    ):
        self.app = app
        self.send = send
        self.interval = interval
        self.overdue_days = overdue_days
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="loan-reminders", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                with self.app.app_context():
                    send_due_reminders(self.send, overdue_days=self.overdue_days)
            except Exception:  # thread boundary: keep checking after a bad run
                logger.exception("Loan reminder check failed")

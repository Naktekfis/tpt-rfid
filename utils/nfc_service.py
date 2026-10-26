"""Route each NFC tap to one short registration capture or the kiosk."""

from __future__ import annotations

import secrets
import threading
import time

from .nfc_policy import CardPolicy


class NFCCaptureError(ValueError):
    pass


class NFCService:
    def __init__(self, app, reader, kiosk, clock=time.monotonic, policy=None):
        self.app, self.reader, self.kiosk = app, reader, kiosk
        self.policy = policy or CardPolicy(enforce=False)
        self.clock = clock
        self.lock = threading.RLock()
        self.capture = None
        reader.add_listener(self.on_card)

    def _expire(self):
        if self.capture and self.clock() >= self.capture["expires"]:
            self.capture = None

    def start(self, owner):
        with self.lock:
            self._expire()
            if self.kiosk.state_dict()["state"] == "session":
                raise NFCCaptureError("Selesaikan sesi kiosk terlebih dahulu")
            if self.capture and self.capture["owner"] != owner:
                raise NFCCaptureError("Reader sedang dipakai untuk pendaftaran lain")
            token = secrets.token_urlsafe(32)
            self.capture = dict(
                owner=owner,
                token=token,
                uid=None,
                error=None,
                expires=self.clock() + 120,
                after=self.reader.status()["sequence"],
            )
            return token

    def ready(self, owner):
        with self.lock:
            self._expire()
            return bool(
                self.capture and self.capture["owner"] == owner and self.capture["uid"]
            )

    def rejection(self, owner):
        """Why the last tap was refused (a message, never the card data)."""
        with self.lock:
            self._expire()
            if self.capture and self.capture["owner"] == owner:
                return self.capture["error"]
            return None

    def cancel(self, owner, token):
        with self.lock:
            if (
                self.capture
                and self.capture["owner"] == owner
                and secrets.compare_digest(self.capture["token"], token)
            ):
                self.capture = None

    def on_card(self, event):
        with self.lock:
            self._expire()
            if self.capture:
                if event["sequence"] <= self.capture["after"]:
                    return
                if self.capture["uid"] is None:
                    error = self.policy.check_tap(event)
                    self.capture["error"] = error
                    if error is None:
                        self.capture["uid"] = event["uid"]
                return
            with self.app.app_context():
                if self._refused(event):
                    self.kiosk.reject_card()
                else:
                    self.kiosk.on_card(event["uid"])

    def _refused(self, event):
        if self.policy.check_tap(event):
            return True
        if self.policy.is_special(event["uid"]):
            student = self.kiosk.database.get_student_by_nfc(event["uid"])
            return bool(
                student and self.policy.check_student(event["uid"], student["nim"])
            )
        return False

    def submit(self, owner, token, operation):
        with self.lock:
            self._expire()
            cap = self.capture
            if (
                not cap
                or cap["owner"] != owner
                or not secrets.compare_digest(cap["token"], token)
            ):
                raise NFCCaptureError(
                    "Mulai pembacaan KTM kembali; waktu pendaftaran habis"
                )
            if not cap["uid"]:
                raise NFCCaptureError("Tempelkan KTM terlebih dahulu")
            result = operation(cap["uid"])
            self.capture = None
            return result

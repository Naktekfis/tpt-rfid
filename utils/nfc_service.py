"""Route each NFC tap to one short registration capture or the kiosk."""

from __future__ import annotations

import logging
import secrets
import threading
import time

from .nfc_policy import CardPolicy

logger = logging.getLogger(__name__)


class NFCCaptureError(ValueError):
    pass


def chip_profile(card):
    """(ATQA, SAK, ATS) as the reader gives them; ATS is "" when the chip sends none."""
    return (
        str(card.get("atqa", "")).upper(),
        card.get("sak"),
        str(card.get("ats", "")).upper(),
    )


class NFCService:
    def __init__(self, app, reader, kiosk, clock=time.monotonic, policy=None):
        self.app, self.reader, self.kiosk = app, reader, kiosk
        self.policy = policy or CardPolicy(enforce=False)
        self.clock = clock
        self.lock = threading.RLock()
        self.capture = None
        # owner -> capture from an admin phone (Web NFC); kept apart so it
        # never holds the kiosk reader.
        self.phone = {}
        reader.add_listener(self.on_card)

    def _expire(self):
        if self.capture and self.clock() >= self.capture["expires"]:
            self.capture = None
        for owner in [o for o, c in self.phone.items() if self.clock() >= c["expires"]]:
            del self.phone[owner]

    def start(self, owner, any_card=False):
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
                card=None,
                error=None,
                any_card=any_card,  # admin card exceptions read every chip
                expires=self.clock() + 120,
                after=self.reader.status()["sequence"],
            )
            return token

    def start_phone(self, owner, uid):
        """Capture for a UID an admin's phone read (already normalized)."""
        with self.lock:
            self._expire()
            token = secrets.token_urlsafe(32)
            self.phone[owner] = dict(
                owner=owner, token=token, uid=uid, expires=self.clock() + 120
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
        with self.lock, self.app.app_context():
            self._expire()
            if self.capture:
                if event["sequence"] <= self.capture["after"]:
                    return
                if self.capture["uid"] is None:
                    error = (
                        None
                        if self.capture["any_card"]
                        else self.policy.check_tap(event)
                    )
                    self.capture["error"] = error
                    self._log_refusal(event, error)
                    if error is None:
                        self.capture["uid"] = event["uid"]
                        self.capture["card"] = event.get("card")
                return
            refusal = self._refusal(event)
            if refusal:
                self.kiosk.reject_card(refusal if refusal == "card_mismatch" else None)
            else:
                self.kiosk.on_card(event["uid"])

    def _log_refusal(self, event, error):
        card = event.get("card")
        if error and card:  # chip type only, never the UID
            logger.info(
                "NFC tap refused: %s (ATQA=%s SAK=0x%02X ATS=%s)",
                error,
                card.get("atqa"),
                card.get("sak") or 0,
                card.get("ats"),
            )

    def _refusal(self, event):
        """None to open the kiosk, else the kiosk's reason for refusing the tap."""
        uid, card = event["uid"], event.get("card")
        database = self.kiosk.database
        student = database.get_student_by_nfc(uid)
        chip = chip_profile(card) if card else None  # mock taps carry no chip data
        profile = database.get_nfc_profile(uid) if student and chip else None
        if profile and profile["complete"]:
            if tuple(profile["chip"]) != chip:
                logger.warning(
                    "NFC tap refused: chip differs from the card registered as ...%s",
                    uid[-4:],
                )
                return "card_mismatch"
        elif profile is None:  # unbound, mock, or bound before profiles: as before
            error = self.policy.check_tap(event)
            if error:
                self._log_refusal(event, error)
                return "refused"
        # A pending profile skips the KTM check: an admin registered the card.
        if student and self.policy.check_student(uid, student["nim"]):
            return "refused"
        if chip and student and not (profile and profile["complete"]):
            database.save_nfc_profile(uid, chip)
        return None

    def submit(self, owner, token, operation, bind=False):
        """Run operation(uid) once; bind=True also stores the card's profile."""
        with self.lock:
            self._expire()
            matches = [
                c
                for c in (self.capture, self.phone.get(owner))
                if c
                and c["owner"] == owner
                and secrets.compare_digest(c["token"], token)
            ]
            cap = matches[0] if matches else None
            if cap is None:
                raise NFCCaptureError(
                    "Mulai pembacaan KTM kembali; waktu pendaftaran habis"
                )
            if not cap["uid"]:
                raise NFCCaptureError("Tempelkan KTM terlebih dahulu")
            result = operation(cap["uid"])
            if bind:
                self._save_bound_profile(cap)
            if cap is self.capture:
                self.capture = None
            else:
                del self.phone[owner]
            return result

    def _save_bound_profile(self, cap):
        database = self.kiosk.database
        if cap is not self.capture:  # phone: no chip data, learnt on the first tap
            database.save_nfc_profile(cap["uid"], None, "admin_phone")
        elif cap["card"]:
            source = "admin_reader" if cap["any_card"] else "kiosk"
            database.save_nfc_profile(cap["uid"], chip_profile(cap["card"]), source)

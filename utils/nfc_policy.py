"""Which NFC cards may register or open a kiosk session.

Only KTM chips are accepted, recognised by ATQA + SAK + ATS (all three: ATQA and
SAK alone also match e-money and Flazz cards). One personal card is exempt, but
only for one NIM. Both the card UID and the NIM are kept as HMAC digests keyed
with a secret from `.env`, so neither can be read from the repository, the
config or a backup (an 8-digit NIM would fall to a plain hash in seconds).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Callable, Dict, Optional, Tuple

# (ATQA hex, SAK, ATS hex) measured on KTMs, 2026-10-26. Batches differ in the
# ATS, so a KTM refused at the kiosk usually just needs its profile added here.
KTM_PROFILES = (
    ("0004", 0x28, "0D78007003990200D103042201"),
    ("0004", 0x28, "0D7800A10257694C4C20230307"),
)

MSG_NOT_KTM = "Kartunya bukan KTM, silakan daftar menggunakan KTM"
MSG_BROKEN = "Kartu rusak"


class CardPolicy:
    def __init__(
        self,
        pepper: str = "",
        special_uid_hmac: str = "",
        special_nim_hmac: str = "",
        ktm_profiles: Tuple[Tuple[str, int, str], ...] = KTM_PROFILES,
        enforce: bool = True,
        lookup: Optional[Callable[[str], Optional[Dict[str, str]]]] = None,
    ):
        self._pepper = pepper.encode()
        self._uid_hmac = special_uid_hmac.strip().lower()
        self._nim_hmac = special_nim_hmac.strip().lower()
        self._profiles = tuple(
            (a.upper(), int(s), t.upper()) for a, s, t in ktm_profiles
        )
        self.enforce = enforce
        # uid digest -> {"kind", "nim_hmac"} for cards an admin let through
        self.lookup = lookup

    @property
    def can_hash(self) -> bool:
        return bool(self._pepper)

    def digest(self, kind: str, value: str) -> str:
        message = "{}:{}".format(kind, value.strip().upper()).encode()
        return hmac.new(self._pepper, message, hashlib.sha256).hexdigest()

    def _matches(self, kind: str, value: str, expected: str) -> bool:
        if not self._pepper or not expected:
            return False
        return hmac.compare_digest(self.digest(kind, value), expected)

    def is_special(self, uid: str) -> bool:
        return self._matches("uid", uid, self._uid_hmac)

    def _exemption(self, uid: str) -> Optional[str]:
        """None if the card gets no exemption, else the NIM digest it is tied to
        ("" = any NIM)."""
        if self.is_special(uid):
            return self._nim_hmac or "-"
        if not self._pepper or self.lookup is None:
            return None
        row = self.lookup(self.digest("uid", uid))
        return None if row is None else (row.get("nim_hmac") or "")

    def is_exempt(self, uid: str) -> bool:
        return self._exemption(uid) is not None

    def check_tap(self, event: dict) -> Optional[str]:
        """Error message for a tap that must not be used at all, else None."""
        card = event.get("card")
        if not self.enforce or card is None:  # mock taps carry no chip data
            return None
        if self._exemption(event["uid"]) is not None:
            return None  # its NIM is checked once the account is known
        profile = (
            str(card.get("atqa", "")).upper(),
            card.get("sak"),
            str(card.get("ats", "")).upper(),
        )
        return None if profile in self._profiles else MSG_NOT_KTM

    def check_student(self, uid: str, nim: str) -> Optional[str]:
        """A card tied to one NIM works for that NIM only; any other gets 'broken'."""
        expected = self._exemption(uid) if self.enforce else None
        if not expected:
            return None
        return None if self._matches("nim", nim, expected) else MSG_BROKEN

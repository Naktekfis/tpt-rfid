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
from typing import Optional, Tuple

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
    ):
        self._pepper = pepper.encode()
        self._uid_hmac = special_uid_hmac.strip().lower()
        self._nim_hmac = special_nim_hmac.strip().lower()
        self._profiles = tuple(
            (a.upper(), int(s), t.upper()) for a, s, t in ktm_profiles
        )
        self.enforce = enforce

    def digest(self, kind: str, value: str) -> str:
        message = "{}:{}".format(kind, value.strip().upper()).encode()
        return hmac.new(self._pepper, message, hashlib.sha256).hexdigest()

    def _matches(self, kind: str, value: str, expected: str) -> bool:
        if not self._pepper or not expected:
            return False
        return hmac.compare_digest(self.digest(kind, value), expected)

    def is_special(self, uid: str) -> bool:
        return self._matches("uid", uid, self._uid_hmac)

    def check_tap(self, event: dict) -> Optional[str]:
        """Error message for a tap that must not be used at all, else None."""
        card = event.get("card")
        if not self.enforce or card is None:  # mock taps carry no chip data
            return None
        if self.is_special(event["uid"]):
            return None  # its NIM is checked once the account is known
        profile = (
            str(card.get("atqa", "")).upper(),
            card.get("sak"),
            str(card.get("ats", "")).upper(),
        )
        return None if profile in self._profiles else MSG_NOT_KTM

    def check_student(self, uid: str, nim: str) -> Optional[str]:
        """The exempt card works for exactly one NIM; any other gets 'broken'."""
        if not self.enforce or not self.is_special(uid):
            return None
        return None if self._matches("nim", nim, self._nim_hmac) else MSG_BROKEN

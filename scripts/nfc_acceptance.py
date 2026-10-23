#!/usr/bin/env python3
"""PN532 acceptance: real card, synthetic registration and in-memory loans.

Run with the deployed app virtualenv while the main application's NFC reader
is stopped. No card data is written; no on-disk database is opened. The card
UID is held only in this process and is never printed.
"""

from __future__ import annotations

import atexit
import html
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


class AcceptanceFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AcceptanceFailure(message)


def wait_for(predicate, timeout, message):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AcceptanceFailure(message)


def exercise(module):
    app = module.app
    require(
        app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://", "RAM database required"
    )
    require(app.config.get("WTF_CSRF_ENABLED", True), "CSRF must remain enabled")
    require(module.nfc_reader.mode == "pn532", "Real NFC reader required")
    require(module.rfid_reader.mode == "mock", "Mock UHF reader required")
    require(module.camera.status().get("mock"), "Mock camera required")
    wait_for(
        lambda: module.nfc_reader.status()["connected"],
        25,
        "PN532 connection timeout",
    )
    print("PASS: PN532 connected; RAM database; CSRF enabled", flush=True)
    client = app.test_client()
    page = client.get("/daftar")
    require(page.status_code == 200, "Registration page failed")
    match = re.search(
        r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
        page.get_data(as_text=True),
    )
    require(match is not None, "CSRF token missing")
    headers = {"X-CSRFToken": html.unescape(match.group(1))}

    # Prove a missing token is rejected; keep the application's protections on.
    rejected = client.post("/api/nfc/registration/start", json={})
    require(rejected.status_code == 400, "Missing CSRF token was accepted")
    response = client.post("/api/nfc/registration/start", json={}, headers=headers)
    data = response.get_json(silent=True) or {}
    require(response.status_code == 200 and data.get("success"), "Capture start failed")
    capture_token = data.get("token")
    require(bool(capture_token), "Capture token missing")
    print("READY: tap #1 for synthetic registration (90 seconds)", flush=True)

    def capture_ready():
        response = client.get("/api/nfc/registration")
        result = response.get_json(silent=True) or {}
        return response.status_code == 200 and result.get("ready")

    wait_for(capture_ready, 90, "First card tap timeout")
    response = client.post(
        "/api/register",
        data={
            "name": "Synthetic NFC Acceptance",
            "nim": "NFCACCEPT01",
            "email": "nfc-acceptance@example.invalid",
            "phone": "000000000000",
            "nfc_token": capture_token,
        },
        headers=headers,
    )
    result = response.get_json(silent=True) or {}
    require(
        response.status_code == 200 and result.get("success"), "Registration failed"
    )
    student_id = (result.get("student") or {}).get("student_id")
    require(student_id is not None, "Registration identity missing")
    print("PASS: NFC registration saved only in RAM", flush=True)
    print(
        "READY: lift card >=2 seconds, then retap #2 to open session (90 seconds)",
        flush=True,
    )

    def session_ready():
        state = module.kiosk.state_dict()
        return state["state"] == "session"

    wait_for(session_ready, 90, "Second card tap/session timeout")
    state = module.kiosk.state_dict()
    require(
        str((state.get("student") or {}).get("student_id")) == str(student_id),
        "Session identity mismatch",
    )
    print("PASS: physical retap opened the expected session", flush=True)

    epc = "ACCE00000000000000000001"  # synthetic UHF identity; never sent to hardware
    with app.app_context():
        module.database.create_tool(
            {"name": "Synthetic acceptance tool", "rfid_uid": epc, "category": "Test"}
        )
    module.rfid_reader.set_present([epc])
    wait_for(
        lambda: (
            module.presence_service.monitor.snapshot().get(epc, {}).get("state")
            == "present"
        ),
        5,
        "Mock UHF arrival timeout",
    )
    module.rfid_reader.set_present([])
    wait_for(
        lambda: len(module.kiosk.state_dict().get("borrowed", [])) == 1,
        10,
        "UHF departure did not create a borrow",
    )
    module.rfid_reader.set_present([epc])
    wait_for(
        lambda: len(module.kiosk.state_dict().get("returned", [])) == 1,
        5,
        "UHF return did not close the borrow",
    )
    with app.app_context():
        info = module.database.get_tool_presence_info(epc)
        require(
            info is not None and info["status"] == "available",
            "Tool return state failed",
        )
        require(not module.database.get_open_alarms(), "Unexpected tool alarm")
    response = client.post("/api/kiosk/end", json={}, headers=headers)
    require(response.status_code == 200, "CSRF-protected session end failed")
    state = module.kiosk.state_dict()
    require(state["state"] == "summary", "Session summary missing")
    require(len(state.get("borrowed", [])) == 1, "Borrow summary missing")
    require(len(state.get("returned", [])) == 1, "Return summary missing")
    print(
        "PASS: mock UHF rounds -> borrow -> return -> protected session end", flush=True
    )


def main() -> int:
    # Override before importing config/app, and skip .env entirely. A temporary
    # cwd also keeps the app's unused upload directory outside the deployment.
    os.environ.update(
        DATABASE_URL="sqlite://",
        NFC_READER_ENABLED="true",
        RFID_READER_ENABLED="false",
        CAMERA_ENABLED="false",
        RFID_MISSING_AFTER="0.5",
        FLASK_ENV="development",
        SECRET_KEY="synthetic-nfc-acceptance-key",
        ADMIN_PIN_HASH="",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)  # never expose a hardware UID in error logs
    previous_cwd = os.getcwd()
    module = None
    try:
        with tempfile.TemporaryDirectory(prefix="tpt-nfc-acceptance-") as temporary:
            os.chdir(temporary)
            try:
                with patch("dotenv.load_dotenv", return_value=False):
                    import app as module

                exercise(module)
            finally:
                if module is not None:
                    module.cleanup()
                    atexit.unregister(module.cleanup)
                    with module.app.app_context():
                        module.db.session.remove()
                        module.db.engine.dispose()
                os.chdir(previous_cwd)
    except AcceptanceFailure as error:
        print("FAIL: {}".format(error), flush=True)
        return 1
    except KeyboardInterrupt:
        print("STOPPED: acceptance interrupted", flush=True)
        return 130
    except Exception as error:  # CLI boundary; never print driver or DB payloads
        print(
            "FAIL: unexpected {} (details suppressed)".format(type(error).__name__),
            flush=True,
        )
        return 1
    finally:
        logging.disable(previous_logging)
    print(
        "PASS: acceptance complete; RAM database disposed; readers stopped", flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

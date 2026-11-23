#!/usr/bin/env python3
"""Build a static UI demo (no backend) into demo/dist for Vercel or any host.

Runs the real app with mocks and an in-memory database seeded with the
sample data from seed_database.py, renders every page, records the JSON the
pages fetch plus a walk through the kiosk states, and writes it all as static
files. demo/demo.js replaces fetch() in the browser with those recordings.

    .venv/bin/python scripts/build_demo.py
    npx vercel deploy demo/dist --prod
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "demo" / "dist"
sys.path.insert(0, str(ROOT))

# Set before `app` is imported: config reads env at import (dotenv never overrides).
os.environ.update(
    DATABASE_URL="sqlite://",
    FLASK_ENV="development",
    SECRET_KEY="demo",
    RFID_READER_ENABLED="false",
    NFC_READER_ENABLED="false",
    CAMERA_ENABLED="false",
    LOAN_REMINDERS_ENABLED="false",
    FACE_LOGIN_ENABLED="false",
    SECURITY_STORAGE_DIR=tempfile.mkdtemp(prefix="tpt-demo-"),
)

import app as app_module  # noqa: E402
import seed_database  # noqa: E402
from utils import Tool, db  # noqa: E402

PAGES = [
    "/kiosk",
    "/register",
    "/monitor",
    "/admin",
    "/admin/monitor",
    "/admin/input_tool",
    "/admin/students",
    "/admin/security",
    "/admin/history",
    "/admin/register",
    "/admin/nfc-test",
]

# GET endpoints the page scripts call; demo.js looks them up by path.
APIS = [
    "/api/nfc/registration",
    "/api/admin/cards",
    "/api/admin/faces",
    "/api/admin/login_events",
    "/api/admin/transactions",
    "/api/admin/emails",
    "/api/admin/face/status",
    "/api/admin/kiosk/alerts",
    "/api/admin/tool_types",
    "/api/admin/tools_status",
    "/api/admin/security",
    "/api/admin/students",
    "/api/presence",
    "/api/devices/status",
    "/api/register/photo/status",
    "/api/register/nim?nim=13329999",  # unknown NIM: the "new student" path
]

DEMO_TAGS = '<script src="/demo/data.js"></script><script src="/demo/demo.js"></script>'
UI_TAG = '<script src="/static/js/ui.js"></script>'


def tool(name: str) -> Tool:
    return Tool.query.filter_by(name=name).one()


def set_presence(name: str, presence: str) -> None:
    tool(name).presence = presence
    db.session.commit()


def write_page(path: str, html: str) -> None:
    assert UI_TAG in html, f"{path}: ui.js tag not found, demo.js would not load"
    out = DIST / path.lstrip("/") / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html.replace(UI_TAG, DEMO_TAGS + UI_TAG), encoding="utf-8")


def get_json(client, url: str):
    res = client.get(url)
    assert res.is_json, f"{url}: HTTP {res.status_code}, not JSON"
    return res.get_json()


def main() -> None:
    flask_app = app_module.app
    flask_app.config["WTF_CSRF_ENABLED"] = False
    app_module.limiter.enabled = False
    app_module.presence_service.stop()  # the mock reader's empty field must not mark tools missing
    database, kiosk = app_module.database, app_module.kiosk
    client = flask_app.test_client()

    DIST.mkdir(parents=True, exist_ok=True)
    for old in DIST.iterdir():  # keep .vercel: the CLI's link to the Vercel project
        if old.name != ".vercel":
            shutil.rmtree(old) if old.is_dir() else old.unlink()

    with flask_app.app_context():
        db.create_all()
        seed_database.seed_students(flask_app, database)
        seed_database.seed_tools(flask_app, database)
        for t in Tool.query.all():
            t.presence = "present"
        db.session.commit()
        ahmad, siti, budi = (
            database.get_student_by_nim(s["nim"]) for s in seed_database.STUDENTS
        )

        # Some history: one finished loan, one still open.
        database.borrow_tool_atomic(budi["student_id"], str(tool("Obeng Set #1").id))
        database.close_borrow(tool("Obeng Set #1").id, int(budi["student_id"]), True)
        database.borrow_tool_atomic(
            siti["student_id"], str(tool("Solder Station #2").id)
        )
        set_presence("Solder Station #2", "missing")

        # Walk through the kiosk states the demo panel switches between.
        states = {}

        def snap(name: str) -> None:
            states[name] = get_json(client, "/api/kiosk/state")

        snap("idle")
        kiosk.reject_card()
        snap("unknown_card")
        kiosk._to_idle()
        kiosk.start_session(ahmad)
        snap("session")
        bor = tool("Bor Listrik #1")
        kiosk.on_tool_left({"id": bor.id, "status": "available"})
        set_presence("Bor Listrik #1", "missing")
        snap("borrowed")
        kiosk.end()
        snap("summary")
        kiosk._to_idle()
        snap("after")
        database.create_alarm(tool("Multimeter Digital #1").id)
        set_presence("Multimeter Digital #1", "missing")
        snap("alarm")

        write_page("/admin/login", client.get("/admin/login").get_data(as_text=True))
        with client.session_transaction() as s:
            s["admin_logged_in"] = True
        for page in PAGES:
            res = client.get(page)
            assert res.status_code == 200, f"{page}: HTTP {res.status_code}"
            write_page(page, res.get_data(as_text=True))
        apis = {url.split("?")[0]: get_json(client, url) for url in APIS}

    for name in ("manifest.webmanifest", "sw.js"):
        (DIST / name).write_bytes(client.get("/" + name).get_data())
    shutil.copytree(
        ROOT / "static", DIST / "static", ignore=shutil.ignore_patterns("*.map")
    )
    (DIST / "demo").mkdir()
    shutil.copy(ROOT / "demo" / "demo.js", DIST / "demo" / "demo.js")
    data = json.dumps({"api": apis, "kiosk": states}, ensure_ascii=False)
    (DIST / "demo" / "data.js").write_text(
        f"window.DEMO_DATA = {data};\n", encoding="utf-8"
    )
    shutil.copy(ROOT / "demo" / "vercel.json", DIST / "vercel.json")
    print(
        f"Demo built: {DIST} ({len(PAGES) + 1} pages, {len(apis)} APIs, {len(states)} kiosk states)"
    )


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)  # the app's mock hardware threads are not daemons everywhere

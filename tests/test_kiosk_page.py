import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
EXTERNAL = re.compile(
    r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""",
    re.I,
)


def test_kiosk_page_renders_without_external_assets(client):
    resp = client.get("/kiosk")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert not EXTERNAL.search(html)
    assert "tailwind" not in html.lower()


def test_kiosk_static_assets_are_local():
    for rel in (
        "css/tokens.css",
        "css/ui.css",
        "css/kiosk.css",
        "js/ui.js",
        "js/kiosk.js",
    ):
        text = (STATIC / rel).read_text(encoding="utf-8")
        assert not EXTERNAL.search(text), rel
        assert "http://" not in text and "https://" not in text, rel
    for weight in ("Regular", "Semibold", "Bold"):
        assert (STATIC / "fonts" / f"SourceSans3-{weight}.woff2").stat().st_size > 10000


def test_tool_type_photo_and_board_url(client, database):
    from utils import db
    from utils.models import ToolType

    tt = database.create_tool_type("Bor Listrik")
    database.create_tool(
        {
            "name": "Bor Listrik #1",
            "rfid_uid": "EPC-1",
            "type_id": int(tt["type_id"]),
            "unit_no": 1,
        }
    )
    url = f"/api/tool_type/{tt['type_id']}/photo"
    assert client.get(url).status_code == 404
    assert client.get("/api/kiosk/state").get_json()["board"][0]["photo_url"] == ""

    row = db.session.get(ToolType, int(tt["type_id"]))
    row.photo_data = b"\x89PNG fake"
    row.photo_mimetype = "image/png"
    db.session.commit()

    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == b"\x89PNG fake"
    assert client.get("/api/kiosk/state").get_json()["board"][0]["photo_url"] == url
    assert client.get("/api/tool_type/9999/photo").status_code == 404


def test_devices_status(client):
    data = client.get("/api/devices/status").get_json()
    assert data["success"] is True
    assert data["reader"]["mode"] == "mock"
    assert data["camera"]["enabled"] is False


def test_admin_alert_poll_is_authorized_and_omits_full_board(client, admin_client):
    from tests.conftest import TEST_PIN

    assert client.get("/api/admin/kiosk/alerts").status_code == 401
    assert (
        admin_client.post("/api/admin/login", json={"pin": TEST_PIN}).status_code == 200
    )
    response = admin_client.get("/api/admin/kiosk/alerts")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["alarms"] == []
    assert payload["unverified_returns"] == []
    assert "board" not in payload


def test_kiosk_state_gives_alarm_age_and_overlay_timeout(client, database, tool):
    from datetime import datetime, timedelta

    from utils.models import AlarmEvent, db

    alarm = database.create_alarm(int(tool["tool_id"]))
    row = db.session.get(AlarmEvent, int(alarm["alarm_id"]))
    row.started_at = datetime.utcnow() - timedelta(seconds=45)
    db.session.commit()

    data = client.get("/api/kiosk/state").get_json()
    assert data["alarm_overlay_seconds"] == 30
    [shown] = data["alarms"]
    assert shown["alarm_id"] == alarm["alarm_id"]
    assert 44 <= shown["age_seconds"] < 60
    # The overlay timeout only hides it on the kiosk; the alarm stays open.
    assert database.open_alarm_for_tool(int(tool["tool_id"])) is not None


def test_kiosk_page_has_alarm_close_button_and_logos(client):
    html = client.get("/kiosk").get_data(as_text=True)
    assert 'id="alarm-close-btn"' in html
    assert "assets/Logo_Teknik_Fisika.jpg" in html
    assert "assets/Logo_Institut_Teknologi_Bandung.png" in html

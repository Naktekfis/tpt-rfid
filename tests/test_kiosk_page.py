import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""", re.I)


def test_kiosk_page_renders_without_external_assets(client):
    resp = client.get("/kiosk")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert not EXTERNAL.search(html)
    assert "tailwind" not in html.lower()


def test_kiosk_static_assets_are_local():
    for rel in ("css/tokens.css", "css/ui.css", "css/kiosk.css", "js/ui.js", "js/kiosk.js"):
        text = (STATIC / rel).read_text(encoding="utf-8")
        assert not EXTERNAL.search(text), rel
        assert "http://" not in text and "https://" not in text, rel
    for weight in ("Regular", "Medium", "SemiBold", "Bold"):
        assert (STATIC / "fonts" / f"IBMPlexSans-{weight}.woff2").stat().st_size > 10000
    for weight in ("Regular", "Medium"):
        assert (STATIC / "fonts" / f"IBMPlexMono-{weight}.woff2").stat().st_size > 10000


def test_devices_status(client):
    data = client.get("/api/devices/status").get_json()
    assert data["success"] is True
    assert data["reader"]["mode"] == "mock"
    assert data["camera"]["enabled"] is False

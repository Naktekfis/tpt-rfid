import re

import pytest

from tests.conftest import TEST_PIN

EXTERNAL = re.compile(
    r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""",
    re.I,
)

PUBLIC = [
    "/register",
    "/daftar",
    "/monitor",
    "/admin/login",
    "/kiosk",
]
ADMIN = [
    "/admin",
    "/admin/monitor",
    "/admin/students",
    "/admin/security",
    "/admin/input_tool",
    "/admin/history",
]


@pytest.mark.parametrize("path", PUBLIC)
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_admin_page_redirects_without_session(client):
    resp = client.get("/admin", headers={"Accept": "text/html"})
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


@pytest.mark.parametrize("path", ["/", "/mahasiswa"])
def test_old_menus_lead_to_kiosk(client, path):
    resp = client.get(path, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.request.path == "/kiosk"


def test_logout_returns_to_the_kiosk_on_the_kiosk_screen(admin_client):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    page = admin_client.get("/admin/monitor").get_data(as_text=True)
    assert 'class="switcher"' in page and "/admin/logout" in page
    resp = admin_client.get("/admin/logout")
    assert resp.headers["Location"].endswith("/kiosk")


def test_logout_elsewhere_returns_to_admin_login(admin_client):
    remote = {"REMOTE_ADDR": "10.42.0.1"}
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN}, environ_base=remote)
    resp = admin_client.get("/admin/logout", environ_base=remote)
    assert resp.headers["Location"].endswith("/admin/login")


def test_scan_redirects_to_kiosk(client):
    resp = client.get("/scan")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/kiosk")


def test_daftar_is_the_register_page(client):
    a = client.get("/daftar").get_data(as_text=True)
    b = client.get("/register").get_data(as_text=True)
    assert 'id="reg-form"' in a and 'id="reg-form"' in b
    assert "KTM (Kartu Tanda Mahasiswa)" in a
    assert "/api/face/" not in a


def test_register_admin_mode_needs_session(client, admin_client, student):
    sid = student["student_id"]
    html = client.get(f"/daftar?student_id={sid}").get_data(as_text=True)
    assert "Hubungkan KTM" not in html
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    html = admin_client.get(f"/daftar?student_id={sid}").get_data(as_text=True)
    assert "Hubungkan KTM" in html
    assert student["nim"] in html


def _assert_local(html, path):
    assert 'name="csrf-token"' in html, path
    assert not EXTERNAL.search(html), path
    lower = html.lower()
    assert "tailwind" not in lower, path
    assert "googleapis" not in lower, path


@pytest.mark.parametrize("path", PUBLIC)
def test_public_pages_have_no_external_assets(client, path):
    _assert_local(client.get(path).get_data(as_text=True), path)


def test_admin_pages_have_no_external_assets(admin_client):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    for path in ADMIN:
        resp = admin_client.get(path)
        assert resp.status_code == 200, path
        _assert_local(resp.get_data(as_text=True), path)


def test_cv_pages_have_no_external_assets(app, client):
    if "cv" not in app.blueprints:
        pytest.skip("CV benchmark blueprint not registered (optional deps)")
    for path in ("/cv/", "/cv/live", "/cv/face-rec"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        _assert_local(resp.get_data(as_text=True), path)


def test_static_css_js_are_local():
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "static"
    for f in list(static.glob("css/*.css")) + list(static.glob("js/*.js")):
        text = f.read_text(encoding="utf-8")
        assert not EXTERNAL.search(text), f.name
        assert "http://" not in text and "https://" not in text, f.name
        assert "tailwind" not in text.lower(), f.name


def test_admin_app_is_installable(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.mimetype == "application/manifest+json"
    data = manifest.get_json(force=True)
    assert data["start_url"] == "/admin" and data["display"] == "standalone"
    for icon in data["icons"]:
        assert client.get(icon["src"]).status_code == 200
    worker = client.get("/sw.js")
    assert worker.status_code == 200 and worker.mimetype == "text/javascript"
    page = client.get("/admin/login").get_data(as_text=True)
    assert 'rel="manifest"' in page and "serviceWorker" in page
    assert client.get("/favicon.ico").status_code == 200

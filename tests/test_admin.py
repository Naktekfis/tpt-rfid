from tests.conftest import TEST_PIN


def test_login_wrong_pin(client):
    resp = client.post("/api/admin/login", json={"pin": "000000"})
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_login_invalid_payload(client):
    resp = client.post("/api/admin/login", data="nope")
    assert resp.status_code == 400


def test_admin_api_requires_session(client):
    resp = client.get("/api/admin/tools_status")
    assert resp.status_code == 401
    # NOTE: a browser-style request (accepts HTML) is redirected instead.
    resp = client.get("/api/admin/tools_status", headers={"Accept": "text/html"})
    assert resp.status_code == 302


def test_login_success_grants_access(admin_client, tool):
    resp = admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    resp = admin_client.get("/api/admin/tools_status")
    assert resp.status_code == 200
    assert len(resp.get_json()["tools"]) == 1
    assert admin_client.get("/admin").status_code == 200
    # Logged-in users hitting the login page are redirected to /admin.
    assert admin_client.get("/admin/login").status_code == 302


def test_logout_clears_session(admin_client):
    admin_client.post("/api/admin/login", json={"pin": TEST_PIN})
    assert admin_client.get("/admin/logout").status_code == 302
    assert admin_client.get("/admin").status_code == 401

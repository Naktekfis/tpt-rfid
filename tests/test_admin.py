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


def test_login_refused_when_pin_not_configured(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "ADMIN_PIN_HASH", None)
    resp = client.post("/api/admin/login", json={"pin": "whatever"})
    assert resp.status_code == 503


def test_login_non_string_pin(admin_client):
    resp = admin_client.post("/api/admin/login", json={"pin": 424242})
    assert resp.status_code == 401


def test_set_env_value_replaces_and_quotes(tmp_path):
    import sys
    from pathlib import Path

    from dotenv import dotenv_values

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from set_admin_pin import set_env_value

    from werkzeug.security import check_password_hash, generate_password_hash

    h = generate_password_hash("424242")
    text = "SECRET_KEY=x\nADMIN_PIN_HASH=old\nADMIN_PIN_HASH=older\n"
    env = tmp_path / ".env"
    env.write_text(set_env_value(text, "ADMIN_PIN_HASH", h))
    values = dotenv_values(env)
    assert values["SECRET_KEY"] == "x"
    assert check_password_hash(values["ADMIN_PIN_HASH"], "424242")
    assert env.read_text().count("ADMIN_PIN_HASH") == 1

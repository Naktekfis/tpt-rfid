import pytest

import app as app_module


@pytest.fixture()
def limited_client(client):
    app_module.limiter.enabled = True
    app_module.limiter.reset()
    yield client
    app_module.limiter.reset()
    app_module.limiter.enabled = False


def test_polling_endpoints_are_not_limited(limited_client):
    """The scan page polls /api/check_rfid every second from one IP."""
    for _ in range(120):
        assert limited_client.get("/api/check_rfid").status_code == 200


def test_admin_login_still_limited(limited_client):
    codes = [
        limited_client.post("/api/admin/login", json={"pin": "000000"}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429

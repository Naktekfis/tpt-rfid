import pytest


@pytest.mark.parametrize("path", ["/", "/register", "/scan", "/monitor", "/admin/login"])
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_admin_page_redirects_without_session(client):
    resp = client.get("/admin", headers={"Accept": "text/html"})
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]

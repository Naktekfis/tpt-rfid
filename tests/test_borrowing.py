def _borrow(client, student, tool):
    return client.post(
        "/api/borrow_tool",
        json={"student_id": student["student_id"], "tool_id": tool["tool_id"]},
    )


def _return(client, student, tool):
    return client.post(
        "/api/return_tool",
        json={"student_id": student["student_id"], "tool_id": tool["tool_id"]},
    )


def test_scan_tool(client, tool):
    resp = client.post("/api/scan_tool", json={"rfid_uid": "TOOL-001"})
    assert resp.status_code == 200
    assert resp.get_json()["tool"]["name"] == "Obeng"


def test_scan_tool_unknown_and_empty(client):
    assert client.post("/api/scan_tool", json={"rfid_uid": "nope"}).status_code == 404
    assert client.post("/api/scan_tool", json={"rfid_uid": ""}).status_code == 400


def test_borrow_and_return(client, student, tool):
    resp = _borrow(client, student, tool)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    status = client.get("/api/tools_status").get_json()
    assert status["success"] is True
    assert len(status["tools"]) == 1
    assert status["tools"][0]["status"] == "borrowed"

    resp = _return(client, student, tool)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    status = client.get("/api/tools_status").get_json()
    assert status["tools"][0]["status"] == "available"


def test_double_borrow_rejected(client, student, tool):
    assert _borrow(client, student, tool).status_code == 200
    resp = _borrow(client, student, tool)
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_return_without_borrow_rejected(client, student, tool):
    resp = _return(client, student, tool)
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_borrow_validation(client, student, tool):
    resp = client.post("/api/borrow_tool", json={"student_id": student["student_id"]})
    assert resp.status_code == 400
    resp = client.post("/api/borrow_tool", json={"student_id": "abc", "tool_id": "x"})
    assert resp.status_code == 400
    resp = client.post("/api/return_tool", json={"student_id": "abc", "tool_id": "x"})
    assert resp.status_code == 400


def test_borrow_unknown_ids(client):
    resp = client.post("/api/borrow_tool", json={"student_id": 999, "tool_id": 999})
    assert resp.status_code == 400


def test_transactions_listing(client, student, tool):
    assert client.get("/api/transactions").get_json() == {
        "success": True,
        "transactions": [],
    }
    _borrow(client, student, tool)
    body = client.get("/api/transactions?limit=5").get_json()
    assert body["success"] is True
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["status"] == "borrowed"
    assert body["transactions"][0]["tool_name"] == "Obeng"


def test_tools_status_empty(client):
    assert client.get("/api/tools_status").get_json() == {"success": True, "tools": []}

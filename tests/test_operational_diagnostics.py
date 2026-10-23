"""Identifier-free diagnostics use the existing admin boundary."""

from __future__ import annotations


def test_uhf_diagnostics_require_admin_and_report_effective_threshold(
    client, monkeypatch
):
    import app as app_module

    monkeypatch.setattr(app_module.presence_service.monitor, "missing_after", 4.25)
    url = "/api/admin/diagnostics/uhf"
    assert client.get(url).status_code == 401
    with client.session_transaction() as browser_session:
        browser_session["admin_logged_in"] = True
    result = client.get(url).get_json()
    assert result["success"] is True
    assert result["reader"] == {"mode": "mock"}
    assert result["presence"]["missing_after_s"] == 4.25
    assert "epcs" not in result["presence"]
    assert result["loss"]["missing_events_total"] == 0
    assert result["loss"]["alarm_beeps_enqueued_total"] == 0

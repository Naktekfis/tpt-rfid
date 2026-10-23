"""
Kiosk API: one polled state (session state + tool board + alarms +
unverified returns), tool type photos for the board, end/cancel a session,
admin verification of returns.

Kiosk, database and the admin decorator are passed in by app.py so this
module does not import app. Not CSRF-exempt: the UI must send the token.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify


def create_kiosk_blueprint(database, kiosk, admin_required) -> Blueprint:
    bp = Blueprint("kiosk", __name__)

    @bp.route("/api/kiosk/state", methods=["GET"])
    def api_kiosk_state():
        return jsonify(
            {
                "success": True,
                **kiosk.state_dict(),
                "board": database.get_board(),
                "alarms": database.get_open_alarms(),
                "unverified_returns": database.get_unverified_returns(),
            }
        )

    @bp.route("/api/admin/kiosk/alerts", methods=["GET"])
    @admin_required
    def api_admin_kiosk_alerts():
        """Small admin poll for alarms/returns; avoids rebuilding the full board."""
        return jsonify(
            {
                "success": True,
                "alarms": database.get_open_alarms(),
                "unverified_returns": database.get_unverified_returns(),
            }
        )

    @bp.route("/api/tool_type/<int:type_id>/photo", methods=["GET"])
    def api_tool_type_photo(type_id):
        result = database.get_tool_type_photo(type_id)
        if result is None:
            return jsonify({"success": False, "error": "Foto tidak ditemukan"}), 404
        photo_data, mimetype = result
        resp = Response(photo_data, mimetype=mimetype or "image/jpeg")
        resp.cache_control.max_age = 300
        return resp

    @bp.route("/api/kiosk/end", methods=["POST"])
    def api_kiosk_end():
        if kiosk.end():
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Tidak ada sesi aktif"}), 409

    @bp.route("/api/kiosk/cancel", methods=["POST"])
    def api_kiosk_cancel():
        result = kiosk.cancel()
        if result == "ok":
            return jsonify({"success": True})
        error = (
            "Tidak ada sesi aktif"
            if result == "no_session"
            else "Sesi sudah mencatat alat, tidak bisa dibatalkan"
        )
        return jsonify({"success": False, "error": error}), 409

    @bp.route(
        "/api/admin/transactions/<int:transaction_id>/verify_return", methods=["POST"]
    )
    @admin_required
    def api_verify_return(transaction_id):
        if database.verify_return(transaction_id):
            return jsonify({"success": True})
        return (
            jsonify({"success": False, "error": "Pengembalian tidak ditemukan"}),
            404,
        )

    return bp

"""
Tool presence API: who is in the reader field, open alarms, unknown tags.

The service and the admin decorator are passed in by app.py so this module
does not import app.
"""

from __future__ import annotations

from flask import Blueprint, jsonify


def create_presence_blueprint(database, service, admin_required) -> Blueprint:
    bp = Blueprint("presence", __name__)

    @bp.route("/api/presence", methods=["GET"])
    def api_presence():
        return jsonify(
            {
                "success": True,
                "tools": database.get_tools_presence(),
                "alarms": database.get_open_alarms(),
                "unknown_epcs": service.unknown_epcs(),
            }
        )

    @bp.route("/api/alarms/<int:alarm_id>/ack", methods=["POST"])
    @admin_required
    def api_ack_alarm(alarm_id):
        if service.acknowledge(alarm_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Alarm tidak ditemukan"}), 404

    return bp

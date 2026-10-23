"""Aggregate timing diagnostics without card, tag or student identifiers."""

from __future__ import annotations

from flask import Blueprint, jsonify


def create_diagnostics_blueprint(reader, presence_service, admin_required):
    bp = Blueprint("diagnostics", __name__)

    @bp.route("/api/admin/diagnostics/uhf")
    @admin_required
    def uhf_diagnostics():
        diagnostics = getattr(reader, "diagnostics", None)
        return jsonify(
            success=True,
            reader=diagnostics() if diagnostics else {"mode": reader.mode},
            presence=presence_service.monitor.diagnostics(),
            loss=presence_service.diagnostics()
            if getattr(presence_service, "diagnostics", None)
            else {},
            persistence_interval_seconds=10.0,
            kiosk_poll_seconds=0.5,
        )

    return bp

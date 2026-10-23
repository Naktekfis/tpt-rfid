"""NFC capture API; UIDs stay on the server and POSTs retain CSRF protection."""

from __future__ import annotations

import secrets

from flask import Blueprint, jsonify, request, session

from utils.nfc_service import NFCCaptureError


def capture_owner():
    if "nfc_owner" not in session:
        session["nfc_owner"] = secrets.token_urlsafe(24)
    return session["nfc_owner"]


def create_nfc_blueprint(service, database, admin_required):
    bp = Blueprint("nfc", __name__)

    @bp.route("/api/nfc/registration/start", methods=["POST"])
    def start():
        try:
            token = service.start(capture_owner())
            return jsonify(success=True, token=token)
        except NFCCaptureError as exc:
            return jsonify(success=False, error=str(exc)), 409

    @bp.route("/api/nfc/registration", methods=["GET"])
    def status():
        return jsonify(
            success=True,
            ready=service.ready(capture_owner()),
            connected=service.reader.status().get("connected", False),
        )

    @bp.route("/api/nfc/registration/cancel", methods=["POST"])
    def cancel():
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            service.cancel(capture_owner(), str(data.get("nfc_token", "")))
        return jsonify(success=True)

    @bp.route("/api/admin/students/<int:student_id>/nfc", methods=["POST"])
    @admin_required
    def bind(student_id):
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(success=False, error="Payload tidak valid"), 400
        try:
            service.submit(
                capture_owner(),
                str(data.get("nfc_token", "")),
                lambda uid: database.bind_student_nfc(student_id, uid),
            )
            return jsonify(success=True)
        except (NFCCaptureError, ValueError) as exc:
            return jsonify(success=False, error=str(exc)), 409

    return bp

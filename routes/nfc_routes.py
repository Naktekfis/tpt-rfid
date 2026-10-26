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
            rejected=service.rejection(capture_owner()),
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
                lambda uid: database.bind_student_nfc(student_id, uid, service.policy),
            )
            return jsonify(success=True)
        except (NFCCaptureError, ValueError) as exc:
            return jsonify(success=False, error=str(exc)), 409

    @bp.route("/api/admin/cards", methods=["GET"])
    @admin_required
    def list_cards():
        return jsonify(
            success=True,
            can_hash=service.policy.can_hash,
            cards=database.list_card_exceptions(),
        )

    @bp.route("/api/admin/cards/start", methods=["POST"])
    @admin_required
    def start_card():
        try:
            token = service.start(capture_owner(), any_card=True)
            return jsonify(success=True, token=token)
        except NFCCaptureError as exc:
            return jsonify(success=False, error=str(exc)), 409

    @bp.route("/api/admin/cards", methods=["POST"])
    @admin_required
    def add_card():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(success=False, error="Payload tidak valid"), 400
        kind = "other" if data.get("kind") == "other" else "ktm"
        nim = str(data.get("nim", "")).strip()
        policy = service.policy
        if not policy.can_hash:
            return jsonify(
                success=False,
                error="NFC_POLICY_PEPPER belum diatur di .env; jalankan scripts/set_special_card.py",
            ), 409
        if kind == "other" and not nim.isdigit():
            return jsonify(success=False, error="Isi NIM pemilik kartu (angka)"), 400

        def save(uid):
            database.add_card_exception(
                policy.digest("uid", uid),
                kind,
                policy.digest("nim", nim) if kind == "other" else "",
            )

        try:
            service.submit(capture_owner(), str(data.get("nfc_token", "")), save)
            return jsonify(success=True)
        except (NFCCaptureError, ValueError) as exc:
            return jsonify(success=False, error=str(exc)), 409

    @bp.route("/api/admin/cards/<int:exception_id>/delete", methods=["POST"])
    @admin_required
    def delete_card(exception_id):
        if not database.delete_card_exception(exception_id):
            return jsonify(success=False, error="Kartu tidak ditemukan"), 404
        return jsonify(success=True)

    return bp

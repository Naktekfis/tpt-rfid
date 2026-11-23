"""NFC capture API; UIDs stay on the server and POSTs retain CSRF protection."""

from __future__ import annotations

import secrets

from flask import Blueprint, jsonify, request, session

from utils.nfc_reader import normalize_uid
from utils.nfc_service import NFCCaptureError


def capture_owner():
    if "nfc_owner" not in session:
        session["nfc_owner"] = secrets.token_urlsafe(24)
    return session["nfc_owner"]


PEPPER_MISSING = (
    "NFC_POLICY_PEPPER belum diatur di .env; jalankan scripts/set_special_card.py"
)


def save_card_exception(database, policy, uid, kind, nim):
    """Let this card past the KTM chip check; kind "other" ties it to one NIM."""
    database.add_card_exception(
        policy.digest("uid", uid),
        kind,
        policy.digest("nim", nim) if kind == "other" else "",
    )


def create_nfc_blueprint(service, database, admin_required, limiter):
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
        # Optional card exception saved with the binding (admin registration page).
        kind = data.get("card_exception") or ""
        if kind not in ("", "ktm", "other"):
            return jsonify(success=False, error="Jenis kartu tidak valid"), 400
        policy = service.policy
        if kind and not policy.can_hash:
            return jsonify(success=False, error=PEPPER_MISSING), 409

        def bind_card(uid):
            if kind and not policy.is_exempt(uid):
                student = database.get_student_by_id(student_id)
                if student is None:
                    raise ValueError("Mahasiswa tidak ditemukan")
                save_card_exception(database, policy, uid, kind, student["nim"])
            database.bind_student_nfc(student_id, uid, policy)

        try:
            service.submit(
                capture_owner(), str(data.get("nfc_token", "")), bind_card, bind=True
            )
            return jsonify(success=True)
        except (NFCCaptureError, ValueError) as exc:
            return jsonify(success=False, error=str(exc)), 409

    @bp.route("/api/admin/nfc/phone-capture", methods=["POST"])
    @limiter.limit("10 per minute")
    @admin_required
    def phone_capture():
        """A card an admin read with a phone (Web NFC serialNumber, "ff:4e:..").
        Same capture token as the reader; the chip is learnt on the first tap."""
        data = request.get_json(silent=True) or {}
        raw = data.get("uid") if isinstance(data, dict) else None
        try:
            if not isinstance(raw, str):
                raise ValueError
            uid = normalize_uid(raw.replace(":", ""))
        except ValueError:
            return jsonify(success=False, error="Nomor kartu tidak valid"), 400
        if database.get_student_by_nfc(uid):
            return jsonify(success=False, error="KTM sudah terdaftar"), 409
        return jsonify(success=True, token=service.start_phone(capture_owner(), uid))

    @bp.route("/api/admin/students/<int:student_id>/nfc/reset", methods=["POST"])
    @admin_required
    def reset_profile(student_id):
        """Reset sidik kartu: the next kiosk tap learns the chip again."""
        if not database.reset_nfc_profile(student_id):
            return jsonify(success=False, error="Mahasiswa belum punya KTM"), 404
        return jsonify(success=True)

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
            return jsonify(success=False, error=PEPPER_MISSING), 409
        if kind == "other" and not nim.isdigit():
            return jsonify(success=False, error="Isi NIM pemilik kartu (angka)"), 400

        def save(uid):
            save_card_exception(database, policy, uid, kind, nim)

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

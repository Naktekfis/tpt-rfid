"""Admin face login, face enrolment and the admin login log (utils/admin_face.py).

Face login and enrolment only run for requests from the kiosk itself
(loopback): the camera is the Jetson's, and a remote browser must not be able
to start it. The browser that started a login attempt gets the session when it
polls the passed attempt; nobody else can.
"""

from __future__ import annotations

import time

from flask import Blueprint, Response, jsonify, request, session

from utils.admin_face import (
    ENROLL,
    LOGIN,
    FaceLocked,
    FaceUnavailable,
    delete_admin_face,
    list_admin_faces,
)
from utils.helpers import utc_to_wib
from utils.models import AdminLoginEvent

LOCAL_ADDRS = ("127.0.0.1", "::1")


def _is_local() -> bool:
    # Valid only while gunicorn faces clients directly (deploy/jetson binds it
    # without a proxy). A reverse proxy or an `ssh -L` tunnel would make every
    # request look local: then trust a proxy header set by the proxy instead.
    return request.remote_addr in LOCAL_ADDRS


def _error(message: str, status: int, **extra):
    return jsonify({"success": False, "error": message, **extra}), status


def create_admin_face_blueprint(face_auth, admin_required, limiter, session_seconds: int = 900):
    bp = Blueprint("admin_face", __name__)

    def start(mode, name=None):
        if not _is_local():
            return _error("Login wajah hanya bisa di layar kiosk.", 403)
        try:
            attempt = face_auth.start(mode, name)
        except FaceUnavailable as exc:
            return _error(str(exc), 503)
        except FaceLocked:
            return _error(
                "Terlalu banyak percobaan gagal. Gunakan PIN.",
                429,
                locked_seconds=int(face_auth.locked_for()),
            )
        session["face_attempt"] = attempt.id
        return jsonify({"success": True, **attempt.to_dict()})

    @bp.route("/api/admin/face/status", methods=["GET"])
    def face_status():
        return jsonify(
            {
                "success": True,
                "available": face_auth.available,
                "reason": face_auth.unavailable,
                "local": _is_local(),
                "locked_seconds": int(face_auth.locked_for()),
            }
        )

    @bp.route("/api/admin/face/login/start", methods=["POST"])
    @limiter.limit("10 per minute")
    def face_login_start():
        return start(LOGIN)

    @bp.route("/api/admin/faces/enroll/start", methods=["POST"])
    @admin_required
    def face_enroll_start():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        name = name.strip() if isinstance(name, str) else ""
        if not 1 <= len(name) <= 80:
            return _error("Isi nama admin (maksimal 80 karakter).", 400)
        return start(ENROLL, name)

    @bp.route("/api/admin/face/attempt", methods=["GET"])
    def face_attempt():
        attempt_id = session.get("face_attempt")
        attempt = face_auth.get(attempt_id)
        if attempt is None:
            return _error("Tidak ada percobaan aktif.", 404)
        if attempt.mode == ENROLL and not session.get("admin_logged_in"):
            return _error("Unauthorized", 401)
        name = face_auth.consume(attempt_id)
        if name:
            # The kiosk browser is shared and never closes: a face login ends
            # after FACE_SESSION_MINUTES (enforced in app.py), not 8 hours.
            session["admin_logged_in"] = True
            session["admin_name"] = name
            session["admin_until"] = time.time() + session_seconds
            session.permanent = False
        return jsonify({"success": True, **attempt.to_dict()})

    @bp.route("/api/admin/face/cancel", methods=["POST"])
    def face_cancel():
        face_auth.cancel(session.get("face_attempt"))
        return jsonify({"success": True})

    @bp.route("/api/admin/faces", methods=["GET"])
    @admin_required
    def faces_list():
        faces = [
            {**f, "created_at": utc_to_wib(f["created_at"])} for f in list_admin_faces()
        ]
        return jsonify({"success": True, "faces": faces, "local": _is_local()})

    @bp.route("/api/admin/faces/delete", methods=["POST"])
    @admin_required
    def faces_delete():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not isinstance(name, str) or not delete_admin_face(name):
            return _error("Admin tidak ditemukan.", 404)
        return jsonify({"success": True})

    @bp.route("/api/admin/login_events", methods=["GET"])
    @admin_required
    def login_events():
        rows = AdminLoginEvent.query.order_by(AdminLoginEvent.id.desc()).limit(50).all()
        return jsonify({"success": True, "events": [r.to_dict() for r in rows]})

    @bp.route("/api/admin/login_events/<int:event_id>/photo", methods=["GET"])
    @admin_required
    def login_event_photo(event_id):
        row = AdminLoginEvent.query.get(event_id)
        if row is None or row.photo is None:
            return _error("Foto tidak ada.", 404)
        return Response(row.photo, mimetype="image/jpeg")

    return bp

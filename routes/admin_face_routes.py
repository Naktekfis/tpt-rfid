"""Admin face login, face enrolment and the admin login log (utils/admin_face.py).

On the kiosk itself (loopback without a proxy header,
utils.helpers.is_kiosk_request) an attempt reads the Jetson's camera. A remote
browser (through the Cloudflare tunnel) never starts that camera: its attempt
is fed JPEG frames from the browser's own camera via /api/admin/face/frame.
The browser that started an attempt is the only one that can feed it, and it
gets the session when the passed login attempt is polled or fed.
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
from utils.helpers import is_kiosk_request, utc_to_wib
from utils.models import AdminLoginEvent


def _is_local() -> bool:
    # An `ssh -L` tunnel adds no header and would still look local: use tailscale serve.
    return is_kiosk_request(request)


MAX_FRAME_BYTES = 1_000_000  # a 640x480 JPEG is ~50 kB


def decode_jpeg(data: bytes):
    """BGR frame from JPEG bytes, or None if they are not an image."""
    import cv2  # optional dependency (requirements-cv.txt), only on the device
    import numpy as np

    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def _error(message: str, status: int, **extra):
    return jsonify({"success": False, "error": message, **extra}), status


def create_admin_face_blueprint(
    face_auth, admin_required, limiter, session_seconds: int = 900
):
    bp = Blueprint("admin_face", __name__)

    def start(mode, name=None):
        try:
            attempt = face_auth.start(mode, name, remote=not _is_local())
        except FaceUnavailable as exc:
            return _error(str(exc), 503)
        except FaceLocked:
            return _error(
                "Terlalu banyak percobaan gagal. Coba lagi dalam "
                f"{max(1, int(face_auth.locked_for()))} detik.",
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

    def own_attempt():
        """This browser's attempt, or an error response."""
        attempt = face_auth.get(session.get("face_attempt"))
        if attempt is None:
            return None, _error("Tidak ada percobaan aktif.", 404)
        if attempt.mode == ENROLL and not session.get("admin_logged_in"):
            return None, _error("Unauthorized", 401)
        return attempt, None

    @bp.route("/api/admin/face/frame", methods=["POST"])
    @limiter.limit("300 per minute")
    def face_frame():
        attempt, error = own_attempt()
        if error:
            return error
        if not attempt.remote:
            return _error("Percobaan ini memakai kamera rak peminjaman.", 409)
        if not 0 < (request.content_length or 0) <= MAX_FRAME_BYTES:
            return _error("Gambar kosong atau terlalu besar.", 400)
        frame = decode_jpeg(request.get_data(cache=False))
        if frame is None:
            return _error("Gambar tidak terbaca.", 400)
        face_auth.feed(attempt, frame)
        return reply(attempt)

    @bp.route("/api/admin/face/attempt", methods=["GET"])
    def face_attempt():
        attempt, error = own_attempt()
        if error:
            return error
        return reply(attempt)

    def reply(attempt):
        name = face_auth.consume(attempt.id)
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
            {**f, "created_at": utc_to_wib(f["created_at"])}
            for f in list_admin_faces(getattr(face_auth.engine, "name", None))
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

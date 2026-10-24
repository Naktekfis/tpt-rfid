"""Registration face photo API: a guided capture owned by this browser's
session; /api/register later takes the photo by token."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from routes.nfc_routes import capture_owner
from utils.photo_capture import PhotoCaptureError


def create_register_photo_blueprint(capture, limiter) -> Blueprint:
    bp = Blueprint("register_photo", __name__)

    def _token():
        data = request.get_json(silent=True) if request.is_json else None
        if isinstance(data, dict) and data.get("token"):
            return str(data["token"])
        return str(request.args.get("token", ""))

    @bp.route("/api/register/photo/status", methods=["GET"])
    def status():
        return jsonify(
            success=True, available=capture.available, reason=capture.unavailable
        )

    @bp.route("/api/register/photo/start", methods=["POST"])
    @limiter.limit("10 per minute")
    def start():
        try:
            c = capture.start(capture_owner())
        except PhotoCaptureError as exc:
            return jsonify(success=False, error=str(exc)), 503
        return jsonify(success=True, **c.to_dict())

    @bp.route("/api/register/photo", methods=["GET"])
    def get():
        c = capture.get(capture_owner(), _token())
        if c is None:
            return jsonify(success=False, error="Foto tidak ditemukan. Ulangi."), 404
        return jsonify(success=True, **c.to_dict())

    @bp.route("/api/register/photo/preview", methods=["GET"])
    def preview():
        jpeg = capture.preview(capture_owner(), _token())
        if jpeg is None:
            return jsonify(success=False, error="Foto tidak tersedia"), 404
        response = Response(jpeg, mimetype="image/jpeg")
        response.headers["Cache-Control"] = "no-store, private"
        return response

    @bp.route("/api/register/photo/cancel", methods=["POST"])
    def cancel():
        capture.cancel(capture_owner(), _token())
        return jsonify(success=True)

    return bp

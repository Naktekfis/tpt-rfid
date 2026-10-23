"""Admin-only security history and private camera evidence."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, send_file


def create_security_blueprint(service, database, admin_required):
    bp = Blueprint("security", __name__)

    @bp.route("/admin/security")
    @admin_required
    def page():
        return render_template("admin_security.html")

    @bp.route("/api/admin/security")
    @admin_required
    def events():
        alarms = database.get_alarm_history(limit=100)
        history = service.store.events()
        response = jsonify(success=True, condition=service.condition,
                           events=history, alarms=alarms,
                           evidence_storage_error=bool(service.storage_error))
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.route("/api/admin/security/events/<event_id>/photo")
    @admin_required
    def photo(event_id):
        path = service.store.photo_path(event_id)
        if path is None:
            return jsonify(success=False, error="Foto tidak tersedia"), 404
        response = send_file(str(path.resolve()), mimetype="image/jpeg", conditional=False)
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.route("/api/admin/security/events/<event_id>/ack", methods=["POST"])
    @admin_required
    def acknowledge(event_id):
        if not service.store.acknowledge(event_id):
            return jsonify(success=False, error="Kejadian tidak ditemukan"), 404
        return jsonify(success=True)

    return bp

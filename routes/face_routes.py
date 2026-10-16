"""
Face API: camera stream, identify, enroll, delete.

The service, camera and admin decorator are passed in by app.py so this module
does not import app. Enroll takes no admin PIN on purpose (kiosk flow, phase 4
puts the UI and its guard in front of it).
"""

from __future__ import annotations

import time

from flask import Blueprint, Response, jsonify

ENROLL_FRAMES = 8
ENROLL_INTERVAL = 0.3  # s between captured frames (~2 s total)


def create_face_blueprint(database, service, camera, admin_required) -> Blueprint:
    bp = Blueprint("face", __name__)

    @bp.route("/camera/stream", methods=["GET"])
    def camera_stream():
        if not camera.status().get("enabled"):
            return jsonify({"success": False, "error": "Kamera tidak aktif"}), 503

        def frames():
            while True:
                jpeg = camera.jpeg()
                if jpeg is None:
                    time.sleep(0.2)
                    continue
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
                time.sleep(0.1)

        return Response(
            frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    @bp.route("/api/face/identify", methods=["GET"])
    def api_face_identify():
        result = service.identify_frame(camera.read())
        return jsonify({"success": result["status"] == "ok", **result})

    @bp.route("/api/face/enroll/<int:student_id>", methods=["POST"])
    def api_face_enroll(student_id):
        frames = []
        for i in range(ENROLL_FRAMES):
            if i:
                time.sleep(ENROLL_INTERVAL)
            frame = camera.read()
            if frame is not None:
                frames.append(frame)
        result = service.enroll(student_id, frames)
        code = 404 if result["status"] == "not_found" else 200
        return jsonify({"success": result["status"] == "ok", **result}), code

    @bp.route("/api/admin/students/<int:student_id>/face/delete", methods=["POST"])
    @admin_required
    def api_face_delete(student_id):
        if service.delete(student_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Siswa tidak ditemukan"}), 404

    return bp

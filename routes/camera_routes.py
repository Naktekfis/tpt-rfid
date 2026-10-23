"""Camera stream shared by tool photography; no face dependencies."""

from __future__ import annotations

import time
from flask import Blueprint, Response, jsonify


def create_camera_blueprint(camera):
    bp = Blueprint("camera", __name__)

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
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                time.sleep(0.1)

        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return bp

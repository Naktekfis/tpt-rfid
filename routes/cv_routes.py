"""
CV Benchmark Routes — TPT-RFID
Blueprint: cv_bp  (prefix /cv)

Routes:
  GET  /cv                        → landing page (pilih Live Monitor / Face Rec)
  GET  /cv/live                   → live monitor page
  GET  /cv/face-rec               → face recognition benchmark page
  GET  /cv/stream/live            → MJPEG stream (live monitor)
  GET  /cv/stream/recognition     → MJPEG stream (recognition mode)
  GET  /cv/stats                  → JSON system stats (SSE-friendly polling)
  POST /cv/camera/open            → open camera, probe resolutions
  POST /cv/camera/close           → release camera
  POST /cv/resolution             → set resolution
  GET  /cv/resolutions            → list available + current resolution
  POST /cv/capture                → capture reference photo (face rec mode)
  POST /cv/retry                  → increment retry attempt (lower threshold)
  POST /cv/reset                  → reset recognition state
"""

import time
from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
    Response,
    stream_with_context,
)
from utils.cv_handler import (
    camera,
    get_system_stats,
    generate_live_frames,
    generate_recognition_frames,
    RESOLUTIONS,
    RESOLUTION_ORDER,
)

cv_bp = Blueprint("cv", __name__, url_prefix="/cv")


# ─── Page routes ──────────────────────────────────────────────────────────────


@cv_bp.route("/")
def cv_index():
    return render_template("cv_benchmark.html")


@cv_bp.route("/live")
def cv_live():
    return render_template("cv_live.html")


@cv_bp.route("/face-rec")
def cv_face_rec():
    return render_template("cv_face_rec.html")


# ─── MJPEG streams ────────────────────────────────────────────────────────────


@cv_bp.route("/stream/live")
def stream_live():
    if not camera.is_open():
        camera.open(0)
    return Response(
        stream_with_context(generate_live_frames(camera)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@cv_bp.route("/stream/recognition")
def stream_recognition():
    if not camera.is_open():
        camera.open(0)
    return Response(
        stream_with_context(generate_recognition_frames(camera)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ─── JSON API ─────────────────────────────────────────────────────────────────


@cv_bp.route("/stats")
def stats():
    """
    Returns current system stats + camera state.
    Poll this every 1–2 seconds from JS.
    """
    data = get_system_stats()
    data.update(
        {
            "fps": round(camera.fps, 1),
            "resolution": camera.current_res,
            "camera_open": camera.is_open(),
            # Recognition state
            "has_reference": camera.reference_encoding is not None,
            "last_match": camera.last_match,
            "last_similarity": round(camera.last_similarity * 100, 1),
            "attempt": camera.attempt_number,
            "threshold": camera.current_threshold,
            "ts": time.time(),
        }
    )
    return jsonify(data)


@cv_bp.route("/camera/open", methods=["POST"])
def camera_open():
    index = request.json.get("index", 0) if request.is_json else 0
    ok = camera.open(index)
    return jsonify(
        {
            "ok": ok,
            "available": camera.available_res,
            "current": camera.current_res,
            "message": "Kamera berhasil dibuka."
            if ok
            else "Gagal membuka kamera. Pastikan kamera terpasang.",
        }
    )


@cv_bp.route("/camera/close", methods=["POST"])
def camera_close():
    camera.release()
    return jsonify({"ok": True, "message": "Kamera dilepas."})


@cv_bp.route("/resolution", methods=["POST"])
def set_resolution():
    if not request.is_json:
        return jsonify({"ok": False, "reason": "no_json"}), 400
    label = request.json.get("resolution")
    if not label:
        return jsonify({"ok": False, "reason": "missing_field"}), 400
    result = camera.set_resolution(label)
    return jsonify(result)


@cv_bp.route("/resolutions")
def list_resolutions():
    return jsonify(
        {
            "available": camera.available_res,
            "current": camera.current_res,
            "all": RESOLUTION_ORDER,
            "dims": {k: list(v) for k, v in RESOLUTIONS.items()},
        }
    )


@cv_bp.route("/capture", methods=["POST"])
def capture():
    """Capture reference photo at highest resolution."""
    if not camera.is_open():
        ok = camera.open(0)
        if not ok:
            return jsonify({"ok": False, "message": "Kamera tidak tersedia."}), 503
    result = camera.capture_reference_photo()
    return jsonify(result), 200 if result["ok"] else 422


@cv_bp.route("/retry", methods=["POST"])
def retry():
    """Advance to next attempt with looser threshold."""
    result = camera.retry_recognition()
    return jsonify(result)


@cv_bp.route("/reset", methods=["POST"])
def reset():
    """Clear reference encoding and recognition state."""
    camera.reset_recognition()
    return jsonify({"ok": True, "message": "State recognition di-reset."})

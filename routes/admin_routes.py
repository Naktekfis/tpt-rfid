"""
Admin API for tool registration and the student list: tool types (list,
create, photo upload or webcam capture), physical units from an EPC, and
students with their NFC binding state.

Database, presence service, camera and the admin decorator are passed in by
app.py so this module does not import app. Every route is admin-only and not
CSRF-exempt (the UI sends the token).
"""

from __future__ import annotations

import logging
import re

from flask import Blueprint, jsonify, render_template, request

from utils.helpers import allowed_file, sanitize_input
from utils.loan_reminders import email_history

logger = logging.getLogger(__name__)

EPC_RE = re.compile(r"^[0-9A-F]{4,64}$")
MAX_UNIT_NO = 999

# Magic bytes of the image types the upload accepts.
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def normalize_epc(raw) -> str:
    """Uppercase hex without spaces/dashes ("e200 0017-22" -> "E200001722")."""
    return re.sub(r"[\s\-:]", "", str(raw or "")).upper()


def _image_mimetype(data: bytes):
    for magic, mimetype in _SIGNATURES:
        if data.startswith(magic):
            return mimetype
    return None


def create_admin_blueprint(
    database, presence_service, camera, admin_required, allowed_extensions
) -> Blueprint:
    bp = Blueprint("admin_api", __name__)

    def _error(message, code=400):
        return jsonify({"success": False, "error": message}), code

    def _type_or_404(type_id):
        for tool_type in database.get_tool_types():
            if tool_type["type_id"] == str(type_id):
                return tool_type
        return None

    @bp.route("/admin/students")
    @admin_required
    def students_page():
        return render_template("admin_students.html")

    @bp.route("/api/admin/tool_types/<int:type_id>/edit", methods=["POST"])
    @admin_required
    def api_edit_tool_type(type_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("Payload JSON tidak valid")
        if not isinstance(data.get("name"), str):
            return _error("Nama harus berupa teks")
        name = sanitize_input(data["name"])
        if not name or len(name) > 200:
            return _error("Nama jenis alat harus diisi, maksimal 200 karakter")
        try:
            found = database.rename_tool_type(type_id, name)
        except ValueError as exc:
            return _error(str(exc))
        if not found:
            return _error("Jenis alat tidak ditemukan", 404)
        return jsonify({"success": True})

    @bp.route("/api/admin/tool_units/<int:tool_id>/edit", methods=["POST"])
    @admin_required
    def api_edit_tool_unit(tool_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("Payload JSON tidak valid")
        if not isinstance(data.get("name"), str) or not isinstance(
            data.get("category"), str
        ):
            return _error("Nama dan kategori harus berupa teks")
        name = sanitize_input(data["name"])
        category = sanitize_input(data["category"])
        if not name or len(name) > 200:
            return _error("Nama alat harus diisi, maksimal 200 karakter")
        if not category or len(category) > 100:
            return _error("Kategori harus diisi, maksimal 100 karakter")
        if not database.update_tool_details(tool_id, name, category):
            return _error("Alat tidak ditemukan", 404)
        return jsonify({"success": True})

    @bp.route("/api/admin/tool_types", methods=["GET"])
    @admin_required
    def api_tool_types():
        return jsonify({"success": True, "tool_types": database.get_tool_types()})

    @bp.route("/api/admin/tool_types", methods=["POST"])
    @admin_required
    def api_create_tool_type():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("Payload JSON tidak valid")
        name = sanitize_input(str(data.get("name", "")))
        if not name:
            return _error("Nama jenis alat harus diisi")
        if len(name) > 200:
            return _error("Nama jenis alat terlalu panjang")
        if database.get_tool_type_by_name(name):
            return _error(f"Jenis alat '{name}' sudah ada")
        tool_type = database.create_tool_type(name)
        tool_type.pop("created_at", None)
        tool_type.update({"units": 0, "next_unit_no": 1})
        return jsonify({"success": True, "tool_type": tool_type})

    @bp.route("/api/admin/tool_types/<int:type_id>/photo", methods=["POST"])
    @admin_required
    def api_upload_tool_type_photo(type_id):
        photo = request.files.get("photo")
        if photo is None or not photo.filename:
            return _error("Pilih file foto")
        if not allowed_file(photo.filename, allowed_extensions):
            return _error("Format foto tidak valid. Gunakan PNG, JPG, atau JPEG")
        data = photo.read()
        mimetype = _image_mimetype(data)
        if mimetype is None:
            return _error("File ini bukan gambar PNG, JPG, atau GIF")
        if not database.set_tool_type_photo(type_id, data, mimetype):
            return _error("Jenis alat tidak ditemukan", 404)
        return jsonify(
            {"success": True, "photo_url": f"/api/tool_type/{type_id}/photo"}
        )

    @bp.route("/api/admin/tool_types/<int:type_id>/photo/capture", methods=["POST"])
    @admin_required
    def api_capture_tool_type_photo(type_id):
        if _type_or_404(type_id) is None:
            return _error("Jenis alat tidak ditemukan", 404)
        jpeg = camera.jpeg()  # latest camera.read() frame, JPEG-encoded
        if not jpeg:
            return _error("Kamera tidak mengirim gambar", 503)
        database.set_tool_type_photo(type_id, jpeg, "image/jpeg")
        return jsonify(
            {"success": True, "photo_url": f"/api/tool_type/{type_id}/photo"}
        )

    @bp.route("/api/admin/tool_units", methods=["POST"])
    @admin_required
    def api_create_tool_unit():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("Payload JSON tidak valid")
        type_id = str(data.get("type_id", ""))
        if not type_id.isdigit():
            return _error("Pilih jenis alat")
        epc = normalize_epc(data.get("epc"))
        if not EPC_RE.match(epc):
            return _error(
                "EPC harus berupa heksadesimal (0-9, A-F), 4 sampai 64 karakter"
            )
        tool_type = _type_or_404(type_id)
        if tool_type is None:
            return _error("Jenis alat tidak ditemukan", 404)
        raw_unit = data.get("unit_no")
        if raw_unit in (None, ""):
            unit_no = tool_type["next_unit_no"]
        else:
            try:
                unit_no = int(raw_unit)
            except (TypeError, ValueError):
                return _error("Nomor unit harus berupa angka")
        if not 1 <= unit_no <= MAX_UNIT_NO:
            return _error(f"Nomor unit 1 sampai {MAX_UNIT_NO}")
        try:
            tool = database.create_tool_unit(int(type_id), unit_no, epc)
        except ValueError as e:
            return _error(str(e))
        presence_service.tool_registered(epc, int(tool["tool_id"]))
        return jsonify(
            {
                "success": True,
                "message": f"{tool['name']} terdaftar",
                "tool": {
                    "tool_id": tool["tool_id"],
                    "name": tool["name"],
                    "rfid_uid": tool["rfid_uid"],
                    "unit_no": tool["unit_no"],
                    "type_id": tool["type_id"],
                },
            }
        )

    @bp.route("/api/admin/students", methods=["GET"])
    @admin_required
    def api_students():
        return jsonify({"success": True, "students": database.get_students_admin()})

    @bp.route("/api/admin/emails", methods=["GET"])
    @admin_required
    def api_emails():
        """The last 100 reminder emails to students (automatic and manual)."""
        return jsonify({"success": True, "emails": email_history(100)})

    return bp

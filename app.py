"""
RFID Workshop Tool Monitoring System - Main Flask Application
A touchscreen kiosk application for workshop tool borrowing using RFID cards
"""

import os
import sys
import logging
import functools
import secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from werkzeug.utils import secure_filename

from config import get_config
from utils import (
    DatabaseHandler,
    db,
    allowed_file,
    generate_unique_filename,
    validate_nim,
    sanitize_input,
    validate_record_id,
)
from utils.rfid_mock import rfid_reader

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(get_config())

# Configure Flask-Mail
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME")
)

# Initialize Flask-Mail
mail = Mail(app)
logger.info(f"Flask-Mail configured with server: {app.config['MAIL_SERVER']}")

# Initialize rate limiter (defaults: 200/day, 50/hour per IP)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# Initialize database handler with PostgreSQL
database = DatabaseHandler(app)
migrate = Migrate(app, db)
logger.info("PostgreSQL database handler initialized successfully")

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Admin authentication via PIN (set ADMIN_PIN in .env, or a random one is generated)
ADMIN_PIN = os.getenv("ADMIN_PIN", "")
if not ADMIN_PIN:
    ADMIN_PIN = secrets.token_hex(4)  # 8-char random hex
    logger.warning(f"ADMIN_PIN not set in .env -- generated temporary PIN: {ADMIN_PIN}")


def admin_required(f):
    """
    Decorator that protects admin API endpoints.
    Expects 'X-Admin-Pin' header or 'admin_pin' query parameter.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        pin = request.headers.get("X-Admin-Pin") or request.args.get("admin_pin", "")
        if not secrets.compare_digest(pin, ADMIN_PIN):
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def _serialize_borrow_timestamps(tools_data):
    """Convert datetime timestamps in tool list to JSON-serializable dicts."""
    for tool_info in tools_data:
        bt = tool_info.get("borrow_time")
        if bt is not None and isinstance(bt, datetime):
            tool_info["borrow_time"] = {"_seconds": int(bt.timestamp())}


# ==================== Page Routes ====================


@app.route("/")
def index():
    """Role selection landing page"""
    return render_template("landing.html")


@app.route("/mahasiswa")
def mahasiswa_menu():
    """Mahasiswa welcome/menu page"""
    return render_template("welcome.html")


@app.route("/register")
def register():
    """Student registration page"""
    return render_template("register.html")


@app.route("/scan")
def scan():
    """Tool scanning/borrowing page"""
    return render_template("scan.html")


@app.route("/monitor")
def monitor():
    """Tool monitoring page"""
    return render_template("monitor.html")


@app.route("/admin")
def admin_menu():
    """Admin welcome/menu page"""
    return render_template("admin_welcome.html")


@app.route("/admin/monitor")
def admin_monitor():
    """Admin tool monitoring page with enhanced borrower info"""
    return render_template("admin_monitor.html", admin_pin=ADMIN_PIN)


# ==================== API Routes ====================


@app.route("/api/check_rfid", methods=["GET"])
def check_rfid():
    """
    Check for RFID card (polling endpoint for registration page)
    Returns current UID if available
    """
    try:
        uid = rfid_reader.get_current_uid()

        if uid:
            return jsonify({"success": True, "uid": uid, "detected": True})
        else:
            return jsonify({"success": True, "uid": None, "detected": False})

    except Exception as e:
        logger.error(f"Error checking RFID: {str(e)}")
        return jsonify({"success": False, "error": "Failed to check RFID"}), 500


@app.route("/api/register", methods=["POST"])
@limiter.limit("10 per minute")
def api_register():
    """Register new student"""
    try:
        # Get form data
        name = sanitize_input(request.form.get("name", ""))
        nim = sanitize_input(request.form.get("nim", ""))
        email = sanitize_input(request.form.get("email", ""))
        phone = sanitize_input(request.form.get("phone", ""))
        rfid_uid = request.form.get("rfid_uid", "")

        # Validate required fields
        if not all([name, nim, email, phone, rfid_uid]):
            return jsonify({"success": False, "error": "Semua field harus diisi"}), 400

        # Validate NIM format
        if not validate_nim(nim):
            return jsonify({"success": False, "error": "Format NIM tidak valid"}), 400

        # Check if NIM already exists
        existing_student = database.get_student_by_nim(nim)
        if existing_student:
            return jsonify({"success": False, "error": "NIM sudah terdaftar"}), 400

        # Check if RFID UID already exists
        existing_rfid = database.get_student_by_uid(rfid_uid)
        if existing_rfid:
            return jsonify(
                {"success": False, "error": "Kartu RFID sudah terdaftar"}
            ), 400

        # Prepare student data
        student_data = {
            "name": name,
            "nim": nim,
            "email": email,
            "phone": phone,
            "rfid_uid": rfid_uid,
        }

        # Handle photo upload
        photo = request.files.get("photo")
        has_photo = (
            photo
            and photo.filename
            and allowed_file(photo.filename, app.config["ALLOWED_EXTENSIONS"])
        )

        if photo and photo.filename and not has_photo:
            return jsonify(
                {
                    "success": False,
                    "error": "Format foto tidak valid. Gunakan PNG, JPG, atau JPEG",
                }
            ), 400

        # Create student
        student = database.create_student(student_data)

        # Upload photo if provided (save to database as binary)
        if has_photo:
            try:
                photo_data = photo.read()
                mimetype = photo.content_type or "image/jpeg"
                database.update_student_photo(
                    student["student_id"], photo_data, mimetype
                )
            except Exception as e:
                logger.error(f"Error saving photo: {str(e)}")

        # Clear RFID after successful registration
        rfid_reader.clear()

        return jsonify(
            {
                "success": True,
                "message": "Registrasi berhasil!",
                "student": {
                    "student_id": student["student_id"],
                    "name": name,
                    "nim": nim,
                },
            }
        )

    except Exception as e:
        logger.error(f"Error in registration: {str(e)}")
        return jsonify(
            {"success": False, "error": "Terjadi kesalahan saat registrasi"}
        ), 500


@app.route("/api/student/<int:student_id>/photo", methods=["GET"])
def get_student_photo(student_id):
    """Serve student photo from database"""
    try:
        result = database.get_student_photo(str(student_id))
        if result:
            photo_data, mimetype = result
            return Response(photo_data, mimetype=mimetype or "image/jpeg")
        else:
            return jsonify({"success": False, "error": "Photo not found"}), 404
    except Exception as e:
        logger.error(f"Error getting student photo: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/scan_student", methods=["POST"])
def scan_student():
    """Fetch student data by RFID UID"""
    try:
        data = request.get_json()
        rfid_uid = data.get("rfid_uid", "")

        if not rfid_uid:
            return jsonify({"success": False, "error": "UID tidak valid"}), 400

        # Get student from database
        student = database.get_student_by_uid(rfid_uid)

        if not student:
            return jsonify(
                {"success": False, "error": "Mahasiswa tidak terdaftar"}
            ), 404

        return jsonify({"success": True, "student": student})

    except Exception as e:
        logger.error(f"Error scanning student: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/scan_tool", methods=["POST"])
def scan_tool():
    """Fetch tool data by RFID UID"""
    try:
        data = request.get_json()
        rfid_uid = data.get("rfid_uid", "")

        if not rfid_uid:
            return jsonify({"success": False, "error": "UID tidak valid"}), 400

        # Get tool from database
        tool = database.get_tool_by_uid(rfid_uid)

        if not tool:
            return jsonify({"success": False, "error": "Tool tidak terdaftar"}), 404

        return jsonify({"success": True, "tool": tool})

    except Exception as e:
        logger.error(f"Error scanning tool: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/borrow_tool", methods=["POST"])
@limiter.limit("20 per minute")
def borrow_tool():
    """Create borrow transaction (atomic)"""
    try:
        data = request.get_json()
        student_id = data.get("student_id", "")
        tool_id = data.get("tool_id", "")

        if not all([student_id, tool_id]):
            return jsonify({"success": False, "error": "Data tidak lengkap"}), 400

        if not validate_record_id(student_id) or not validate_record_id(tool_id):
            return jsonify({"success": False, "error": "ID tidak valid"}), 400

        # Atomic borrow: validates and writes in a single database transaction
        transaction = database.borrow_tool_atomic(student_id, tool_id)

        return jsonify(
            {
                "success": True,
                "message": "Peminjaman berhasil!",
                "transaction": transaction,
            }
        )

    except ValueError as e:
        # Business logic errors (tool unavailable, already borrowed, etc.)
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error borrowing tool: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/return_tool", methods=["POST"])
@limiter.limit("20 per minute")
def return_tool():
    """Return a borrowed tool (atomic)"""
    try:
        data = request.get_json()
        student_id = data.get("student_id", "")
        tool_id = data.get("tool_id", "")

        if not all([student_id, tool_id]):
            return jsonify({"success": False, "error": "Data tidak lengkap"}), 400

        if not validate_record_id(student_id) or not validate_record_id(tool_id):
            return jsonify({"success": False, "error": "ID tidak valid"}), 400

        # Atomic return: finds active borrow and updates in a single transaction
        database.return_tool_atomic(student_id, tool_id)

        return jsonify({"success": True, "message": "Pengembalian berhasil!"})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error returning tool: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    """Get recent transactions"""
    try:
        limit = request.args.get("limit", 5, type=int)
        transactions = database.get_recent_transactions(limit)

        # Convert timestamps to strings for JSON serialization
        for trans in transactions:
            if "borrow_time" in trans and trans["borrow_time"]:
                if isinstance(trans["borrow_time"], datetime):
                    trans["borrow_time"] = trans["borrow_time"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            if "return_time" in trans and trans["return_time"]:
                if isinstance(trans["return_time"], datetime):
                    trans["return_time"] = trans["return_time"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            if "created_at" in trans and trans["created_at"]:
                if isinstance(trans["created_at"], datetime):
                    trans["created_at"] = trans["created_at"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

        return jsonify({"success": True, "transactions": transactions})

    except Exception as e:
        logger.error(f"Error getting transactions: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/tools_status", methods=["GET"])
def get_tools_status():
    """Get all tools with their current status and borrower info"""
    try:
        page_limit = request.args.get("limit", default=None, type=int)
        page_offset = request.args.get("offset", default=0, type=int)
        tools_data = database.get_all_tools_with_borrowers(
            include_email=False, limit=page_limit, offset=page_offset
        )
        _serialize_borrow_timestamps(tools_data)

        return jsonify({"success": True, "tools": tools_data})

    except Exception as e:
        logger.error(f"Error getting tools status: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


# ==================== Debug/Development Routes ====================
# Only registered in development mode to prevent misuse in production


if app.config.get("DEBUG"):

    @app.route("/debug/scan", methods=["GET"])
    def debug_scan():
        """Debug endpoint to simulate RFID scan (development only)"""
        uid = request.args.get("uid", "")

        if uid:
            rfid_reader.simulate_scan(uid)
            return jsonify(
                {
                    "success": True,
                    "message": f"Simulated scan of UID: {uid}",
                    "uid": uid,
                }
            )
        else:
            return jsonify({"success": False, "error": "No UID provided"}), 400

    @app.route("/debug/clear", methods=["GET"])
    def debug_clear():
        """Debug endpoint to clear RFID (development only)"""
        rfid_reader.clear()
        return jsonify({"success": True, "message": "RFID cleared"})

    logger.info("Debug routes registered (development mode)")
else:
    logger.info("Debug routes DISABLED (production mode)")


# ==================== Admin API Endpoints ====================


@app.route("/api/admin/tools_status", methods=["GET"])
@admin_required
def get_admin_tools_status():
    """Get all tools with enhanced borrower info for admin"""
    try:
        page_limit = request.args.get("limit", default=None, type=int)
        page_offset = request.args.get("offset", default=0, type=int)
        tools_data = database.get_all_tools_with_borrowers(
            include_email=True, limit=page_limit, offset=page_offset
        )
        _serialize_borrow_timestamps(tools_data)

        return jsonify({"success": True, "tools": tools_data})

    except Exception as e:
        logger.error(f"Error getting admin tools status: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


@app.route("/api/admin/send_warning_email", methods=["POST"])
@admin_required
@limiter.limit("5 per minute")
def send_warning_email():
    """Send warning email to student about tool return"""
    try:
        data = request.json

        # Validate required fields
        required_fields = ["student_name", "student_email", "tool_name", "borrow_date"]
        for field in required_fields:
            if field not in data:
                return jsonify(
                    {"success": False, "error": f"Missing field: {field}"}
                ), 400

        student_name = data["student_name"]
        student_email = data["student_email"]
        tool_name = data["tool_name"]
        borrow_date = data["borrow_date"]

        # Calculate borrow duration and format date for email
        try:
            borrow_dt = datetime.fromisoformat(borrow_date.replace("Z", "+00:00"))
            # Make comparison timezone-naive
            borrow_naive = borrow_dt.replace(tzinfo=None)
            duration_days = (datetime.now() - borrow_naive).days
            duration_text = f"{duration_days} hari" if duration_days > 0 else "hari ini"
            # Format date nicely for email body
            borrow_date_display = borrow_naive.strftime("%d-%m-%Y pukul %H:%M")
        except (ValueError, TypeError):
            duration_text = "beberapa waktu lalu"
            borrow_date_display = borrow_date

        # Create email message
        subject = "[Lab Fabrikasi ITB] Peringatan Pengembalian Alat"

        body = f"""Kepada Yth. {student_name},

Kami ingin mengingatkan bahwa alat berikut masih tercatat dalam status peminjaman atas nama Anda:

Nama Alat: {tool_name}
Dipinjam sejak: {borrow_date_display}
Durasi peminjaman: {duration_text}

Mohon untuk segera mengembalikan alat tersebut ke Lab Fabrikasi pada jam operasional.

Apabila alat sudah dikembalikan, mohon abaikan email ini. Jika terdapat kendala atau pertanyaan, silakan hubungi petugas lab.

Terima kasih atas perhatian dan kerjasamanya.

Salam,
Tim Lab Fabrikasi
Teknik Fisika ITB

---
Email ini dikirim secara otomatis oleh sistem monitoring Lab Fabrikasi.
"""

        # Send email
        msg = Message(
            subject=subject,
            sender=("Lab Fabrikasi Teknik Fisika ITB", app.config["MAIL_USERNAME"]),
            recipients=[student_email],
            body=body,
        )

        mail.send(msg)

        logger.info(f"Warning email sent to ***@*** for tool {tool_name}")

        return jsonify({"success": True, "message": "Email berhasil dikirim"})

    except Exception as e:
        logger.error(f"Error sending warning email: {str(e)}")
        return jsonify(
            {"success": False, "error": f"Gagal mengirim email: {str(e)}"}
        ), 500


# ==================== Error Handlers ====================


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors -- redirect to homepage"""
    return redirect(url_for("index"))


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({"success": False, "error": "Terjadi kesalahan server"}), 500


# ==================== Main ====================

if __name__ == "__main__":
    # Run the application
    # For production, use gunicorn or similar WSGI server
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])

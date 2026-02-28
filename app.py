"""
RFID Workshop Tool Monitoring System - Main Flask Application
A touchscreen kiosk application for workshop tool borrowing using RFID cards
"""

import os
import sys
import logging
import functools
import secrets
import csv
import io
from datetime import datetime, timedelta
import openpyxl
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    Response,
    session,
    send_file,
)
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
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

# Initialize CSRF Protection
csrf = CSRFProtect(app)
logger.info("CSRF Protection enabled")

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

# Import and register CV Benchmark blueprint (optional, requires opencv)
CV_BENCHMARK_AVAILABLE = False
try:
    from routes.cv_routes import cv_bp

    app.register_blueprint(cv_bp)
    CV_BENCHMARK_AVAILABLE = True
    logger.info("CV Benchmark blueprint registered")
except ImportError as e:
    logger.warning(f"CV Benchmark not available (missing dependencies: {e})")
    logger.info(
        "To enable CV Benchmark: pip install opencv-python face-recognition psutil"
    )

# Initialize MQTT client (mock or real based on MQTT_ENABLED)
from utils import create_mqtt_client, create_websocket_handler

mqtt_client = create_mqtt_client(
    enabled=app.config.get("MQTT_ENABLED", False),
    broker_host=app.config.get("MQTT_BROKER_HOST", "localhost"),
    broker_port=app.config.get("MQTT_BROKER_PORT", 1883),
    client_id=app.config.get("MQTT_CLIENT_ID", "tpt-rfid-server"),
    username=app.config.get("MQTT_USERNAME"),
    password=app.config.get("MQTT_PASSWORD"),
)

# Initialize WebSocket handler (mock or real based on WEBSOCKET_ENABLED)
ws_handler = create_websocket_handler(
    enabled=app.config.get("WEBSOCKET_ENABLED", False), app=app
)

# Connect MQTT client if enabled
if app.config.get("MQTT_ENABLED", False):
    try:
        mqtt_client.connect()
        logger.info("MQTT client connected successfully")

        # Subscribe to relevant topics
        mqtt_client.subscribe(
            app.config.get("MQTT_TOPIC_RFID_SCAN", "rfid/scan"),
            lambda topic, payload: handle_mqtt_rfid_scan(topic, payload),
            qos=app.config.get("MQTT_QOS_CRITICAL", 1),
        )
        logger.info("Subscribed to MQTT topics")
    except Exception as e:
        logger.error(f"Failed to connect MQTT client: {e}")
else:
    logger.info("MQTT disabled - using mock mode")

if not app.config.get("WEBSOCKET_ENABLED", False):
    logger.info("WebSocket disabled - using mock mode")

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Admin authentication via hardcoded hashed PIN
# PIN: 133133 (hashed with werkzeug scrypt)
from werkzeug.security import check_password_hash

ADMIN_PIN_HASH = "scrypt:32768:8:1$v6unCJMhmE1m6btB$6cff2d6ce01facfb3b8c13ce4c248175507f02b1ef3d442013ccc2b79d0ae1f12c6aa48ee2051e706e096c05fa2279bccfd4b2e40099f742742fedbb6bc41097"


def admin_required(f):
    """
    Decorator that protects admin API endpoints.
    Requires valid session authentication.
    Redirects to login page if unauthorized HTML request.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Check Session
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)

        # If Unauthorized
        # If it's a browser requesting a page, redirect to login
        if request.accept_mimetypes.accept_html and not request.is_json:
            return redirect(url_for("admin_login"))

        return jsonify({"success": False, "error": "Unauthorized"}), 401

    return decorated


# ==================== MQTT Message Handlers ====================


def handle_mqtt_rfid_scan(topic: str, payload: dict):
    """
    Handle RFID scan messages from MQTT broker

    Expected payload format:
    {
        "rfid_uid": "1234567890",
        "reader_id": "esp32_01",
        "timestamp": "2024-01-01T12:00:00Z"  # Optional
    }
    """
    try:
        rfid_uid = payload.get("rfid_uid")
        reader_id = payload.get("reader_id", "unknown")

        if not rfid_uid:
            logger.error(f"Invalid MQTT payload - missing rfid_uid: {payload}")
            return

        logger.info(f"MQTT RFID scan received: {rfid_uid} from {reader_id}")

        # Look up student by RFID
        student_data = database.get_student_by_uid(rfid_uid)

        if not student_data:
            logger.warning(f"Unknown RFID scanned: {rfid_uid}")
            # Broadcast unknown RFID event to WebSocket clients
            from utils import broadcast_rfid_scan

            broadcast_rfid_scan(
                ws_handler,
                {"rfid_uid": rfid_uid, "status": "unknown", "reader_id": reader_id},
            )
            return

        logger.info(
            f"Student identified: {student_data.get('name')} (NIM: {student_data.get('nim')})"
        )

        # Broadcast successful scan to WebSocket clients
        from utils import broadcast_rfid_scan

        broadcast_rfid_scan(
            ws_handler,
            {
                "rfid_uid": rfid_uid,
                "student_id": student_data.get("id"),
                "student_name": student_data.get("name"),
                "student_nim": student_data.get("nim"),
                "status": "success",
                "reader_id": reader_id,
            },
        )

        # Note: Actual borrow/return logic happens in the web interface
        # This just notifies about the RFID scan event

    except Exception as e:
        logger.error(f"Error handling MQTT RFID scan: {e}")


def _serialize_borrow_timestamps(tools_data):
    """Convert datetime timestamps in tool list to JSON-serializable dicts."""
    for tool_info in tools_data:
        bt = tool_info.get("borrow_time")
        if bt is not None and isinstance(bt, datetime):
            tool_info["borrow_time"] = {"_seconds": int(bt.timestamp())}


# ==================== Template Context ====================


@app.context_processor
def inject_cv_availability():
    """Make CV_BENCHMARK_AVAILABLE available in all templates"""
    return {"cv_benchmark_available": CV_BENCHMARK_AVAILABLE}


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
@admin_required
def admin_menu():
    """Admin welcome/menu page"""
    return render_template("admin_welcome.html")


@app.route("/admin/login")
def admin_login():
    """Admin login page"""
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_menu"))
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Admin logout"""
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin/monitor")
@admin_required
def admin_monitor():
    """Admin tool monitoring page with enhanced borrower info"""
    return render_template("admin_monitor.html")


@app.route("/admin/input_tool")
@admin_required
def admin_input_tool():
    """Admin tool registration page"""
    return render_template("input_tool.html")


@app.route("/admin/export_history")
@admin_required
def admin_export_history():
    """Placeholder for export history"""
    # Redirecting to new history page logic
    return redirect(url_for("admin_history"))


@app.route("/admin/history")
@admin_required
def admin_history():
    """Admin history and export page"""
    return render_template("admin_history.html")


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


@app.route("/api/admin/login", methods=["POST"])
@limiter.limit("5 per minute")
def api_admin_login():
    """Verify admin PIN and create session"""
    try:
        data = request.json
        pin = data.get("pin", "")

        if check_password_hash(ADMIN_PIN_HASH, pin):
            session["admin_logged_in"] = True
            session.permanent = (
                True  # Uses config PERMANENT_SESSION_LIFETIME (default 31 days)
            )
            return jsonify({"success": True, "message": "Login successful"})

        return jsonify({"success": False, "error": "PIN salah"}), 401

    except Exception as e:
        logger.error(f"Error in admin login: {str(e)}")
        return jsonify({"success": False, "error": "Terjadi kesalahan"}), 500


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


@app.route("/api/admin/send_export_email", methods=["POST"])
@admin_required
@limiter.limit("3 per minute")
def send_export_email():
    """Send export file via email"""
    # Maximum records to export (prevent memory issues)
    MAX_EXPORT_RECORDS = 10000

    try:
        data = request.json

        # Validate required fields
        if not data or "email" not in data:
            return jsonify({"success": False, "error": "Email tidak boleh kosong"}), 400

        recipient_email = data["email"].strip()

        # Basic email validation
        if (
            not recipient_email
            or "@" not in recipient_email
            or "." not in recipient_email
        ):
            return jsonify({"success": False, "error": "Format email tidak valid"}), 400

        # Get date range
        start_str = data.get("start_date")
        end_str = data.get("end_date")

        start_date = None
        end_date = None

        # Parse dates
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                return jsonify(
                    {"success": False, "error": "Format tanggal mulai tidak valid"}
                ), 400

        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify(
                    {"success": False, "error": "Format tanggal akhir tidak valid"}
                ), 400

        # Get transactions
        transactions = database.get_transactions_filtered(start_date, end_date)

        # Check if dataset is too large
        record_count = len(transactions)
        if record_count > MAX_EXPORT_RECORDS:
            return jsonify(
                {
                    "success": False,
                    "error": f"Dataset terlalu besar ({record_count:,} records). "
                    f"Maksimal export adalah {MAX_EXPORT_RECORDS:,} records. "
                    f"Harap persempit rentang tanggal.",
                }
            ), 400

        if record_count == 0:
            return jsonify(
                {
                    "success": False,
                    "error": "Tidak ada data untuk diekspor pada rentang tanggal yang dipilih.",
                }
            ), 400

        # Generate Excel file in memory
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Riwayat Peminjaman"

        # Header
        headers = [
            "ID",
            "Nama Mahasiswa",
            "NIM",
            "Alat",
            "Kategori",
            "Waktu Pinjam",
            "Waktu Kembali",
            "Status",
        ]
        ws.append(headers)

        # Data
        for t in transactions:
            # Format dates for Excel
            b_time = (
                t["borrow_time"].strftime("%Y-%m-%d %H:%M:%S")
                if t["borrow_time"]
                else ""
            )
            r_time = (
                t["return_time"].strftime("%Y-%m-%d %H:%M:%S")
                if t["return_time"]
                else ""
            )

            ws.append(
                [
                    t["id"],
                    t["student_name"],
                    t["student_nim"],
                    t["tool_name"],
                    t["tool_category"],
                    b_time,
                    r_time,
                    t["status"],
                ]
            )

        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = max_length + 2
            ws.column_dimensions[column[0].column_letter].width = adjusted_width

        # Save to BytesIO
        excel_file = io.BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        # Prepare email
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rekap_peminjaman_{timestamp}.xlsx"

        # Format date range for email subject/body
        date_range_text = ""
        if start_date and end_date:
            date_range_text = f" ({start_date.strftime('%d-%m-%Y')} s/d {end_date.strftime('%d-%m-%Y')})"
        elif start_date:
            date_range_text = f" (mulai {start_date.strftime('%d-%m-%Y')})"
        elif end_date:
            date_range_text = f" (sampai {end_date.strftime('%d-%m-%Y')})"

        subject = "Laporan Rekap Peminjaman Lab Fabrikasi Teknik Fisika ITB"

        body = f"""Berikut terlampir laporan rekap peminjaman alat Lab Fabrikasi{date_range_text}.

Total transaksi: {record_count:,} records

File terlampir: {filename}

Terima kasih.

---
Email ini dikirim secara otomatis oleh sistem monitoring Lab Fabrikasi.
"""

        # Create message
        msg = Message(
            subject=subject,
            sender=("Lab Fabrikasi Teknik Fisika ITB", app.config["MAIL_USERNAME"]),
            recipients=[recipient_email],
            body=body,
        )

        # Attach Excel file
        msg.attach(
            filename,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            excel_file.read(),
        )

        # Send email
        mail.send(msg)

        logger.info(f"Export email sent to ***@*** with {record_count} records")

        return jsonify(
            {"success": True, "message": f"Email berhasil dikirim ke {recipient_email}"}
        )

    except Exception as e:
        logger.error(f"Error sending export email: {str(e)}")
        return jsonify(
            {"success": False, "error": f"Gagal mengirim email: {str(e)}"}
        ), 500


@app.route("/api/admin/tools", methods=["POST"])
@admin_required
def add_tool():
    """Add new tool"""
    try:
        data = request.json or request.form

        name = sanitize_input(data.get("name", ""))
        rfid_uid = data.get("rfid_uid", "")
        category = sanitize_input(data.get("category", "Uncategorized"))

        if not all([name, rfid_uid]):
            return jsonify(
                {"success": False, "error": "Nama alat dan UID harus diisi"}
            ), 400

        # Check if UID already exists
        existing_tool = database.get_tool_by_uid(rfid_uid)
        if existing_tool:
            return jsonify({"success": False, "error": "UID RFID sudah terdaftar"}), 400

        # Check if tool name already exists (case-insensitive)
        existing_name = database.get_tool_by_name(name)
        if existing_name:
            return jsonify(
                {
                    "success": False,
                    "error": f"Alat dengan nama '{name}' sudah terdaftar. Gunakan nama yang berbeda.",
                }
            ), 400

        tool_data = {
            "name": name,
            "rfid_uid": rfid_uid,
            "category": category,
            "status": "available",
        }

        # Create tool
        tool = database.create_tool(tool_data)

        # Handle photo upload if present (multipart/form-data)
        if request.files.get("photo"):
            # Placeholder for tool photo logic if needed later
            pass

        # Clear RFID reader after successful registration
        rfid_reader.clear()

        return jsonify(
            {"success": True, "message": "Alat berhasil ditambahkan", "tool": tool}
        )

    except Exception as e:
        logger.error(f"Error adding tool: {str(e)}")
        return jsonify(
            {"success": False, "error": "Terjadi kesalahan saat menambah alat"}
        ), 500


@app.route("/api/admin/transactions", methods=["GET"])
@admin_required
def get_admin_transactions():
    """Get filtered transactions for data table"""
    try:
        start_str = request.args.get("start_date")
        end_str = request.args.get("end_date")

        start_date = None
        end_date = None

        # Parse start date with error handling
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                return jsonify(
                    {
                        "success": False,
                        "error": "Format tanggal mulai tidak valid. Gunakan format YYYY-MM-DD",
                    }
                ), 400

        # Parse end date with error handling
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                # Set to end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify(
                    {
                        "success": False,
                        "error": "Format tanggal akhir tidak valid. Gunakan format YYYY-MM-DD",
                    }
                ), 400

        # Database handler handles None as "no filter"
        transactions = database.get_transactions_filtered(start_date, end_date)

        # Serialize dates
        for trans in transactions:
            if isinstance(trans["borrow_time"], datetime):
                trans["borrow_time"] = trans["borrow_time"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            if isinstance(trans["return_time"], datetime):
                trans["return_time"] = trans["return_time"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

        return jsonify({"success": True, "data": transactions})

    except Exception as e:
        logger.error(f"Error fetching admin transactions: {str(e)}")
        return jsonify(
            {"success": False, "error": "Terjadi kesalahan loading data"}
        ), 500


@app.route("/api/admin/export", methods=["GET"])
@admin_required
def export_history():
    """Export transaction history with size limit protection"""
    # Maximum records to export (prevent memory issues)
    MAX_EXPORT_RECORDS = 10000

    try:
        fmt = request.args.get("format", "csv")
        start_str = request.args.get("start_date")
        end_str = request.args.get("end_date")

        start_date = None
        end_date = None

        # Parse start date with error handling
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                return jsonify(
                    {"success": False, "error": "Format tanggal mulai tidak valid"}
                ), 400

        # Parse end date with error handling
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify(
                    {"success": False, "error": "Format tanggal akhir tidak valid"}
                ), 400

        transactions = database.get_transactions_filtered(start_date, end_date)

        # Check if dataset is too large
        record_count = len(transactions)
        if record_count > MAX_EXPORT_RECORDS:
            return jsonify(
                {
                    "success": False,
                    "error": f"Dataset terlalu besar ({record_count:,} records). "
                    f"Maksimal export adalah {MAX_EXPORT_RECORDS:,} records. "
                    f"Harap persempit rentang tanggal.",
                }
            ), 400

        # Log export activity
        logger.info(f"Exporting {record_count} transactions as {fmt.upper()}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rekap_peminjaman_{timestamp}"

        if fmt == "xlsx":
            # Excel Export
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Riwayat Peminjaman"

            # Header
            headers = [
                "ID",
                "Nama Mahasiswa",
                "NIM",
                "Alat",
                "Kategori",
                "Waktu Pinjam",
                "Waktu Kembali",
                "Status",
            ]
            ws.append(headers)

            # Data
            for t in transactions:
                # Format dates for Excel
                b_time = (
                    t["borrow_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if t["borrow_time"]
                    else ""
                )
                r_time = (
                    t["return_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if t["return_time"]
                    else ""
                )

                ws.append(
                    [
                        t["id"],
                        t["student_name"],
                        t["student_nim"],
                        t["tool_name"],
                        t["tool_category"],
                        b_time,
                        r_time,
                        t["status"],
                    ]
                )

            # Auto-adjust column widths (simple)
            for column in ws.columns:
                max_length = 0
                column = [cell for cell in column]
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = max_length + 2
                ws.column_dimensions[column[0].column_letter].width = adjusted_width

            out = io.BytesIO()
            wb.save(out)
            out.seek(0)

            return send_file(
                out,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"{filename}.xlsx",
            )

        else:
            # CSV Export (Default)
            si = io.StringIO()
            cw = csv.writer(si)

            # Header
            cw.writerow(
                [
                    "ID",
                    "Nama Mahasiswa",
                    "NIM",
                    "Alat",
                    "Kategori",
                    "Waktu Pinjam",
                    "Waktu Kembali",
                    "Status",
                ]
            )

            # Data
            for t in transactions:
                b_time = (
                    t["borrow_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if t["borrow_time"]
                    else ""
                )
                r_time = (
                    t["return_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if t["return_time"]
                    else ""
                )

                cw.writerow(
                    [
                        t["id"],
                        t["student_name"],
                        t["student_nim"],
                        t["tool_name"],
                        t["tool_category"],
                        b_time,
                        r_time,
                        t["status"],
                    ]
                )

            output = io.BytesIO(si.getvalue().encode("utf-8"))
            return send_file(
                output,
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{filename}.csv",
            )

    except Exception as e:
        logger.error(f"Error exporting history: {str(e)}")
        return jsonify(
            {"success": False, "error": "Terjadi kesalahan saat export"}
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

# Cleanup handler for graceful shutdown
import atexit


def cleanup():
    """Cleanup resources on application shutdown"""
    logger.info("Shutting down application...")
    if app.config.get("MQTT_ENABLED", False):
        try:
            mqtt_client.disconnect()
            logger.info("MQTT client disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting MQTT: {e}")


atexit.register(cleanup)

if __name__ == "__main__":
    # Run the application
    # For production, use gunicorn or similar WSGI server
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])

"""
Configuration management for the RFID Workshop Tool Monitoring System
"""

import os
import sys
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration"""

    # SECRET_KEY is required - fail if not set in production
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        # Allow default only in development
        if os.getenv("FLASK_ENV", "development") == "production":
            print("ERROR: SECRET_KEY must be set in production environment!")
            print(
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
            sys.exit(1)
        SECRET_KEY = "dev-secret-key-change-in-production"

    # Default: SQLite file under <repo>/instance. Set DATABASE_URL to override
    # (e.g. postgresql://... if psycopg2 is installed manually).
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _INSTANCE_DIR = os.path.join(_BASE_DIR, "instance")
    os.makedirs(_INSTANCE_DIR, exist_ok=True)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + os.path.join(_INSTANCE_DIR, "tpt_rfid.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # werkzeug hash of the admin PIN; written by scripts/set_admin_pin.py.
    # Unset means DEFAULT_ADMIN_PIN.
    ADMIN_PIN_HASH = os.getenv("ADMIN_PIN_HASH")
    DEFAULT_ADMIN_PIN = "133133"

    # Session Security Settings
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # 8 hour session timeout for admin

    # USB UHF reader (HW-VX6336). Disabled = mock reader (debug routes only).
    RFID_READER_ENABLED = os.getenv("RFID_READER_ENABLED", "false").lower() == "true"
    RFID_READER_MODEL = os.getenv("RFID_READER_MODEL", "vx6336")
    RFID_READER_PORT = os.getenv("RFID_READER_PORT", "/dev/ttyUSB0")
    RFID_READER_ADDR = int(os.getenv("RFID_READER_ADDR", "0"), 0)
    # A tag must be away this long (s) before the same tag is reported again.
    RFID_ABSENT_TIMEOUT = float(os.getenv("RFID_ABSENT_TIMEOUT", "2.5"))
    # A tool tag not seen for this long (s) counts as gone from the reader field.
    RFID_MISSING_AFTER = float(os.getenv("RFID_MISSING_AFTER", "1.5"))
    # An unborrowed tool must stay gone this much longer (s) before the alarm,
    # so weak reads at the edge of the field do not raise false alarms.
    RFID_ALARM_CONFIRM_SECONDS = float(os.getenv("RFID_ALARM_CONFIRM_SECONDS", "2"))
    # Beep the reader when an unborrowed tool leaves.
    RFID_ALARM_ENABLED = os.getenv("RFID_ALARM_ENABLED", "true").lower() == "true"

    NFC_READER_ENABLED = os.getenv("NFC_READER_ENABLED", "false").lower() == "true"

    # Camera remains available for tool photography.
    CAMERA_ENABLED = os.getenv("CAMERA_ENABLED", "false").lower() == "true"
    CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
    # Private alarm evidence; no automatic deletion of older captures.
    SECURITY_STORAGE_DIR = os.getenv("SECURITY_STORAGE_DIR")
    SECURITY_MAX_STORAGE_BYTES = int(
        os.getenv("SECURITY_MAX_STORAGE_BYTES", "209715200")
    )
    CAMERA_OBSTRUCTION_SECONDS = float(os.getenv("CAMERA_OBSTRUCTION_SECONDS", "5"))
    CAMERA_RECOVERY_SECONDS = float(os.getenv("CAMERA_RECOVERY_SECONDS", "3"))

    # Loan period in days (Transaction.due_at = borrow_time + LOAN_DAYS).
    LOAN_DAYS = 2
    # Automatic reminder emails (utils/loan_reminders.py): one when a borrow is
    # due, one LOAN_OVERDUE_REMINDER_DAYS later. Off until mail is configured.
    LOAN_REMINDERS_ENABLED = (
        os.getenv("LOAN_REMINDERS_ENABLED", "false").lower() == "true"
    )
    LOAN_OVERDUE_REMINDER_DAYS = int(os.getenv("LOAN_OVERDUE_REMINDER_DAYS", "2"))
    LOAN_REMINDER_INTERVAL_SECONDS = int(
        os.getenv("LOAN_REMINDER_INTERVAL_SECONDS", "300")
    )

    # Kiosk session (NFC tap, then tools leaving/returning are
    # attributed to the student). Extended on every tool event, capped at
    # KIOSK_SESSION_MAX_SECONDS from now.
    KIOSK_SESSION_SECONDS = int(os.getenv("KIOSK_SESSION_SECONDS", "60"))
    KIOSK_SESSION_EXTEND = int(os.getenv("KIOSK_SESSION_EXTEND", "30"))
    KIOSK_SESSION_MAX_SECONDS = int(os.getenv("KIOSK_SESSION_MAX_SECONDS", "120"))
    # An open alarm this young becomes a borrow by the student who identifies.
    ALARM_GRACE_SECONDS = int(os.getenv("ALARM_GRACE_SECONDS", "30"))
    # The kiosk hides an alarm overlay after this long (or on "Tutup") so others
    # can use the kiosk; the alarm itself stays open for admin.
    ALARM_OVERLAY_SECONDS = int(os.getenv("ALARM_OVERLAY_SECONDS", "30"))


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    FLASK_ENV = "development"
    # Allow non-HTTPS in development
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    FLASK_ENV = "production"
    # Require HTTPS in production
    SESSION_COOKIE_SECURE = True  # Only send cookie over HTTPS


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get configuration based on environment"""
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config["default"])

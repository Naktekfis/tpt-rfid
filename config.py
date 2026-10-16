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
    RFID_READER_PORT = os.getenv("RFID_READER_PORT", "/dev/ttyUSB0")
    RFID_READER_ADDR = int(os.getenv("RFID_READER_ADDR", "0"), 0)
    # A tag must be away this long (s) before the same tag is reported again.
    RFID_ABSENT_TIMEOUT = float(os.getenv("RFID_ABSENT_TIMEOUT", "2.5"))


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

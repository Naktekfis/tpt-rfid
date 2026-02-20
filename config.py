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

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://localhost/tpt_rfid"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # Session Security Settings
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # 8 hour session timeout for admin

    # MQTT Configuration
    MQTT_ENABLED = os.getenv("MQTT_ENABLED", "false").lower() == "true"
    MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "tpt-rfid-server")
    MQTT_USERNAME = os.getenv("MQTT_USERNAME")  # Optional
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")  # Optional
    MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))
    MQTT_QOS_CRITICAL = int(
        os.getenv("MQTT_QOS_CRITICAL", "1")
    )  # For RFID scans, transactions
    MQTT_QOS_NORMAL = int(os.getenv("MQTT_QOS_NORMAL", "0"))  # For sensor data

    # WebSocket Configuration
    WEBSOCKET_ENABLED = os.getenv("WEBSOCKET_ENABLED", "false").lower() == "true"
    WEBSOCKET_CORS_ORIGINS = os.getenv(
        "WEBSOCKET_CORS_ORIGINS", "*"
    )  # Change for production

    # MQTT Topics
    MQTT_TOPIC_RFID_SCAN = "rfid/scan"
    MQTT_TOPIC_TRANSACTION_UPDATE = "transaction/update"
    MQTT_TOPIC_TOOL_STATUS = "tool/status"
    MQTT_TOPIC_SENSOR_PREFIX = "sensor/"  # sensor/temperature, sensor/humidity, etc.


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

import os

# Must be set before `app` is imported (config.py reads env at import time;
# load_dotenv does not override variables that are already set).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["FLASK_ENV"] = "development"
os.environ["SECRET_KEY"] = "test"
os.environ["RFID_READER_ENABLED"] = "false"  # mock reader, whatever .env says
os.environ["NFC_READER_ENABLED"] = "false"
os.environ["CAMERA_ENABLED"] = "false"  # mock camera, whatever .env says
os.environ["LOAN_REMINDERS_ENABLED"] = "false"  # never mail real people from tests

import pytest  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

import app as app_module  # noqa: E402
from utils import db  # noqa: E402

app_module.app.config["TESTING"] = True
app_module.app.config["WTF_CSRF_ENABLED"] = False
app_module.limiter.enabled = False
app_module.presence_service.stop()  # handle rounds inline so tests see results

TEST_PIN = "424242"
app_module.ADMIN_PIN_HASH = generate_password_hash(TEST_PIN)


@pytest.fixture()
def app():
    app_module.nfc_service.capture = None
    app_module.kiosk._to_idle()
    flask_app = app_module.app
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def database(app):
    return app_module.database


@pytest.fixture()
def student(database):
    return database.create_student(
        {
            "name": "Budi",
            "nim": "12345678",
            "email": "budi@example.com",
            "phone": "08123456789",
            "rfid_uid": "STU-001",
        }
    )


@pytest.fixture()
def tool(database):
    return database.create_tool(
        {"name": "Obeng", "rfid_uid": "TOOL-001", "category": "Hand Tools"}
    )


@pytest.fixture()
def admin_client(client, monkeypatch):
    monkeypatch.setattr(app_module, "ADMIN_PIN_HASH", generate_password_hash(TEST_PIN))
    return client

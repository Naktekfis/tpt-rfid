"""
Helper utility functions for the RFID Workshop Tool Monitoring System
"""

import os
import uuid
import html
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename

# Indonesia Timezone - WIB (Western Indonesia Time) = UTC+7
WIB_OFFSET = timedelta(hours=7)


def get_wib_time():
    """
    Get current time in WIB (UTC+7)

    Returns:
        datetime: Current time in WIB timezone
    """
    return datetime.now(timezone.utc) + WIB_OFFSET


def utc_to_wib(utc_datetime):
    """
    Convert UTC datetime to WIB (UTC+7)

    Args:
        utc_datetime: datetime object in UTC (can be naive or aware)

    Returns:
        datetime: datetime in WIB timezone (naive)
    """
    if utc_datetime is None:
        return None

    # If naive datetime, assume it's UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)

    # Convert to WIB
    wib_datetime = utc_datetime.astimezone(timezone(WIB_OFFSET))

    # Return as naive datetime (remove timezone info for consistency)
    return wib_datetime.replace(tzinfo=None)


def wib_to_utc(wib_datetime):
    """
    Convert WIB datetime to UTC

    Args:
        wib_datetime: datetime object in WIB (naive)

    Returns:
        datetime: datetime in UTC timezone (naive)
    """
    if wib_datetime is None:
        return None

    # Add WIB timezone info
    wib_aware = wib_datetime.replace(tzinfo=timezone(WIB_OFFSET))

    # Convert to UTC
    utc_datetime = wib_aware.astimezone(timezone.utc)

    # Return as naive datetime
    return utc_datetime.replace(tzinfo=None)


def allowed_file(filename, allowed_extensions):
    """
    Check if file has an allowed extension

    Args:
        filename (str): Name of the file to check
        allowed_extensions (set): Set of allowed extensions

    Returns:
        bool: True if file extension is allowed, False otherwise
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def generate_unique_filename(original_filename):
    """
    Generate a unique filename using UUID to prevent collisions

    Args:
        original_filename (str): Original filename

    Returns:
        str: Unique filename with UUID prefix
    """
    # Secure the filename to prevent directory traversal attacks
    filename = secure_filename(original_filename)

    # Get file extension
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""

    # Generate unique filename with timestamp and UUID
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"{timestamp}_{unique_id}.{ext}" if ext else f"{timestamp}_{unique_id}"


def format_timestamp(timestamp):
    """
    Format a datetime timestamp to readable string

    Args:
        timestamp: datetime object

    Returns:
        str: Formatted timestamp string
    """
    if timestamp:
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def validate_nim(nim):
    """
    Validate NIM (Student ID Number) format
    Basic validation - can be customized based on institution rules

    Args:
        nim (str): Student ID number to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not nim:
        return False

    # Remove whitespace
    nim = nim.strip()

    # Basic validation: must be alphanumeric and between 5-20 characters
    return nim.isalnum() and 5 <= len(nim) <= 20


def validate_record_id(record_id):
    """
    Validate a database record ID (integer or string representation).

    Args:
        record_id: Record ID to validate (str or int)

    Returns:
        bool: True if valid, False otherwise
    """
    if record_id is None:
        return False

    # Convert to string for validation
    record_id_str = str(record_id).strip()

    if not record_id_str:
        return False

    # Must be a positive integer
    try:
        val = int(record_id_str)
        return val > 0
    except (ValueError, TypeError):
        return False


def sanitize_input(text):
    """
    Sanitize user input to prevent XSS attacks.
    Uses Python's built-in html.escape() which handles &, <, >, ", and '.

    Args:
        text (str): Input text to sanitize

    Returns:
        str: Sanitized text
    """
    if not text:
        return ""

    # Strip whitespace
    text = text.strip()

    # Escape all HTML-significant characters: & < > " '
    text = html.escape(text, quote=True)

    return text

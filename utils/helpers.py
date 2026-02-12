"""
Helper utility functions for the RFID Workshop Tool Monitoring System
"""
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename


def allowed_file(filename, allowed_extensions):
    """
    Check if file has an allowed extension
    
    Args:
        filename (str): Name of the file to check
        allowed_extensions (set): Set of allowed extensions
        
    Returns:
        bool: True if file extension is allowed, False otherwise
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


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
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    # Generate unique filename with timestamp and UUID
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    return f"{timestamp}_{unique_id}.{ext}" if ext else f"{timestamp}_{unique_id}"


def format_timestamp(timestamp):
    """
    Format Firestore timestamp to readable string
    
    Args:
        timestamp: Firestore timestamp object
        
    Returns:
        str: Formatted timestamp string
    """
    if timestamp:
        dt = timestamp.replace(tzinfo=None)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return ''


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


def sanitize_input(text):
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text (str): Input text to sanitize
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ''
    
    # Strip whitespace
    text = text.strip()
    
    # Remove any HTML tags (basic sanitization)
    # For production, consider using a library like bleach
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    
    return text

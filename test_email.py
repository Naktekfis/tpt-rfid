#!/usr/bin/env python3
"""
Test Email Script - Lab Fabrikasi
Simple script to test Flask-Mail configuration by sending a test email
"""

import os
from flask import Flask
from flask_mail import Mail, Message
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create minimal Flask app for email testing
app = Flask(__name__)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

# Initialize Flask-Mail
mail = Mail(app)

def send_test_email():
    """Send a test email to verify configuration"""
    
    recipient = "adrian.rachman.rustandi@gmail.com"
    
    print(f"🚀 Sending test email...")
    print(f"   From: {app.config['MAIL_DEFAULT_SENDER']}")
    print(f"   To: {recipient}")
    print(f"   Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
    print()
    
    try:
        with app.app_context():
            # Create test message with display name
            msg = Message(
                subject="[Test] Sistem Email Lab Fabrikasi ITB",
                sender=("Lab Fabrikasi Teknik Fisika ITB", app.config['MAIL_USERNAME']),
                recipients=[recipient],
                body="""Halo!

Ini adalah email test dari sistem monitoring Lab Fabrikasi ITB.

Jika Anda menerima email ini, berarti konfigurasi email sudah berhasil! ✅

Detail sistem:
- SMTP Server: smtp.gmail.com:587
- Sender: Lab Fabrikasi Teknik Fisika ITB
- Backend: Flask-Mail

Email ini dikirim secara otomatis untuk testing konfigurasi sistem.

Salam,
Tim Lab Fabrikasi
Teknik Fisika ITB
"""
            )
            
            # Send email
            mail.send(msg)
            
            print("✅ Email berhasil dikirim!")
            print(f"   Silakan cek inbox di {recipient}")
            return True
            
    except Exception as e:
        print(f"❌ Error mengirim email: {str(e)}")
        print()
        print("Troubleshooting:")
        print("1. Pastikan .env file ada dan berisi konfigurasi email yang benar")
        print("2. Pastikan MAIL_PASSWORD adalah App Password (bukan password Gmail biasa)")
        print("3. Pastikan koneksi internet stabil dan port 587 tidak diblok")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Lab Fabrikasi - Email Test Script")
    print("=" * 60)
    print()
    
    send_test_email()
    
    print()
    print("=" * 60)

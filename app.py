"""
RFID Workshop Tool Monitoring System - Main Flask Application
A touchscreen kiosk application for workshop tool borrowing using RFID cards
"""
import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename

from config import get_config
from utils import FirebaseHandler, allowed_file, generate_unique_filename, validate_nim, sanitize_input
from utils.rfid_mock import rfid_reader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(get_config())

# Initialize Firebase handler
try:
    firebase = FirebaseHandler()
    logger.info("Firebase handler initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {str(e)}")
    firebase = None

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ==================== Page Routes ====================

@app.route('/')
def index():
    """Welcome/landing page"""
    return render_template('welcome.html')


@app.route('/register')
def register():
    """Student registration page"""
    return render_template('register.html')


@app.route('/scan')
def scan():
    """Tool scanning/borrowing page"""
    return render_template('scan.html')


# ==================== API Routes ====================

@app.route('/api/check_rfid', methods=['GET'])
def check_rfid():
    """
    Check for RFID card (polling endpoint for registration page)
    Returns current UID if available
    """
    try:
        uid = rfid_reader.get_current_uid()
        
        if uid:
            return jsonify({
                'success': True,
                'uid': uid,
                'detected': True
            })
        else:
            return jsonify({
                'success': True,
                'uid': None,
                'detected': False
            })
            
    except Exception as e:
        logger.error(f"Error checking RFID: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to check RFID'
        }), 500


@app.route('/api/register', methods=['POST'])
def api_register():
    """Register new student"""
    try:
        # Get form data
        name = sanitize_input(request.form.get('name', ''))
        nim = sanitize_input(request.form.get('nim', ''))
        email = sanitize_input(request.form.get('email', ''))
        phone = sanitize_input(request.form.get('phone', ''))
        rfid_uid = request.form.get('rfid_uid', '')
        
        # Validate required fields
        if not all([name, nim, email, phone, rfid_uid]):
            return jsonify({
                'success': False,
                'error': 'Semua field harus diisi'
            }), 400
        
        # Validate NIM format
        if not validate_nim(nim):
            return jsonify({
                'success': False,
                'error': 'Format NIM tidak valid'
            }), 400
        
        # Check if NIM already exists
        existing_student = firebase.get_student_by_nim(nim)
        if existing_student:
            return jsonify({
                'success': False,
                'error': 'NIM sudah terdaftar'
            }), 400
        
        # Check if RFID UID already exists
        existing_rfid = firebase.get_student_by_uid(rfid_uid)
        if existing_rfid:
            return jsonify({
                'success': False,
                'error': 'Kartu RFID sudah terdaftar'
            }), 400
        
        # Handle photo upload
        photo_url = ''
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename:
                if not allowed_file(photo.filename, app.config['ALLOWED_EXTENSIONS']):
                    return jsonify({
                        'success': False,
                        'error': 'Format foto tidak valid. Gunakan PNG, JPG, atau JPEG'
                    }), 400
                
                # Save photo temporarily
                filename = generate_unique_filename(photo.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                photo.save(filepath)
                
                # Create student first to get ID
                student_data = {
                    'name': name,
                    'nim': nim,
                    'email': email,
                    'phone': phone,
                    'rfid_uid': rfid_uid,
                    'photo_url': ''  # Will be updated after upload
                }
                
                student = firebase.create_student(student_data)
                
                # Upload photo to Firebase Storage
                try:
                    photo_url = firebase.upload_photo(filepath, student['student_id'])
                    
                    # Update student with photo URL
                    firebase.db.collection('students').document(student['student_id']).update({
                        'photo_url': photo_url
                    })
                    
                    # Clean up temporary file
                    os.remove(filepath)
                    
                except Exception as e:
                    logger.error(f"Error uploading photo: {str(e)}")
                    # Continue without photo if upload fails
                    photo_url = ''
        else:
            # Create student without photo
            student_data = {
                'name': name,
                'nim': nim,
                'email': email,
                'phone': phone,
                'rfid_uid': rfid_uid,
                'photo_url': ''
            }
            student = firebase.create_student(student_data)
        
        # Clear RFID after successful registration
        rfid_reader.clear()
        
        return jsonify({
            'success': True,
            'message': 'Registrasi berhasil!',
            'student': {
                'student_id': student['student_id'],
                'name': name,
                'nim': nim
            }
        })
        
    except Exception as e:
        logger.error(f"Error in registration: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan saat registrasi'
        }), 500


@app.route('/api/scan_student', methods=['POST'])
def scan_student():
    """Fetch student data by RFID UID"""
    try:
        data = request.get_json()
        rfid_uid = data.get('rfid_uid', '')
        
        if not rfid_uid:
            return jsonify({
                'success': False,
                'error': 'UID tidak valid'
            }), 400
        
        # Get student from database
        student = firebase.get_student_by_uid(rfid_uid)
        
        if not student:
            return jsonify({
                'success': False,
                'error': 'Mahasiswa tidak terdaftar'
            }), 404
        
        return jsonify({
            'success': True,
            'student': student
        })
        
    except Exception as e:
        logger.error(f"Error scanning student: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan'
        }), 500


@app.route('/api/scan_tool', methods=['POST'])
def scan_tool():
    """Fetch tool data by RFID UID"""
    try:
        data = request.get_json()
        rfid_uid = data.get('rfid_uid', '')
        
        if not rfid_uid:
            return jsonify({
                'success': False,
                'error': 'UID tidak valid'
            }), 400
        
        # Get tool from database
        tool = firebase.get_tool_by_uid(rfid_uid)
        
        if not tool:
            return jsonify({
                'success': False,
                'error': 'Tool tidak terdaftar'
            }), 404
        
        return jsonify({
            'success': True,
            'tool': tool
        })
        
    except Exception as e:
        logger.error(f"Error scanning tool: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan'
        }), 500


@app.route('/api/borrow_tool', methods=['POST'])
def borrow_tool():
    """Create borrow transaction"""
    try:
        data = request.get_json()
        student_id = data.get('student_id', '')
        tool_id = data.get('tool_id', '')
        
        if not all([student_id, tool_id]):
            return jsonify({
                'success': False,
                'error': 'Data tidak lengkap'
            }), 400
        
        # Get student and tool data (for denormalization)
        student = firebase.db.collection('students').document(student_id).get().to_dict()
        tool = firebase.db.collection('tools').document(tool_id).get().to_dict()
        
        if not student or not tool:
            return jsonify({
                'success': False,
                'error': 'Data mahasiswa atau tool tidak valid'
            }), 404
        
        # Check if tool is available
        if tool['status'] != 'available':
            return jsonify({
                'success': False,
                'error': 'Tool sedang dipinjam'
            }), 400
        
        # Create borrow transaction
        transaction_data = {
            'student_id': student_id,
            'student_name': student['name'],
            'tool_id': tool_id,
            'tool_name': tool['name'],
            'borrow_time': datetime.now(),
            'return_time': None,
            'status': 'borrowed'
        }
        
        transaction = firebase.create_transaction(transaction_data)
        
        # Update tool status
        firebase.update_tool_status(tool_id, 'borrowed')
        
        return jsonify({
            'success': True,
            'message': 'Peminjaman berhasil!',
            'transaction': transaction
        })
        
    except Exception as e:
        logger.error(f"Error borrowing tool: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan'
        }), 500


@app.route('/api/return_tool', methods=['POST'])
def return_tool():
    """Create return transaction"""
    try:
        data = request.get_json()
        student_id = data.get('student_id', '')
        tool_id = data.get('tool_id', '')
        
        if not all([student_id, tool_id]):
            return jsonify({
                'success': False,
                'error': 'Data tidak lengkap'
            }), 400
        
        # Find active borrow transaction
        active_borrow = firebase.get_active_borrow(student_id, tool_id)
        
        if not active_borrow:
            return jsonify({
                'success': False,
                'error': 'Tidak ada peminjaman aktif untuk tool ini'
            }), 400
        
        # Update transaction to returned
        firebase.update_transaction_return(active_borrow['transaction_id'])
        
        # Update tool status
        firebase.update_tool_status(tool_id, 'available')
        
        return jsonify({
            'success': True,
            'message': 'Pengembalian berhasil!'
        })
        
    except Exception as e:
        logger.error(f"Error returning tool: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan'
        }), 500


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get recent transactions"""
    try:
        limit = request.args.get('limit', 5, type=int)
        transactions = firebase.get_recent_transactions(limit)
        
        # Convert timestamps to strings for JSON serialization
        for trans in transactions:
            if 'borrow_time' in trans and trans['borrow_time']:
                trans['borrow_time'] = trans['borrow_time'].strftime('%Y-%m-%d %H:%M:%S')
            if 'return_time' in trans and trans['return_time']:
                trans['return_time'] = trans['return_time'].strftime('%Y-%m-%d %H:%M:%S')
            if 'created_at' in trans and trans['created_at']:
                trans['created_at'] = trans['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            'success': True,
            'transactions': transactions
        })
        
    except Exception as e:
        logger.error(f"Error getting transactions: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan'
        }), 500


# ==================== Debug/Development Routes ====================

@app.route('/debug/scan', methods=['GET'])
def debug_scan():
    """Debug endpoint to simulate RFID scan"""
    uid = request.args.get('uid', '')
    
    if uid:
        rfid_reader.simulate_scan(uid)
        return jsonify({
            'success': True,
            'message': f'Simulated scan of UID: {uid}',
            'uid': uid
        })
    else:
        return jsonify({
            'success': False,
            'error': 'No UID provided'
        }), 400


@app.route('/debug/clear', methods=['GET'])
def debug_clear():
    """Debug endpoint to clear RFID"""
    rfid_reader.clear()
    return jsonify({
        'success': True,
        'message': 'RFID cleared'
    })


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('welcome.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'Terjadi kesalahan server'
    }), 500


# ==================== Main ====================

if __name__ == '__main__':
    # Run the application
    # For production, use gunicorn or similar WSGI server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=app.config['DEBUG']
    )

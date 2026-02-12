# Lab Fabrikasi ITB - RFID Tool Monitoring System

Sistem peminjaman alat workshop berbasis RFID untuk Lab Fabrikasi Teknik Fisika ITB.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## 🚀 Quick Setup (Raspberry Pi)

### 1. Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and pip
sudo apt install python3 python3-pip python3-venv -y

# Install Git (if not installed)
sudo apt install git -y
```

### 2. Clone Repository
```bash
cd ~
git clone https://github.com/Naktekfis/tpt-rfid.git
cd tpt-rfid
```

### 3. Setup Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Firebase Configuration

1. **Download Service Account Key:**
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Select your project
   - Go to Project Settings → Service Accounts
   - Click "Generate New Private Key"
   - Save as `serviceAccountKey.json` in project root

2. **Create `.env` file:**
```bash
cp .env.example .env
nano .env
```

3. **Edit `.env`:**
```env
FLASK_SECRET_KEY=your-secret-key-here
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
DEBUG=False
```

### 5. Seed Database (First Time Only)
```bash
python seed_database.py
```

### 6. Run Application
```bash
# Development
python app.py

# Production (recommended for Raspberry Pi)
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

Access at: `http://localhost:5000` or `http://<raspberry-pi-ip>:5000`

---

## 🔧 Production Setup (Auto-start on Boot)

### Create systemd service
```bash
sudo nano /etc/systemd/system/tpt-rfid.service
```

**Paste this:**
```ini
[Unit]
Description=TPT RFID Tool Monitoring System
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/tpt-rfid
Environment="PATH=/home/pi/tpt-rfid/venv/bin"
ExecStart=/home/pi/tpt-rfid/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl enable tpt-rfid
sudo systemctl start tpt-rfid
sudo systemctl status tpt-rfid
```

---

## 📁 Project Structure

```
tpt-rfid/
├── app.py                  # Main Flask application
├── config.py              # Configuration management
├── seed_database.py       # Database seeding script
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create from .env.example)
├── serviceAccountKey.json # Firebase credentials (download from console)
├── templates/             # HTML templates
│   ├── base.html
│   ├── welcome.html
│   ├── register.html
│   └── scan.html
├── static/
│   ├── css/              # Custom styles
│   ├── js/               # JavaScript logic
│   └── assets/           # Images and icons
└── utils/
    ├── firebase_handler.py  # Firebase operations
    ├── rfid_reader.py       # RFID mock utility
    └── helpers.py           # Utility functions
```

---

## 🎯 Usage

### Register New Student
1. Go to **Registrasi** page
2. Fill in form (Name, NIM, Email, Phone)
3. Upload photo
4. Tap RFID card (use **console**: `simulateRFID('student_uid')`)
5. Click **Daftar**

### Borrow/Return Tool
1. Go to **Scan** page
2. Tap student KTM
3. Tap tool RFID tag
4. Click **Confirm Pinjam** or **Confirm Kembalikan**

### Debug (Development)
Open browser console:
```javascript
// Simulate student RFID
simulateRFID('123ABC456')

// Simulate tool RFID
simulateRFID('TOOL001')

// Clear RFID
clearRFID()
```

---

## 🛠️ Troubleshooting

**Port already in use:**
```bash
sudo lsof -i :5000
sudo kill -9 <PID>
```

**Permission denied on Raspberry Pi:**
```bash
chmod +x app.py
```

**Firebase connection error:**
- Check `serviceAccountKey.json` exists
- Verify `.env` has correct `FIREBASE_STORAGE_BUCKET`
- Check internet connection

**Service not starting:**
```bash
sudo journalctl -u tpt-rfid -f
```

---

## 📝 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Flask session secret | `your-random-secret-key` |
| `FIREBASE_STORAGE_BUCKET` | Firebase storage bucket | `project-id.appspot.com` |
| `DEBUG` | Debug mode (True/False) | `False` |

---

## 🔐 Security Notes

**Before deploying:**
1. ✅ Change `FLASK_SECRET_KEY` in `.env`
2. ✅ Set `DEBUG=False` in production
3. ✅ Never commit `serviceAccountKey.json` (already in `.gitignore`)
4. ✅ Never commit `.env` file (already in `.gitignore`)

---

## 📄 License

MIT License - see LICENSE file for details.

---

## 👨‍💻 Developer

Lab Fabrikasi Teknik Fisika ITB

**Tech Stack:**
- Backend: Flask (Python)
- Database: Firebase Firestore
- Storage: Firebase Storage
- Frontend: Tailwind CSS + Vanilla JS
- Deployment: Raspberry Pi + systemd

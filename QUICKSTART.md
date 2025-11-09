# Quick Start Guide - Face Attendance System

## 🚀 Complete Setup in 5 Steps

### Step 1: Install Dependencies

```bash
# System packages
sudo apt update
sudo apt install -y python3-pip python3-opencv cmake build-essential
sudo apt install -y libopenblas-dev liblapack-dev libatlas-base-dev gfortran

# Python packages
pip3 install -r requirements.txt
```

### Step 2: Download Anti-Spoof Model

```bash
# If not already present
wget https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth
```

### Step 3: Configure Backend URLs

Edit `attendance_server.py`:
- Set `BACKEND_WEBHOOK_URL` (line 31)
- Set `WEBHOOK_ACCESS_KEY` (line 32)

Edit `sync_faces.py`:
- Set `REMOTE_URL` (line 17)

### Step 4: Start the Server

```bash
python3 attendance_server.py
```

✅ Done! The system will:
1. Sync faces from backend
2. Start face recognition
3. Upload attendance every 10 minutes

### Step 5: Access the System

- **API Status**: http://raspberrypi:8000
- **API Docs**: http://raspberrypi:8000/docs
- **Today's Attendance**: http://raspberrypi:8000/attendance/today

---

## 🎯 Production Setup (Auto-start on Boot)

### Create Systemd Service

```bash
sudo nano /etc/systemd/system/attendance-server.service
```

Paste this:

```ini
[Unit]
Description=Face Attendance Server with Backend Sync
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/camera
ExecStart=/usr/bin/python3 /home/pi/camera/attendance_server.py
Restart=always
RestartSec=10
StandardOutput=append:/home/pi/camera/server.log
StandardError=append:/home/pi/camera/server.log

[Install]
WantedBy=multi-user.target
```

### Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable attendance-server.service
sudo systemctl start attendance-server.service

# Check status
sudo systemctl status attendance-server.service

# View logs
tail -f server.log
```

---

## 📊 How It Works

```
1. Server starts → Syncs faces from backend
                ↓
2. Launches face_attendance.py (camera + recognition)
                ↓
3. Students stand in front of camera
                ↓
4. System detects face → Checks liveness → Marks IN/OUT
                ↓
5. Saves to attendance_YYYY-MM-DD.csv locally
                ↓
6. Every 10 minutes → Uploads CSV to backend webhook
                ↓
7. Backend stores in MongoDB
```

---

## 🔧 Useful Commands

### Manual Operations

```bash
# Trigger manual face sync
curl -X POST http://raspberrypi:8000/sync/manual

# Trigger manual attendance upload
curl -X POST http://raspberrypi:8000/upload/manual

# Restart face recognition
curl -X POST http://raspberrypi:8000/attendance/restart

# Check today's attendance
curl http://raspberrypi:8000/attendance/today

# Check system status
curl http://raspberrypi:8000/status
```

### Logs

```bash
# View server logs
tail -f server.log

# View systemd logs
sudo journalctl -u attendance-server.service -f

# View attendance CSV
cat attendance_$(date +%Y-%m-%d).csv
```

---

## ⚙️ Configuration

### Adjust Timing

Edit `attendance_server.py`:

```python
SYNC_INTERVAL_MINUTES = 5    # How often to sync faces
UPLOAD_INTERVAL_MINUTES = 10  # How often to upload attendance
```

### Change Backend

Edit `attendance_server.py`:

```python
BACKEND_WEBHOOK_URL = "http://your-backend.com/webhook/"
WEBHOOK_ACCESS_KEY = "your_secret_key"
```

Edit `sync_faces.py`:

```python
REMOTE_URL = "http://your-backend.com/media/students?key=yourkey"
```

---

## 🐛 Troubleshooting

### Problem: Server won't start

```bash
# Check if port 8000 is in use
sudo lsof -i :8000

# Kill existing process
sudo kill -9 <PID>

# Restart
python3 attendance_server.py
```

### Problem: Face sync fails

```bash
# Test URL manually
curl "http://vdm.csceducation.net/media/students?key=accessvdmfile"

# Run sync manually with debug
python3 sync_faces.py
```

### Problem: Attendance upload fails

```bash
# Check webhook manually
curl -X POST \
  -H "X-Webhook-Key: vdm_attendance_webhook_2025" \
  -F "file=@attendance_$(date +%Y-%m-%d).csv" \
  http://vdm.csceducation.net/attendance/webhook/daily-attendance/
```

### Problem: Camera not working

```bash
# Check camera
libcamera-hello

# Test picamera2
python3 -c "from picamera2 import Picamera2; print('OK')"
```

### Problem: No faces detected

```bash
# Check cached faces
ls -lR cached_faces/

# Test with diagnostic tool
python3 face_detection.py
```

---

## 📁 Directory Structure

```
camera/
├── attendance_server.py       # FastAPI entry point
├── face_attendance.py          # Face recognition engine
├── sync_faces.py              # Face sync worker
├── face_detection.py          # Diagnostic tool
├── requirements.txt           # Python dependencies
├── 2.7_80x80_MiniFASNetV2.pth # Anti-spoof model
├── cached_faces/              # Synced student faces
│   ├── 23040453/
│   │   └── photo.png
│   ├── 23040454/
│   │   └── image.jpg
│   └── .cache_metadata.json
├── attendance_2025-11-09.csv  # Daily attendance logs
├── server.log                 # Server logs
└── README.md                  # Full documentation
```

---

## 🎓 Student Roll Numbers

The system uses folder names as student identifiers:

```
cached_faces/
├── 23040453/photo.png  → Student ID: 23040453
├── 23040454/image.jpg  → Student ID: 23040454
└── 23040455/face.png   → Student ID: 23040455
```

Attendance CSV:
```csv
name,status,timestamp
23040453,IN,2025-11-09 09:30:00
23040453,OUT,2025-11-09 17:45:00
```

---

## 📡 Backend Webhook Format

The system sends CSV data in this format:

```csv
enrollment_number,status,timestamp
23040453,in,2025-11-09 09:30:00
23040453,out,2025-11-09 17:45:00
23040454,in,2025-11-09 09:35:00
```

Backend response:
```json
{
  "success": true,
  "summary": {
    "total_rows": 3,
    "successful": 3,
    "failed": 0,
    "duplicates": 0
  }
}
```

See `WEBHOOK_API_DOCUMENTATION.md` for full API details.

---

## ✅ Verification Checklist

After setup, verify:

- [ ] `python3 attendance_server.py` starts without errors
- [ ] `cached_faces/` directory has student images
- [ ] `http://raspberrypi:8000` shows server status
- [ ] Camera preview window appears
- [ ] Face detection works (green box around face)
- [ ] Attendance CSV file created
- [ ] Attendance uploaded to backend (check logs)
- [ ] Systemd service starts on boot

---

## 🔐 Security Notes

1. **Change webhook key**: Update `WEBHOOK_ACCESS_KEY` in production
2. **Use HTTPS**: Enable SSL/TLS for production
3. **Firewall**: Restrict port 8000 access
4. **Logs**: Rotate logs regularly to prevent disk fill
5. **Backups**: Backup attendance CSV files daily

---

## 📞 Support

For issues:
1. Check server logs: `tail -f server.log`
2. Check systemd logs: `sudo journalctl -u attendance-server.service -f`
3. Test individual components (sync_faces.py, face_attendance.py)
4. Verify backend connectivity
5. Review WEBHOOK_API_DOCUMENTATION.md

---

**Ready to deploy! 🎉**

"# Face Attendance System with Backend Sync

Production-ready face recognition attendance system for Raspberry Pi 5 with automatic backend sync and webhook integration.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Backend Server (VDM)                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  File Browser: /media/students                       │   │
│  │  - rollnumber1/photo.png                             │   │
│  │  - rollnumber2/image.jpg                             │   │
│  │  (Updates when new students added)                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Webhook API: /attendance/webhook/daily-attendance/  │   │
│  │  - Receives attendance CSV data                      │   │
│  │  - Stores in MongoDB                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────┬───────────────────┘
                     │                    │
         Download faces (every 5 min)     │ Upload attendance (every 10 min)
                     │                    │
                     ▼                    │
┌─────────────────────────────────────────────────────────────┐
│  Raspberry Pi 5 - FastAPI Attendance Server                 │
│  http://raspberrypi:8000                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  attendance_server.py (Entry Point)                  │   │
│  │  1. Sync faces at startup                            │   │
│  │  2. Start face_attendance.py                         │   │
│  │  3. Periodic sync (every 5 min)                      │   │
│  │  4. Upload attendance CSV (every 10 min)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  sync_faces.py (Background Worker)                   │   │
│  │  - Recursively scans file browser                    │   │
│  │  - Mirrors directory structure (rollnumber/photo)    │   │
│  │  - Smart incremental updates                         │   │
│  │  - Cleanup deleted students                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  cached_faces/                                       │   │
│  │  ├── 23040453/photo.png                              │   │
│  │  ├── 23040454/image.jpg                              │   │
│  │  └── .cache_metadata.json                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  face_attendance.py (Recognition Engine)             │   │
│  │  - PiCamera2 live video capture                      │   │
│  │  - CNN face detection                                │   │
│  │  - Anti-spoof (MiniFASNetV2)                         │   │
│  │  - Liveness detection (blink/motion)                 │   │
│  │  - IN/OUT tracking                                   │   │
│  │  - Daily CSV logging                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  attendance_YYYY-MM-DD.csv                           │   │
│  │  name,status,timestamp                               │   │
│  │  23040453,IN,2025-11-09 09:30:00                     │   │
│  │  23040453,OUT,2025-11-09 17:45:00                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     └────────────────────────────────────────┘
│                                  Uploaded to backend (every 10 min)
└─────────────────────────────────────────────────────────────┘
```

## Features

## Features

- ✅ **FastAPI Server**: Central entry point with REST API
- ✅ **Auto Sync**: Downloads faces at startup and every 5 minutes
- ✅ **Auto Upload**: Sends attendance CSV to backend every 10 minutes
- ✅ **Webhook Integration**: Compatible with VDM backend API
- ✅ **Recursive Scanning**: Automatically discovers student directories
- ✅ **Directory Mirroring**: Preserves rollnumber/photo.png structure
- ✅ **Face Recognition**: CNN detection with face_recognition library
- ✅ **Anti-Spoof**: MiniFASNetV2 model prevents photo/video attacks
- ✅ **Liveness Detection**: MediaPipe blink and motion detection
- ✅ **IN/OUT Tracking**: Alternates between entry and exit
- ✅ **Daily CSV Logs**: Stores attendance locally before upload
- ✅ **Smart Updates**: Only downloads changed files
- ✅ **Auto Cleanup**: Removes deleted students automatically
- ✅ **HTTP/HTTPS Support**: Works with self-signed certificates
- ✅ **REST API**: Monitor status, trigger manual sync/upload
- ✅ **Raspberry Pi Optimized**: Designed for Raspberry Pi 5

## Installation (Raspberry Pi 5)

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-opencv
sudo apt install -y cmake build-essential
sudo apt install -y libopenblas-dev liblapack-dev libatlas-base-dev gfortran
sudo apt install -y libhdf5-dev libhdf5-serial-dev libharfbuzz0b libwebp7 libjasper1
sudo apt install -y libqtgui4 libqtwebkit4 libqt4-test libilmbase-dev libopenexr-dev
```

### 2. Install Python Packages

```bash
# Install all dependencies
pip3 install -r requirements.txt

# Or install manually
pip3 install opencv-python face_recognition numpy imutils
pip3 install torch torchvision mediapipe picamera2
pip3 install fastapi uvicorn requests
```

**Note:** On Raspberry Pi, `dlib` (required by face_recognition) may take 20-30 minutes to compile. Be patient!

### 3. Download Anti-Spoof Model

Download the MiniFASNetV2 model (if not already present):

```bash
wget https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth
```

### 4. Configure Backend URLs

Edit `attendance_server.py` and configure:

```python
BACKEND_WEBHOOK_URL = "http://vdm.csceducation.net/attendance/webhook/daily-attendance/"
WEBHOOK_ACCESS_KEY = "vdm_attendance_webhook_2025"
```

Edit `sync_faces.py` and configure:

```python
REMOTE_URL = "http://vdm.csceducation.net/media/students?key=accessvdmfile"
```

## Usage

### Option 1: FastAPI Server (Recommended - Production)

Start the complete system with one command:

```bash
python3 attendance_server.py
```

This will:
1. ✅ Sync faces from backend at startup
2. ✅ Start face_attendance.py for recognition
3. ✅ Sync faces every 5 minutes in background
4. ✅ Upload attendance CSV every 10 minutes to backend
5. ✅ Provide REST API at http://raspberrypi:8000

**Access API Documentation:**
- http://raspberrypi:8000/docs (Swagger UI)
- http://raspberrypi:8000 (Status)

### Option 2: Manual Mode (Testing/Development)

#### Step 1: Initial Sync

```bash
python3 sync_faces.py
```

#### Step 2: Start Attendance System

```bash
python3 face_attendance.py
```

### Option 3: Systemd Service (Auto-start on Boot)

Create a systemd service for the FastAPI server:

```bash
# Create service file
sudo nano /etc/systemd/system/attendance-server.service
```

Add this content:

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

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable attendance-server.service
sudo systemctl start attendance-server.service

# Check status
sudo systemctl status attendance-server.service

# View live logs
tail -f server.log
```

The server will:
- Start automatically on boot
- Sync faces every 5 minutes
- Upload attendance every 10 minutes
- Restart automatically if crashes
- Log all operations to `server.log`

## REST API Endpoints

The FastAPI server provides these endpoints:

### GET /
Server status and uptime
```bash
curl http://raspberrypi:8000/
```

### GET /status
Detailed system status
```bash
curl http://raspberrypi:8000/status
```

### GET /attendance/today
Get today's attendance records
```bash
curl http://raspberrypi:8000/attendance/today
```

### POST /sync/manual
Manually trigger face sync
```bash
curl -X POST http://raspberrypi:8000/sync/manual
```

### POST /upload/manual
Manually upload attendance to backend
```bash
curl -X POST http://raspberrypi:8000/upload/manual
```

### POST /attendance/restart
Restart face attendance system
```bash
curl -X POST http://raspberrypi:8000/attendance/restart
```

## Configuration

### Adjust Sync/Upload Intervals

Edit `attendance_server.py`:

```python
SYNC_INTERVAL_MINUTES = 5    # Sync faces every 5 minutes
UPLOAD_INTERVAL_MINUTES = 10  # Upload attendance every 10 minutes
```

### Change Backend URLs

Edit `attendance_server.py`:

```python
BACKEND_WEBHOOK_URL = "http://vdm.csceducation.net/attendance/webhook/daily-attendance/"
WEBHOOK_ACCESS_KEY = "vdm_attendance_webhook_2025"
```

Edit `sync_faces.py`:

```python
REMOTE_URL = "http://vdm.csceducation.net/media/students?key=accessvdmfile"
# Single sync (one-time)
python3 sync_faces.py

# Continuous mode with default interval (5 minutes)
python3 sync_faces.py --continuous

# Continuous mode with custom interval (2 minutes)
python3 sync_faces.py --continuous --interval 120

# Continuous mode with faster polling (30 seconds) - for testing
python3 sync_faces.py --continuous --interval 30
```

## Automated Continuous Sync

### Systemd Service (Recommended for Production)

The included `face-sync.service` file provides:
- Automatic startup on boot
- Continuous sync every 5 minutes
- Auto-restart on failure
- Proper logging

**Setup:**

1. Copy and configure service:
```bash
sudo cp face-sync.service /etc/systemd/system/
sudo nano /etc/systemd/system/face-sync.service  # Adjust paths if needed
```

2. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-sync.service
sudo systemctl start face-sync.service
```

3. Monitor:
```bash
# Check status
sudo systemctl status face-sync.service

# View logs
tail -f sync.log

# Stop/restart
sudo systemctl stop face-sync.service
sudo systemctl restart face-sync.service
```

### Alternative: Cron (Simple but less robust)

If you prefer cron instead of systemd:

```bash
crontab -e
```

Add this line to sync every 5 minutes:
```cron
*/5 * * * * cd /home/pi/camera && /usr/bin/python3 sync_faces.py >> sync.log 2>&1
```

**Note:** Cron is simpler but systemd provides better process management, logging, and auto-restart.

## Configuration

### Sync Settings

In `sync_faces.py`:

```python
REMOTE_URL = "http://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"
DEFAULT_SYNC_INTERVAL = 300  # 5 minutes in seconds
```

**How it works with file browser:**
- The script recursively scans the file browser at `REMOTE_URL`
- Discovers all subdirectories (e.g., rollnumber1/, rollnumber2/)
- Downloads images found in each directory
- Preserves the exact directory structure locally
- Example: `rollnumber1/photo.png` → `cached_faces/rollnumber1/photo.png`

**Recommended intervals based on usage:**
- **High frequency updates** (students added often): 120-180 seconds (2-3 minutes)
- **Normal usage**: 300 seconds (5 minutes) - **Default**
- **Low frequency updates**: 600-900 seconds (10-15 minutes)

### Face Detection Settings

In `face_detection.py`:

```python
KNOWN_FACES_SOURCE = "http://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"
```

**For local directory instead of remote:**
```python
KNOWN_FACES_SOURCE = "known_faces"  # Use local directory
```

**Directory structure for face recognition:**
- Each subdirectory in the cache represents a person/student
- Directory name (e.g., "rollnumber1") is used as the person's identifier
- Multiple images per person are supported (all images in that directory)
- Example structure:
  ```
  cached_faces/
  ├── 12345/
  │   ├── photo.png
  │   └── photo2.jpg
  ├── 67890/
  │   └── image.png
  └── .cache_metadata.json
  ```

## Directory Structure

```
camera/
├── face_detection.py          # Main diagnostic/attendance script
├── sync_faces.py              # Background sync service
├── face-sync.service          # Systemd service configuration
├── README.md                  # This file
├── cached_faces/              # Auto-generated cache directory (mirrors remote)
│   ├── rollnumber1/           # Student directory (from remote)
│   │   ├── photo.png
│   │   └── photo2.jpg
│   ├── rollnumber2/           # Another student
│   │   └── image.png
│   ├── 12345/                 # Yet another student
│   │   └── face.jpg
│   └── .cache_metadata.json   # Sync metadata (timestamps, counts)
├── known_faces/               # Optional local faces directory
│   └── person_name/
│       └── image.jpg
└── sync.log                   # Sync operation logs
```

## How It Works

### Continuous Sync Mode (Recommended)

1. **Background Service Runs:**
   - `sync_faces.py --continuous` runs as systemd service
   - Every 5 minutes (or configured interval):

2. **Smart Sync Process:**
   - Recursively scans file browser at backend URL
   - Discovers all subdirectories (e.g., student roll numbers)
   - Compares with local cache
   - Downloads only new/updated images (checks file size)
   - Removes images/directories no longer on backend
   - **Preserves exact directory structure** (rollnumber/photo.png)
   - Updates `.cache_metadata.json`

3. **Attendance System:**
   - Runs `face_detection.py` (or your main app)
   - Reads from local `cached_faces/` with subdirectories
   - Each subdirectory = one person/student
   - Subdirectory name = student identifier (e.g., roll number)
   - No network delay - instant face recognition
   - Cache is always fresh (within sync interval)

### Example Flow

**Remote file browser structure:**
```
http://vdm.csceducation.net/media/students/
├── 12345/
│   └── photo.png
├── 67890/
│   └── image.jpg
└── 54321/
    ├── face1.png
    └── face2.jpg
```

**Local cached structure (after sync):**
```
cached_faces/
├── 12345/
│   └── photo.png
├── 67890/
│   └── image.jpg
├── 54321/
│   ├── face1.png
│   └── face2.jpg
└── .cache_metadata.json
```

**Face detection processes:**
- Student "12345" → checks photo.png
- Student "67890" → checks image.jpg
- Student "54321" → checks both face1.png and face2.jpg

### Benefits of This Architecture

✅ **Fast:** Local file access, no network latency during recognition  
✅ **Reliable:** Works offline between syncs  
✅ **Efficient:** Only downloads changes, not entire dataset  
✅ **Automatic:** Systemd ensures sync keeps running  
✅ **Fresh:** Regular updates ensure new students appear quickly  
✅ **Clean:** Old students automatically removed from cache  
✅ **Organized:** Directory structure mirrors remote (student roll numbers preserved)  
✅ **Scalable:** Handles unlimited students/subdirectories  
✅ **Flexible:** Works with any file browser structure

## Troubleshooting

### Sync service not running
Check service status:
```bash
sudo systemctl status face-sync.service
journalctl -u face-sync.service -f
```

Restart if needed:
```bash
sudo systemctl restart face-sync.service
```

### Cache not updating
1. Check if sync service is running: `systemctl status face-sync.service`
2. Check sync logs: `tail -f sync.log`
3. Verify network connectivity: `ping vdm.csceducation.net`
4. Test manual sync: `python3 sync_faces.py`

### "Cache is X minutes old" warning
- If sync service is running, this is normal (max = sync interval)
- If >10 minutes old and service running, check logs for errors
- If service stopped, restart it

### Images not appearing in attendance system
1. Check cache directory: `ls -la cached_faces/remote_students/`
2. Check metadata: `cat cached_faces/.cache_metadata.json`
3. Verify sync is working: `tail -f sync.log`
4. Run manual sync to test: `python3 sync_faces.py`

### High network usage
- Increase sync interval (default: 300s = 5 minutes)
- Check if backend is returning proper Content-Length headers
- Monitor with: `grep "Sync complete" sync.log`

### "dlib" installation fails
The face_recognition library requires dlib, which compiles from source on Raspberry Pi:
- Ensure you have at least 2GB free RAM
- Installation takes 20-30 minutes on Pi 5
- If it fails, try: `pip3 install --no-cache-dir dlib`

### CNN model is too slow
The script uses CNN for accuracy. If too slow:
- It automatically falls back to HOG model
- Both models are tested for each image

## Performance Tips for Raspberry Pi 5

1. **Use continuous sync service:** More reliable than cron, auto-restarts on failure
2. **Optimize sync interval:** Balance freshness vs network usage (5 min recommended)
3. **Local cache is key:** Face recognition uses local files = no network delay
4. **Monitor resource usage:** `htop` to check CPU/RAM during sync
5. **Limit image resolution on backend:** Smaller images = faster download & processing
6. **Use systemd journal for logs:** `journalctl -u face-sync.service -f`

## Quick Start Checklist

- [ ] Install dependencies: `pip3 install opencv-python face_recognition numpy`
- [ ] Configure `REMOTE_URL` in `sync_faces.py`
- [ ] Run first sync: `python3 sync_faces.py`
- [ ] Verify cache: `ls cached_faces/remote_students/`
- [ ] Set up systemd service: `sudo cp face-sync.service /etc/systemd/system/`
- [ ] Start service: `sudo systemctl enable --now face-sync.service`
- [ ] Check service: `sudo systemctl status face-sync.service`
- [ ] Test face detection: `python3 face_detection.py`
- [ ] Monitor logs: `tail -f sync.log`

## Example Output

### Sync Service (every 5 minutes)
```
[2025-11-09 10:00:15] Starting face sync...
  Source: http://vdm.csceducation.net/media/students?key=accessvdmfile
  Cache: cached_faces
  🔍 Scanning file browser for images (recursive)...
  Found 47 image(s) from backend
  ↓ Downloaded: 12345/photo.png
  ↓ Downloaded: 67890/image.jpg
  ↻ Updated: 54321/face1.png
  🗑 Removed: oldstudent/photo.jpg
  🗑 Removed empty dir: oldstudent
  ✅ Sync complete: 2 new, 1 updated, 43 unchanged, 1 removed, 0 failed

  💤 Waiting 300 seconds until next sync...
```

### Face Detection (uses cached files)
```
======================================================================
FACE IMAGE DIAGNOSTIC TOOL
======================================================================
🔗 Remote known-faces source: http://vdm.csceducation.net/...
  ℹ️  Using cached files from: cached_faces
  ℹ️  Note: Ensure sync_faces.py is running to keep cache updated

  📊 Cache status:
     Last synced: 2025-11-09 10:00:15 (2 minutes ago)
     Images cached: 47
  ✅ Cache is fresh

======================================================================
👤 Person: 12345
======================================================================
  Found 1 image file(s)

📄 Checking: cached_faces/12345/photo.png
  📐 Image size: 640x480 pixels
  🔍 Detecting faces with CNN model...
  ✅ CNN model detected 1 face(s)
  ✅ Generated 1 face encoding(s)

======================================================================
👤 Person: 67890
======================================================================
  Found 1 image file(s)

📄 Checking: cached_faces/67890/image.jpg
  📐 Image size: 800x600 pixels
  🔍 Detecting faces with CNN model...
  ✅ CNN model detected 1 face(s)
  ✅ Generated 1 face encoding(s)
```

## License

MIT
" 

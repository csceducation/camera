"# Camera Face Detection System

Face detection diagnostic tool with continuous sync from backend API for Raspberry Pi 5 attendance system.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Backend Server (VDM) - File Browser                        │
│  http://vdm.csceducation.net/media/students                 │
│  - Directory structure with student roll numbers            │
│  - Example: rollnumber1/photo.png, rollnumber2/image.jpg    │
│  - Updates when new students are added                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ HTTP(S) - Every 5 minutes
                     │ (Recursive directory scan + sync)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Raspberry Pi 5 - Attendance Device                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  sync_faces.py (Background Service)                  │   │
│  │  - Recursively scans file browser structure          │   │
│  │  - Mirrors directory structure locally               │   │
│  │  - Downloads new/updated images                      │   │
│  │  - Removes deleted students/images                   │   │
│  │  - Maintains local cache with same structure         │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  cached_faces/                                       │   │
│  │  ├── rollnumber1/photo.png                           │   │
│  │  ├── rollnumber2/image.jpg                           │   │
│  │  ├── rollnumber3/photo.png                           │   │
│  │  └── .cache_metadata.json                            │   │
│  │  (Mirrors remote directory structure exactly)        │   │
│  └──────────────────────────────────────────────────────┘   │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Attendance System (face_detection.py / main app)    │   │
│  │  - Uses local cached images for face recognition     │   │
│  │  - Each subdirectory = student/person name           │   │
│  │  - Real-time processing (no network delay)           │   │
│  │  - Marks attendance based on detected faces          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Features

- ✅ Recursive file browser scanning (automatically discovers subdirectories)
- ✅ Preserves directory structure (rollnumber/photo.png → cached_faces/rollnumber/photo.png)
- ✅ Continuous sync from backend API (every 2-5 minutes, configurable)
- ✅ Smart incremental updates (only downloads changed files)
- ✅ Automatic cleanup (removes deleted students/directories)
- ✅ Face detection using OpenCV and face_recognition library
- ✅ Local cache for fast, offline face recognition
- ✅ Works with HTTP and HTTPS (including self-signed certificates)
- ✅ Systemd service for reliable background operation
- ✅ Optimized for Raspberry Pi 5

## Installation (Raspberry Pi 5)

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-opencv
sudo apt install -y cmake build-essential
sudo apt install -y libopenblas-dev liblapack-dev
sudo apt install -y libatlas-base-dev gfortran
```

### 2. Install Python Packages

```bash
pip3 install opencv-python face_recognition numpy
```

**Note:** On Raspberry Pi, `dlib` (required by face_recognition) may take 20-30 minutes to compile. Be patient!

### 3. Configure Remote Source

Edit `face_detection.py` and set your remote URL:

```python
KNOWN_FACES_SOURCE = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
```

Or keep it as a local directory:

```python
KNOWN_FACES_SOURCE = "known_faces"
```

## Usage

### 1. Initial Setup - Run First Sync

Before starting the attendance system, sync images once:

```bash
python3 sync_faces.py
```

This will download all face images to `cached_faces/remote_students/`.

### 2. Start Background Sync Service (Recommended)

Enable continuous sync as a background service:

```bash
# Copy service file
sudo cp face-sync.service /etc/systemd/system/

# Edit paths if needed (change /home/pi/camera to your actual path)
sudo nano /etc/systemd/system/face-sync.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable face-sync.service
sudo systemctl start face-sync.service

# Check status
sudo systemctl status face-sync.service

# View live logs
tail -f sync.log
```

The service will:
- Start automatically on boot
- Sync every 5 minutes (configurable)
- Restart automatically if it crashes
- Log all operations to `sync.log`

### 3. Run Face Detection

Now your attendance system can use the cached images:

```bash
python3 face_detection.py
```

This will:
- Use locally cached images (fast, no network delay)
- Show cache status (last sync time, number of images)
- Check all faces for validity
- Display detailed diagnostics

### Manual Sync Options

```bash
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

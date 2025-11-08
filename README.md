"# Camera Face Detection System

Face detection diagnostic tool with remote image syncing support for Raspberry Pi 5.

## Features

- ✅ Face detection using OpenCV and face_recognition library
- ✅ Supports both local directories and remote URLs
- ✅ Automatic twice-daily sync from remote sources
- ✅ Smart caching to minimize network usage
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

### Manual Face Detection Check

```bash
python3 face_detection.py
```

This will:
- Sync images from remote URL (if configured) when cache is stale
- Check all faces for validity
- Display detailed diagnostics

### Manual Sync

Force a sync from the remote source:

```bash
python3 sync_faces.py
```

## Automated Twice-Daily Sync

### Option 1: Using Cron (Recommended for Raspberry Pi)

Edit your crontab:

```bash
crontab -e
```

Add this line to sync at 6 AM and 6 PM every day:

```cron
0 6,18 * * * cd /home/pi/camera && /usr/bin/python3 sync_faces.py >> sync.log 2>&1
```

Adjust the path `/home/pi/camera` to match your project location.

### Option 2: Using systemd Timer

Create `/etc/systemd/system/face-sync.service`:

```ini
[Unit]
Description=Sync face images from remote source

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/camera
ExecStart=/usr/bin/python3 /home/pi/camera/sync_faces.py
StandardOutput=append:/home/pi/camera/sync.log
StandardError=append:/home/pi/camera/sync.log
```

Create `/etc/systemd/system/face-sync.timer`:

```ini
[Unit]
Description=Run face sync twice daily

[Timer]
OnCalendar=06:00
OnCalendar=18:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl enable face-sync.timer
sudo systemctl start face-sync.timer
sudo systemctl status face-sync.timer
```

## Configuration

### Cache Settings

In `face_detection.py`:

```python
CACHE_DIR = "cached_faces"           # Where to store downloaded images
CACHE_REFRESH_HOURS = 12             # Refresh every 12 hours (twice daily)
```

### Sync Script Settings

In `sync_faces.py`:

```python
REMOTE_URL = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"
```

## Directory Structure

```
camera/
├── face_detection.py          # Main diagnostic script
├── sync_faces.py              # Standalone sync script
├── README.md                  # This file
├── cached_faces/              # Auto-generated cache directory
│   ├── remote_students/       # Downloaded images
│   └── .cache_metadata.json   # Sync timestamp tracking
├── known_faces/               # Optional local faces directory
│   └── person_name/
│       └── image.jpg
└── sync.log                   # Sync operation logs
```

## How It Works

### Remote Mode
1. First run or when cache is stale (>12 hours old):
   - Connects to remote URL
   - Parses HTML/JSON for image links
   - Downloads all images to `cached_faces/remote_students/`
   - Updates `.cache_metadata.json` with timestamp

2. Subsequent runs within 12 hours:
   - Uses cached images (no network access)
   - Displays time until next sync

### Local Mode
- Directly processes images from `known_faces/` directory
- No caching or network activity

## Troubleshooting

### "dlib" installation fails
The face_recognition library requires dlib, which compiles from source on Raspberry Pi:
- Ensure you have at least 2GB free RAM
- Installation takes 20-30 minutes on Pi 5
- If it fails, try: `pip3 install --no-cache-dir dlib`

### Sync fails with timeout
- Check your internet connection
- Verify the remote URL is accessible
- Increase timeout in `sync_faces.py` (default: 30 seconds)

### CNN model is too slow
The script uses CNN for accuracy. If too slow:
- It automatically falls back to HOG model
- Both models are tested for each image

### Cache not refreshing
Check:
- `.cache_metadata.json` exists in `cached_faces/`
- Permissions allow writing to cache directory
- Cron job is running: `grep CRON /var/log/syslog`

## Performance Tips for Raspberry Pi 5

1. **Use local cache:** Remote sync reduces network overhead
2. **Limit image resolution:** Smaller images = faster processing
3. **Schedule sync during off-hours:** Avoid peak usage times
4. **Monitor logs:** Check `sync.log` for issues

## License

MIT
" 

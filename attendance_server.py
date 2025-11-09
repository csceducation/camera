#!/usr/bin/env python3
"""
FastAPI Attendance Server - Production Entry Point
===================================================
Centralized attendance system server with:
- Automated face sync from backend
- Face recognition process management
- Periodic attendance data upload to webhook
- RESTful API for monitoring and control

Usage:
    python attendance_server.py
    
    Or with uvicorn:
    uvicorn attendance_server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import time
import subprocess
import threading
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== Configuration ====================
BACKEND_WEBHOOK_URL = "https://vdm.csceducation.net/attendance/webhook/daily-attendance/"
WEBHOOK_ACCESS_KEY = "vdm_attendance_webhook_2025"
SYNC_SCRIPT = "sync_faces.py"
ATTENDANCE_SCRIPT = "face_attendance.py"
SYNC_INTERVAL_MINUTES = 5
UPLOAD_INTERVAL_MINUTES = 10
SUBPROCESS_TIMEOUT = 300  # 5 minutes
SHUTDOWN_GRACE_PERIOD = 5  # seconds
INITIAL_UPLOAD_DELAY = 120  # 2 minutes

# ==================== FastAPI App ====================
app = FastAPI(
    title="Face Attendance System",
    description="Automated face recognition attendance with backend sync",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ==================== Global State ====================
class ServerState:
    """Thread-safe server state management."""
    def __init__(self):
        self.attendance_process: Optional[subprocess.Popen] = None
        self.sync_thread: Optional[threading.Thread] = None
        self.upload_thread: Optional[threading.Thread] = None
        self.server_start_time = datetime.now()
        self._lock = threading.Lock()
    
    def set_attendance_process(self, process):
        with self._lock:
            self.attendance_process = process
    
    def get_attendance_process(self):
        with self._lock:
            return self.attendance_process
    
    def is_attendance_running(self):
        with self._lock:
            return self.attendance_process is not None and self.attendance_process.poll() is None

state = ServerState()

# ==================== Helper Functions ====================

def get_today_csv_file() -> str:
    """Get today's attendance CSV filename."""
    return f"attendance_{datetime.now().strftime('%Y-%m-%d')}.csv"


def run_subprocess(script: str, timeout: int = SUBPROCESS_TIMEOUT) -> tuple[bool, str, str]:
    """Execute subprocess with timeout and error handling.
    
    Returns:
        tuple: (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"{script} timed out after {timeout} seconds")
        return False, "", f"Timeout after {timeout}s"
    except Exception as e:
        logger.error(f"Failed to run {script}: {e}")
        return False, "", str(e)


def run_initial_sync() -> bool:
    """Run initial face sync at server startup."""
    logger.info("=" * 70)
    logger.info("Running initial face sync...")
    logger.info("=" * 70)
    
    success, stdout, stderr = run_subprocess(SYNC_SCRIPT)
    
    if success:
        logger.info("Initial face sync completed successfully")
        if stdout:
            logger.debug(stdout)
        return True
    else:
        logger.error("Initial face sync failed")
        if stderr:
            logger.error(stderr)
        return False


def start_attendance_system() -> bool:
    """Start the face_attendance.py process."""
    logger.info("=" * 70)
    logger.info("Starting face attendance system...")
    logger.info("=" * 70)
    
    try:
        process = subprocess.Popen(
            [sys.executable, ATTENDANCE_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        state.set_attendance_process(process)
        logger.info(f"Face attendance system started (PID: {process.pid})")
        return True
    except Exception as e:
        logger.error(f"Failed to start attendance system: {e}")
        return False


def read_csv_safely(csv_path: Path) -> List[Dict]:
    """Safely read CSV file with error handling.
    
    Returns:
        List of dictionaries representing CSV rows
    """
    if not csv_path.exists():
        return []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        logger.error(f"Failed to read CSV {csv_path}: {e}")
        return []


def upload_attendance_to_backend() -> None:
    """Upload today's attendance CSV to backend webhook."""
    csv_file = get_today_csv_file()
    csv_path = Path(csv_file)
    
    if not csv_path.exists():
        logger.debug(f"No attendance file found: {csv_file}")
        return
    
    # Read CSV data
    rows = read_csv_safely(csv_path)
    if not rows:
        logger.debug("No attendance data to upload")
        return
    
    logger.info(f"Uploading {len(rows)} attendance records from {csv_file}...")
    
    try:
        # Convert our CSV format (name, status, timestamp) to backend format
        # (enrollment_number, status, timestamp)
        csv_content = "enrollment_number,status,timestamp\n"
        for row in rows:
            csv_content += f"{row['name']},{row['status'].lower()},{row['timestamp']}\n"
        
        # Send to webhook
        headers = {
            "X-Webhook-Key": WEBHOOK_ACCESS_KEY,
            "Content-Type": "text/csv"
        }
        
        response = requests.post(
            BACKEND_WEBHOOK_URL,
            headers=headers,
            data=csv_content.encode('utf-8'),
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Log results
        summary = result.get('summary', {})
        logger.info(
            f"Upload successful: {summary.get('successful', 0)} uploaded, "
            f"{summary.get('failed', 0)} failed, {summary.get('duplicates', 0)} duplicates"
        )
        
        # Log errors if any
        if result.get('errors'):
            logger.warning(f"Upload had {len(result['errors'])} errors")
            for error in result['errors'][:3]:  # Show first 3
                logger.warning(f"  Row {error['row']}: {error['error']}")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during upload: {e}")
    except Exception as e:
        logger.error(f"Failed to upload attendance: {e}")


def periodic_sync() -> None:
    """Background thread: Periodically sync faces."""
    logger.info(f"Starting periodic sync (every {SYNC_INTERVAL_MINUTES} minutes)")
    
    while True:
        time.sleep(SYNC_INTERVAL_MINUTES * 60)
        
        try:
            logger.info("Running periodic face sync...")
            success, stdout, stderr = run_subprocess(SYNC_SCRIPT)
            
            if success:
                logger.info("Periodic sync completed successfully")
            else:
                logger.error(f"Periodic sync failed: {stderr}")
        except Exception as e:
            logger.error(f"Error during periodic sync: {e}")


def periodic_upload() -> None:
    """Background thread: Periodically upload attendance to backend."""
    logger.info(f"Starting periodic upload (every {UPLOAD_INTERVAL_MINUTES} minutes)")
    
    # Initial delay to allow attendance data collection
    logger.info(f"Waiting {INITIAL_UPLOAD_DELAY}s before first upload...")
    time.sleep(INITIAL_UPLOAD_DELAY)
    
    while True:
        try:
            upload_attendance_to_backend()
        except Exception as e:
            logger.error(f"Error during periodic upload: {e}")
        
        time.sleep(UPLOAD_INTERVAL_MINUTES * 60)


# ==================== FastAPI Lifecycle Events ====================

@app.on_event("startup")
async def startup_event():
    """Initialize server on startup."""
    logger.info("=" * 70)
    logger.info("FACE ATTENDANCE SERVER - STARTING UP")
    logger.info("=" * 70)
    
    # Step 1: Initial face sync
    if not run_initial_sync():
        logger.warning("Initial sync failed, but continuing...")
    
    # Step 2: Start attendance system
    if not start_attendance_system():
        logger.error("Failed to start attendance system!")
    
    # Step 3: Start background sync thread
    state.sync_thread = threading.Thread(target=periodic_sync, daemon=True, name="SyncThread")
    state.sync_thread.start()
    
    # Step 4: Start background upload thread
    state.upload_thread = threading.Thread(target=periodic_upload, daemon=True, name="UploadThread")
    state.upload_thread.start()
    
    logger.info("=" * 70)
    logger.info("Server initialization complete!")
    logger.info(f"  Face sync interval: {SYNC_INTERVAL_MINUTES} minutes")
    logger.info(f"  Upload interval: {UPLOAD_INTERVAL_MINUTES} minutes")
    logger.info(f"  Backend webhook: {BACKEND_WEBHOOK_URL}")
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on server shutdown."""
    logger.info("Shutting down server...")
    
    # Stop attendance process
    process = state.get_attendance_process()
    if process and process.poll() is None:
        logger.info("Stopping attendance system...")
        process.terminate()
        try:
            process.wait(timeout=SHUTDOWN_GRACE_PERIOD)
            logger.info("Attendance system stopped gracefully")
        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning("Attendance system force killed")
    
    # Upload final attendance
    logger.info("Uploading final attendance data...")
    try:
        upload_attendance_to_backend()
    except Exception as e:
        logger.error(f"Failed to upload final attendance: {e}")
    
    logger.info("Server stopped")


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Server status and information."""
    uptime = datetime.now() - state.server_start_time
    
    return {
        "service": "Face Attendance System",
        "status": "running",
        "uptime": str(uptime).split('.')[0],
        "started_at": state.server_start_time.isoformat(),
        "attendance_system": {
            "running": state.is_attendance_running(),
            "pid": state.attendance_process.pid if state.attendance_process else None
        },
        "sync": {
            "interval_minutes": SYNC_INTERVAL_MINUTES,
            "csv_file": get_today_csv_file()
        },
        "upload": {
            "interval_minutes": UPLOAD_INTERVAL_MINUTES,
            "backend_url": BACKEND_WEBHOOK_URL
        }
    }


@app.get("/status")
async def get_status():
    """Detailed system status."""
    csv_file = get_today_csv_file()
    csv_path = Path(csv_file)
    
    # Count attendance records
    attendance_count = max(0, len(read_csv_safely(csv_path)))
    
    return {
        "server": {
            "running": True,
            "uptime": str(datetime.now() - state.server_start_time).split('.')[0],
            "started": state.server_start_time.isoformat()
        },
        "attendance_system": {
            "running": state.is_attendance_running(),
            "pid": state.attendance_process.pid if state.attendance_process else None
        },
        "today_attendance": {
            "file": csv_file,
            "exists": csv_path.exists(),
            "total_records": attendance_count
        },
        "sync_thread": {
            "running": state.sync_thread is not None and state.sync_thread.is_alive(),
            "interval_minutes": SYNC_INTERVAL_MINUTES
        },
        "upload_thread": {
            "running": state.upload_thread is not None and state.upload_thread.is_alive(),
            "interval_minutes": UPLOAD_INTERVAL_MINUTES
        }
    }


@app.post("/sync/manual")
async def manual_sync():
    """Manually trigger face sync."""
    logger.info("Manual sync requested via API")
    
    success, stdout, stderr = run_subprocess(SYNC_SCRIPT)
    
    if success:
        return {
            "success": True,
            "message": "Face sync completed successfully",
            "output": stdout
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={"error": "Sync failed", "details": stderr}
        )


@app.post("/upload/manual")
async def manual_upload():
    """Manually trigger attendance upload to backend."""
    logger.info("Manual upload requested via API")
    
    try:
        upload_attendance_to_backend()
        return {
            "success": True,
            "message": "Attendance upload completed",
            "csv_file": get_today_csv_file()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/attendance/restart")
async def restart_attendance():
    """Restart the face attendance system."""
    logger.info("Attendance system restart requested via API")
    
    # Stop existing process
    process = state.get_attendance_process()
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=SHUTDOWN_GRACE_PERIOD)
        except subprocess.TimeoutExpired:
            process.kill()
    
    # Start new process
    if start_attendance_system():
        return {
            "success": True,
            "message": "Attendance system restarted",
            "pid": state.attendance_process.pid
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to restart attendance system"
        )


@app.get("/attendance/today")
async def get_today_attendance():
    """Get today's attendance records."""
    csv_file = get_today_csv_file()
    csv_path = Path(csv_file)
    
    records = read_csv_safely(csv_path)
    
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "records": records,
        "total": len(records)
    }


# ==================== Main ====================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("=" * 70)
    logger.info("Starting Face Attendance Server")
    logger.info("=" * 70)
    logger.info("API available at: http://0.0.0.0:8000")
    logger.info("API Docs: http://0.0.0.0:8000/docs")
    logger.info("=" * 70)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

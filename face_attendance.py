#!/usr/bin/env python3
"""
Crowd Attendance System — IN/OUT + MiniFASNetV2 Anti-Spoof (Raspberry Pi 5)
----------------------------------------------------------------------------
✅ Real-time PiCamera2 capture
✅ Face recognition + blink + motion liveness
✅ Deep MiniFASNet V2 anti-spoof model (2.7_80x80_MiniFASNetV2.pth)
✅ Skips CSV for phones/photos
✅ Daily CSV: attendance_YYYY-MM-DD.csv  (name, status, timestamp)
✅ Alternates automatically (IN ↔ OUT)
✅ Persistent green once verified
✅ Uses synced cached faces from backend
"""

import os, time, csv, cv2, torch, torch.nn as nn, torch.nn.functional as F, numpy as np
from datetime import datetime, timedelta
from picamera2 import Picamera2
from mediapipe import solutions as mp_solutions
from collections import deque
import face_recognition, imutils
from pathlib import Path
import json

# ---------- CONFIG ----------
# Remote source - synced by sync_faces.py background service
KNOWN_FACES_SOURCE = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"  # Synced by background service

FRAME_WIDTH, FRAME_HEIGHT = 640, 480
TOLERANCE = 0.45
BLINK_EAR_THRESH = 0.22
BLINK_CONSEC_FRAMES = 2
LIVENESS_WINDOW = 12
MIN_CONFIDENCE = 0.5
IN_OUT_GAP_SECONDS = 10  # Minimum seconds between same person's IN/OUT (prevents duplicate rapid detections)
MODEL_PATH = "2.7_80x80_MiniFASNetV2.pth"

# Anti-spoof configuration
ANTI_SPOOF_THRESHOLD = 0.3  # Lower = more strict, Higher = more lenient (0.3-0.5 recommended)
ENABLE_ANTI_SPOOF = True    # Set to False to disable anti-spoof checking
# ----------------------------

# ---------- MiniFASNet V2 (official lightweight version) ----------
class ConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch, stride):
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 3, stride, 1, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.prelu = nn.PReLU(out_ch)
    def forward(self, x): return self.prelu(self.bn(self.conv(x)))

class DepthWise(nn.Module):
    def __init__(self, in_ch, out_ch, stride):
        super().__init__()
        self.conv = nn.Conv2d(in_ch, in_ch, 3, stride, 1, groups=in_ch, bias=False)
        self.bn = nn.BatchNorm2d(in_ch)
        self.prelu = nn.PReLU(in_ch)
        self.project = nn.Conv2d(in_ch, out_ch, 1, 1, 0, bias=False)
        self.bn_proj = nn.BatchNorm2d(out_ch)
    def forward(self, x):
        x = self.prelu(self.bn(self.conv(x)))
        return self.bn_proj(self.project(x))

class MiniFASNetV2(nn.Module):
    def __init__(self, num_classes=2):
        super().__init__()
        self.conv1 = ConvBlock(3, 64, 1)
        self.conv2_dw = DepthWise(64, 64, 1)
        self.conv_23 = DepthWise(64, 128, 2)
        self.conv_34 = DepthWise(128, 128, 1)
        self.conv_45 = DepthWise(128, 128, 1)
        self.conv_56 = DepthWise(128, 256, 2)
        self.conv_67 = DepthWise(256, 256, 1)
        self.conv_78 = DepthWise(256, 512, 2)
        self.conv_89 = DepthWise(512, 512, 1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.linear = nn.Linear(512, num_classes)
        self.bn = nn.BatchNorm1d(num_classes)
        self.softmax = nn.Softmax(dim=1)
    def forward(self, x):
        x = self.conv1(x); x = self.conv2_dw(x)
        x = self.conv_23(x); x = self.conv_34(x); x = self.conv_45(x)
        x = self.conv_56(x); x = self.conv_67(x)
        x = self.conv_78(x); x = self.conv_89(x)
        x = self.pool(x).view(x.size(0), -1)
        x = self.linear(x); x = self.bn(x)
        return self.softmax(x)

device = "cpu"
anti_spoof_model = MiniFASNetV2()
anti_spoof_model.load_state_dict(torch.load(MODEL_PATH, map_location=device), strict=False)
anti_spoof_model.eval()

def is_spoof_or_phone(frame_bgr, bbox):
    """Check if face is a spoof (photo/video) or real person.
    
    Returns:
        tuple: (is_spoof: bool, real_score: float)
    """
    if not ENABLE_ANTI_SPOOF:
        return False, 1.0  # Anti-spoof disabled, always consider real
    
    (l,t,r,b) = bbox
    h,w = frame_bgr.shape[:2]
    x1,y1 = max(l-20,0), max(t-20,0)
    x2,y2 = min(r+20,w), min(b+20,h)
    roi = frame_bgr[y1:y2, x1:x2]
    
    if roi.size == 0:
        return False, 0.0  # Can't determine, assume real
    
    # Preprocess for model
    roi = cv2.resize(roi, (80, 80))
    roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB).transpose(2, 0, 1) / 255.0
    roi = torch.tensor(roi, dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        prob = anti_spoof_model(roi).numpy()[0]
        real_score = prob[1]  # Probability of being real
    
    # Return (is_spoof, score)
    is_spoof = real_score < ANTI_SPOOF_THRESHOLD
    return is_spoof, real_score
# ---------------------------------------------------------------

mp_face_mesh = mp_solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=4, refine_landmarks=True,
                                  min_detection_confidence=0.5, min_tracking_confidence=0.5)
LEFT_EYE, RIGHT_EYE = [33,159,133,145,153,154], [263,386,362,374,380,381]
last_attendance_time, current_status, verified_names = {}, {}, set()

# ---------- CSV ----------
def get_today_csv():
    today = datetime.now().strftime("%Y-%m-%d")
    fn = f"attendance_{today}.csv"
    if not os.path.exists(fn):
        with open(fn,"w",newline="") as f:
            csv.writer(f).writerow(["name","status","timestamp"])
    return fn
def append_csv(name,status):
    with open(get_today_csv(),"a",newline="") as f:
        csv.writer(f).writerow([name,status,datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# ---------- Helpers ----------
def ear_ratio(lms, eye, w, h):
    def p(i): lm=lms[i]; return np.array([lm.x*w,lm.y*h])
    pts=[p(i) for i in eye]
    A=np.linalg.norm(pts[1]-pts[4]); B=np.linalg.norm(pts[2]-pts[5]); C=np.linalg.norm(pts[0]-pts[3])
    return (A+B)/(2.0*(C+1e-8))

def load_known_faces():
    """Load face encodings from cached_faces directory (synced by sync_faces.py)."""
    encs, names = [], []
    
    # Determine which directory to use
    if str(KNOWN_FACES_SOURCE).lower().startswith(('http://', 'https://')):
        # Use cached directory synced by background service
        known_dir = Path(CACHE_DIR)
        
        # Check cache status
        if not known_dir.exists():
            print(f"[ERROR] Cache directory not found: {CACHE_DIR}")
            print(f"[INFO] Run 'python sync_faces.py' first to download images")
            return encs, names
        
        metadata_file = known_dir / ".cache_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                last_sync = datetime.fromisoformat(metadata.get('last_sync', ''))
                time_since_sync = datetime.now() - last_sync
                minutes_ago = int(time_since_sync.total_seconds() / 60)
                
                print(f"[INFO] Cache last synced: {last_sync.strftime('%Y-%m-%d %H:%M:%S')} ({minutes_ago} minutes ago)")
                print(f"[INFO] Images cached: {metadata.get('total_images', 'unknown')}")
                
                if minutes_ago > 10:
                    print(f"[WARN] Cache is {minutes_ago} minutes old - check sync service")
            except Exception as e:
                print(f"[WARN] Could not read cache metadata: {e}")
    else:
        # Use local directory
        known_dir = Path(KNOWN_FACES_SOURCE)
        if not known_dir.exists():
            print(f"[ERROR] Directory not found: {KNOWN_FACES_SOURCE}")
            return encs, names
    
    # Load encodings from directory structure (each subdirectory = person)
    for person_dir in known_dir.iterdir():
        if not person_dir.is_dir() or person_dir.name.startswith('.'):
            continue
        
        person_name = person_dir.name  # Roll number or student ID
        
        for img_file in person_dir.iterdir():
            if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                continue
            
            try:
                img = face_recognition.load_image_file(str(img_file))
                encodings = face_recognition.face_encodings(img)
                if encodings:
                    encs.append(encodings[0])
                    names.append(person_name)
                    print(f"[INFO] Loaded: {person_name}/{img_file.name}")
            except Exception as e:
                print(f"[WARN] Failed to load {img_file}: {e}")
    
    print(f"[INFO] Loaded {len(encs)} face encodings from {len(set(names))} persons.")
    return encs, names

def match_face(enc, encs, names):
    if not encs: return None,0.0
    d=face_recognition.face_distance(encs,enc); i=np.argmin(d)
    return (names[i],1-d[i]) if d[i]<=TOLERANCE else (None,1-d[i])

def should_record(name):
    """Determine if attendance should be recorded and what status (IN/OUT).
    
    Logic:
    - First time seeing person: Mark as IN
    - Subsequent times: Toggle between IN and OUT
    - Cooldown period: Prevent duplicate rapid detections (10 seconds)
    
    Returns:
        tuple: (should_record: bool, status: str)
    """
    now = datetime.now()
    
    # First time seeing this person TODAY
    if name not in last_attendance_time:
        print(f"[DEBUG] {name} - First time detected, marking as IN")
        last_attendance_time[name] = now
        current_status[name] = "IN"
        return True, "IN"
    
    # Check cooldown period to prevent duplicate rapid detections
    time_since_last = now - last_attendance_time[name]
    seconds_since = time_since_last.total_seconds()
    
    if seconds_since < IN_OUT_GAP_SECONDS:
        # Too soon - ignore to prevent duplicates
        print(f"[DEBUG] {name} - Cooldown active: {seconds_since:.1f}s / {IN_OUT_GAP_SECONDS}s")
        return False, current_status.get(name, "IN")
    
    # Enough time has passed - toggle status
    # If last status was IN, mark as OUT (and vice versa)
    last_status = current_status.get(name, "IN")  # Get current status
    new_status = "OUT" if last_status == "IN" else "IN"
    
    print(f"[DEBUG] {name} - Toggling from {last_status} to {new_status} (time since last: {seconds_since:.1f}s)")
    
    current_status[name] = new_status
    last_attendance_time[name] = now
    
    return True, new_status

# ---------- Main ----------
def main():
    print("="*70)
    print("CROWD ATTENDANCE SYSTEM - IN/OUT Tracking")
    print("="*70)
    print(f"[INFO] Face source: {KNOWN_FACES_SOURCE}")
    if str(KNOWN_FACES_SOURCE).lower().startswith(('http://', 'https://')):
        print(f"[INFO] Using cached faces from: {CACHE_DIR}")
        print(f"[INFO] Ensure sync_faces.py is running to keep cache updated")
    print("="*70)
    
    known_encs,known_names=load_known_faces()
    
    if not known_encs:
        print("[ERROR] No face encodings loaded! Cannot start attendance system.")
        print("[INFO] If using remote source, run: python sync_faces.py")
        return
    
    picam=Picamera2()
    cfg=picam.create_preview_configuration(main={"size":(FRAME_WIDTH,FRAME_HEIGHT),"format":"RGB888"})
    picam.configure(cfg); picam.start()
    print("[INFO] Pi Camera started. Press 'q' to quit.")
    print("="*70)
    ear_w,mot_w=deque(maxlen=LIVENESS_WINDOW),deque(maxlen=LIVENESS_WINDOW)
    blink_frames=blinks=0; last_gray=None; t0=time.time(); frames=0
    
    # Status display variables
    show_status_until = None  # Timestamp until which to show status
    frozen_frame = None  # The frame to display during status show
    frozen_name = None  # Name of person whose status is being shown
    frozen_status = None  # Status (IN/OUT) being shown

    while True:
        # Check if we're in status display mode
        if show_status_until and time.time() < show_status_until:
            # Display the frozen frame with status message
            if frozen_frame is not None:
                cv2.imshow("Crowd Attendance (IN/OUT)", imutils.resize(frozen_frame, width=FRAME_WIDTH))
            if cv2.waitKey(1) & 0xFF == ord('q'): 
                break
            continue  # Skip face detection while showing status
        else:
            # Reset status display mode
            show_status_until = None
            frozen_frame = None
        
        frame_rgb=picam.capture_array()
        frame_bgr=cv2.cvtColor(frame_rgb,cv2.COLOR_RGB2BGR)
        frames+=1
        face_locs=face_recognition.face_locations(frame_rgb,model="hog")
        face_encs=face_recognition.face_encodings(frame_rgb,face_locs)

        gray=cv2.cvtColor(frame_bgr,cv2.COLOR_BGR2GRAY)
        motion=np.mean(cv2.absdiff(last_gray,gray)) if last_gray is not None else 0
        mot_w.append(motion); last_gray=gray

        res=face_mesh.process(frame_rgb)
        if res.multi_face_landmarks:
            lm=res.multi_face_landmarks[0].landmark
            ear=(ear_ratio(lm,LEFT_EYE,FRAME_WIDTH,FRAME_HEIGHT)+
                 ear_ratio(lm,RIGHT_EYE,FRAME_WIDTH,FRAME_HEIGHT))/2
            ear_w.append(ear)
            if ear<BLINK_EAR_THRESH: blink_frames+=1
            else:
                if blink_frames>=BLINK_CONSEC_FRAMES: blinks+=1
                blink_frames=0

        for (t,r,b,l),enc in zip(face_locs,face_encs):
            name,conf=match_face(enc,known_encs,known_names)
            motion_ok=np.mean(list(mot_w))>3.5; blink_ok=blinks>0
            spoof, spoof_score = is_spoof_or_phone(frame_bgr,(l,t,r,b))
            live=bool(name and conf>=MIN_CONFIDENCE and (blink_ok or motion_ok) and not spoof)
            if live: verified_names.add(name)

            # Get current status for display
            if name in last_attendance_time:
                # Already recorded - show current status
                current_person_status = current_status.get(name, "IN")
                # Calculate what next status will be
                next_status = "OUT" if current_person_status == "IN" else "IN"
                status_display = f"Status: {current_person_status} → Next: {next_status}"
            else:
                # First time - will be marked IN
                current_person_status = "IN (New)"
                status_display = "Status: New → Will mark IN"
            
            if spoof:
                color=(0,0,255)
                label=f"SPOOF! Score:{spoof_score:.2f}"
            elif name in verified_names:
                color=(0,255,0)
                label=f"{name}"
            else:
                color=(0,0,255)
                label=f"Unknown {conf:.2f}"
            
            cv2.rectangle(frame_bgr,(l,t),(r,b),color,2)
            cv2.putText(frame_bgr,label,(l,t-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)
            
            # Show current status prominently below the face
            if name and not spoof:
                # Create status message
                if name in last_attendance_time:
                    status_text = f"{name} you're marked as {current_person_status}"
                    status_color = (0,255,0) if current_person_status == "IN" else (0,165,255)  # Green for IN, Orange for OUT
                else:
                    status_text = f"{name} you're marked as IN"
                    status_color = (0,255,0)  # Green for new/IN
                
                # Status background box for better visibility
                text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                box_coords = ((l, b+5), (l + text_size[0] + 10, b + text_size[1] + 15))
                cv2.rectangle(frame_bgr, box_coords[0], box_coords[1], status_color, -1)
                cv2.putText(frame_bgr, status_text, (l+5, b+text_size[1]+10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
            
            # Show liveness indicators
            status_y = b + 20
            if ENABLE_ANTI_SPOOF:
                score_color = (0,255,0) if not spoof else (0,0,255)
                cv2.putText(frame_bgr,f"AS:{spoof_score:.2f}",(l,status_y),cv2.FONT_HERSHEY_SIMPLEX,0.4,score_color,1)
            
            if live and not spoof:
                record,status=should_record(name)
                if record:
                    append_csv(name,status)
                    print(f"[LOG] ✓ {name} marked {status} at {datetime.now():%Y-%m-%d %H:%M:%S}")
                    
                    # Prepare frozen frame with success message
                    frozen_frame = frame_bgr.copy()
                    frozen_name = name
                    frozen_status = status
                    
                    # Draw semi-transparent overlay for better visibility
                    overlay = frozen_frame.copy()
                    cv2.rectangle(overlay, (0, 0), (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.5, frozen_frame, 0.5, 0, frozen_frame)
                    
                    # Draw success message on frozen frame
                    msg = f"{name} you're marked as {status}"
                    msg_color = (0,255,0) if status == "IN" else (0,165,255)
                    
                    # Calculate text size and position (centered)
                    text_size = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)[0]
                    text_x = (FRAME_WIDTH - text_size[0]) // 2
                    text_y = FRAME_HEIGHT // 2
                    
                    # Background box with padding
                    padding = 30
                    box_coords = ((text_x - padding, text_y - text_size[1] - padding), 
                                  (text_x + text_size[0] + padding, text_y + padding))
                    cv2.rectangle(frozen_frame, box_coords[0], box_coords[1], msg_color, -1)
                    
                    # Draw border
                    cv2.rectangle(frozen_frame, box_coords[0], box_coords[1], (255,255,255), 3)
                    
                    # Draw text
                    cv2.putText(frozen_frame, msg, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 3)
                    
                    # Add checkmark above the message
                    check_size = cv2.getTextSize("✓", cv2.FONT_HERSHEY_SIMPLEX, 3.0, 5)[0]
                    check_x = (FRAME_WIDTH - check_size[0]) // 2
                    cv2.putText(frozen_frame, "✓", (check_x, text_y - 80), cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255,255,255), 5)
                    
                    # Set display duration (7 seconds)
                    show_status_until = time.time() + 7
                    
                    # Don't reset blinks here - let them accumulate naturally
                else:
                    # Cooldown period
                    time_since = datetime.now() - last_attendance_time.get(name, datetime.now())
                    cooldown_left = IN_OUT_GAP_SECONDS - int(time_since.total_seconds())
                    if cooldown_left > 0 and cooldown_left == IN_OUT_GAP_SECONDS - 1:  # Only print once per second
                        print(f"[INFO] {name} - Cooldown: {cooldown_left}s remaining, next: {current_person_status}")
            elif spoof:
                print(f"[WARN] Spoof detected! Score:{spoof_score:.3f} (threshold:{ANTI_SPOOF_THRESHOLD}) - {name or 'Unknown'}")
            elif name:
                # Recognized but not live (waiting for blink/motion)
                print(f"[INFO] {name} detected - waiting for liveness (blinks:{blinks}, motion:{motion_ok})")

        fps=frames/(time.time()-t0)
        info_text = f"FPS:{fps:.1f} | Blinks:{blinks} | Motion:{np.mean(list(mot_w)):.1f}"
        cv2.putText(frame_bgr,info_text,(10,25),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,255),2)
        cv2.imshow("Crowd Attendance (IN/OUT)",imutils.resize(frame_bgr,width=FRAME_WIDTH))
        if cv2.waitKey(1)&0xFF==ord('q'): break

    picam.stop(); cv2.destroyAllWindows(); print("[INFO] Session ended.")

if __name__=="__main__": main()

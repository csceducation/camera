#!/usr/bin/env python3
"""
Diagnostic tool to check face images in known_faces directory
"""

import cv2
import face_recognition
from pathlib import Path
import numpy as np
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import tempfile
import shutil
import os
import mimetypes
import json
from datetime import datetime, timedelta

# This can be a local directory name (e.g. "known_faces")
# or a URL such as the provided VDM endpoint.
KNOWN_FACES_SOURCE = "known_faces"

# Cache directory for downloaded remote faces
CACHE_DIR = "cached_faces"
# How often to refresh cache (in hours) - 12 hours = twice daily
CACHE_REFRESH_HOURS = 12

def check_image(image_path):
    """Check if an image contains a detectable face."""
    print(f"\n📄 Checking: {image_path}")
    
    try:
        # Try to read the image
        image = cv2.imread(str(image_path))
        
        if image is None:
            print(f"  ❌ ERROR: Cannot read file (corrupted or wrong format)")
            return False
        
        h, w = image.shape[:2]
        print(f"  📐 Image size: {w}x{h} pixels")
        
        # Convert to RGB
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Try CNN model (more accurate but slower)
        print(f"  🔍 Detecting faces with CNN model...")
        face_locations_cnn = face_recognition.face_locations(rgb_image, model="cnn")
        
        if len(face_locations_cnn) > 0:
            print(f"  ✅ CNN model detected {len(face_locations_cnn)} face(s)")
            encodings = face_recognition.face_encodings(rgb_image, face_locations_cnn)
            print(f"  ✅ Generated {len(encodings)} face encoding(s)")
            return True
        
        # Try HOG model (faster but less accurate)
        print(f"  🔍 Detecting faces with HOG model...")
        face_locations_hog = face_recognition.face_locations(rgb_image, model="hog")
        
        if len(face_locations_hog) > 0:
            print(f"  ✅ HOG model detected {len(face_locations_hog)} face(s)")
            encodings = face_recognition.face_encodings(rgb_image, face_locations_hog)
            print(f"  ✅ Generated {len(encodings)} face encoding(s)")
            return True
        
        # No faces detected
        print(f"  ❌ No faces detected!")
        print(f"  💡 Suggestions:")
        print(f"     - Ensure the face is clearly visible and front-facing")
        print(f"     - Make sure the image is well-lit")
        print(f"     - Face should be at least 80x80 pixels")
        print(f"     - Avoid sunglasses, masks, or obstructions")
        
        return False
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False

def main():
    """Check all images in known_faces directory."""
    print("=" * 70)
    print("FACE IMAGE DIAGNOSTIC TOOL")
    print("=" * 70)
    
    # If the source is a URL, use the locally cached files maintained by sync_faces.py
    # The sync script should be running as a background service to keep cache updated.
    # If it's a local path, process that directory directly.
    if str(KNOWN_FACES_SOURCE).lower().startswith(('http://', 'https://')):
        print(f"🔗 Remote known-faces source: {KNOWN_FACES_SOURCE}")
        print(f"  ℹ️  Using cached files from: {CACHE_DIR}")
        print(f"  ℹ️  Note: Ensure sync_faces.py is running to keep cache updated\n")
        
        cache_path = Path(CACHE_DIR)
        
        # Check if cache exists and has been synced
        if not cache_path.exists():
            print(f"❌ Cache directory not found: {CACHE_DIR}")
            print(f"💡 Run 'python sync_faces.py' first to download images")
            return
        
        metadata_file = cache_path / ".cache_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                last_sync = datetime.fromisoformat(metadata.get('last_sync', ''))
                time_since_sync = datetime.now() - last_sync
                minutes_ago = int(time_since_sync.total_seconds() / 60)
                
                print(f"  📊 Cache status:")
                print(f"     Last synced: {last_sync.strftime('%Y-%m-%d %H:%M:%S')} ({minutes_ago} minutes ago)")
                print(f"     Images cached: {metadata.get('total_images', 'unknown')}")
                
                if minutes_ago > 10:
                    print(f"  ⚠️  Cache is {minutes_ago} minutes old - consider checking sync service\n")
                else:
                    print(f"  ✅ Cache is fresh\n")
            except Exception as e:
                print(f"  ⚠️  Could not read cache metadata: {e}\n")
        
        known_faces_path = cache_path
    else:
        known_faces_path = Path(KNOWN_FACES_SOURCE)

        if not known_faces_path.exists():
            print(f"❌ Directory '{KNOWN_FACES_SOURCE}' not found!")
            return

        total_images = 0
        valid_images = 0

        for person_dir in sorted(known_faces_path.iterdir()):
            if not person_dir.is_dir():
                continue

            print(f"\n{'=' * 70}")
            print(f"👤 Person: {person_dir.name}")
            print(f"{'=' * 70}")

            # Find all image files
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.JPG', '*.JPEG', '*.png', '*.PNG']:
                image_files.extend(list(person_dir.glob(ext)))

            if not image_files:
                print(f"  ⚠️  No image files found in {person_dir.name}/")
                print(f"  💡 Add images with extensions: .jpg, .jpeg, .png")
                continue

            print(f"  Found {len(image_files)} image file(s)")

            for image_path in sorted(image_files):
                total_images += 1
                if check_image(image_path):
                    valid_images += 1

    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total images checked: {total_images}")
    print(f"Valid face images: {valid_images}")
    print(f"Failed images: {total_images - valid_images}")
    
    if valid_images == 0:
        print(f"\n⚠️  WARNING: No valid face images found!")
        print(f"\n💡 TIPS FOR GOOD FACE IMAGES:")
        print(f"   1. Face should be clearly visible and front-facing")
        print(f"   2. Good lighting (avoid shadows on face)")
        print(f"   3. No sunglasses, masks, or face coverings")
        print(f"   4. Face should fill at least 20% of the image")
        print(f"   5. Image resolution at least 640x480 pixels")
        print(f"   6. Single person per photo (primary face)")
    elif valid_images < total_images:
        print(f"\n⚠️  Some images failed. Check the details above.")
    else:
        print(f"\n✅ All images are valid! You can run the attendance system.")

if __name__ == "__main__":
    main()


### Helper functions for remote fetching ###

def needs_cache_refresh(cache_dir, refresh_hours):
    """Check if cache needs to be refreshed based on last sync time."""
    cache_path = Path(cache_dir)
    metadata_file = cache_path / ".cache_metadata.json"
    
    if not metadata_file.exists():
        return True
    
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        last_sync = datetime.fromisoformat(metadata.get('last_sync', ''))
        time_since_sync = datetime.now() - last_sync
        
        return time_since_sync > timedelta(hours=refresh_hours)
    except Exception:
        return True


def sync_remote_faces(source_url, cache_dir, refresh_hours):
    """Download/update cached faces from remote URL if refresh is needed.
    
    This function:
    - Checks if cache needs refresh (based on refresh_hours interval)
    - Downloads images from source_url
    - Saves them to cache_dir/remote_students/
    - Updates metadata with last sync time
    """
    cache_path = Path(cache_dir)
    
    if not needs_cache_refresh(cache_dir, refresh_hours):
        metadata_file = cache_path / ".cache_metadata.json"
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        last_sync = datetime.fromisoformat(metadata['last_sync'])
        next_sync = last_sync + timedelta(hours=refresh_hours)
        time_remaining = next_sync - datetime.now()
        hours = int(time_remaining.total_seconds() // 3600)
        minutes = int((time_remaining.total_seconds() % 3600) // 60)
        
        print(f"  ✓ Cache is fresh (last synced: {last_sync.strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"  ↳ Next sync in {hours}h {minutes}m")
        return
    
    print(f"  🔄 Syncing images from remote source...")
    
    # Create cache directory
    cache_path.mkdir(parents=True, exist_ok=True)
    remote_dir = cache_path / "remote_students"
    
    # Clear old cache
    if remote_dir.exists():
        shutil.rmtree(remote_dir)
    remote_dir.mkdir(parents=True, exist_ok=True)
    
    # Get image URLs
    try:
        image_urls = get_image_urls_from_url(source_url)
    except Exception as e:
        raise RuntimeError(f"Failed to get image URLs: {e}")
    
    if not image_urls:
        raise RuntimeError("No images found at remote source")
    
    print(f"  ↳ Found {len(image_urls)} image(s) to download")
    
    # Download images
    downloaded = 0
    for url in image_urls:
        try:
            filename = os.path.basename(urllib.parse.urlsplit(url).path)
            if not filename or not _is_image_url(filename):
                filename = f'student_{downloaded}.jpg'
            
            target_path = remote_dir / filename
            
            req = urllib.request.Request(url, headers={'User-Agent': 'face-diagnostic/1.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(target_path, 'wb') as f:
                    shutil.copyfileobj(resp, f)
            
            downloaded += 1
            print(f"  ↓ Downloaded: {filename}")
        except Exception as e:
            print(f"  ⚠️  Failed to download {url}: {e}")
    
    if downloaded == 0:
        raise RuntimeError("No images were successfully downloaded")
    
    # Update metadata
    metadata = {
        'last_sync': datetime.now().isoformat(),
        'source_url': source_url,
        'images_downloaded': downloaded
    }
    
    metadata_file = cache_path / ".cache_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  ✅ Successfully synced {downloaded} image(s)")
    print(f"  ↳ Next sync in {refresh_hours} hours")


class _LinkParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self._maybe_add(attrs['href'])
        elif tag == 'img' and 'src' in attrs:
            self._maybe_add(attrs['src'])

    def _maybe_add(self, url):
        abs_url = urllib.parse.urljoin(self.base_url, url)
        self.links.append(abs_url)


def _is_image_url(url):
    # Quick check by extension or mime type guess
    lower = url.lower()
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
        if lower.endswith(ext):
            return True
    # Fallback: ask for a HEAD to check content-type (but avoid heavy ops)
    return False


def get_image_urls_from_url(base_url):
    """Return a list of image URLs discovered at base_url (HTML or JSON).

    Does not download images; only parses links and returns absolute URLs.
    """
    req = urllib.request.Request(base_url, headers={
        'User-Agent': 'face-diagnostic/1.0'
    })
    with urllib.request.urlopen(req) as resp:
        content_type = resp.headers.get('Content-Type', '')
        data = resp.read()

    text = None
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        text = None

    image_urls = []

    # If the server returned JSON list of URLs
    if 'application/json' in content_type:
        import json
        arr = json.loads(data)
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, str) and _is_image_url(item):
                    image_urls.append(urllib.parse.urljoin(base_url, item))

    # If HTML/text, parse links
    if text is not None:
        parser = _LinkParser(base_url)
        parser.feed(text)
        for link in parser.links:
            if _is_image_url(link):
                image_urls.append(link)

    # As a fallback, if the base_url itself points to an image, use it
    if _is_image_url(base_url):
        image_urls.append(base_url)

    # Deduplicate while preserving order
    return list(dict.fromkeys(image_urls))


def check_image_url(url):
    """Fetch image bytes from URL, decode into OpenCV image, and run face checks."""
    print(f"\n📄 Checking: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'face-diagnostic/1.0'})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()

        arr = np.frombuffer(data, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            print(f"  ❌ ERROR: Could not decode image data from URL")
            return False

        h, w = image.shape[:2]
        print(f"  📐 Image size: {w}x{h} pixels")

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        print(f"  🔍 Detecting faces with CNN model...")
        face_locations_cnn = face_recognition.face_locations(rgb_image, model="cnn")
        if len(face_locations_cnn) > 0:
            print(f"  ✅ CNN model detected {len(face_locations_cnn)} face(s)")
            encodings = face_recognition.face_encodings(rgb_image, face_locations_cnn)
            print(f"  ✅ Generated {len(encodings)} face encoding(s)")
            return True

        print(f"  🔍 Detecting faces with HOG model...")
        face_locations_hog = face_recognition.face_locations(rgb_image, model="hog")
        if len(face_locations_hog) > 0:
            print(f"  ✅ HOG model detected {len(face_locations_hog)} face(s)")
            encodings = face_recognition.face_encodings(rgb_image, face_locations_hog)
            print(f"  ✅ Generated {len(encodings)} face encoding(s)")
            return True

        print(f"  ❌ No faces detected!")
        return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False

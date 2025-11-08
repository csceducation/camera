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

# This can be a local directory name (e.g. "known_faces")
# or a URL such as the provided VDM endpoint.
KNOWN_FACES_SOURCE = "known_faces"

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
    
    # If the source is a URL, process images directly from the remote URLs
    # in-memory (no disk downloads). If it's a local path, keep current behavior.
    if str(KNOWN_FACES_SOURCE).lower().startswith(('http://', 'https://')):
        print(f"🔗 Detected remote known-faces source: {KNOWN_FACES_SOURCE}")
        try:
            image_urls = get_image_urls_from_url(KNOWN_FACES_SOURCE)
        except Exception as e:
            print(f"❌ Failed to retrieve image URLs: {e}")
            return

        if not image_urls:
            print(f"❌ No images found at remote source: {KNOWN_FACES_SOURCE}")
            return

        total_images = 0
        valid_images = 0
        print(f"  ↳ Found {len(image_urls)} remote image(s)")

        for url in sorted(image_urls):
            total_images += 1
            if check_image_url(url):
                valid_images += 1

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

#!/usr/bin/env python3
"""
Standalone script to sync remote faces to local cache.
Designed to be run via cron or systemd timer on Raspberry Pi.

Usage:
    python sync_faces.py

Schedule with cron (twice daily at 6 AM and 6 PM):
    0 6,18 * * * cd /path/to/camera && /usr/bin/python3 sync_faces.py >> sync.log 2>&1
"""

import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
import shutil
import os
import json
from datetime import datetime

# Configuration
REMOTE_URL = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"


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
    lower = url.lower()
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
        if lower.endswith(ext):
            return True
    return False


def get_image_urls_from_url(base_url):
    """Return a list of image URLs discovered at base_url (HTML or JSON)."""
    req = urllib.request.Request(base_url, headers={
        'User-Agent': 'face-diagnostic/1.0'
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
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


def sync_faces():
    """Download images from remote URL to local cache."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting face sync...")
    print(f"  Source: {REMOTE_URL}")
    print(f"  Cache: {CACHE_DIR}")
    
    cache_path = Path(CACHE_DIR)
    cache_path.mkdir(parents=True, exist_ok=True)
    remote_dir = cache_path / "remote_students"
    
    # Clear old cache
    if remote_dir.exists():
        shutil.rmtree(remote_dir)
    remote_dir.mkdir(parents=True, exist_ok=True)
    
    # Get image URLs
    try:
        image_urls = get_image_urls_from_url(REMOTE_URL)
    except Exception as e:
        print(f"  ❌ Failed to get image URLs: {e}")
        return False
    
    if not image_urls:
        print(f"  ❌ No images found at remote source")
        return False
    
    print(f"  Found {len(image_urls)} image(s) to download")
    
    # Download images
    downloaded = 0
    failed = 0
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
            print(f"  ✓ {filename}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Failed: {url} - {e}")
    
    # Update metadata
    metadata = {
        'last_sync': datetime.now().isoformat(),
        'source_url': REMOTE_URL,
        'images_downloaded': downloaded,
        'images_failed': failed
    }
    
    metadata_file = cache_path / ".cache_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  ✅ Sync complete: {downloaded} downloaded, {failed} failed")
    return True


if __name__ == "__main__":
    try:
        success = sync_faces()
        exit(0 if success else 1)
    except Exception as e:
        print(f"  ❌ Sync failed with error: {e}")
        exit(1)

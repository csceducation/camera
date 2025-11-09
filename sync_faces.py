#!/usr/bin/env python3
"""
Continuous sync script for Raspberry Pi attendance system.
Pulls face images from backend API and maintains local cache.

Architecture:
- Backend API: Provides student face images via HTTP endpoint
- Raspberry Pi: Runs this script as a background service (every 2-5 minutes)
- Attendance System: Uses locally cached images for real-time face recognition

Usage:
    # Single run:
    python sync_faces.py
    
    # Continuous mode (runs every 5 minutes):
    python sync_faces.py --continuous
    
    # Custom interval (in seconds):
    python sync_faces.py --continuous --interval 120

Setup as systemd service (recommended for Raspberry Pi):
    See README.md for systemd configuration
"""

import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
import shutil
import os
import json
from datetime import datetime
import time
import argparse
import hashlib
import ssl

# Configuration
REMOTE_URL = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"
DEFAULT_SYNC_INTERVAL = 300  # 5 minutes in seconds

# Create SSL context that doesn't verify certificates (for self-signed certs or HTTP)
# WARNING: This disables SSL verification - use only if you trust the source
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


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
    
    # Use SSL context for HTTPS, works with HTTP too
    with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
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
    remote_dir.mkdir(parents=True, exist_ok=True)
    
    # Get image URLs from backend
    try:
        image_urls = get_image_urls_from_url(REMOTE_URL)
    except Exception as e:
        print(f"  ❌ Failed to get image URLs: {e}")
        return False
    
    if not image_urls:
        print(f"  ❌ No images found at remote source")
        return False
    
    print(f"  Found {len(image_urls)} image(s) from backend")
    
    # Track existing files for cleanup
    existing_files = {f.name: f for f in remote_dir.glob('*') if f.is_file() and f.name != '.cache_metadata.json'}
    downloaded_files = set()
    
    # Download/update images
    downloaded = 0
    updated = 0
    skipped = 0
    failed = 0
    
    for url in image_urls:
        try:
            filename = os.path.basename(urllib.parse.urlsplit(url).path)
            if not filename or not _is_image_url(filename):
                # Generate consistent filename from URL hash
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f'student_{url_hash}.jpg'
            
            target_path = remote_dir / filename
            downloaded_files.add(filename)
            
            # Check if file exists and compare
            should_download = True
            if target_path.exists():
                # Quick size check - could be enhanced with ETag/Last-Modified headers
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'face-diagnostic/1.0'})
                    req.get_method = lambda: 'HEAD'
                    with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
                        remote_size = int(resp.headers.get('Content-Length', 0))
                        local_size = target_path.stat().st_size
                        if remote_size > 0 and remote_size == local_size:
                            should_download = False
                            skipped += 1
                except:
                    pass  # If HEAD fails, just download
            
            if should_download:
                # Download the image
                req = urllib.request.Request(url, headers={'User-Agent': 'face-diagnostic/1.0'})
                with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                    with open(target_path, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                
                if target_path in existing_files.values():
                    updated += 1
                    print(f"  ↻ Updated: {filename}")
                else:
                    downloaded += 1
                    print(f"  ↓ Downloaded: {filename}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Failed: {url} - {e}")
    
    # Remove files that no longer exist on backend
    removed = 0
    for filename, filepath in existing_files.items():
        if filename not in downloaded_files and filename != '.cache_metadata.json':
            try:
                filepath.unlink()
                removed += 1
                print(f"  🗑 Removed: {filename}")
            except Exception as e:
                print(f"  ⚠️  Failed to remove {filename}: {e}")
    
    # Update metadata
    metadata = {
        'last_sync': datetime.now().isoformat(),
        'source_url': REMOTE_URL,
        'total_images': len(downloaded_files),
        'downloaded': downloaded,
        'updated': updated,
        'skipped': skipped,
        'removed': removed,
        'failed': failed
    }
    
    metadata_file = cache_path / ".cache_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  ✅ Sync complete: {downloaded} new, {updated} updated, {skipped} unchanged, {removed} removed, {failed} failed")
    return True


def continuous_sync(interval_seconds):
    """Run sync continuously at specified interval."""
    print(f"Starting continuous sync mode (interval: {interval_seconds}s)")
    print(f"Press Ctrl+C to stop\n")
    
    while True:
        try:
            sync_faces()
            print(f"\n  💤 Waiting {interval_seconds} seconds until next sync...\n")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n\n👋 Stopping continuous sync...")
            break
        except Exception as e:
            print(f"\n  ⚠️  Sync error: {e}")
            print(f"  Retrying in {interval_seconds} seconds...\n")
            time.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Sync face images from backend API to local cache for Raspberry Pi attendance system'
    )
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously at specified interval'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=DEFAULT_SYNC_INTERVAL,
        help=f'Sync interval in seconds (default: {DEFAULT_SYNC_INTERVAL}s = 5 minutes)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.continuous:
            continuous_sync(args.interval)
        else:
            success = sync_faces()
            exit(0 if success else 1)
    except Exception as e:
        print(f"  ❌ Sync failed with error: {e}")
        exit(1)

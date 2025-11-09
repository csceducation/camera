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
REMOTE_URL = "http://vdm.csceducation.net/media/students?key=accessvdmfile"
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
            href = attrs['href']
            # Skip parent directory links
            if href == '..' or href.endswith('/..'):
                return
            # Convert relative URL to absolute
            abs_url = urllib.parse.urljoin(self.base_url, href)
            self.links.append(abs_url)
        elif tag == 'img' and 'src' in attrs:
            src = attrs['src']
            abs_url = urllib.parse.urljoin(self.base_url, src)
            self.links.append(abs_url)


def _is_image_url(url):
    lower = url.lower()
    # Remove query parameters before checking extension
    path = urllib.parse.urlsplit(url).path.lower()
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
        if path.endswith(ext):
            return True
    return False


def _is_directory_url(url):
    """Check if URL likely points to a directory (ends with / or no extension)."""
    path = urllib.parse.urlsplit(url).path
    # If it ends with /, it's a directory
    if path.endswith('/'):
        return True
    # If no file extension (no dot in the last part) and not an image, likely a directory
    basename = os.path.basename(path)
    if '.' not in basename and not _is_image_url(url):
        return True
    # If path looks like a folder (no extension), it's a directory
    return False


def get_all_images_recursive(base_url, visited=None, depth=0):
    """Recursively discover all image URLs from file browser, preserving directory structure.
    
    Returns a list of tuples: (absolute_url, relative_path)
    For example: ('http://example.com/students/12345/photo.png', '12345/photo.png')
    """
    if visited is None:
        visited = set()
    
    if base_url in visited:
        return []
    visited.add(base_url)
    
    # Prevent infinite recursion
    if depth > 10:
        return []
    
    results = []
    indent = "  " * depth
    
    try:
        print(f"{indent}[Scan] {base_url}")
        
        req = urllib.request.Request(base_url, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
            content_type = resp.headers.get('Content-Type', '')
            data = resp.read()
        
        # Try to decode as text
        text = None
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            return results
        
        # Parse HTML for links
        if text:
            parser = _LinkParser(base_url)
            parser.feed(text)
            
            print(f"{indent}   Found {len(parser.links)} links")
            
            for link in parser.links:
                # Skip if already visited
                if link in visited:
                    continue
                
                # If it's an image, add it
                if _is_image_url(link):
                    # Calculate relative path from base URL
                    rel_path = get_relative_path(REMOTE_URL, link)
                    results.append((link, rel_path))
                    print(f"{indent}   [+] Image: {rel_path}")
                
                # If it's a directory, check if it's a valid roll number folder
                elif _is_directory_url(link):
                    # Only recurse if it's under our base path
                    base_path = REMOTE_URL.split('?')[0]  # Remove query params for comparison
                    if link.startswith(base_path):
                        # Check if this is a roll number folder (skip passport and non-numeric)
                        path_part = urllib.parse.urlsplit(link).path
                        folder_name = os.path.basename(path_part.rstrip('/'))
                        
                        # Skip passport folder
                        if folder_name.lower() == 'passport':
                            print(f"{indent}   [-] Skipping: passport folder")
                            continue
                        
                        # Only process numeric folders (roll numbers) or the root
                        # Root folder has no specific folder name or is the base
                        is_root = (link.rstrip('/').split('?')[0] == base_path.rstrip('/'))
                        is_rollnumber = folder_name.isdigit()
                        
                        if is_root or is_rollnumber:
                            if is_rollnumber:
                                print(f"{indent}   [>] Entering roll number folder: {folder_name}")
                            sub_results = get_all_images_recursive(link, visited, depth + 1)
                            results.extend(sub_results)
                        else:
                            print(f"{indent}   [-] Skipping non-numeric folder: {folder_name}")
    
    except Exception as e:
        print(f"{indent}   [!] Error: {e}")
    
    return results


def get_relative_path(base_url, full_url):
    """Extract relative path from full URL compared to base URL.
    
    Example:
        base: http://example.com/media/students?key=xxx
        full: http://example.com/media/students/12345/photo.png?key=xxx
        returns: 12345/photo.png
    """
    # Remove query parameters for path comparison
    base_parts = urllib.parse.urlsplit(base_url)
    full_parts = urllib.parse.urlsplit(full_url)
    
    # Get the path components (without query)
    base_path = base_parts.path.rstrip('/')
    full_path = full_parts.path
    
    # Remove base path from full path
    if full_path.startswith(base_path):
        rel_path = full_path[len(base_path):].lstrip('/')
        return rel_path
    
    # Fallback: just use the last two path components (folder/file)
    path_parts = full_path.strip('/').split('/')
    if len(path_parts) >= 2:
        return '/'.join(path_parts[-2:])
    
    # Ultimate fallback: just the filename
    return os.path.basename(full_path)


def sync_faces():
    """Download images from remote URL to local cache, preserving directory structure."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting face sync...")
    print(f"  Source: {REMOTE_URL}")
    print(f"  Cache: {CACHE_DIR}")
    
    cache_path = Path(CACHE_DIR)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Get all image URLs with their relative paths from backend (recursive file browser scan)
    print(f"  [*] Scanning file browser for images (recursive)...")
    try:
        image_data = get_all_images_recursive(REMOTE_URL)
    except Exception as e:
        print(f"  [X] Failed to scan file browser: {e}")
        return False
    
    if not image_data:
        print(f"  [X] No images found at remote source")
        return False
    
    print(f"  Found {len(image_data)} image(s) from backend")
    
    # Track existing files for cleanup
    existing_files = {}
    for root, dirs, files in os.walk(cache_path):
        for f in files:
            if f != '.cache_metadata.json':
                full_path = Path(root) / f
                rel_to_cache = full_path.relative_to(cache_path)
                existing_files[str(rel_to_cache)] = full_path
    
    downloaded_files = set()
    
    # Download/update images, preserving directory structure
    downloaded = 0
    updated = 0
    skipped = 0
    failed = 0
    
    for url, rel_path in image_data:
        try:
            # Create target path preserving directory structure
            # rel_path is like "12345/photo.png" or "rollnumber/image.jpg"
            target_path = cache_path / rel_path
            target_dir = target_path.parent
            
            # Create directory if it doesn't exist
            target_dir.mkdir(parents=True, exist_ok=True)
            
            downloaded_files.add(str(rel_path))
            
            # Check if file exists and compare
            should_download = True
            if target_path.exists():
                # Quick size check
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
                
                if str(rel_path) in existing_files:
                    updated += 1
                    print(f"  [^] Updated: {rel_path}")
                else:
                    downloaded += 1
                    print(f"  [+] Downloaded: {rel_path}")
        except Exception as e:
            failed += 1
            print(f"  [!] Failed: {url} - {e}")
    
    # Remove files that no longer exist on backend
    removed = 0
    for rel_path_str, filepath in existing_files.items():
        if rel_path_str not in downloaded_files:
            try:
                filepath.unlink()
                removed += 1
                print(f"  [-] Removed: {rel_path_str}")
                
                # Remove empty directories
                parent = filepath.parent
                try:
                    if parent != cache_path and not any(parent.iterdir()):
                        parent.rmdir()
                        print(f"  [-] Removed empty dir: {parent.relative_to(cache_path)}")
                except:
                    pass
            except Exception as e:
                print(f"  [!] Failed to remove {rel_path_str}: {e}")
    
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
    
    print(f"  [OK] Sync complete: {downloaded} new, {updated} updated, {skipped} unchanged, {removed} removed, {failed} failed")
    return True


def continuous_sync(interval_seconds):
    """Run sync continuously at specified interval."""
    print(f"Starting continuous sync mode (interval: {interval_seconds}s)")
    print(f"Press Ctrl+C to stop\n")
    
    while True:
        try:
            sync_faces()
            print(f"\n  [~] Waiting {interval_seconds} seconds until next sync...\n")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n\n[*] Stopping continuous sync...")
            break
        except Exception as e:
            print(f"\n  [!] Sync error: {e}")
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
        print(f"  [X] Sync failed with error: {e}")
        exit(1)

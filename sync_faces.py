#!/usr/bin/env python3
"""
Face Image Sync Service - Production Ready
===========================================
Continuously syncs student face images from backend file browser
to local cache for offline face recognition.

Features:
- Recursive directory scanning
- Smart incremental updates
- Directory structure preservation
- Automatic cleanup
- SSL/TLS support with self-signed cert handling

Usage:
    # Single run:
    python sync_faces.py
    
    # Continuous mode (default 5 min interval):
    python sync_faces.py --continuous
    
    # Custom interval:
    python sync_faces.py --continuous --interval 120

Setup as systemd service:
    See README.md for configuration
"""

import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
import shutil
import os
import sys
import json
import logging
from datetime import datetime
import time
import argparse
import ssl
from typing import List, Tuple, Set, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== Configuration ====================
REMOTE_URL = "https://vdm.csceducation.net/media/students?key=accessvdmfile"
CACHE_DIR = "cached_faces"
DEFAULT_SYNC_INTERVAL = 300  # 5 minutes
REQUEST_TIMEOUT = 30
MAX_RECURSION_DEPTH = 10

# SSL context for HTTPS with self-signed certificates
# WARNING: Disables SSL verification - use only for trusted sources
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


# ==================== HTML Parser ====================

class LinkParser(HTMLParser):
    """Extract links from HTML file browser."""
    
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """Extract href and src attributes."""
        attrs_dict = dict(attrs)
        
        if tag == 'a' and 'href' in attrs_dict:
            href = attrs_dict['href']
            # Skip parent directory links
            if href not in ('..', '../') and not href.endswith('/..'):
                abs_url = urllib.parse.urljoin(self.base_url, href)
                self.links.append(abs_url)
        
        elif tag == 'img' and 'src' in attrs_dict:
            src = attrs_dict['src']
            abs_url = urllib.parse.urljoin(self.base_url, src)
            self.links.append(abs_url)


# ==================== Helper Functions ====================

def is_image_url(url: str) -> bool:
    """Check if URL points to an image file."""
    path = urllib.parse.urlsplit(url).path.lower()
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    return any(path.endswith(ext) for ext in image_extensions)


def is_directory_url(url: str) -> bool:
    """Check if URL likely points to a directory."""
    path = urllib.parse.urlsplit(url).path
    
    # Ends with / = directory
    if path.endswith('/'):
        return True
    
    # No file extension = likely directory
    basename = os.path.basename(path)
    if '.' not in basename and not is_image_url(url):
        return True
    
    return False


def is_rollnumber_folder(folder_name: str) -> bool:
    """Check if folder name is a numeric roll number."""
    return folder_name.isdigit()


def get_relative_path(base_url: str, full_url: str) -> str:
    """Extract relative path from full URL.
    
    Example:
        base: https://example.com/media/students?key=xxx
        full: https://example.com/media/students/12345/photo.png?key=xxx
        returns: 12345/photo.png
    """
    base_parts = urllib.parse.urlsplit(base_url)
    full_parts = urllib.parse.urlsplit(full_url)
    
    base_path = base_parts.path.rstrip('/')
    full_path = full_parts.path
    
    # Remove base path from full path
    if full_path.startswith(base_path):
        rel_path = full_path[len(base_path):].lstrip('/')
        return rel_path
    
    # Fallback: use last two path components (folder/file)
    path_parts = full_path.strip('/').split('/')
    if len(path_parts) >= 2:
        return '/'.join(path_parts[-2:])
    
    # Ultimate fallback: just filename
    return os.path.basename(full_path)


def fetch_url_content(url: str) -> Optional[bytes]:
    """Fetch URL content with error handling."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'face-sync/2.0'})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ssl_context) as resp:
            return resp.read()
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def get_remote_file_size(url: str) -> int:
    """Get remote file size using HEAD request."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'face-sync/2.0'})
        req.get_method = lambda: 'HEAD'
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ssl_context) as resp:
            return int(resp.headers.get('Content-Length', 0))
    except Exception:
        return 0


def discover_images_recursive(
    base_url: str,
    visited: Optional[Set[str]] = None,
    depth: int = 0
) -> List[Tuple[str, str]]:
    """Recursively discover all image URLs from file browser.
    
    Args:
        base_url: URL to scan
        visited: Set of already visited URLs
        depth: Current recursion depth
    
    Returns:
        List of tuples: (absolute_url, relative_path)
    """
    if visited is None:
        visited = set()
    
    if base_url in visited or depth > MAX_RECURSION_DEPTH:
        return []
    
    visited.add(base_url)
    results = []
    indent = "  " * depth
    
    logger.debug(f"{indent}Scanning: {base_url}")
    
    # Fetch and parse HTML
    content = fetch_url_content(base_url)
    if not content:
        return results
    
    try:
        text = content.decode('utf-8', errors='replace')
    except Exception:
        return results
    
    # Parse links
    parser = LinkParser(base_url)
    parser.feed(text)
    
    logger.debug(f"{indent}Found {len(parser.links)} links")
    
    # Process each link
    for link in parser.links:
        if link in visited:
            continue
        
        # If it's an image, add it
        if is_image_url(link):
            rel_path = get_relative_path(REMOTE_URL, link)
            results.append((link, rel_path))
            logger.debug(f"{indent}[IMAGE] {rel_path}")
        
        # If it's a directory, recurse into it
        elif is_directory_url(link):
            base_path = REMOTE_URL.split('?')[0]
            
            # Only process links under our base path
            if not link.startswith(base_path):
                continue
            
            # Extract folder name
            path_part = urllib.parse.urlsplit(link).path
            folder_name = os.path.basename(path_part.rstrip('/'))
            
            # Skip passport folder
            if folder_name.lower() == 'passport':
                logger.debug(f"{indent}[SKIP] passport folder")
                continue
            
            # Only process root or numeric folders (roll numbers)
            is_root = link.rstrip('/').split('?')[0] == base_path.rstrip('/')
            
            if is_root or is_rollnumber_folder(folder_name):
                if is_rollnumber_folder(folder_name):
                    logger.debug(f"{indent}[FOLDER] {folder_name}")
                
                # Recurse into subdirectory
                sub_results = discover_images_recursive(link, visited, depth + 1)
                results.extend(sub_results)
            else:
                logger.debug(f"{indent}[SKIP] non-numeric folder: {folder_name}")
    
    return results


def download_file(url: str, target_path: Path) -> bool:
    """Download file from URL to target path."""
    try:
        content = fetch_url_content(url)
        if not content:
            return False
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target_path, 'wb') as f:
            f.write(content)
        
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


# ==================== Main Sync Logic ====================

def sync_faces() -> bool:
    """Sync face images from backend to local cache."""
    logger.info("=" * 70)
    logger.info(f"Starting face sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Source: {REMOTE_URL}")
    logger.info(f"Cache: {CACHE_DIR}")
    logger.info("=" * 70)
    
    cache_path = Path(CACHE_DIR)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Discover all images from backend
    logger.info("Scanning file browser (recursive)...")
    try:
        image_data = discover_images_recursive(REMOTE_URL)
    except Exception as e:
        logger.error(f"Failed to scan file browser: {e}")
        return False
    
    if not image_data:
        logger.error("No images found at remote source")
        return False
    
    logger.info(f"Found {len(image_data)} images from backend")
    
    # Track existing local files for cleanup
    existing_files = {}
    for root, dirs, files in os.walk(cache_path):
        for f in files:
            if f != '.cache_metadata.json':
                full_path = Path(root) / f
                rel_to_cache = full_path.relative_to(cache_path)
                existing_files[str(rel_to_cache)] = full_path
    
    # Statistics
    stats = {
        'downloaded': 0,
        'updated': 0,
        'skipped': 0,
        'failed': 0,
        'removed': 0
    }
    
    downloaded_files = set()
    
    # Process each image
    for url, rel_path in image_data:
        target_path = cache_path / rel_path
        downloaded_files.add(str(rel_path))
        
        # Check if download is needed
        should_download = True
        
        if target_path.exists():
            # Compare file sizes
            remote_size = get_remote_file_size(url)
            local_size = target_path.stat().st_size
            
            if remote_size > 0 and remote_size == local_size:
                should_download = False
                stats['skipped'] += 1
        
        # Download if needed
        if should_download:
            if download_file(url, target_path):
                if str(rel_path) in existing_files:
                    stats['updated'] += 1
                    logger.info(f"[UPDATED] {rel_path}")
                else:
                    stats['downloaded'] += 1
                    logger.info(f"[NEW] {rel_path}")
            else:
                stats['failed'] += 1
    
    # Remove files no longer on backend
    for rel_path_str, filepath in existing_files.items():
        if rel_path_str not in downloaded_files:
            try:
                filepath.unlink()
                stats['removed'] += 1
                logger.info(f"[REMOVED] {rel_path_str}")
                
                # Clean up empty directories
                parent = filepath.parent
                if parent != cache_path and not any(parent.iterdir()):
                    parent.rmdir()
                    logger.debug(f"Removed empty dir: {parent.relative_to(cache_path)}")
            except Exception as e:
                logger.error(f"Failed to remove {rel_path_str}: {e}")
    
    # Save metadata
    metadata = {
        'last_sync': datetime.now().isoformat(),
        'source_url': REMOTE_URL,
        'total_images': len(downloaded_files),
        **stats
    }
    
    metadata_file = cache_path / ".cache_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info("=" * 70)
    logger.info(
        f"Sync complete: {stats['downloaded']} new, {stats['updated']} updated, "
        f"{stats['skipped']} unchanged, {stats['removed']} removed, {stats['failed']} failed"
    )
    logger.info("=" * 70)
    
    return stats['failed'] == 0


def continuous_sync(interval_seconds: int) -> None:
    """Run sync continuously at specified interval."""
    logger.info(f"Starting continuous sync mode (interval: {interval_seconds}s)")
    logger.info("Press Ctrl+C to stop\n")
    
    while True:
        try:
            sync_faces()
            logger.info(f"\nWaiting {interval_seconds} seconds until next sync...\n")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("\nStopping continuous sync...")
            break
        except Exception as e:
            logger.error(f"Sync error: {e}")
            logger.info(f"Retrying in {interval_seconds} seconds...\n")
            time.sleep(interval_seconds)


# ==================== Main ====================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Sync face images from backend to local cache',
        formatter_class=argparse.RawDescriptionHelpFormatter
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
        help=f'Sync interval in seconds (default: {DEFAULT_SYNC_INTERVAL}s)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        if args.continuous:
            continuous_sync(args.interval)
        else:
            success = sync_faces()
            sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


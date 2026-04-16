"""
drive_downloader.py
Downloads product photos from Google Drive sharing links.

Supports these URL formats:
  https://drive.google.com/file/d/FILE_ID/view?usp=sharing
  https://drive.google.com/open?id=FILE_ID
  https://drive.google.com/uc?id=FILE_ID
"""

import re
import os
from pathlib import Path
from typing import Optional

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS = [
    r"/file/d/([a-zA-Z0-9_-]+)",   # /file/d/FILE_ID/view
    r"[?&]id=([a-zA-Z0-9_-]+)",    # ?id=FILE_ID or &id=FILE_ID
    r"/d/([a-zA-Z0-9_-]+)",        # short /d/FILE_ID
]


def extract_drive_id(url: str) -> Optional[str]:
    """Return the Google Drive file ID embedded in *url*, or None."""
    for pattern in _PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def download_drive_file(url: str, output_dir: str) -> Optional[str]:
    """
    Download a Google Drive file to *output_dir* and return its local path.

    Files are cached by their Drive ID, so re-running the agent won't
    re-download photos that already exist.

    Returns None if the URL is empty, the ID can't be parsed, or the
    download fails.
    """
    if not url:
        return None

    file_id = extract_drive_id(url)
    if not file_id:
        print(f"  [drive] Could not parse file ID from: {url}")
        return None

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Cache check ──────────────────────────────────────────────────────────
    for existing in out_dir.iterdir():
        if existing.is_file() and existing.stem == file_id:
            print(f"  [drive] Using cached photo → {existing.name}")
            return str(existing)

    # ── Download ─────────────────────────────────────────────────────────────
    print(f"  [drive] Downloading file ID: {file_id}")
    download_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    session = requests.Session()
    response = session.get(download_url, stream=True, timeout=60)

    # Google returns a confirmation cookie for large files
    confirm_token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            confirm_token = value
            break

    if confirm_token:
        download_url = f"{download_url}&confirm={confirm_token}"
        response = session.get(download_url, stream=True, timeout=60)

    if response.status_code != 200:
        print(f"  [drive] HTTP {response.status_code} — download failed for {url}")
        return None

    # Determine file extension
    raw_ct = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    ext = _EXT_MAP.get(raw_ct, ".jpg")
    output_path = out_dir / f"{file_id}{ext}"

    with open(output_path, "wb") as fh:
        for chunk in response.iter_content(chunk_size=16_384):
            fh.write(chunk)

    size_kb = output_path.stat().st_size // 1024
    print(f"  [drive] Saved → {output_path.name} ({size_kb} KB)")
    return str(output_path)

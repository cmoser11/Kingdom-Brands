#!/usr/bin/env python3
"""
Wicked One USA — Product Image Downloader
==========================================
Reads the w1cked_manifest.json file (already downloaded to your machine)
and downloads all 236 product images into collection-based subfolders under:

  /Users/caseymoser/Desktop/Kingdom-Brands/W1cked/

Folder structure:
  W1cked/
  ├── _manifest.json              ← reference copy
  ├── BJJ/
  │   └── kimono-xxx_1.jpg ...
  ├── COMPASS/
  ├── CONTROL/
  ├── CROSS-LINE/
  ├── DVSN/
  ├── ESSENTIAL/
  ├── FAVELA RISING/
  ├── Gloves/
  ├── HEAT/
  ├── HUSSLE/
  ├── Leggings / Shorts/
  ├── Lifestyle T-Shirts/
  ├── Luggage/
  ├── MMA/
  ├── MMA Shorts/
  ├── Muay Thai/
  ├── Muay Thai Shorts/
  ├── Protections/
  ├── RAW/
  ├── ROLLIN/
  ├── Spats/
  ├── Strike Equipment/
  ├── T-Shirts/
  ├── Tank Tops / Shorts/
  ├── Tracksuits/
  ├── Training Equipment/
  └── Uncategorized/

Usage:
  1. Make sure w1cked_manifest.json is in the same folder as this script
     (it was downloaded to your Downloads folder by the browser step)
  2. Run:  python3 download_w1cked_images.py

Requirements:
  pip install requests
"""

import os
import re
import sys
import json
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

# ── Configuration ─────────────────────────────────────────────────────────────

OUTPUT_DIR    = Path("/Users/caseymoser/Desktop/Kingdom-Brands/W1cked")
MANIFEST_FILE = Path(__file__).parent / "w1cked_manifest.json"
DELAY         = 0.2   # seconds between downloads
MAX_RETRIES   = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_folder(name: str) -> str:
    """Make a collection title safe as a macOS folder name."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name or "Uncategorized"


def get_extension(url: str, filename: str) -> str:
    """Determine file extension from URL or filename."""
    for source in [url, filename]:
        ext = os.path.splitext(urlparse(source).path)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return ext
    return ".jpg"


def download_image(url: str, dest: Path) -> bool:
    """Download a single image. Returns True on success."""
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"      ⚠ Retry {attempt + 1} — {e} (waiting {wait}s)")
                time.sleep(wait)
            else:
                print(f"      ✗ Failed: {e}")
                return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Load manifest
    if not MANIFEST_FILE.exists():
        print(f"❌  Manifest not found: {MANIFEST_FILE}")
        print("    Move w1cked_manifest.json to the same folder as this script.")
        sys.exit(1)

    with open(MANIFEST_FILE, encoding="utf-8") as f:
        manifest = json.load(f)

    # Count total images
    total_images = sum(len(p["images"]) for p in manifest)
    print(f"""
╔══════════════════════════════════════════════╗
║   Wicked One USA — Image Downloader          ║
╠══════════════════════════════════════════════╣
║  Products : {len(manifest):<34}║
║  Images   : {total_images:<34}║
║  Output   : {str(OUTPUT_DIR)[:34]:<34}║
╚══════════════════════════════════════════════╝
""")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save manifest copy to output dir
    import shutil
    shutil.copy(MANIFEST_FILE, OUTPUT_DIR / "_manifest.json")

    downloaded = 0
    skipped    = 0
    failed     = 0
    img_num    = 0

    for product in manifest:
        title       = product["product_title"]
        handle      = product["product_handle"]
        folder_name = sanitize_folder(product["primary_folder"])
        images      = product["images"]

        if not images:
            continue

        folder_path = OUTPUT_DIR / folder_name
        print(f"📦  {title}")
        print(f"    └─ {folder_name}/  ({len(images)} images)")

        for img in images:
            img_num += 1
            url      = img["url"].split("?")[0]   # strip Shopify resize params
            fname    = img["filename"]
            # Fix extension if URL is .png but filename says .jpg
            real_ext = get_extension(url, fname)
            stem     = os.path.splitext(fname)[0]
            fname    = stem + real_ext
            dest     = folder_path / fname

            progress = f"[{img_num}/{total_images}]"

            if dest.exists():
                print(f"    {progress} ↷ {fname} (skip — already exists)")
                skipped += 1
                continue

            print(f"    {progress} ↓ {fname}")
            ok = download_image(url, dest)
            if ok:
                downloaded += 1
            else:
                failed += 1

            time.sleep(DELAY)

        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("━" * 48)
    print(f"✅  Download complete!")
    print(f"    Downloaded : {downloaded}")
    print(f"    Skipped    : {skipped}  (already existed)")
    print(f"    Failed     : {failed}")
    print(f"    Output dir : {OUTPUT_DIR}")
    print("━" * 48)

    print("\n📁 Folder breakdown:")
    for folder in sorted(OUTPUT_DIR.iterdir()):
        if folder.is_dir():
            files = list(folder.glob("*"))
            print(f"    {folder.name}/  — {len(files)} files")

    if failed > 0:
        print(f"\n⚠  {failed} images failed. Re-run the script to retry them.")


if __name__ == "__main__":
    main()

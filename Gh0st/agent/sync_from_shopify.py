#!/usr/bin/env python3
"""
sync_from_shopify.py  —  GH05T Shopify Sync Tool
==================================================
Downloads product photos (and optionally product data) from your existing
Shopify store using the PUBLIC storefront endpoint — no API token required.

Every Shopify store exposes a public products.json endpoint:
  https://STORE.myshopify.com/products.json

What it does
------------
  1. Fetches every product via the public products.json endpoint
  2. Downloads the first image for each product → photos/{handle}.jpg
  3. (Optional) Back-fills products/products.csv with real data from Shopify
     (Title, Description, Price, Vendor, Tags, etc.)

Setup
-----
  No API token needed! Just make sure SHOPIFY_MYSHOPIFY_URL is set in
  agent/config.py, e.g.:
    SHOPIFY_MYSHOPIFY_URL = "https://aeqdba-yw.myshopify.com"

Usage
-----
  # Download photos only
  python agent/sync_from_shopify.py

  # Download photos AND back-fill products.csv
  python agent/sync_from_shopify.py --update-csv

  # Preview what would be downloaded (no files written)
  python agent/sync_from_shopify.py --dry-run
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import SHOPIFY_MYSHOPIFY_URL, PRODUCTS_CSV, PHOTOS_DIR

REPO_ROOT   = Path(__file__).parent.parent
PHOTOS_PATH = REPO_ROOT / PHOTOS_DIR
CSV_PATH    = REPO_ROOT / PRODUCTS_CSV

IMAGE_EXTS  = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public storefront helpers (no auth required)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_products() -> list[dict]:
    """
    Page through the public /products.json endpoint and return every product.
    Shopify returns max 250 per page; we paginate using the page param.
    No authentication required.
    """
    store   = SHOPIFY_MYSHOPIFY_URL.rstrip("/")
    results = []
    page    = 1

    while True:
        url  = f"{store}/products.json"
        resp = requests.get(url, params={"limit": 250, "page": page}, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])

        if not batch:
            break

        results.extend(batch)
        print(f"  Fetched {len(results)} products so far …")

        if len(batch) < 250:
            break  # last page

        page += 1
        time.sleep(0.25)

    return results


def _parse_next_link(link_header: str) -> Optional[str]:
    """Extract the 'next' URL from a Shopify Link header."""
    for part in link_header.split(","):
        if 'rel="next"' in part:
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Photo download
# ─────────────────────────────────────────────────────────────────────────────

def download_product_photos(
    products: list[dict],
    dry_run:  bool = False,
) -> dict[str, Optional[str]]:
    """
    Download the primary image for each product to photos/{handle}.ext.
    Returns a dict mapping handle → local file path (or None if no image).
    """
    PHOTOS_PATH.mkdir(parents=True, exist_ok=True)
    photo_map: dict[str, Optional[str]] = {}

    for product in products:
        handle = product["handle"]
        images = product.get("images", [])

        if not images:
            print(f"  ⚠️   {handle}  — no images on Shopify")
            photo_map[handle] = None
            continue

        img_url = images[0]["src"]

        # Check cache first
        for existing in PHOTOS_PATH.iterdir():
            if existing.is_file() and existing.stem == handle:
                print(f"  ✓   {handle}  — already cached ({existing.name})")
                photo_map[handle] = str(existing)
                break
        else:
            if dry_run:
                print(f"  [dry-run]  would download → {handle}.*  from {img_url[:60]}…")
                photo_map[handle] = None
            else:
                path = _download_image(img_url, handle)
                photo_map[handle] = path

    return photo_map


def _download_image(url: str, handle: str) -> Optional[str]:
    """Download *url* to photos/{handle}.ext and return the local path."""
    try:
        # Strip Shopify query params before HEAD so we get a clean content-type
        clean_url = url.split("?")[0]
        resp = requests.get(clean_url, stream=True, timeout=30)
        resp.raise_for_status()

        raw_ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        ext    = IMAGE_EXTS.get(raw_ct, ".jpg")

        # Fall back to extension in URL if content-type is generic
        if ext == ".jpg" and any(clean_url.lower().endswith(e) for e in (".png", ".webp", ".gif")):
            for e in (".png", ".webp", ".gif"):
                if clean_url.lower().endswith(e):
                    ext = e
                    break

        out_path = PHOTOS_PATH / f"{handle}{ext}"
        with open(out_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=16_384):
                fh.write(chunk)

        size_kb = out_path.stat().st_size // 1024
        print(f"  ✅  {handle}  → {out_path.name} ({size_kb} KB)")
        return str(out_path)

    except Exception as exc:
        print(f"  ❌  {handle}  — download failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Optional CSV back-fill
# ─────────────────────────────────────────────────────────────────────────────

def update_products_csv(products: list[dict]) -> None:
    """
    Merge real Shopify product data (Title, Description, Price, Vendor, Tags)
    back into products/products.csv so it's always in sync.
    """
    if not CSV_PATH.exists():
        print(f"  ⚠️   {CSV_PATH} not found — skipping CSV update.")
        return

    # Build a lookup: handle → Shopify product
    shopify_by_handle = {p["handle"]: p for p in products}

    # Read existing CSV
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader  = csv.DictReader(f)
        rows    = list(reader)
        columns = reader.fieldnames

    # Update rows
    updated = 0
    for row in rows:
        handle = row.get("Handle", "").strip()
        sp = shopify_by_handle.get(handle)
        if not sp:
            continue

        # Product-level fields only on the first variant row for each handle
        is_first = not any(
            r["Handle"] == handle
            for r in rows[: rows.index(row)]
        )

        if is_first:
            if not row.get("Description"):
                # Strip HTML tags for a plain-text description
                raw_html = sp.get("body_html", "") or ""
                plain    = re.sub(r"<[^>]+>", "", raw_html).strip()
                row["Description"] = plain

            if not row.get("Vendor") or row["Vendor"] == "GH05T X BRAND":
                row["Vendor"] = sp.get("vendor", "") or row["Vendor"]

            if not row.get("Tags"):
                row["Tags"] = sp.get("tags", "")

            if not row.get("Type"):
                row["Type"] = sp.get("product_type", "")

            if not row.get("Photo URL"):
                imgs = sp.get("images", [])
                if imgs:
                    row["Photo URL"] = imgs[0]["src"]

        # Price from matching variant
        variants_shopify = sp.get("variants", [])
        if variants_shopify and not row.get("Price"):
            row["Price"] = variants_shopify[0].get("price", "0.00")

        updated += 1

    # Write back
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  ✅  products.csv updated — {updated} rows enriched from Shopify.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download product photos (and data) from Shopify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--update-csv", action="store_true",
        help="Also back-fill products.csv with data from Shopify.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without writing any files.",
    )
    args = parser.parse_args()

    print(f"\n🛍   Fetching products from Shopify …\n")
    products = fetch_all_products()
    print(f"\n  Total products: {len(products)}\n")

    print("📸  Downloading product photos …\n")
    download_product_photos(products, dry_run=args.dry_run)

    if args.update_csv and not args.dry_run:
        print("\n📋  Back-filling products.csv …\n")
        update_products_csv(products)

    print("\n✅  Done.\n")


if __name__ == "__main__":
    main()

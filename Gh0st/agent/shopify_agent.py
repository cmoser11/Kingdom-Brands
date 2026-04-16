#!/usr/bin/env python3
"""
shopify_agent.py  —  GH05T Shopify Product Upload Agent
=========================================================
Reads products/products.csv, resolves a photo for each product
(from the local photos/ folder or a Google Drive URL), then fills
out the Shopify "Add Product" form using a Playwright-controlled browser.

Usage
-----
  # Upload all products
  python agent/shopify_agent.py

  # Upload specific products by handle
  python agent/shopify_agent.py --handles friday-beanie marble-shorts

  # Run headlessly (no visible browser window)
  python agent/shopify_agent.py --headless

  # Dry-run: parse CSV & match photos but don't touch Shopify
  python agent/shopify_agent.py --dry-run
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── make sure sibling modules are importable when running from repo root ──────
sys.path.insert(0, str(Path(__file__).parent))

from config        import SHOPIFY_CONFIG, PRODUCTS_CSV, PHOTOS_DIR
from csv_reader    import load_products
from photo_matcher import resolve_photo
from form_filler   import fill_product_form


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = Path(__file__).parent.parent / "logs" / "upload_log.csv"
LOG_FIELDS = ["timestamp_utc", "handle", "title", "photo_used", "status", "notes"]


def _init_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()


def _log(handle: str, title: str, photo: str | None, status: str, notes: str = "") -> None:
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow({
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "handle":        handle,
            "title":         title,
            "photo_used":    Path(photo).name if photo else "",
            "status":        status,
            "notes":         notes,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Main agent
# ─────────────────────────────────────────────────────────────────────────────

def run_agent(
    handles:  list | None = None,
    headless: bool = False,
    dry_run:  bool = False,
) -> None:
    """
    Orchestrate the full upload loop.

    Args:
        handles:   If provided, only process products whose handle is in this list.
        headless:  Launch Chromium without a visible window.
        dry_run:   Skip all browser interaction; just print what would happen.
    """
    _init_log()

    repo_root    = Path(__file__).parent.parent
    products_csv = repo_root / PRODUCTS_CSV
    photos_dir   = repo_root / PHOTOS_DIR

    # ── Load products ─────────────────────────────────────────────────────────
    print(f"\n📋  Loading products from: {products_csv.relative_to(repo_root)}")
    products = load_products(str(products_csv))

    if handles:
        products = [p for p in products if p.handle in handles]

    if not products:
        print("  No matching products found. Exiting.")
        return

    print(f"  Found {len(products)} product(s) to process.\n")

    # ── Resolve photos (no browser needed) ───────────────────────────────────
    photo_map: dict[str, str | None] = {}
    for p in products:
        photo_map[p.handle] = resolve_photo(p, str(photos_dir))

    if dry_run:
        print("\n── DRY RUN ─────────────────────────────────────────────────────")
        for p in products:
            photo = photo_map[p.handle]
            photo_label = Path(photo).name if photo else "⚠️  not found"
            print(f"  {p.handle}")
            print(f"    title  : {p.title}")
            print(f"    price  : {p.price}")
            print(f"    photo  : {photo_label}")
            print(f"    vars   : {len(p.variants)}")
        print("\nDry run complete — no changes made to Shopify.\n")
        return

    # ── Browser session ───────────────────────────────────────────────────────
    results: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context()
        page    = context.new_page()

        # Navigate and wait for login if needed
        print(f"🌐  Opening Shopify admin …")
        page.goto(SHOPIFY_CONFIG["store_url"] + "/admin")
        page.wait_for_load_state("networkidle", timeout=30_000)

        if "login" in page.url or "accounts.shopify" in page.url:
            print("\n⚠️  Not logged in. Please log in to Shopify in the browser window")
            print("    that just opened, then press  Enter  here to continue …")
            input()

        # ── Per-product loop ──────────────────────────────────────────────────
        for i, product in enumerate(products, 1):
            sep = "─" * 56
            print(f"\n{sep}")
            print(f"  [{i}/{len(products)}]  {product.title}")
            print(sep)

            photo = photo_map[product.handle]

            try:
                fill_product_form(page, product, photo, SHOPIFY_CONFIG)
                _log(product.handle, product.title, photo, "success")
                results.append({"handle": product.handle, "status": "success"})

            except Exception as exc:
                msg = str(exc)
                print(f"  ❌  Error: {msg}")
                _log(product.handle, product.title, photo, "error", notes=msg)
                results.append({"handle": product.handle, "status": "error", "notes": msg})

        browser.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    ok  = sum(1 for r in results if r["status"] == "success")
    err = len(results) - ok

    print(f"\n{'═'*56}")
    print(f"  UPLOAD SUMMARY  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*56}")
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {icon}  {r['handle']}")
    print(f"\n  {ok} succeeded  /  {err} failed  /  {len(results)} total")
    print(f"  Full log → logs/upload_log.csv\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GH05T Shopify Product Upload Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--handles", nargs="+", metavar="HANDLE",
        help="Only upload these product handles (space-separated).",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chromium without a visible window.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse CSV & match photos; print plan without touching Shopify.",
    )
    args = parser.parse_args()

    run_agent(
        handles=args.handles,
        headless=args.headless,
        dry_run=args.dry_run,
    )

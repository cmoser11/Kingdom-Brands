"""
form_filler.py
Uses Playwright to fill out the Shopify "Add product" form.

Called once per product by shopify_agent.py.
"""

import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def fill_product_form(
    page: Page,
    product,
    photo_path: Optional[str],
    config: dict,
) -> None:
    """
    Navigate to the Shopify new-product URL and fill the form completely.

    Raises on unrecoverable errors so the caller can record the failure.
    """
    print(f"  → Navigating to new product page …")
    page.goto(config["new_product_url"])
    page.wait_for_load_state("networkidle", timeout=30_000)

    _fill_title(page, product.title)
    _fill_description(page, product.description)
    _upload_photo(page, photo_path)
    _fill_price(page, product.price, product.compare_at_price, product.cost_per_item)
    _fill_organization(page, product.vendor, product.product_type, product.tags)
    _fill_variants(page, product.variants)
    _fill_weight(page, product.weight)
    _save(page)


# ─────────────────────────────────────────────────────────────────────────────
# Section fillers
# ─────────────────────────────────────────────────────────────────────────────

def _fill_title(page: Page, title: str) -> None:
    loc = page.locator('input[placeholder="Short sleeve t-shirt"]')
    loc.wait_for(state="visible", timeout=10_000)
    loc.triple_click()
    loc.fill(title)
    print(f"  ✓ Title: {title}")


def _fill_description(page: Page, description: str) -> None:
    if not description:
        return
    # Shopify uses a ProseMirror contenteditable div for the description
    editor = page.locator(".ProseMirror, [contenteditable='true']").first
    if editor.is_visible():
        editor.click()
        editor.fill(description)
        print("  ✓ Description filled")


def _upload_photo(page: Page, photo_path: Optional[str]) -> None:
    if not photo_path or not Path(photo_path).exists():
        return

    print(f"  → Uploading photo: {Path(photo_path).name} …")

    # The Shopify media uploader exposes a hidden <input type="file">
    # Playwright can set files on it directly without clicking the button.
    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files(photo_path)

    # Wait for the thumbnail to appear (up to 45 s for large files)
    page.wait_for_selector(
        ".media-card__media, [data-testid='media-thumbnail'], img[alt*='product']",
        timeout=45_000,
    )
    print("  ✓ Photo uploaded")


def _fill_price(
    page: Page,
    price: str,
    compare_at: str,
    cost: str,
) -> None:
    # Main price
    _set_input(page, 'input[name="price"], #price-field input', price)

    # "Compare at" price — click the label chip first if the field is hidden
    if compare_at:
        _click_if_visible(page, 'button:has-text("Compare-at")')
        _set_input(page, 'input[name="compareAtPrice"], #compare-at-price-field input', compare_at)

    # Cost per item — similarly gated behind a disclosure button
    if cost:
        _click_if_visible(page, 'button:has-text("Cost per item")')
        _set_input(page, 'input[name="costPerItem"], #cost-per-item-field input', cost)

    print(f"  ✓ Price: {price}")


def _fill_organization(
    page: Page,
    vendor: str,
    product_type: str,
    tags: str,
) -> None:
    if vendor:
        _set_input(page, 'input[name="vendor"], #vendor-field input', vendor)
        print(f"  ✓ Vendor: {vendor}")

    if product_type:
        _set_input(page, 'input[name="productType"], #product-type-field input', product_type)
        print(f"  ✓ Type: {product_type}")

    if tags:
        tags_input = page.locator('[aria-label="Tags"], input[placeholder*="tag"]').first
        if tags_input.is_visible():
            for tag in [t.strip() for t in tags.split(",") if t.strip()]:
                tags_input.fill(tag)
                page.keyboard.press("Enter")
            print(f"  ✓ Tags: {tags}")


def _fill_variants(page: Page, variants: list) -> None:
    if not variants:
        return

    opt1_name = variants[0].option1_name
    if not opt1_name:
        # No options — just set quantity in the single inventory field
        if variants[0].quantity:
            qty = page.locator('input[name="quantity"]').first
            if qty.is_visible():
                qty.fill(str(variants[0].quantity))
        return

    # ── Open variant editor ───────────────────────────────────────────────────
    add_options_btn = page.locator(
        'button:has-text("Add options like size or color")'
    )
    if add_options_btn.is_visible():
        add_options_btn.click()
        time.sleep(0.6)

    # ── Option 1 (e.g. Size) ─────────────────────────────────────────────────
    _fill_option_block(page, 0, opt1_name, variants, "option1_value")

    # ── Option 2 (e.g. Style / Color) ────────────────────────────────────────
    opt2_name = variants[0].option2_name
    if opt2_name:
        add_another = page.locator('button:has-text("Add another option")')
        if add_another.is_visible():
            add_another.click()
            time.sleep(0.4)
        _fill_option_block(page, 1, opt2_name, variants, "option2_value")

    # Shopify regenerates the variant table; wait for it
    time.sleep(1.2)

    # ── Per-variant SKU + quantity ────────────────────────────────────────────
    _fill_variant_table(page, variants)

    print(f"  ✓ Variants configured ({len(variants)} rows)")


def _fill_option_block(
    page: Page,
    block_index: int,
    option_name: str,
    variants: list,
    value_attr: str,
) -> None:
    """Fill the name input and all value chips for one option block."""
    name_inputs = page.locator('input[placeholder="e.g. Size"]')
    if name_inputs.count() > block_index:
        name_inputs.nth(block_index).fill(option_name)

    # Unique values in original order
    seen: dict = {}
    for v in variants:
        val = getattr(v, value_attr)
        if val and val not in seen:
            seen[val] = True

    for i, val in enumerate(seen.keys()):
        val_input = page.locator('input[placeholder="Add a value"]').last
        if val_input.is_visible():
            val_input.fill(val)
            # Press Enter to confirm and create the next chip
            page.keyboard.press("Enter")
            time.sleep(0.15)


def _fill_variant_table(page: Page, variants: list) -> None:
    """
    After options are set Shopify renders a table with one row per variant.
    We match each row by its label text and fill SKU + quantity.
    """
    for v in variants:
        # Build the label Shopify would show, e.g. "L" or "10oz / Velcro"
        label_parts = [v.option1_value]
        if v.option2_value:
            label_parts.append(v.option2_value)
        if v.option3_value:
            label_parts.append(v.option3_value)
        label = " / ".join(label_parts)

        row = page.locator(f"tr:has-text('{label}')").first
        if not row.is_visible():
            continue

        if v.sku:
            sku_inp = row.locator('input[aria-label*="SKU"], input[name*="sku"]').first
            if sku_inp.is_visible():
                sku_inp.triple_click()
                sku_inp.fill(v.sku)

        if v.quantity:
            qty_inp = row.locator('input[type="number"]').first
            if qty_inp.is_visible():
                qty_inp.triple_click()
                qty_inp.fill(str(v.quantity))


def _fill_weight(page: Page, weight: str) -> None:
    if not weight or weight == "0.0":
        return
    _set_input(page, 'input[name="weight"], #weight-field input', weight)
    print(f"  ✓ Weight: {weight} lb")


def _save(page: Page) -> None:
    save_btn = page.locator('button:has-text("Save")').last
    save_btn.click()
    page.wait_for_load_state("networkidle", timeout=30_000)
    print("  ✓ Saved")


# ─────────────────────────────────────────────────────────────────────────────
# Tiny utilities
# ─────────────────────────────────────────────────────────────────────────────

def _set_input(page: Page, selector: str, value: str) -> None:
    """Fill the first visible input that matches *selector*."""
    loc = page.locator(selector).first
    if loc.is_visible():
        loc.triple_click()
        loc.fill(value)


def _click_if_visible(page: Page, selector: str) -> None:
    loc = page.locator(selector).first
    if loc.is_visible():
        loc.click()
        time.sleep(0.3)

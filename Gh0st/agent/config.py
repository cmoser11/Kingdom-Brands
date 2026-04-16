# =============================================================================
# GH05T Shopify Agent — Configuration
# =============================================================================
# Fill in SHOPIFY_STORE_URL before running.
# Format: https://your-store-name.myshopify.com
# =============================================================================

SHOPIFY_STORE_URL = "https://gh0stbrand.com"

# Your internal myshopify.com URL — used by sync_from_shopify.py
# No API token needed; this endpoint is public
SHOPIFY_MYSHOPIFY_URL = "https://aeqdba-yw.myshopify.com"

SHOPIFY_CONFIG = {
    "store_url": SHOPIFY_STORE_URL,
    "new_product_url": f"{SHOPIFY_STORE_URL}/admin/products/new",
}

# Paths (relative to repo root)
PRODUCTS_CSV = "products/products.csv"
PHOTOS_DIR   = "photos"

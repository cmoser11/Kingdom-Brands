"""
photo_matcher.py
Resolves a product photo via three strategies (tried in order):

  1. Exact handle match  — photos/tiger-eye-muay-thai-shorts.jpg
  2. Fuzzy title match   — best-matching filename by token overlap
  3. Google Drive URL    — download from the Photo URL column (fallback)

Place product photos inside the  photos/  folder at the repo root.
Name them after the Shopify handle (e.g. "friday-beanie.jpg") for the
cleanest match, but any reasonably descriptive filename will work.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from drive_downloader import download_drive_file


# ─────────────────────────────────────────────────────────────────────────────
# Supported image extensions
# ─────────────────────────────────────────────────────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def resolve_photo(
    product,
    photos_dir: str,
    fuzzy_threshold: float = 0.55,
) -> Optional[str]:
    """
    Return the local path to the best-matching photo for *product*, or None.

    Args:
        product:          A Product dataclass with .handle, .title, .photo_url
        photos_dir:       Absolute path to the photos folder.
        fuzzy_threshold:  Minimum similarity score (0–1) to accept a fuzzy match.
    """
    dir_path = Path(photos_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    candidates = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    ]

    # ── Strategy 1: exact handle match ───────────────────────────────────────
    match = _exact_handle_match(product.handle, candidates)
    if match:
        print(f"  [photo] Exact match  → {match.name}")
        return str(match)

    # ── Strategy 2: fuzzy title match ────────────────────────────────────────
    match = _fuzzy_title_match(product.title, candidates, fuzzy_threshold)
    if match:
        print(f"  [photo] Fuzzy match  → {match.name}")
        return str(match)

    # ── Strategy 3: Google Drive URL ─────────────────────────────────────────
    if product.photo_url:
        print(f"  [photo] Downloading from Drive …")
        return download_drive_file(product.photo_url, photos_dir)

    print(f"  [photo] No photo found for: {product.handle}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", " ", text)   # keep hyphens and word chars
    text = re.sub(r"[\s_-]+", " ", text)    # unify separators
    return text.strip()


def _tokenize(text: str) -> set:
    return set(_normalise(text).split())


def _exact_handle_match(handle: str, candidates: list) -> Optional[Path]:
    """Return the file whose stem exactly equals the product handle."""
    handle_norm = handle.lower()
    for f in candidates:
        if f.stem.lower() == handle_norm:
            return f
    return None


def _fuzzy_title_match(
    title: str,
    candidates: list,
    threshold: float,
) -> Optional[Path]:
    """
    Score each candidate filename against the product title using two metrics:
      - Jaccard similarity on word tokens
      - SequenceMatcher ratio on normalised strings

    The candidate with the highest combined score wins, if it clears *threshold*.
    """
    title_tokens = _tokenize(title)
    title_norm   = _normalise(title)

    best_path:  Optional[Path] = None
    best_score: float = 0.0

    for f in candidates:
        stem_tokens = _tokenize(f.stem)
        stem_norm   = _normalise(f.stem)

        # Jaccard: intersection / union
        union = title_tokens | stem_tokens
        jaccard = len(title_tokens & stem_tokens) / len(union) if union else 0.0

        # SequenceMatcher ratio
        seq = SequenceMatcher(None, title_norm, stem_norm).ratio()

        score = 0.6 * jaccard + 0.4 * seq

        if score > best_score:
            best_score = score
            best_path  = f

    if best_score >= threshold:
        return best_path
    return None

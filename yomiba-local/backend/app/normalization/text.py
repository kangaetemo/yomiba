"""Text normalization helpers.

The goal is a *stable comparison key*: two strings that refer to the same real
world entity should normalize to the same key, while genuinely different
entities must not collide. We deliberately keep the transformation
conservative (case / accent / Turkish-character / whitespace / punctuation)
so we never merge unrelated titles such as "Berserk" and "Berserk of
Gluttony".
"""

from __future__ import annotations

import re
import unicodedata

# Turkish characters folded to their ASCII equivalents. Turkish dotted /
# dotless "i" variants are all mapped to "i" so that case / dot differences
# never create distinct keys.
_TURKISH_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    }
)


def _strip_accents(text: str) -> str:
    """Remove combining marks so that e.g. "é" becomes "e"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(value: str | None) -> str:
    """Return a canonical comparison key for ``value``.

    Steps (all deterministic):
      1. Unicode NFKC normalization.
      2. Strip diacritics (é -> e).
      3. Fold Turkish characters (ş -> s, İ/I/ı/i -> i, ...).
      4. Casefold.
      5. Replace every run of non-alphanumerics with a single space.
      6. Trim.

    >>> normalize_text("  Athica   Yayınları ")
    'athica yayinlari'
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = _strip_accents(text)
    text = text.translate(_TURKISH_FOLD)
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_publisher(value: str | None) -> str:
    """Normalize a publisher name to its comparison key.

    Currently identical to :func:`normalize_text` (case / whitespace /
    punctuation / Turkish characters). We keep it as a separate, documented
    entry point so publisher-specific rules (e.g. dropping a corporate
    suffix) can be added here without touching generic code. We intentionally
    do NOT strip suffixes such as "Yayınları", to avoid over-merging distinct
    publishers.
    """
    return normalize_text(value)


def slugify(value: str | None) -> str:
    """Build a URL-friendly slug from a (already or not) normalized title."""
    key = normalize_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    return slug or "item"

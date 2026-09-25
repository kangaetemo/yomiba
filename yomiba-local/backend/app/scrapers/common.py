"""Shared parsing helpers for scrapers (price formats etc.)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Matches a Turkish thousands group: 1.234 / 1.234.567 but not 1.234,56 or 163.54
_TL_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def parse_tr_price(raw: str | int | float | Decimal | None) -> Decimal | None:
    """Parse a Turkish-style price string into a ``Decimal``.

    Handles the formats actually seen in the wild:
      * ``"163,54"``          -> 163.54   (comma decimal)
      * ``"1.234,56"``        -> 1234.56  (dot thousands, comma decimal)
      * ``"1.234"``           -> 1234     (dot thousands, no decimal)
      * ``"163.54 TL"`` / ``"₺163.54"`` -> 163.54
      * ``182``               -> 182

    Returns ``None`` when no valid price can be extracted.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float, Decimal)):
        value = Decimal(str(raw))
        return value if value >= 0 else None

    text = str(raw).strip()
    if not text:
        return None
    text = re.sub(r"(?i)(\btl\b|₺|\btry\b)", "", text)
    text = text.strip().strip("₺").strip()
    if not text:
        return None

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif _TL_THOUSANDS_RE.match(text):
        text = text.replace(".", "")

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return value


#: Status codes that indicate an anti-bot / robot wall (fail fast — retrying
#: a bot wall is pointless and rude).
_BLOCK_STATUS = {403, 429, 503, 509, 999}

#: Page-content markers seen on real bot-wall pages (Amazon, D&R, T-Soft).
_BLOCK_MARKERS = (
    "captcha",
    "robot check",
    "otomatik robot",
    "izni olan kişilere",
    "api-services-support@amazon",
    "automated access",
    "type the characters",
    "güvenlik doğrulaması",
    "access denied",
)

#: ``<script>`` / ``<link>`` tags. A normal page can legally *include* a
#: reCAPTCHA loader (``<script src=".../recaptcha/api.js">``) while still
#: being fully rendered and scrapeable; every real wall marker above is
#: VISIBLE challenge text, never content inside such tags — so they are
#: stripped before matching. (No over-consumption: each pattern consumes at
#: most its own tag.)
_SELF_CLOSING_SCRIPT_LINK_RE = re.compile(r"<\s*(?:script|link)\b[^>]*/>", re.I)
_SCRIPT_BODY_RE = re.compile(r"<\s*script\b[^>]*>.*?</\s*script\s*>", re.I | re.S)
_LINK_TAG_RE = re.compile(r"<\s*link\b[^>]*>", re.I)


def _strip_script_link_tags(html: str) -> str:
    html = _SELF_CLOSING_SCRIPT_LINK_RE.sub("", html)
    html = _SCRIPT_BODY_RE.sub("", html)
    return _LINK_TAG_RE.sub("", html)


def has_block_marker(html: str = "") -> bool:
    """True when the visible page content carries known bot-wall markers."""
    lowered = _strip_script_link_tags(html or "")[:4000].lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def looks_like_blocked_page(status_code: int, html: str = "") -> bool:
    """Heuristic: did the store return an anti-bot / robot page?

    Store-level check (Amazon / D&R / T-Soft): the wall status codes alone
    are treated as a wall. The transport layer uses a stricter rule
    (403 or content markers) so plain 5xx/429 stay retryable — see
    ``BaseScraper.get``.
    """
    if status_code in _BLOCK_STATUS:
        return True
    return has_block_marker(html)

"""Volume-number parsing.

Splits a raw product title into a *base series title* and a *volume number*,
and flags collections / boxes (e.g. "Berserk 1-5") which must not be treated
as a single volume.

Parsing is intentionally conservative:
  * Explicit markers (Cilt, C., Vol, Volume, Bant, Sayı, No, S, #, "2 Cilt",
    "(3)", ": 4", "- 5") are strongest.
  * A number before a dash with the title continuing ("One Punch Man 3 -
    Tek Yumruk") marks a bilingual volume title.
  * A bare trailing number is a weaker signal ("Berserk 6").
  * A small number range ("1-5", "1 – 12") marks the item as a collection.
    Large ranges (e.g. fragments of an ISBN such as "978-605") are NOT
    collections.
  * When nothing matches, ``volume_number`` is ``None``. Store import must
    resolve safely or reject; it never creates a sentinel volume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Max plausible volume count used to distinguish a volume range ("1-12") from
# an ISBN fragment ("978-605").
_MAX_VOLUME = 300

# Markers that explicitly introduce a volume number.
_VOLUME_MARKER_RE = re.compile(
    # The marker must be a whole word: without the leading \b the "s" of
    # "Happiness 8" / "Made in Abyss 11" was read as an "S 8" marker and the
    # series title lost its last letter ("happines"), so the most common
    # store format "<Title> <N>" never matched titles ending in s/c/no.
    r"(?:\b(?:cilt|c|vol(?:ume)?|bant|say[ıi]|no|s)\b\.?\s*[:#]?\s*|\(\s*|(?<!\d)[:\-–#]\s*)(\d{1,4})\b",
    re.IGNORECASE,
)
# Number placed before the marker: "2 Cilt", "4. Cilt".
_VOLUME_AFTER_RE = re.compile(
    r"\b(\d{1,4})\.?\s*(?:cilt|c|vol(?:ume)?|bant|say[ıi]|no)\b", re.IGNORECASE
)
# A lone trailing number: "Berserk 6".
_TRAILING_NUMBER_RE = re.compile(r"\s(\d{1,4})\s*$")
# Number before a dash with the title continuing after it:
# "One Punch Man 3 - Tek Yumruk" (bilingual store titles). Requires a letter
# after the dash so ISBN fragments ("978-605") and ranges ("1-5", handled
# earlier) are never treated as volumes.
_MID_DASH_NUMBER_RE = re.compile(r"\b(\d{1,3})\s+[-\u2013]\s+(?=[^\W\d])")
# A range such as "1-5" / "1 – 12" -> collection.
_RANGE_RE = re.compile(r"\b(\d{1,4})\s*[-–]\s*(\d{1,4})\b")
# Words that strongly indicate a collection / boxed set / separate edition.
_COLLECTION_WORD_RE = re.compile(
    r"\b(box|set|seti|kutu|bundle|toplu|koleksiyon|collection|complete|deluxe|box\s*set|seri\s*set)\b",
    re.IGNORECASE,
)

# Legacy sentinel stored in ``volumes.volume_number`` for unresolved items.
# It does not prove a box/set product type. Negative numbers
# never occur in real volume numbering, so this is collision-free and keeps
# the (series_id, volume_number) uniqueness constraint effective for them.
UNNUMBERED_VOLUME = -1


@dataclass(frozen=True)
class VolumeParseResult:
    base_title: str
    volume_number: int | None
    is_collection: bool = False
    evidence: str | None = None


def _is_volume_range(text: str) -> bool:
    for match in _RANGE_RE.finditer(text):
        first, second = int(match.group(1)), int(match.group(2))
        # A range goes up ("1-5"). "8 - 8" is not a box set: it is how
        # "Kaiju No: 8 - 8 No'lu Canavar" spells its own title, and treating
        # it as a range made every scraper drop the whole series.
        if first < second <= _MAX_VOLUME:
            return True
    return False


def _strip_volume_tokens(text: str) -> str:
    """Remove volume tokens from ``text`` leaving the base series title."""
    out = text
    out = re.sub(
        r"\b(?:cilt|c|vol(?:ume)?|bant|say[ıi]|no|s)\b\.?\s*[:#]?\s*\d{1,4}\b",
        " ",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(\d{1,4})\.?\s*(?:cilt|c|vol(?:ume)?|bant|say[ıi]|no)\b",
        " ",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\(\s*\d{1,4}\s*\)", " ", out)
    out = re.sub(r"[:\-–#]\s*\d{1,4}\b", " ", out)
    out = re.sub(r"\b\d{1,3}\s+[-–]\s+(?=[^\W\d])", " ", out)
    out = re.sub(r"\s\d{1,4}\s*$", " ", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip(" \t:;.,-–#()[]")


@dataclass(frozen=True)
class VolumeRange:
    """An omnibus book's original-volume span ("Dragon Ball 9&10")."""

    base_title: str
    first: int
    last: int


# A TRAILING span of 2-3 consecutive original volumes, joined by "&", "ve"
# or a dash, each number optionally carrying a "Cilt" marker: "9&10",
# "5 ve 6", "Cilt: 7-8", "1-2 Cilt", "Cilt 5 - 6", "1-2-3",
# "1. Cilt - 2. Cilt".
_SPAN_NUMBER = r"(?:\b(?:cilt|vol(?:ume)?)\b\.?\s*:?\s*)?(\d{1,3})(?:\s*\.?\s*cilt\b)?"
_SPAN_JOIN = r"\s*(?:&|\bve\b|[-–])\s*"
_OMNIBUS_RANGE_RE = re.compile(
    _SPAN_NUMBER + _SPAN_JOIN + _SPAN_NUMBER + r"(?:" + _SPAN_JOIN + _SPAN_NUMBER + r")?\s*$",
    re.IGNORECASE,
)
# A trailing note that only restates the binding: "(İki Cilt Bir Arada)",
# "(2'si 1 Arada)", "(3'ü 1 Arada)", "(İkisi Bir Arada)".
_OMNIBUS_NOTE_RE = re.compile(
    r"\s*[(\[]\s*(?:iki|üç|uc|\d)\s*(?:cilt|'?\s*(?:si|sı|ü|u))?\s*(?:bir|1)\s*arada\s*[)\]]\s*$"
    r"|\s*[(\[]\s*(?:ikisi|üçü|ucu)\s*bir\s*arada\s*[)\]]\s*$",
    re.IGNORECASE,
)


def parse_volume_range(title: str | None) -> VolumeRange | None:
    """Parse an omnibus title ending in a consecutive volume span.

    Only a candidate: whether "9&10" is one 2-in-1 book or a two-book box
    is decided by the catalog (a volume that covers exactly 9-10). Titles
    with collection words ("Kutu Set") are never candidates.
    """
    if not title:
        return None
    text = re.sub(r"\s+", " ", title.strip()).rstrip(" .")
    text = _OMNIBUS_NOTE_RE.sub("", text).rstrip(" .")
    if _COLLECTION_WORD_RE.search(text):
        return None
    match = _OMNIBUS_RANGE_RE.search(text)
    if match is None:
        return None
    numbers = [int(n) for n in match.groups() if n is not None]
    if numbers[0] < 1 or any(b != a + 1 for a, b in zip(numbers, numbers[1:])):
        return None
    base = text[: match.start()].strip(" \t:;.,-–#([")
    if not base:
        return None
    return VolumeRange(base, numbers[0], numbers[-1])


def parse_volume_title(title: str | None) -> VolumeParseResult:
    """Parse ``title`` into base title, volume number and collection flag."""
    if not title or not title.strip():
        return VolumeParseResult("", None)

    text = re.sub(r"\s+", " ", title.strip())

    # Collections: a small volume range, or a strong collection word.
    if _is_volume_range(text) or _COLLECTION_WORD_RE.search(text):
        return VolumeParseResult(_strip_volume_tokens(text), None, is_collection=True)

    # Reject numeric metadata rather than treating a year, price or ISBN
    # fragment as a volume. Do not strip unrecognized numbers from the title.
    if re.search(r"\b(?:isbn|edition|bask[ıi]|fiyat|y[ıi]l)\b|\d[.,]\d|\b\d{10,13}\b", text, re.I):
        return VolumeParseResult(text, None, evidence="numeric_metadata")
    numbers = {int(m.group(1)) for pattern in (_VOLUME_MARKER_RE, _VOLUME_AFTER_RE, _MID_DASH_NUMBER_RE, _TRAILING_NUMBER_RE)
               for m in pattern.finditer(text) if 0 <= int(m.group(1)) <= _MAX_VOLUME}
    if len(numbers) > 1:
        return VolumeParseResult(text, None, evidence="ambiguous_numbers")
    for pattern, evidence in (
        (_VOLUME_MARKER_RE, "marker"), (_VOLUME_AFTER_RE, "number_before_marker"),
        (_MID_DASH_NUMBER_RE, "bilingual"), (_TRAILING_NUMBER_RE, "trailing_number"),
    ):
        match = pattern.search(text)
        if match and 0 <= int(match.group(1)) <= _MAX_VOLUME:
            base = (text[:match.start()] + " " + text[match.end():]).strip(" \t:;.,-–#()[]")
            base = re.sub(r"\s+", " ", base)
            return VolumeParseResult(base, int(match.group(1)), evidence=evidence)
    return VolumeParseResult(text, None)

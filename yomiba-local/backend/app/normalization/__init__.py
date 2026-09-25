"""Reusable, deterministic normalization utilities.

Everything here is a pure function: same input always yields the same output.
That makes the matching rules unit-testable and keeps business code free of
ad-hoc string handling.
"""

from .text import normalize_publisher, normalize_text
from .volume import VolumeParseResult, parse_volume_title
from .isbn import normalize_isbn

__all__ = [
    "normalize_text",
    "normalize_publisher",
    "parse_volume_title",
    "VolumeParseResult",
    "normalize_isbn",
]

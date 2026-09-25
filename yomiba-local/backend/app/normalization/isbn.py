"""ISBN normalization.

An ISBN is the strongest cross-store identifier for a physical book. We keep
only the digits (an ISBN-10 may end in "X") and accept only valid lengths,
so garbage is never used as a matching key.
"""

from __future__ import annotations

import re


def normalize_isbn(value: str | None) -> str | None:
    """Return a canonical digit-string ISBN, or ``None`` if not a valid ISBN.

    >>> normalize_isbn("978-605-9544-01-9")
    '9786059544019'
    >>> normalize_isbn("not-an-isbn") is None
    True
    """
    if not value:
        return None
    digits = re.sub(r"[^0-9Xx]", "", value).upper()
    if len(digits) in (10, 13):
        # For ISBN-10, only a trailing X check digit is legitimate.
        if len(digits) == 10 and "X" in digits[:-1]:
            return None
        return digits
    return None

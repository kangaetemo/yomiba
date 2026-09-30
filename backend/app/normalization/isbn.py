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


#: ISBN registration groups of Turkey (ISBN-13 prefixes). The catalog lists
#: Turkish editions only, so any other group (978-0/978-1 English, 978-4
#: Japanese, ...) is another edition of the work, never the catalog volume.
_TURKISH_ISBN13 = ("978975", "978605", "978625", "9789944")
_TURKISH_ISBN10 = ("975", "605", "9944")


def is_foreign_isbn(isbn: str | None) -> bool:
    """True when ``isbn`` is valid but not registered in Turkey.

    >>> is_foreign_isbn("9786257590549"), is_foreign_isbn("9781421502410")
    (False, True)
    >>> is_foreign_isbn(None)
    False
    """
    isbn = normalize_isbn(isbn)
    if isbn is None:
        return False
    prefixes = _TURKISH_ISBN13 if len(isbn) == 13 else _TURKISH_ISBN10
    return not isbn.startswith(prefixes)


_TURKISH_LANGUAGE = {"tr", "tur", "turkce", "turkish", "turkiye"}


def is_foreign_language(value: str | None) -> bool:
    """True when a store names a language that is not Turkish ("en",
    "English", "İngilizce"); unknown / empty is never foreign."""
    from .text import normalize_text

    key = normalize_text(value).split()
    if not key:
        return False
    first = key[0].split("-")[0]
    return first not in _TURKISH_LANGUAGE and not first.startswith("tr")

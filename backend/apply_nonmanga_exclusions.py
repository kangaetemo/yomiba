"""Retired exclusion maintenance entry point.

Mangakol's live manga list is Yomiba's catalog source of truth. Every live
entry belongs in the manifest, so the old non-manga exclusion operation is
invalid. This module stays as a safe stub for old operational references.
"""

from __future__ import annotations


def main() -> int:
    print(
        "apply_nonmanga_exclusions.py is retired: live Mangakol entries "
        "must not be excluded from the catalog."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

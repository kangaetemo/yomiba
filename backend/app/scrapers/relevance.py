"""Common manga/book relevance filter for scraper results.

Every store sells non-book merchandise next to manga (figures, TCG
boosters, posters, stationery, plushies, masks...). This module provides
ONE conservative, evidence-based rejection check that all store scrapers
apply to their normalized results before returning them.

Design rules (learned from the 2026-09 data-quality incidents):

* Title words are never the only signal for *weak* words. Weak tokens
  ("kart", "defter", "maske", "kupa", "puzzle") can appear in real book
  titles — e.g. "Ölüm Defteri" (Death Note) — so a single one never
  rejects on its own. Two INDEPENDENT weak signals (e.g. "kupa" plus a
  Sega publisher) are strong enough to reject.
* A centimetre size in the title ("16cm", "25 cm") is strong merchandise
  evidence: no real book title carries a physical size.
* Strong product-type words ("figür", "grandista", "tcg", "blind box",
  ...) and well-known toy manufacturers ("Banpresto", "Good Smile
  Company", ...) are strong evidence and reject on their own.
* A 978- (or 10-digit) ISBN is positive book evidence: it neutralizes
  weak signals.
* 13-digit codes with a Japanese toy prefix (45/49, no 978) are strong
  merchandise evidence.
* When a store supplies an explicit product category, a book category is
  book evidence (like a 978 ISBN: neutralizes weak signals, never
  overrides strong ones) and a toy category rejects outright. This keeps
  BKM's figure-in-a-book-category error case rejectable while protecting
  real books whose titles merely resemble merchandise.
* When in doubt, KEEP the product: a wrongly rejected real book is worse
  than a stray figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..normalization import normalize_text

#: Rejection score threshold (one strong signal or two weak ones).
_REJECT_SCORE = 2
_STRONG_SCORE = 2
_MEDIUM_SCORE = 1

#: Strong product-type tokens — unambiguous merchandise, reject alone.
_STRONG_MERCH_TOKENS: tuple[str, ...] = (
    # figures / statues / collectibles
    "figür", "figur", "figure", "figurine", "statue",
    "blind box", "blind bag", "mystery box",
    "ichiban kuji", "grandista", "vibration stars", "panel spectacle",
    "effectreme", "memorable saga", "combination battle", "g e m series",
    "reborn doll", "model kit", "plamo", "diorama",
    "funko",  # Funko Pop figures
    # figure-line names observed in live search results (2026-09 audit)
    "yumemirize", "luminasta", "xstellar",
    # cards / games
    "trading card", "tcg", "playing cards", "booster", "starter pack",
    "card game", "kart oyunu", "union arena",
    # printed merchandise
    "poster",
    # plush / toys
    "oyuncak", "plush", "peluş",
    # accessories
    "anahtarlık", "keychain", "akrilik", "acrylic", "piggy bank",
    "tişört", "tshirt", "tisort", "t shirt", "mousepad", "sticker",
    "yastık", "pillow",
    # headwear / lighting / small furniture (store merch lines); the
    # English "hat"/"lamp" are also context-dependent, see below
    "şapka", "hat", "lamp",
    # stationery
    "bloknot", "notebook",
    # money boxes ("Money Bank" product line)
    "money bank",
)

#: Weak tokens — may appear in real book titles ("Ölüm Defteri"!, chibi
#: art books, "Maske" titles); score only, never alone.
_MEDIUM_MERCH_TOKENS: tuple[str, ...] = (
    "kart", "puzzle", "defter", "kupa", "maske", "action", "asorti", "chibi",
    "sega",  # Sega-branded items in book stores are almost always figures
)

#: Strong tokens that are ALSO ordinary English words inside real manga
#: titles ("Witch Hat Atelier"). They reject on their own only when the
#: product carries no book evidence (978 ISBN / book category) and no
#: volume marker; "ONE PIECE - Replica Hat" is still merchandise.
_CONTEXT_STRONG_TOKENS: frozenset[str] = frozenset({"hat", "lamp"})

#: Strong tokens that also start real manga titles ("Oyuncak Bebek
#: Sevgilim" = My Dress-Up Darling). Only a book ISBN / book category
#: neutralizes them — not a bare number, since toy lines carry model
#: numbers ("Elaine Bebek 003").
_BOOK_EVIDENCE_STRONG_TOKENS: frozenset[str] = frozenset({"oyuncak"})

#: A volume marker ("Cilt 3", "Vol. 2", "Witch Hat Atelier 5") is book
#: evidence for the context-dependent tokens above. A size ("25 cm") is
#: never mistaken for one: it is strong merch evidence on its own.
_VOLUME_MARKER_RE = re.compile(r"\b(cilt|vol|volume|sayi)\b|\b\d{1,3}\b(?!\s?cm\b)")

#: A centimetre size in the title ("25cm", "16 cm") marks a physical
#: object; no real book title carries one. Strong evidence.
_SIZE_RE = re.compile(r"\b\d{1,3}\s?cm\b")

#: Publishers that (in book-store contexts) sell figures/merch, not manga.
_TOY_PUBLISHERS: frozenset[str] = frozenset({
    "banpresto",
    "good smile company",
    "megahouse",
    "kotobukiya",
    "prime 1 studio",
    "max factory",
    "medicom toy",
    "bandai spirits",
    "takara tomy",
})

#: Publishers that ALSO publish genuine manga, so a bare match is only weak
#: evidence (scores like a weak title token; never rejects alone).
_WEAK_PUBLISHERS: frozenset[str] = frozenset({
    "sega",  # mostly figure lines (Yumemirize & co.) in book-store results
})

_BOOK_CATEGORY_TOKENS: tuple[str, ...] = (
    "kitap", "kitaplar", "manga", "roman", "çocuk", "anime",
)
_MERCH_CATEGORY_TOKENS: tuple[str, ...] = (
    "oyuncak", "hobi", "figür", "kart", "aksesuar", "toys", "games",
)

_STRONG_RE = re.compile(
    r"\b(" + "|".join(re.escape(normalize_text(t)) for t in _STRONG_MERCH_TOKENS) + r")\b"
)
_MEDIUM_RE = re.compile(
    r"\b(" + "|".join(re.escape(normalize_text(t)) for t in _MEDIUM_MERCH_TOKENS) + r")\b"
)


@dataclass(frozen=True)
class RelevanceVerdict:
    """Outcome of :func:`check_manga_relevance` for one product."""

    accept: bool
    #: Rejection reason (``"merch:<evidence>"``), or ``None`` when accepted.
    reason: str | None = None


def _is_japanese_merch_code(isbn: str) -> bool:
    """13-digit codes with a 45/49 prefix are JAN product codes used by
    Japanese toys/figures; real (imported) books carry a 978- ISBN."""
    return (
        len(isbn) == 13
        and isbn.isdigit()
        and not isbn.startswith("978")
        and isbn.startswith(("45", "49"))
    )


def check_manga_relevance(
    *,
    title: str | None,
    publisher: str | None = None,
    isbn: str | None = None,
    category: str | None = None,
) -> RelevanceVerdict:
    """Decide whether a store product is a manga/book (accept) or
    merchandise (reject).

    Evidence is combined: strong title tokens, weak title tokens, toy
    publishers, ISBN shape and (when available) the store's own category.
    The function never raises; any missing field simply means less
    evidence.
    """
    # 1) The store's explicit toy category rejects outright (defense in
    #    depth: BKM already drops non-book categories; this keeps the rule
    #    in ONE place). A book category is book evidence, handled below.
    if category:
        cat = normalize_text(category)
        if any(tok in cat for tok in _MERCH_CATEGORY_TOKENS):
            return RelevanceVerdict(False, "merch:category")
        book_category = any(tok in cat for tok in _BOOK_CATEGORY_TOKENS)
    else:
        book_category = False

    norm_title = normalize_text(title)
    score = 0
    evidence: list[str] = []

    code = (isbn or "").strip()
    book_evidence = (code.startswith("978") or len(code) == 10) or book_category

    strong_hits = _STRONG_RE.findall(norm_title)
    if strong_hits and set(strong_hits) <= _CONTEXT_STRONG_TOKENS and (
        book_evidence or _VOLUME_MARKER_RE.search(norm_title)
    ):
        # Only "hat"/"lamp"-style words, and the product looks like a book.
        strong_hits = []
    if strong_hits and set(strong_hits) <= _BOOK_EVIDENCE_STRONG_TOKENS and book_evidence:
        strong_hits = []
    if strong_hits:
        score += _STRONG_SCORE
        evidence.append(f"token:{strong_hits[0]}")

    size_hit = _SIZE_RE.search(norm_title)
    if size_hit:
        score += _STRONG_SCORE
        evidence.append(f"size:{size_hit.group(0)}")

    if _is_japanese_merch_code(code):
        score += _STRONG_SCORE
        evidence.append("jp-product-code")

    pub = normalize_text(publisher) if publisher else ""
    if pub in _TOY_PUBLISHERS:
        score += _STRONG_SCORE
        evidence.append(f"publisher:{pub}")
    elif pub in _WEAK_PUBLISHERS and not book_evidence:
        # Weak publisher signal: like weak title tokens, it can be
        # neutralized by book evidence and never rejects on its own.
        score += _MEDIUM_SCORE
        evidence.append(f"weak-publisher:{pub}")
    if not book_evidence:
        # Each distinct weak token scores, so TWO independent weak signals
        # ("kupa" + "sega") are as damning as one strong one — while any
        # single weak word in an otherwise plain title stays.
        medium_hits = set(_MEDIUM_RE.findall(norm_title))
        if medium_hits:
            score += _MEDIUM_SCORE * len(medium_hits)
            evidence.append("weak-token:" + "+".join(sorted(medium_hits)))
    # Book evidence (978-/10-digit ISBN or a book category) neutralizes
    # weak tokens but never strong ones.

    if score >= _REJECT_SCORE:
        return RelevanceVerdict(False, "merch:" + "+".join(evidence))
    return RelevanceVerdict(True)


def filter_manga_results(
    results: list, *, stats: dict | None = None
) -> list:
    """Apply :func:`check_manga_relevance` to a list of ``SearchResult``.

    Rejected products are dropped; when ``stats`` is provided they are
    counted under ``stats["rejected"]["non_manga"]`` using the same
    diagnostics contract the individual scrapers already expose.
    """
    kept: list = []
    for result in results:
        verdict = check_manga_relevance(
            title=result.title,
            publisher=result.publisher,
            isbn=result.isbn,
            category=getattr(result, "category", None),
        )
        if verdict.accept:
            kept.append(result)
        else:
            if stats is not None:
                rejected = stats.setdefault("rejected", {})
                rejected["non_manga"] = rejected.get("non_manga", 0) + 1
    return kept

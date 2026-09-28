"""Common manga/book relevance filter (app/scrapers/relevance.py).

The title tables are the REAL products observed in the 2026-09
data-quality audit of the live database: every merchandise item found in
"naruto", "one punch man", "one piece", "berserk" and "jujutsu kaisen"
store searches must be rejected, and every legitimate book — including
titles that merely resemble merchandise — must be accepted.
"""

from __future__ import annotations

import pytest

from app.scrapers.relevance import check_manga_relevance

# (title, publisher, isbn) — merchandise observed in live searches.
OBSERVED_MERCH = [
    # one punch man (Banpresto figures, Diorama)
    ("One Punch Man - Saitama - Grandista (Bandai Spirits", "Banpresto", None),
    ("One Punch Man - Saitama - One Punch Life ~Shopping~ (Bandai Spirits",
     "Banpresto", None),
    ("ONE-PUNCH MAN - DIORAMA", "Banpresto", "4983164300383"),
    # naruto (Vibration Stars / Grandista / TCG / plush & bank merch)
    ("NARUTO SHIPPUDEN - VIBRATION STARS - UZUMAKI NARUTO", "Banpresto", None),
    ("NARUTO 72 SERIES - VIBRATION STARS", "Banpresto", None),
    ("NARUTO - COMBINATION BATTLE 2 - GAARA", "Banpresto", None),
    ("NARUTO - Memorable Saga - UCHIHA SASUKE", "Banpresto", None),
    ("Naruto Mythos TCG Trading Card", None, None),
    ("Naruto Mythos TCG Trading Cards - 1st Edition Starter Pack Naruto/Sasuke",
     None, None),
    ("Naruto - Hokage Rock piggy bank", None, None),
    ("Naruto G.E.M. Series PVC Statue Naruto Uzumaki Go! 15cm", None, None),
    ("NARUTO SHIPPUDEN - COMBINATION BATTLE - SASUKE UCHIHA", "Banpresto", None),
    ("Naruto Shippuden - Hatake Kakashi - Vibration Stars - III (Bandai Spirits",
     "Banpresto", None),
    ("Naruto Shippuden - Uzumaki Naruto - Grandista", "Banpresto", None),
    ("Naruto Shippuden - Sasori - EFFECTREME", "Banpresto", None),
    ("Naruto Shippuden - Senju Tobirama - Panel Spectacle The Strongest Troops",
     "Banpresto", None),
    ("Naruto Playing Cards", None, None),
    # jujutsu kaisen / tokyo ghoul / other series
    ("JUJUTSU KAISEN - JUFUTSUNOWAZA - SUGURU GETO", "Banpresto", None),
    ("JUJUTSU KAISEN - UNION ARENA - BOOSTER JAPONCA", None, None),
    ("Tokyo Ghoul Playing Cards", None, None),
    ("Fairy Tail Playing Cards", None, None),
    # 2026-09 live re-verification (cizman / gerekliseyler / kitapbulan /
    # kitapsec / kitapsepeti searches)
    ("Funko Pop Jumbo Animation One Piece - Kaido Dragon Form Special Edition"
     " 25cm No:1623", None, None),
    ("One Piece T-Shirt", None, None),
    ("ONE PIECE - Monkey D. Luffy Straw Hat [Hasır Şapka]- Adult Size",
     None, None),
    ("ONE PIECE - Replica Hat - Tony Tony Chopper", None, None),
    ("ONE PIECE - A5 Notebook Wanted Luffy Wano", None, None),
    ("ONE PIECE - Lamp - Skull", None, None),
    ("ONE PIECE - Money Bank - Strawhat", None, None),
    ("Jujutsu Kaisen 0 - Inumaki Toge - Yumemirize (SEGA)", None, None),
    ("Jujutsu Kaisen - Gojo Satoru - Luminasta ~5th Anniversary~",
     None, None),
    ("Jujutsu Kaisen: Culling Game - Itadori Yuji - XStellar", None, None),
    ("Jujutsu Kaisen Bloknot", None, None),
]

# (title, publisher, isbn) — legitimate books, including trap titles that
# merely resemble merchandise.
REAL_BOOKS = [
    # hybrid store titles of the same books (imported as real series)
    ("One Punch Man 30 - Tek Yumruk", "Akılçelen", None),
    ("One-Punch Man - Tek Yumruk (Cilt 3)", "Akılçelen Kitaplar", None),
    ("Berserk 6", "Athica Yayınları", "9786053600725"),
    ("One Piece 36", "Uiui Yayın", "9786256031791"),
    ("Tokyo Ghoul: re", "Gerekli Şeyler Yayıncılık", None),
    ("TOKYO GHOUL VOID LIGHT NOVEL", None, None),
    ("Jujutsu Kaisen Vakitsiz Ölüm", "Gerekli Şeyler Yayıncılık",
     "9786256031791"),
    ("Naruto: Sasuke's Story--The Uchiha and the Heavenly Stardust: The Manga",
     "Viz Media", None),
    ("Naruto Shippuden 1", "Gerekli Şeyler Yayıncılık", "9786051234567"),
    ("Kara Meşale - Black Torch", "Karakarga", None),
    ("Paradise Kiss – Cennet Öpücüğü", "Akılçelen", None),
    ("Vinland Saga - Vinland Destanı (Cilt 2)", "Akılçelen", None),
    ("Orange -To You, Dear One", "Gerekli Şeyler", "9786056123456"),
    # trap titles: weak merch words inside real book titles
    ("Ölüm Defteri 1", "Nobel Yayınları", "9786057890001"),
    ("Ölüm Defteri 2", None, None),
    ("Maske", "Athica Yayınları", None),
    ("Kart", "Nobel", None),
    ("Puzzle", "Bilim Sanat", None),
    ("Kupa Şampiyonu", "Kolektif", None),
    # books accepted in the 2026-09 live re-verification (spin-offs,
    # guidebooks, novels, foreign editions)
    ("Berserk of Gluttony (Manga) Vol. 8", "Viz Media", None),
    ("BERSERK TP VOL 01 BLACK SWORDSMAN", "Viz Media", None),
    ("Berserk Volume 42", "Athica Yayınları", None),
    ("Berserk Official Guidebook", "Athica Yayınları", None),
    ("Savaşçının Açlığı 3", "Athica Yayınları", None),
    ("Naruto 5 Düellocular", "Gerekli Şeyler Yayıncılık", None),
    ("Naruto Felsefesi", "Gerekli Şeyler Yayıncılık", None),
    ("One Piece 27 Uvertür", "Gerekli Şeyler Yayıncılık", None),
    ("One Piece: Güç Dersleri", "Gerekli Şeyler Yayıncılık", None),
    ("One Piece 107 (Japanese Edition)", "Shueisha", None),
    ("Jujutsu Kaisen: The Official Anime Guide: Season 1",
     "Gerekli Şeyler Yayıncılık", None),
    ("Jujutsu Kaisen: Thorny Road at Dawn (Jujutsu Kaisen Novels)",
     "Gerekli Şeyler Yayıncılık", None),
    # word-boundary guard: "hat" inside "Hatsune" is NOT the merch word
    ("Hatsune Miku Songbook 1", "Gerekli Şeyler Yayıncılık", None),
]


@pytest.mark.parametrize(
    "title, pub, isbn", OBSERVED_MERCH, ids=lambda v: v[:32] if isinstance(v, str) else ""
)
def test_observed_merch_is_rejected(title, pub, isbn):
    verdict = check_manga_relevance(title=title, publisher=pub, isbn=isbn)
    assert not verdict.accept, f"merch accepted: {title!r}"
    assert verdict.reason is not None and verdict.reason.startswith("merch:")


@pytest.mark.parametrize(
    "title, pub, isbn", REAL_BOOKS, ids=lambda v: v[:32] if isinstance(v, str) else ""
)
def test_real_books_are_accepted(title, pub, isbn):
    verdict = check_manga_relevance(title=title, publisher=pub, isbn=isbn)
    assert verdict.accept, f"book wrongly rejected: {title!r} ({verdict.reason})"


# -- evidence combinations ---------------------------------------------------------

def test_toy_publisher_alone_rejects():
    verdict = check_manga_relevance(title="Berserk", publisher="Banpresto")
    assert not verdict.accept
    assert "publisher" in verdict.reason


def test_weak_token_alone_kept():
    assert check_manga_relevance(title="Kupa Şampiyonu").accept
    assert check_manga_relevance(title="Ölüm Defteri 2").accept


def test_weak_token_plus_toy_publisher_rejects():
    verdict = check_manga_relevance(title="Kupa", publisher="Banpresto")
    assert not verdict.accept


def test_weak_token_plus_japanese_product_code_rejects():
    verdict = check_manga_relevance(title="Kupa", isbn="4512345678901")
    assert not verdict.accept


def test_japanese_product_code_alone_rejects():
    verdict = check_manga_relevance(title="Berserk", isbn="4983164300383")
    assert not verdict.accept


def test_book_isbn_neutralizes_weak_but_not_strong():
    # weak token + 978 ISBN -> book evidence wins
    assert check_manga_relevance(
        title="Ölüm Defteri 1", isbn="9786057890001"
    ).accept
    # strong token still rejects even with a book ISBN
    assert not check_manga_relevance(
        title="Berserk Figür 16cm", isbn="9786057890001"
    ).accept


def test_book_category_neutralizes_weak_but_not_strong():
    # BKM-shape product: book category + weak-looking title -> keep
    assert check_manga_relevance(
        title="Kupa Şampiyonu", category="Edebiyat Kitapları"
    ).accept
    # BKM data-error shape: book category + strong merch word -> reject
    assert not check_manga_relevance(
        title="One Piece 55. Cilt Grandista", category="Edebiyat Kitapları"
    ).accept


def test_toy_category_rejects_outright():
    verdict = check_manga_relevance(title="Berserk", category="Oyuncak")
    assert not verdict.accept
    assert verdict.reason == "merch:category"


def test_missing_fields_never_raise():
    assert check_manga_relevance(title=None).accept
    assert check_manga_relevance(title="", publisher=None, isbn=None).accept


def test_centimetre_size_rejects():
    # A size like "16cm" / "25 cm" marks a physical figure, not a book.
    assert not check_manga_relevance(
        title="Naruto Go! 15cm",
    ).accept
    assert not check_manga_relevance(
        title="One Piece - Kaido - Special Edition 25 cm",
    ).accept
    # ...and a bare series title with no size stays.
    assert check_manga_relevance(title="Naruto 15").accept


def test_hat_is_word_bounded():
    # "hat" as a merch word rejects a hat product...
    assert not check_manga_relevance(title="ONE PIECE - Replica Hat").accept
    # ...but "hat" embedded in "Hatsune" (a real artist name) must NOT.
    assert check_manga_relevance(title="Hatsune Miku Songbook 1").accept


def test_sega_medium_scores():
    # Sega alone is weak (some manga carry it); combined with another
    # weak signal it rejects, but a bare Sega-published book is kept.
    assert check_manga_relevance(
        title="Sailor Moon", publisher="SEGA"
    ).accept
    assert not check_manga_relevance(
        title="Sailor Moon Kupa", publisher="SEGA"
    ).accept


@pytest.mark.parametrize("title, isbn", [
    ("Witch Hat Atelier 1", None),
    ("Witch Hat Atelier Cilt 3", None),
    ("Witch Hat Atelier", "9786256327100"),
    ("Sapkali Cadi Atolyesi - Witch Hat Atelier Vol. 2", None),
])
def test_hat_in_real_title_is_kept(title, isbn):
    assert check_manga_relevance(title=title, isbn=isbn).accept


def test_context_hat_without_book_evidence_still_rejected():
    assert not check_manga_relevance(title="ONE PIECE - Replica Hat").accept
    assert not check_manga_relevance(title="ONE PIECE - Lamp - Skull").accept
    # A size is not a volume marker: "25 cm" stays merchandise.
    assert not check_manga_relevance(title="Luffy Lamp 25 cm").accept
    # Other strong tokens are never neutralized by a volume number.
    assert not check_manga_relevance(title="Witch Hat Atelier Poster 1").accept

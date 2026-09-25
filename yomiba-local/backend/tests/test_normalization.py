"""Tests for text / publisher normalization."""

from app.normalization import normalize_publisher, normalize_text


def test_basic_case_and_whitespace():
    assert normalize_text("  Berserk   Cilt  2 ") == "berserk cilt 2"
    assert normalize_text("Berserk") == "berserk"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_turkish_characters_fold_to_ascii():
    assert normalize_text("Athica Yayınları") == "athica yayinlari"
    assert normalize_text("Dark Horse") == "dark horse"
    assert normalize_text("Glénat") == "glenat"


def test_dotted_and_dotless_i_converge():
    # İ, I, ı, i must all normalize to the same key.
    assert normalize_text("İstanbul") == normalize_text("Istanbul")
    assert normalize_text("ıstiklal") == normalize_text("Istiklal")
    assert normalize_text("İSTİKLAL") == normalize_text("istiklal")


def test_publisher_normalization_equivalent_forms():
    a = normalize_publisher("Athica  Yayınları")
    b = normalize_publisher("athica yayinlari")
    assert a == b == "athica yayinlari"


def test_publisher_does_not_overmerge_distinct_companies():
    # Different publishers must not collide.
    assert normalize_publisher("Athica Yayınları") != normalize_publisher("Dark Horse")
    assert normalize_publisher("Oğuz Yayınları") != normalize_publisher("Oğuz")


def test_different_titles_stay_different():
    # Critical: must not merge unrelated series that share a prefix.
    assert normalize_text("Berserk") != normalize_text("Berserk of Gluttony")
    assert normalize_text("One Piece") != normalize_text("One Piece Colored")

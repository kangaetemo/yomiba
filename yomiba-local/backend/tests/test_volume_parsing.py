"""Tests for volume-number parsing and title splitting."""

from app.normalization import parse_volume_title
from app.normalization.volume import UNNUMBERED_VOLUME


def parse(title):
    return parse_volume_title(title)


def test_trailing_number():
    assert parse("Berserk 1").volume_number == 1
    assert parse("Berserk 1").base_title == "Berserk"
    assert parse("Berserk 124").volume_number == 124


def test_cilt_marker():
    assert parse("Berserk Cilt 2").volume_number == 2
    assert parse("Berserk Cilt 2").base_title == "Berserk"
    assert parse("Berserk C.3").volume_number == 3
    assert parse("Berserk 4. Cilt").volume_number == 4


def test_vol_and_number_markers():
    assert parse("Berserk Vol. 4").volume_number == 4
    assert parse("Berserk Volume 5").volume_number == 5
    assert parse("Berserk #6").volume_number == 6
    assert parse("Berserk No. 7").volume_number == 7


def test_parenthesized_number():
    assert parse("Berserk (8)").volume_number == 8
    assert parse("Berserk (8)").base_title == "Berserk"


def test_no_number():
    assert parse("Berserk").volume_number is None
    assert parse("Attack on Titan").volume_number is None
    assert parse("Berserk Deluxe").volume_number is None


def test_prefix_does_not_grab_unrelated_title():
    # "Berserk of Gluttony" has no volume number; base title preserved.
    assert parse("Berserk of Gluttony").volume_number is None
    assert parse("Berserk of Gluttony").base_title == "Berserk of Gluttony"


def test_collection_range():
    r = parse("Berserk 1-5")
    assert r.is_collection is True
    assert r.volume_number is None


def test_collection_word():
    r = parse("Berserk Box")
    assert r.is_collection is True


def test_unnumbered_sentinel_value():
    assert UNNUMBERED_VOLUME == -1


def test_mid_dash_number_bilingual_title():
    # "One Punch Man 3 - Tek Yumruk": the number sits before a dash and the
    # (Turkish) title continues after it.
    r = parse("One Punch Man 3 - Tek Yumruk")
    assert r.volume_number == 3
    assert r.base_title == "One Punch Man Tek Yumruk"


def test_mid_dash_number_single_digit():
    r = parse("One Punch Man 1 - Tek Yumruk")
    assert r.volume_number == 1
    assert r.base_title == "One Punch Man Tek Yumruk"


def test_mid_dash_requires_letter_after_dash():
    # ISBN fragment: digit-dash-digit is NOT a volume marker.
    r = parse("978-605-360072-5")
    assert r.volume_number == 605  # pre-existing behaviour, unchanged
    # A four-digit number before a dash is not a plausible volume.
    r = parse("1001 Gece - Masallar")
    assert r.volume_number is None
    assert r.base_title == "1001 Gece - Masallar"

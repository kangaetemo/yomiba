"""Tests for shared scraper helpers (Turkish price parsing + bot-wall detection)."""

from decimal import Decimal

from app.scrapers.common import has_block_marker, looks_like_blocked_page, parse_tr_price


def test_comma_decimal():
    assert parse_tr_price("163,54") == Decimal("163.54")


def test_thousands_and_decimal():
    assert parse_tr_price("1.234,56") == Decimal("1234.56")


def test_thousands_only():
    assert parse_tr_price("1.234") == Decimal("1234")


def test_plain_integer():
    assert parse_tr_price("182") == Decimal("182")
    assert parse_tr_price(182) == Decimal("182")


def test_currency_symbols():
    assert parse_tr_price("₺163,54") == Decimal("163.54")
    assert parse_tr_price("169,00 TL") == Decimal("169.00")


def test_dot_decimal_without_comma():
    # "163.54" (single dot, not a thousands group) is treated as decimal.
    assert parse_tr_price("163.54") == Decimal("163.54")


def test_garbage():
    assert parse_tr_price("") is None
    assert parse_tr_price(None) is None
    assert parse_tr_price("ücretsiz") is None
    assert parse_tr_price("-5") is None


# --- bot-wall marker detection --------------------------------------------
# Regression: kitapsec.com is a fully rendered, scrapeable search page that
# merely *includes* the reCAPTCHA loader script. That script include must NOT
# be mistaken for a bot wall.
def test_recaptcha_script_include_is_not_a_wall():
    page = (
        "<html><head>"
        "<script src=\"https://www.google.com/recaptcha/api.js\"></script>"
        "<link rel=\"stylesheet\" href=\"/temalar/style.css\">"
        "<link rel=\"icon\" href=\"/favicon.ico\"/>"
        "</head><body>"
        "<div class=\"Ks_UrunSatir\" itemtype=\"https://schema.org/Product\">"
        "<meta itemprop=\"name\" content=\"Berserk Cilt 1\"/>"
        "</div>"
        "</body></html>"
    )
    assert has_block_marker(page) is False
    assert looks_like_blocked_page(200, page) is False


def test_visible_captcha_text_is_a_wall():
    page = (
        "<html><body><h1>Robot check</h1>"
        "<p>Lütfen captcha doğrulamasını tamamlayın.</p></body></html>"
    )
    assert has_block_marker(page) is True
    assert looks_like_blocked_page(200, page) is True


def test_wall_status_codes_still_block():
    assert looks_like_blocked_page(403, "") is True
    assert looks_like_blocked_page(429, "") is True
    assert looks_like_blocked_page(503, "") is True
    assert looks_like_blocked_page(200, "") is False

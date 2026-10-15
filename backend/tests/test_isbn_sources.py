"""Source boundaries: no live network, no block bypass, no false absence."""
import httpx
import pytest

from app.scrapers.base import ScraperError
from app.services.isbn_sources import PoliteClient, RetailerSource, collect_sources
from tests.test_isbn_audit import target


def test_robot_failure_is_cached_and_never_becomes_no_result(monkeypatch):
    calls = []
    def robots(url, **_kwargs):
        calls.append(url)
        return httpx.Response(403, text="Forbidden", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", robots)
    with PoliteClient() as client:
        for _ in range(2):
            with pytest.raises(ScraperError, match="403"):
                client.check_request(httpx.Request("GET", "https://www.pandora.com.tr/"))
    assert calls == ["https://www.pandora.com.tr/robots.txt"]


def test_unapproved_redirect_and_robot_disallow_are_rejected(monkeypatch):
    with PoliteClient() as client:
        with pytest.raises(ScraperError, match="alan adının"):
            client.check_request(httpx.Request("GET", "https://internal.example/private"))
        monkeypatch.setattr(httpx, "get", lambda url, **_: httpx.Response(200, text="User-agent: *\nDisallow: /", request=httpx.Request("GET", url)))
        with pytest.raises(ScraperError, match="izin vermiyor"):
            client.check_request(httpx.Request("GET", "https://www.kitapyurdu.com/kitap/x"))


def test_unrecognized_search_template_is_error_not_absence():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<h1>Site maintenance</h1>"))) as client:
        source = RetailerSource("kitapyurdu", "kitapyurdu", client)
        assert collect_sources(target(), [source])[0]["status"] == "ERROR"


def test_edition_discovery_does_not_confuse_novel_and_webtoon_or_variants():
    t = target(title="Solo Leveling", volume_number=2)
    assert RetailerSource.candidate(t, "Solo Leveling Webtoon Cilt 2")
    assert not RetailerSource.candidate(t, "Solo Leveling Novel Cilt 2")
    assert not RetailerSource.candidate(t, "Solo Leveling Webtoon Cilt 2 (Varyant Kapak)")


def test_circuit_backoff_retains_source_error_and_limits_requests():
    class Source:
        code = group = "kitapyurdu"
        calls = 0
        def collect(self, target):
            self.calls += 1
            raise ScraperError("HTTP 429")
    source = Source()
    assert collect_sources(target(), [source])[0]["status"] == "ERROR"
    assert collect_sources(target(), [source])[0]["status"] == "ERROR"
    assert source.calls == 1

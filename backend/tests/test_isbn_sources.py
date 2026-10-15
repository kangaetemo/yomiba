"""Source boundaries: no live network, no block bypass, no false absence."""
import httpx
import pytest

from app.scrapers.base import ScraperError
from app.services.isbn_sources import PoliteClient, RetailerSource, collect_sources
from app.services.isbn_identity import evaluate
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


@pytest.mark.parametrize("first_number", [28, 29])
def test_all_search_pages_are_followed_before_absence_or_consensus(first_number):
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path == "/index.php":
            page = request.url.params.get("page", "1")
            if page == "1":
                html = f'<a class="ky-product-title" href="/kitap/first/1.html">Blue Lock Cilt {first_number}</a><a href="/index.php?route=product/list&amp;filter_name=Blue+Lock+29&amp;page=2">2</a>'
            else:
                html = '<a class="ky-product-title" href="/kitap/second/2.html">Blue Lock Cilt 29</a>'
        else:
            isbn = "9786258630633" if "/first/" in request.url.path else "9786258630640"
            html = '<h1>Blue Lock Cilt 29</h1><script type="application/ld+json">' + '{"@type":"Book","isbn":"'+isbn+'","publisher":{"name":"Komikşeyler"},"inLanguage":"tr","bookFormat":"Paperback"}</script>'
        return httpx.Response(200, text=html)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = RetailerSource("kitapyurdu", "kitapyurdu", client).collect(target())
    assert any("page=2" in url for url in calls)
    assert any(e["isbn"] == "9786258630640" for e in records)
    if first_number == 29:
        assert len(records) == 2
        assert evaluate(target(), records)[0] == "CONFLICT"
    else:
        assert len(records) == 1 and records[0]["status"] == "MATCH"

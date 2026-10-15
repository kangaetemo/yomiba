"""Source boundaries: no live network, no block bypass, no false absence."""
import httpx
import pytest

from app.scrapers.base import ScraperError
from app.services.isbn_sources import PoliteClient, RetailerSource, SearchIncompleteError, collect_sources
from app.services.isbn_identity import evaluate
from tests.test_isbn_audit import target


def bora_product(*, complete=True, language="Türkçe", title="Blue Lock 29"):
    return f'''<h2 class="h2musteri">{title}</h2>
      <table class="description_table"><tr><td>Yayınevi:</td><td>Komikşeyler</td></tr>
      <tr><td>Barkod:</td><td>9786258630633</td></tr></table>
      <table id="tbldetaylar">{f'<tr><td>Basım Dili</td><td>{language}</td></tr><tr><td>Kapak Türü</td><td>Karton Kapak</td></tr>' if complete else ''}</table>
      <table><tr><td>Barkod</td><td>9786258630640</td></tr></table>'''


@pytest.mark.parametrize("complete,status", [(True, "MATCH"), (False, "INCOMPLETE")])
def test_bora_reads_only_primary_utf8_bibliography_and_checks_completeness(complete, status):
    def respond(request):
        if request.url.path.endswith("Listele.aspx"):
            assert request.url.params["ara"] == "Blue Lock 29"
            return httpx.Response(200, text='''<section class="products_container"><div class="product_item">
              <a class="color_dark" href="/Istem/Urun/Detay.aspx?Id=123">Blue Lock 29</a></div></section>
              Gösterilen : 1 - 1 / Hepsi : 1''')
        return httpx.Response(200, content=bora_product(complete=complete).encode("utf-8"))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = RetailerSource("bora", "bora", client).collect(target())
    assert len(records) == 1 and records[0]["status"] == status
    assert records[0]["publisher"] == "Komikşeyler"
    assert records[0]["isbn"] == "9786258630633"
    assert records[0]["raw_isbns"] == ["9786258630633"]


def test_incomplete_bora_search_never_votes_or_declares_absence():
    body = '<section class="products_container"><div class="product_item"><a class="color_dark" href="/Istem/Urun/Detay.aspx?Id=1">Blue Lock 29</a></div></section>Gösterilen : 1 - 1 / Hepsi : 2'
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200,text=body))) as client:
        assert collect_sources(target(), [RetailerSource("bora","bora",client)])[0]["status"] == "ERROR"


def test_temporary_robots_failure_expires_without_bypassing_rules(monkeypatch):
    from app.services import isbn_sources
    now, calls = [1000], []
    monkeypatch.setattr(isbn_sources.time, "monotonic", lambda: now[0])
    def robots(url, **kwargs):
        calls.append(url)
        return httpx.Response(403 if len(calls)==1 else 200, text="User-agent: *\nAllow: /", request=httpx.Request("GET",url))
    monkeypatch.setattr(httpx, "get", robots)
    with PoliteClient() as client:
        request=httpx.Request("GET","https://boradagitim.com/Istem/Urun/Detay.aspx?Id=1")
        for _ in range(2):
            with pytest.raises(ScraperError,match="403"):client.check_request(request)
        assert len(calls)==1
        now[0]+=61
        client.check_request(request)
        assert len(calls)==2


def test_circuit_message_exposes_first_error_and_recovers(monkeypatch):
    from app.services import isbn_sources
    now=[1000]
    monkeypatch.setattr(isbn_sources.time,"monotonic",lambda:now[0])
    class Source:
        code=group="bkm"
        calls=0
        def collect(self,t):
            self.calls+=1
            if self.calls==1:raise ScraperError("HTTP 429: test erişim hatası")
            return [dict(source=self.code,independence_group=self.group,status="NO_RESULT",isbn=None)]
    source=Source()
    collect_sources(target(),[source])
    assert "HTTP 429" in collect_sources(target(),[source])[0]["reason"]
    assert source.calls==1
    now[0]+=61
    assert collect_sources(target(),[source])[0]["status"]=="NO_RESULT"
    assert source.calls==2 and source.failures==0


def test_incomplete_query_does_not_suppress_other_volumes():
    class Source:
        code=group="bkm"
        calls=0
        def collect(self,t):
            self.calls+=1
            if self.calls==1:raise SearchIncompleteError("Bu sorgunun sonuçları kesildi")
            return [dict(source=self.code,independence_group=self.group,status="NO_RESULT",isbn=None)]
    source=Source()
    assert collect_sources(target(),[source])[0]["status"]=="ERROR"
    assert collect_sources(target(volume_number=30),[source])[0]["status"]=="NO_RESULT"
    assert source.calls==2


def test_canonical_title_query_ignores_search_only_alias_noise():
    calls=[]
    def respond(request):
        calls.append(request.url.params.get("q"))
        return httpx.Response(200,text="Arama kriterlerine uygun ürün bulunamadı")
    t=target(title="Jujutsu Kaisen - Lanet Savaşları",original_title="jujutsu kaisen",catalog_slugs=["jujutsu-kaisen"],volume_number=3)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        RetailerSource("kitapsepeti","kitapsepeti",client).collect(t)
    assert calls==["jujutsu kaisen 3"]


def test_bkm_uses_exact_isbn_lookup_but_still_checks_the_whole_book(monkeypatch):
    from app.scrapers.search_result import SearchResult
    from app.services import isbn_sources
    calls=[]
    class Search:
        def __init__(self,**kwargs):
            from app.config import get_settings
            self.settings=get_settings();self.stats={"stop_reason":"complete"}
        def search(self,query):
            calls.append(query)
            return [SearchResult(store_id="bkm",store_name="BKM",title="Blue Lock 29",product_url="https://www.bkmkitap.com/book")]
    monkeypatch.setattr(isbn_sources,"BkmScraper",Search)
    html='''<h1>Blue Lock 29</h1><script type="application/ld+json">{"@type":"Book","isbn":"9786258630633","publisher":"Komikşeyler","inLanguage":"English","bookFormat":"Paperback"}</script>'''
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=html))) as client:
        records=RetailerSource("bkm","bkm",client).collect(target())
    assert calls==[target()["isbn"]]
    assert records[0]["status"]=="MISMATCH"


@pytest.mark.parametrize("title,expected", [("Blue Lock 29","MATCH"),("Blue Lock 28","MISMATCH")])
def test_existing_product_url_is_verified_without_relying_on_search(title,expected):
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        if request.url.path=="/arama":return httpx.Response(200,text="Arama kriterlerine uygun ürün bulunamadı")
        return httpx.Response(200,text=f'''<h1>{title}</h1><script type="application/ld+json">{{"@type":"Book","url":"https://www.kitapsepeti.com/book","publisher":"Komikşeyler","isbn":"9786258630633","inLanguage":"Turkish","bookFormat":"Paperback"}}</script>''')
    t=target(title="Blue Lock (Komikşeyler)",source_product_urls={"kitapsepeti":["https://www.kitapsepeti.com/book","https://internal.example/private"]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records=RetailerSource("kitapsepeti","kitapsepeti",client).collect(t)
    assert records[0]["status"]==expected
    assert calls==["https://www.kitapsepeti.com/book"]


def test_known_product_contradictions_are_all_retained():
    from tests.test_isbn_audit import evidence
    def respond(request):
        code="9786258630633" if request.url.path=="/one" else "9786258630640"
        return httpx.Response(200,text=f'''<h1>Blue Lock 29</h1><script type="application/ld+json">{{"@type":"Book","publisher":"Komikşeyler","isbn":"{code}","inLanguage":"Turkish","bookFormat":"Paperback"}}</script>''')
    t=target(source_product_urls={"kitapsepeti":["https://www.kitapsepeti.com/one","https://www.kitapsepeti.com/two"]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records=RetailerSource("kitapsepeti","kitapsepeti",client).collect(t)
    assert len(records)==2 and evaluate(t,records+[evidence()])[0]=="CONFLICT"


def test_removed_product_url_falls_back_to_canonical_search():
    calls=[]
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(404) if request.url.path=="/gone" else httpx.Response(200,text="Ürün bulunamadı")
    t=target(source_product_urls={"kitapsepeti":["https://www.kitapsepeti.com/gone"]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert RetailerSource("kitapsepeti","kitapsepeti",client).collect(t)[0]["status"]=="NO_RESULT"
    assert calls==["/gone","/arama"]


def test_kitapsepeti_primary_book_and_all_published_pages():
    from app.services.isbn_sources import source_groups
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path == "/arama":
            if request.url.params.get("pg") == "1":
                return httpx.Response(200, text='<div class="product-item"><a class="product-title" href="/wrong-volume">Blue Lock Cilt 28</a></div><a href="/arama?q=Blue+Lock+29&amp;pg=2">2</a>')
            return httpx.Response(200, text='<div class="product-item"><a class="product-title" href="/book">Blue Lock Cilt 29</a></div>')
        return httpx.Response(200, text='''<h1>Blue Lock Cilt 29</h1><script type="application/ld+json">{"@graph":[
          {"@type":["Product","Book"],"@id":"https://www.kitapsepeti.com/book#product","isbn":"9786258630633",
           "publisher":{"name":"Komikşeyler"},"inLanguage":"Turkish","bookFormat":"http://schema.org/Paperback"},
          {"@type":"Product","url":"https://www.kitapsepeti.com/recommendation","isbn":"9786258630640"}]}</script>''')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        evidence = RetailerSource("kitapsepeti", "kitapsepeti", client).collect(target())
    assert len(evidence) == 1 and evidence[0]["status"] == "MATCH" and evidence[0]["isbn"] == target()["isbn"]
    assert evidence[0]["independence_group"] == "kitapsepeti"
    assert len(calls) == 3 and "pg=2" in calls[1]
    assert source_groups()["kitapsepeti"] not in {source_groups()["kitapyurdu"], source_groups()["bkm"]}


@pytest.mark.parametrize("body,expected", [
    ("<h1>Bakım çalışması</h1>", "ERROR"),
    ("<div>Aramanız için ürün bulunamadı</div>", "NO_RESULT"),
    ('<div class="product-item"><a class="product-title" href="/wrong-volume">Blue Lock Cilt 28</a></div>', "NO_RESULT"),
])
def test_kitapsepeti_absence_requires_recognized_template(body, expected):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
        evidence = collect_sources(target(), [RetailerSource("kitapsepeti", "kitapsepeti", client)])
    assert evidence[0]["status"] == expected


def test_kitapsepeti_repeated_pagination_is_source_error():
    body = '<div class="product-item"><a class="product-title" href="/book">Blue Lock Cilt 29</a></div><a href="/arama?q=Blue+Lock+29&amp;pg=2">2</a>'
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
        evidence = collect_sources(target(), [RetailerSource("kitapsepeti", "kitapsepeti", client)])
    assert evidence[0]["status"] == "ERROR"


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

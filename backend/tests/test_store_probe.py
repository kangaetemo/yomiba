"""Store access test: verdicts from canned responses (no network)."""

from __future__ import annotations

import httpx

from app.services.store_probe import Candidate, StoreProbeJob, probe
from tests.helpers import mock_client

SEARCH = "https://shop.example/arama?q=berserk"
PRODUCT = "https://shop.example/berserk-1"
ISBN = "9786256335424"


def _probe(handler, **kw):
    candidate = Candidate("shop", "Shop", "aday", SEARCH, kw.pop("product_url", PRODUCT), kw.pop("isbn", ISBN))
    return probe(candidate, mock_client(handler), pause=0)


def test_readable_store():
    def handler(request):
        if request.url.path == "/arama":
            return httpx.Response(200, text="<a>Berserk 1</a><a>Berserk Cilt 2</a><a>Berserk 2</a>")
        return httpx.Response(200, text=f'<script type="application/ld+json">{{"isbn":"{ISBN}"}}</script>')

    result = _probe(handler)
    assert result.verdict == "erişilebilir"
    assert result.hits == 2 and result.isbn_found is True
    assert result.search.status == 200 and result.product.status == 200


def test_volume_hits_read_entities_and_words_between():
    from app.services.store_probe import _volume_hits

    page = "Vanitas&#8217;ın Anı Defteri Cilt 5 · Vanitas&#8217;ın Anı Defteri Cilt 4 · Vanitas 4"
    assert _volume_hits("vanitas", page) == 2
    assert _volume_hits("berserk", "Berserk 12 Berserk Cilt 03 berserk-3") == 2


def test_isbn_with_dashes_counts():
    def handler(request):
        if request.url.path == "/arama":
            return httpx.Response(200, text="Berserk 1")
        return httpx.Response(200, text="ISBN No: 978-625-6335-42-4")

    assert _probe(handler).isbn_found is True


def test_walls_are_reported_not_retried():
    calls = []

    def forbidden(request):
        calls.append(request.url)
        return httpx.Response(403, text="nope")

    assert _probe(forbidden).verdict == "engelli"
    assert len(calls) == 2  # search + product page, once each

    challenge = lambda r: httpx.Response(200, text="<html><title>Just a moment...</title></html>")  # noqa: E731
    assert _probe(challenge).verdict == "engelli"
    amazon = lambda r: httpx.Response(202, text="")  # noqa: E731
    assert _probe(amazon).verdict == "engelli"
    waf = lambda r: httpx.Response(511, text="The requested URL was rejected.")  # noqa: E731
    assert _probe(waf).verdict == "engelli"


def test_page_without_data():
    result = _probe(lambda r: httpx.Response(200, text="<div id=app></div>"), product_url=None, isbn=None)
    assert result.verdict == "veri yok"


def test_connection_error():
    def boom(request):
        raise httpx.ConnectError("dns failed", request=request)

    result = _probe(boom)
    assert result.verdict == "hata" and "ConnectError" in result.detail


def test_job_runs_every_candidate():
    candidates = (
        Candidate("a", "A", "aktif", "https://a.example/arama?q=berserk"),
        Candidate("b", "B", "kapalı", "https://b.example/arama?q=berserk"),
    )

    def handler(request):
        if request.url.host == "a.example":
            return httpx.Response(200, text="Berserk 7")
        return httpx.Response(403, text="")

    job = StoreProbeJob(candidates, pause=0, client_factory=lambda: mock_client(handler))
    job.state = "running"
    job.run()
    status = job.status()
    assert status["state"] == "done" and status["done"] == 2
    assert [r["verdict"] for r in status["results"]] == ["erişilebilir", "engelli"]


def test_endpoints(client, monkeypatch):
    def handler(request):
        return httpx.Response(200, text="Frieren Cilt 6")

    job = StoreProbeJob((Candidate("a", "A", "aday", "https://a.example/", term="frieren"),), pause=0,
                        client_factory=lambda: mock_client(handler))
    client.app.state.store_probe_job = job
    assert client.post("/catalog/store-probe/run").status_code == 202
    for _ in range(100):
        body = client.get("/catalog/store-probe").json()
        if body["state"] != "running":
            break
        import time
        time.sleep(0.02)
    assert body["state"] == "done"
    assert body["results"][0]["verdict"] == "erişilebilir"


def test_endpoints_require_admin(client):
    client.cookies.clear()
    assert client.get("/catalog/store-probe").status_code == 401
    assert client.post("/catalog/store-probe/run").status_code == 401

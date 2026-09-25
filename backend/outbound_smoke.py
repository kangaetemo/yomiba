"""One small HTTP connectivity request per catalog/store host; no scraping."""

from __future__ import annotations

import argparse
import json
import socket
from urllib.parse import urlsplit

import httpx


TARGETS = {
    "Mangakol": "https://mangakol.com/",
    "BKM": "https://www.bkmkitap.com/",
    "BKM search API host": "https://bkm-best.wawlabs.com/",
    "BKM fallback CDN host": "https://cdn.bkmkitap.com/",
    "Amazon TR": "https://www.amazon.com.tr/",
    "D&R": "https://www.dr.com.tr/",
    "Kitap Sepeti": "https://www.kitapsepeti.com/",
    "Kitapbulan": "https://www.kitapbulan.com/",
    "Gerekli Şeyler": "https://www.gerekliseyler.com.tr/",
    "Cizman": "https://www.cizman.com/",
    "Kitapseç": "https://www.kitapsec.com/",
    "Komikşeyler": "https://komikseyler.com.tr/",
}


def probe(name: str, url: str, client: httpx.Client) -> dict:
    host = urlsplit(url).hostname
    assert host is not None
    result = {"source": name, "host": host, "dns": "error", "tcp_tls": "not_attempted",
              "status": "ERROR", "http_status": None}
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        result["dns"] = "ok"
        result["tcp_tls"] = "error"
        # Stream and close without reading the response body. No search,
        # pagination, login, product detail, or bot-wall workaround occurs.
        with client.stream("GET", url) as response:
            result["tcp_tls"] = "ok"
            result["http_status"] = response.status_code
            if response.status_code in (403, 429, 503):
                result["status"] = "BLOCKED"
            elif response.status_code < 400:
                result["status"] = "PASS"
                # Inspect only the first 4 KiB for a common bot-wall title.
                first_chunk = next(response.iter_bytes(chunk_size=4096), b"").lower()
                if any(marker in first_chunk for marker in (
                    b"<title>just a moment", b"<title>access denied",
                    b"<title>captcha", b"verify you are human",
                )):
                    result["status"] = "BLOCKED"
    except (OSError, httpx.HTTPError) as exc:
        result["error"] = type(exc).__name__
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error("timeout must be between 0 and 30 seconds")
    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        for name, url in TARGETS.items():
            print(json.dumps(probe(name, url, client), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

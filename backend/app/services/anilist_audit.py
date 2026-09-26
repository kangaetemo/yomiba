"""Optional, read-only AniList evidence for audits. Never imported by store runtime.

AniList describes a work, not a Turkish publisher's edition. No database access.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

ENDPOINT = "https://graphql.anilist.co"
QUERY = """query AuditManga($search: String!, $page: Int!) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(search: $search, type: MANGA) {
      id title { romaji english native } synonyms format volumes chapters
      status countryOfOrigin source siteUrl
    }
  }
}"""
GENERIC_TITLES = {"city", "nana", "ada", "limit", "monster", "orange", "another",
                  "kingdom", "leviathan", "parazit", "kehanet", "paranoya"}


def title_key(value: str | None) -> str:
    """Audit-only normalization: unlike runtime ASCII keys, preserve native titles."""
    text = unicodedata.normalize("NFKD", (value or "").casefold().replace("ı", "i"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def search_titles(title, original_title=None, alternatives=()):
    # Do not split a stored flattened bilingual key into guessed individual titles.
    result = {}
    for value in (original_title, title, *alternatives, title_key(title)):
        if isinstance(value, str) and value.strip():
            result.setdefault(title_key(value), value.strip())
    return list(result.values())


def match_candidates(titles, candidates, *, incomplete=False):
    keys = {title_key(t) for t in titles if title_key(t)}
    ranked = []
    for item in candidates:
        names = [*(item.get("title") or {}).values(), *(item.get("synonyms") or [])]
        best, evidence = 0, None
        for name in names:
            if not isinstance(name, str) or not title_key(name):
                continue
            key = title_key(name)
            for wanted in keys:
                generic = len(key) <= 4 or key in GENERIC_TITLES
                if key == wanted:
                    score, why = (65 if generic else 100), "normalized_exact"
                elif len(key.split()) >= 2 and len(wanted.split()) >= 2 and (
                    f" {key} " in f" {wanted} " or f" {wanted} " in f" {key} "
                ):
                    score, why = 65, "subtitle_or_flattened_bilingual"
                elif set(key.split()) & set(wanted.split()):
                    score, why = 30, "weak_word_overlap"
                else:
                    score, why = 0, None
                if score > best:
                    best, evidence = score, why
        ranked.append({"metadata": item, "score": best, "evidence": evidence})
    ranked.sort(key=lambda r: (-r["score"], r["metadata"]["id"]))
    chosen = ranked[0] if ranked else None
    if incomplete:
        confidence = "AMBIGUOUS"
    elif not chosen or chosen["score"] == 0:
        confidence = "NOT_FOUND"
    elif chosen["score"] < 60 or (len(ranked) > 1 and ranked[1]["score"] >= chosen["score"] - 10):
        confidence = "AMBIGUOUS"
    else:
        confidence = "MATCHED_HIGH" if chosen["score"] >= 90 else "MATCHED_MEDIUM"
    return {"match_confidence": confidence,
            "metadata": chosen["metadata"] if confidence.startswith("MATCHED_") else None,
            "candidates": ranked, "search_incomplete": incomplete}


def volume_signals(metadata):
    metadata = metadata or {}
    volumes = metadata.get("volumes")
    valid = type(volumes) is int and volumes > 0
    one_shot = metadata.get("format") == "ONE_SHOT"
    single = valid and volumes == 1
    multi = valid and volumes > 1
    return {"ANILIST_ONE_SHOT": one_shot, "ANILIST_SINGLE_VOLUME": single,
            "ANILIST_MULTI_VOLUME": multi,
            "ANILIST_UNKNOWN": not valid,
            "contradictory_metadata": one_shot and multi}


class AniListUnavailable(RuntimeError):
    pass


class AniListAuditClient:
    """Bounded public queries, <=~28 requests/minute, optional JSON file cache.

    A long server cooldown fails closed instead of retrying before Retry-After.
    Cache failures affect diagnostics only; API failures never reuse stale evidence.
    """
    def __init__(self, *, cache_path: Path | None = None, ttl_days=7, offline=False,
                 client=None, sleep=time.sleep, clock=time.time, min_interval=2.1):
        self.cache_path = cache_path
        self.ttl = ttl_days * 86400
        self.offline = offline
        self.sleep, self.clock = sleep, clock
        self.interval = max(2.1, min_interval)
        self.next_request = 0.0
        self.blocked_until = 0.0
        self.owns_client = client is None
        self.client = client or httpx.Client(timeout=15.0, follow_redirects=False,
                                            headers={"User-Agent": "Yomiba-Audit/1.0"})
        self.cache_warning = None
        self.cache = {}
        if cache_path and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if data.get("version") == 1 and isinstance(data.get("entries"), dict):
                    self.cache = data["entries"]
            except (OSError, ValueError, TypeError, AttributeError):
                self.cache_warning = "cache_unreadable"

    def close(self):
        if self.owns_client:
            self.client.close()

    def _cooldown(self, response):
        delays = []
        retry = response.headers.get("Retry-After")
        if retry:
            try:
                delays.append(float(retry))
            except ValueError:
                try:
                    delays.append(parsedate_to_datetime(retry).timestamp() - self.clock())
                except (ValueError, TypeError, OverflowError):
                    pass
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                delays.append(float(reset) - self.clock())
            except ValueError:
                pass
        return max([self.interval, *[v for v in delays if math.isfinite(v)]]) if delays else 60.0

    def _page(self, search, page):
        for attempt in range(2):
            if self.clock() < self.blocked_until:
                raise AniListUnavailable("rate_limit_cooldown")
            wait = max(0.0, self.next_request - self.clock())
            if wait > 30:
                raise AniListUnavailable("rate_limit_cooldown")
            self.sleep(wait)
            self.next_request = self.clock() + self.interval
            try:
                response = self.client.post(ENDPOINT, json={"query": QUERY,
                    "variables": {"search": search, "page": page}}, timeout=15.0)
            except httpx.HTTPError:
                if attempt == 0:
                    self.sleep(1.0)
                    continue
                raise AniListUnavailable("transport_error") from None
            if response.status_code == 429:
                delay = self._cooldown(response)
                self.blocked_until = self.clock() + delay
                if delay <= 30 and attempt == 0:
                    self.sleep(delay)
                    continue
                raise AniListUnavailable("rate_limited")
            if response.headers.get("X-RateLimit-Remaining") == "0":
                self.next_request = max(self.next_request, self.clock() + self._cooldown(response))
            if response.status_code in (500, 502, 503, 504) and attempt == 0:
                self.sleep(1.0)
                continue
            if response.status_code != 200:
                raise AniListUnavailable(f"http_{response.status_code}")
            try:
                payload = response.json()
                if payload.get("errors"):
                    raise AniListUnavailable("graphql_error")
                data = payload["data"]["Page"]
                media = data["media"]
                has_next = data["pageInfo"]["hasNextPage"]
                if not isinstance(media, list) or type(has_next) is not bool:
                    raise ValueError("bad shape")
                for item in media:
                    if (not isinstance(item, dict) or type(item.get("id")) is not int
                        or not isinstance(item.get("title"), dict)
                        or not isinstance(item.get("synonyms"), list)
                        or any(v is not None and not isinstance(v, str) for v in item["title"].values())
                        or any(not isinstance(v, str) for v in item["synonyms"])
                        or (item.get("volumes") is not None and (type(item["volumes"]) is not int or item["volumes"] < 0))):
                        raise ValueError("bad media")
                return media, has_next
            except (KeyError, TypeError, ValueError, AttributeError):
                raise AniListUnavailable("invalid_response") from None
        raise AniListUnavailable("retry_exhausted")

    def lookup(self, *, series_id, title, original_title=None, publisher="", alternatives=()):
        titles = search_titles(title, original_title, alternatives)
        identity = [series_id, title_key(publisher), sorted(title_key(t) for t in titles)]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        entry = self.cache.get(key)
        if isinstance(entry, dict):
            try:
                fetched = datetime.fromisoformat(entry["fetched_at"])
                age = self.clock() - fetched.timestamp()
                if fetched.tzinfo and 0 <= age < self.ttl and isinstance(entry["result"]["candidates"], list):
                    # Re-evaluate cached candidates under the current confidence rules.
                    result = match_candidates(titles, [r["metadata"] for r in entry["result"]["candidates"]],
                                              incomplete=entry["result"].get("search_incomplete", False))
                    return {**result, "fetched_at": entry["fetched_at"], "cache_status": "hit",
                            "error": None, "cache_warning": self.cache_warning}
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                self.cache_warning = "cache_entry_invalid"
        status = "stale" if entry else "miss"
        unknown = {"match_confidence": "NOT_FOUND", "metadata": None, "candidates": [],
                   "cache_status": status, "fetched_at": None, "cache_warning": self.cache_warning}
        if self.offline:
            return {**unknown, "error": "offline_cache_unavailable"}
        candidates, incomplete = {}, False
        try:
            for title_query in titles[:6]:
                for page in (1, 2):
                    media, has_next = self._page(title_query, page)
                    candidates.update({m["id"]: m for m in media})
                    if not has_next:
                        break
                    if page == 2:
                        incomplete = True
            incomplete |= len(titles) > 6
        except AniListUnavailable as exc:
            return {**unknown, "error": str(exc), "partial_candidates": list(candidates.values())}
        result = match_candidates(titles, list(candidates.values()), incomplete=incomplete)
        fetched = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
        self.cache[key] = {"fetched_at": fetched, "result": result}
        if self.cache_path:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
                temporary.write_text(json.dumps({"version": 1, "entries": self.cache}, ensure_ascii=False), encoding="utf-8")
                temporary.replace(self.cache_path)
            except OSError:
                self.cache_warning = "cache_write_failed"
        return {**result, "error": None, "fetched_at": fetched, "cache_status": status,
                "cache_warning": self.cache_warning}


def enrich_plan(plan, anilist, evidence=None):
    """A recommendation only. No session, mutation, merge or auto-enrichment."""
    evidence = evidence or {}
    metadata = anilist.get("metadata")
    signals = volume_signals(metadata)
    conflicts = list(evidence.get("conflicts", []))
    if plan.get("volume_number", -1) >= 0:
        return {**plan, "anilist": anilist, "single_volume_evidence": signals,
                "conflicts": [], "final_recommendation": "KEEP"}
    if plan.get("positive_volume_numbers") != [1] or plan.get("zero_volume_ids"):
        conflicts.append("catalog_not_sole_volume_one")
    if anilist.get("error"):
        conflicts.append("anilist_unavailable")
    if anilist.get("match_confidence") != "MATCHED_HIGH":
        conflicts.append("title_match_not_high")
    if signals["ANILIST_MULTI_VOLUME"]:
        conflicts.append("anilist_multi_volume")
    if signals["contradictory_metadata"]:
        conflicts.append("contradictory_metadata")
    if (metadata or {}).get("format") not in ("ONE_SHOT", "MANGA"):
        conflicts.append("unsupported_or_unknown_format")
    if not (signals["ANILIST_ONE_SHOT"] or signals["ANILIST_SINGLE_VOLUME"]):
        conflicts.append("single_volume_not_supported")
    # Legacy SAFE_MERGE still requires catalog + every listing's title/publisher/ISBN.
    if plan.get("action") != "SAFE_MERGE":
        conflicts.append(plan.get("reason", "catalog_product_evidence_missing"))
    products = evidence.get("products", [])
    proven = {p.get("product_url") for p in products if p.get("isbn_verified") is True
              and p.get("edition_verified") is True and p.get("source_url")
              and not p.get("conflicts")}
    if not plan.get("product_urls") or not set(plan["product_urls"]).issubset(proven):
        conflicts.append("listing_isbn_edition_evidence_missing")
    for p in products:
        conflicts.extend(p.get("conflicts", []))
    return {**plan, "anilist": anilist, "single_volume_evidence": signals,
            "conflicts": sorted(set(conflicts)),
            "final_recommendation": "REVIEW" if conflicts else "SAFE_MERGE_CANDIDATE"}


def summarize(rows):
    formats = {"ONE_SHOT": 0, "MANGA volumes=1": 0, "multi-volume": 0, "unknown": 0}
    confidence = {k: 0 for k in ("matched_high", "matched_medium", "ambiguous", "not_found")}
    final = {k: 0 for k in ("SAFE_MERGE_CANDIDATE", "REVIEW", "KEEP")}
    for row in rows:
        confidence[row["anilist"]["match_confidence"].lower()] += 1
        final[row["final_recommendation"]] += 1
        meta = row["anilist"].get("metadata") or {}
        flags = row["single_volume_evidence"]
        formats["ONE_SHOT"] += int(flags["ANILIST_ONE_SHOT"])
        formats["MANGA volumes=1"] += int(meta.get("format") == "MANGA" and flags["ANILIST_SINGLE_VOLUME"])
        formats["multi-volume"] += int(flags["ANILIST_MULTI_VOLUME"])
        formats["unknown"] += int(not any((flags["ANILIST_ONE_SHOT"],
            meta.get("format") == "MANGA" and flags["ANILIST_SINGLE_VOLUME"], flags["ANILIST_MULTI_VOLUME"])))
    return {"total_minus_one_candidates": len(rows), "anilist": confidence,
            "format": formats, "final": final,
            "note": "Format signals are independent; contradictory metadata may overlap."}

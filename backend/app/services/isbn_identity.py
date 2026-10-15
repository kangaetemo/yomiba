"""Conservative bibliographic comparison; ISBN alone never establishes identity."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..normalization.text import normalize_text, publisher_family_key
from ..normalization.volume import parse_volume_title, parse_volume_range


def canonical_isbn(value: str | None) -> str | None:
    if not value or re.search(r"[^0-9xX\s-]", value):
        return None
    code = re.sub(r"[\s-]", "", value).upper()
    if len(code) == 10:
        if not code[:9].isdigit() or not (code[-1].isdigit() or code[-1] == "X"):
            return None
        numbers = [int(c) if c != "X" else 10 for c in code]
        if sum((10-i)*n for i, n in enumerate(numbers)) % 11:
            return None
        prefix = "978" + code[:9]
        return prefix + str((-sum(int(n)*(1 if i % 2 == 0 else 3) for i, n in enumerate(prefix))) % 10)
    if len(code) != 13 or not code.isdigit() or not code.startswith(("978", "979")):
        return None
    return code if sum(int(n)*(1 if i % 2 == 0 else 3) for i, n in enumerate(code)) % 10 == 0 else None


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def snapshot(volume) -> dict:
    series = volume.series
    from sqlalchemy import select
    from sqlalchemy.orm import object_session
    from ..models import CatalogSeries
    session = object_session(volume)
    slugs = list(session.scalars(select(CatalogSeries.mangakol_slug).where(
        CatalogSeries.series_id == series.id).order_by(CatalogSeries.mangakol_slug))) if session else []
    return dict(volume_id=volume.id, series_id=series.id, title=series.title,
                catalog_slugs=slugs,
                original_title=series.original_title, volume_number=volume.volume_number,
                publisher_id=series.publisher_id, publisher=series.publisher.name,
                isbn=volume.isbn, covers_from=volume.covers_from, covers_to=volume.covers_to,
                page_count=volume.page_count, catalog_present=volume.catalog_present,
                catalog_released=volume.catalog_released,
                release_date=volume.release_date.isoformat() if volume.release_date else None)


def eligible(target: dict, today: date | None = None) -> bool:
    today = today or datetime.now(ZoneInfo("Europe/Istanbul")).date()
    return (target["catalog_present"] is not False and target["catalog_released"] is True
            and (not target["release_date"] or date.fromisoformat(target["release_date"]) <= today))


def edition(title: str) -> dict:
    text = normalize_text(title)
    variant = "variant" if re.search(r"\b(varyant|variant|alternatif)\b", text) else "standard"
    if re.search(r"\b(limitli|limited|ozel baski|deluxe)\b", text):
        variant = "special:" + " ".join(re.findall(r"limitli|limited|ozel baski|deluxe", text))
    kind = "novel" if re.search(r"\b(novel|roman|light novel)\b", text) else "manga"
    paper = "kuse" if "kuse" in text else "2hamur" if re.search(r"2\s*\.?\s*hamur", text) else None
    return dict(variant=variant, kind=kind, paper=paper)


def base_key(title: str) -> str:
    span = parse_volume_range(title)
    value = normalize_text(re.sub(r"\([^)]*\)", " ", span.base_title if span else title))
    value = re.sub(r"\b(?:webtoon|manga|novel|roman|varyant|variant|ana kapak|karton kapak|limitli|limited)\b", " ", value)
    return normalize_text(parse_volume_title(value).base_title)


def catalog_title_keys(target: dict) -> set[str]:
    """Exact local/canonical names; original_title is a search-only alias bag."""
    keys = {base_key(target["title"])}
    for slug in target.get("catalog_slugs", []):
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            keys.add(base_key(slug.replace("-", " ")))
    return keys - {""}


def title_matches(target: dict, title: str) -> bool:
    keys, actual = catalog_title_keys(target), base_key(title)
    # Retailers may print both declared names: Death Note - Ölüm Defteri.
    # Require the entire key, never a substring or a fuzzy title match.
    return actual in keys or any(actual == f"{left} {right}"
        for left in keys for right in keys if left != right)


def catalog_search_title(target: dict) -> str:
    for slug in target.get("catalog_slugs", []):
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            return slug.replace("-", " ")
    return " ".join(re.sub(r"\([^)]*\)", " ", bibliographic_title(target["title"])).split())


def binding_kind(value: str) -> str | None:
    value = normalize_text(value)
    if re.search(r"\b(bez|cloth|clothbound)\b", value): return "cloth"
    if re.search(r"\b(sert|ciltli|hardback|hardcover)\b", value): return "hard"
    if re.search(r"\b(karton|ciltsiz|yumusak|paperback|softcover)\b", value): return "soft"
    return None


def bibliographic_title(title: str) -> str:
    """Paper '2. Hamur' is not a second volume number; '(2)' still is."""
    def note(match):
        key = normalize_text(match.group())
        return " " if any(word in key for word in ("hamur", "kagit", "kapak", "varyant", "limitli", "bez cilt")) else match.group()
    return re.sub(r"\([^)]*\)", note, title)


def identity_reason(target: dict, book: dict) -> str | None:
    """None means all required identity fields are supported, not merely guessed."""
    title = book.get("title") or ""
    parsed = parse_volume_title(bibliographic_title(title))
    if not title_matches(target, title):
        return "Seri başlığı farklı veya belirsiz."
    if target["volume_number"] < 0:
        return "Numarasız eski kayıt: fiziksel baskı elle çözülmeli."
    span = parse_volume_range(title)
    if target.get("covers_from") is not None:
        if not span or (span.first, span.last) != (target["covers_from"], target["covers_to"]):
            return "Omnibus kapsamı doğrulanamadı."
    elif parsed.is_collection or span:
        return "Set veya omnibus, tek ciltle eşleşmiyor."
    if not span and parsed.volume_number != target["volume_number"]:
        return "Cilt numarası farklı veya belirsiz."
    if not book.get("publisher") or publisher_family_key(book["publisher"]) != publisher_family_key(target["publisher"]):
        return "Yayınevi farklı veya eksik."
    if normalize_text(book.get("language")) not in {"tr", "tur", "turkish", "turkce"}:
        return "Türkçe baskı kanıtı eksik veya dil farklı."
    expected, actual = edition(target["title"]), edition(title)
    if expected["kind"] != actual["kind"]:
        return "Roman ile manga/webtoon ayrımı uyuşmuyor."
    if expected["variant"] != actual["variant"]:
        return "Kapak/baskı varyantı farklı."
    if expected["paper"] != actual["paper"] and (expected["paper"] or actual["paper"]):
        return "Kağıt/baskı türü katalogda ve kaynakta aynı açıklanmıyor."
    actual_binding = binding_kind(book.get("binding") or "")
    if not actual_binding:
        return "Cilt/kapak türü kaynakta doğrulanamadı."
    expected_binding = binding_kind(target["title"]) or "soft"
    if actual_binding != expected_binding:
        return "Kapak/cilt türü katalog baskısıyla aynı değil."
    return None


def evaluate(target: dict, evidence: list[dict]) -> tuple[str, str | None, str]:
    if not eligible(target):
        return "SKIPPED_UPCOMING", None, "Yayımlandığı doğrulanmamış veya gelecekte tarihli; ISBN alarmı açılmadı."
    evidence = [e for e in evidence if e.get("source") != "mangakol"]
    matches = [e for e in evidence if e["status"] == "MATCH"]
    codes = {e["isbn"] for e in matches}
    if len(codes) > 1 or any(e["status"] == "MISMATCH" for e in evidence):
        return "CONFLICT", None, "ISBN veya fiziksel baskı kanıtları çelişiyor."
    agreed = next(iter(codes), None)
    groups = {e["independence_group"] for e in matches if e.get("independence_group")}
    if agreed and len(groups) >= 2:
        if canonical_isbn(target["isbn"]) == agreed:
            return "VERIFIED", agreed, "İki bağımsız kaynak aynı fiziksel cildi doğruladı."
        return ("MISSING_ISBN" if not target["isbn"] else "CONFLICT"), agreed, "Kaynaklar uyuşuyor; ISBN değişikliği admin kararı bekliyor."
    if evidence and all(e["status"] == "ERROR" for e in evidence):
        return "SOURCE_ERROR", None, "Kaynaklara erişilemedi; ISBN yokluğu sonucuna varılmadı."
    if not matches and not target["isbn"] and not any(e["status"] == "ERROR" for e in evidence):
        return "MISSING_ISBN", None, "Erişilen kaynaklarda geçerli ISBN kanıtı bulunamadı."
    return "INSUFFICIENT_EVIDENCE", None, "Aynı fiziksel baskı için iki bağımsız kanıt henüz yok."

"""Build an audit evidence document from manually inspected public pages.

No database connection, network calls or application imports. This is an audit
artifact builder, not a scraper or cleanup command. Raw observations and source
URLs were reviewed on 2026-09-26. Recheck live state before any approved action.
"""
import json
from pathlib import Path

GS = "https://www.gerekliseyler.com.tr/urun/"
KS = "https://www.kitapsec.com/Products/"
BKM = "https://bkmkitap.com/"
SEP = "https://www.kitapsepeti.com/"
BUL = "https://www.kitapbulan.com/"
KOM = "https://komikseyler.com.tr/urun/"

# source, target, semantic product title, publisher, ISBN, pages, manifest slug,
# every current source-listing URL (compared to the fresh read-only snapshot).
observations = [
    (2336, 96, "Elveda Eri", "Gerekli Şeyler", "9786258237559", 208, "sayonara-eri", [
        GS + "elveda-eri", KS + "Elveda-Eri-Gerekli-Seyler-Yayincilik-848850.html",
        BKM + "elveda-eri", SEP + "elveda-eri", BUL + "elveda-eri"]),
    (2338, 145, "Look Back", "Gerekli Şeyler", "9786256031302", 148, "look-back", [
        GS + "look-back-1", KS + "Look-Back-Gerekli-Seyler-Yayincilik-898788.html",
        BKM + "look-back", SEP + "look-back", BUL + "look-back"]),
    (2359, 1156, "Nijigahara Holograf", "Gerekli Şeyler", "9786257590594", 296, "nijigahara-holograph", [
        GS + "nijigahara-holograf", KS + "Nijigahara-Holograf-Gerekli-Seyler-Yayincilik-742720.html", BUL + "nijigahara-holograf"]),
    (2375, 1263, "Humanitas", "Athica", "9786259961347", 256, "humanitas", [
        BKM + "humanitas", SEP + "humanitas", BUL + "humanitas", GS + "humanitas"]),
    (2397, 1334, "Kara Paradoks", "Kayıp Kıta", "9786259324074", 244, "black-paradox", [
        GS + "kara-paradoks", KS + "Kara-Paradoks-Kayip-Kita-Yayinlari-942168.html", BKM + "kara-paradoks", SEP + "kara-paradoks-575892", BUL + "kara-paradoks"]),
    (2418, 1442, "One Room Angel", "Komik Şeyler", "9786256449282", 240, "one-room-angel", [
        GS + "one-room-angel", KOM + "one-room-angel/"]),
    (2419, 1446, "Kelimeler Bahçesi", "Satori", "9786058033412", 200, "kotonoha-no-niwa", [
        BKM + "kelimeler-bahcesi", SEP + "kelimeler-bahcesi", GS + "kelimeler-bahcesi"]),
    (2420, 1460, "Tadımlık Otobüs Hikayeleri", "Komik Şeyler", "9786057111593", 176, "bus-hashiru", [
        GS + "tadimlik-otobus-hikayeleri", KOM + "tadimlik-otobus-hikayeleri/", BKM + "tadimlik-otobus-hikayeleri"]),
    (2422, 1496, "Scientia", "İthaki", "9786052656051", 256, "scientia", [
        KS + "Scientia-Ithaki-Yayinlari-947278.html", BKM + "scientia"]),
    (2428, 1800, "Monotone Blue", "Beta Byou", "9786254239946", 232, "monotone-blue", [
        BKM + "monotone-blue", SEP + "monotone-blue", BUL + "monotone-blue", GS + "monotone-blue"]),
    (2451, 2245, "Komünist Manifesto", "Kırmızı Kedi", "9786254180835", 80, "kyousantou-sengen", [
        GS + "komunist-manifesto"]),
    (2452, 2276, "Karga İle Ayı", "Baobab", "9786259617572", 184, "kuma-to-karasu", [
        GS + "karga-ve-ayi"]),
]

evidence = {}
for source, target, title, publisher, isbn, pages, slug, urls in observations:
    conflicts = ["publisher_edition_conflict:catalog_Yordam_product_Kirmizi_Kedi"] if source == 2451 else []
    products = [{
        "product_url": url, "source_url": url, "title": title,
        "publisher": publisher, "isbn": isbn, "isbn_verified": True,
        "edition_verified": source != 2451, "conflicts": conflicts,
        "observed_at": "2026-09-26", "observed_pages": pages,
        "observation_note": "Semantic book title excludes the retailer's appended publisher label; ISBN and publisher were inspected separately. Page counts are corroboration across the inspected sources, not an assertion that every page displayed them.",
    } for url in urls]
    evidence[str(source)] = {
        "target_id": target, "catalog_confirmed": True,
        "catalog_source_url": "https://mangakol.com/manga/" + slug,
        "products": products, "conflicts": conflicts,
        "reviewed_at": "2026-09-26",
        "decision_scope": "Read-only candidate classification; never permission to merge.",
    }

evidence["2422"]["additional_sources"] = ["https://www.ithakiyayingrubu.com/scientia"]
evidence["2451"]["additional_sources"] = ["https://www.kirmizikedi.com/komunist-manifesto-p-6341"]
evidence["2428"]["review_note"] = (
    "Catalog title is Monoton Blue; product title is Monotone Blue, also the "
    "catalog original title. Identity corroborated, but do not falsify the product "
    "title to bypass the existing exact-title planner. Keep its actual verdict."
)

if __name__ == "__main__":
    path = Path(__file__).with_name("phantom-independent-evidence-2026-09-26.json")
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence candidates: {len(evidence)}; inspected source listings: {sum(len(v['products']) for v in evidence.values())}")

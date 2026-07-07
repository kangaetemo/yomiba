from app.db.session import SessionLocal

from app.scrapers.amazon import AmazonScraper
from app.scrapers.bkm import BKMScraper
from app.scrapers.dr import DRScraper

from app.services.import_service import ImportService


SCRAPERS = [
    AmazonScraper(),
    BKMScraper(),
    DRScraper(),
]


def main():

    all_results = []

    for scraper in SCRAPERS:

        print(f"\n=== {scraper.__class__.__name__} ===")

        results = scraper.search("berserk")

        print(f"{len(results)} sonuç bulundu.")

        all_results.extend(results)

    print(f"\nToplam {len(all_results)} sonuç import edilecek.\n")

    with SessionLocal() as session:

        importer = ImportService(session)

        importer.import_results(all_results)

        session.commit()

    print("\n✅ Import tamamlandı.")


if __name__ == "__main__":
    main()
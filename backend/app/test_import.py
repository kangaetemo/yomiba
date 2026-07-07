from app.db.session import SessionLocal
from app.scrapers.bkm import BKMScraper
from app.services.import_service import ImportService
from sqlalchemy import select
from app.models.publisher import Publisher


results = BKMScraper().search("berserk")

with SessionLocal() as session:

    importer = ImportService(session)

    importer.import_results(results)

    session.commit()   # <-- BU ÇOK ÖNEMLİ
    
    print("Commit öncesi:")
    print(session.new)
    session.commit()
    print("Commit sonrası")
    
with SessionLocal() as session:
    publishers = session.scalars(select(Publisher)).all()
    print(publishers)
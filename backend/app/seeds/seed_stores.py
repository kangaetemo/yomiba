from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.store import Store

STORES = [
    ("Amazon", "https://www.amazon.com.tr"),
    ("Komik Şeyler", "https://www.komikseyler.com"),
    ("Destek Dükkan", "https://www.destekdukkan.com"),
    ("Arkabahçe", "https://www.arkabahce.com"),
    ("Gerekli Şeyler", "https://www.gerekliseyler.com.tr"),
    ("Presstij", "https://www.presstij.com.tr"),
    ("Goril", "https://www.goril.com.tr"),
    ("Edessa Kitabevi", "https://www.edessakitabevi.com"),
    ("Paralel Evren", "https://www.paralelevren.com"),
    ("Çizman", "https://www.cizman.com"),
    ("Darkwood", "https://www.darkwood.com.tr"),
    ("Kayıp Kıta", "https://www.kayipkita.com"),
    ("BKM Kitap", "https://www.bkmkitap.com"),
    ("D&R", "https://www.dr.com.tr"),
    ("İdefix", "https://www.idefix.com"),
    ("Kitapyurdu", "https://www.kitapyurdu.com"),
]


def seed():
    with SessionLocal() as session:
        for name, url in STORES:
            exists = session.scalar(
                select(Store).where(Store.name == name)
            )

            if not exists:
                session.add(
                    Store(
                        name=name,
                        base_url=url,
                    )
                )

        session.commit()


if __name__ == "__main__":
    seed()
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.series import Series
from app.utils.slug import slugify
from app.models.volume import Volume
from app.models.store import Store
from app.models.store_listing import StoreListing
from app.models.publisher import Publisher
from app.scrapers.models import SearchResult
from app.models.price_history import PriceHistory
from datetime import datetime
from app.utils.normalize import (
    normalize_publisher,
    normalize_series_title,
)


class ImportService:
    def __init__(self, session: Session):
        self.session = session

    def import_results(self, results: list[SearchResult]):
        for result in results:

            publisher = self.get_or_create_publisher(
                normalize_publisher(result.publisher)
            )

            series = self.get_or_create_series(
                publisher,
                result.series_title,
            )
            
            volume = self.get_or_create_volume(
                series,
                result,
            )
            
            store = self.get_store(
                result.store_name
            )

            listing = self.upsert_store_listing(
                volume,
                store,
                result,
            )

            print(
                f"[OK] {result.title} | "
                f"Publisher={publisher.id} | "
                f"Series={series.id} | "
                f"Volume={volume.id} | "
                f"Listing={listing.id}"
            )
    def get_or_create_publisher(self, publisher_name: str) -> Publisher:
        publisher = self.session.scalar(
            select(Publisher).where(Publisher.name == publisher_name)
        )

        if publisher:
            return publisher

        publisher = Publisher(name=publisher_name)

        self.session.add(publisher)
        self.session.flush()

        return publisher

    def get_or_create_series(
        self,
        publisher: Publisher,
        series_title: str,
    ) -> Series:

        series = self.session.scalar(
            select(Series).where(
                Series.publisher_id == publisher.id,
                Series.title == series_title,
            )
        )

        if series:
            return series

        series = Series(
            publisher_id=publisher.id,
            title=series_title,
            slug=slugify(series_title),
        )

        self.session.add(series)
        self.session.flush()

        return series
        
    def get_or_create_volume(
        self,
        series: Series,
        result: SearchResult,
    ) -> Volume:

        # 1) Önce ISBN ile ara
        if result.isbn:

            volume = self.session.scalar(
                select(Volume).where(
                    Volume.isbn == result.isbn,
                )
            )

            if volume:
                return volume

        # 2) Sonra seri + cilt numarası ile ara
        volume = self.session.scalar(
            select(Volume).where(
                Volume.series_id == series.id,
                Volume.volume_number == result.volume_number,
            )
        )

        if volume:

            # ISBN sonradan geldiyse doldur
            if not volume.isbn and result.isbn:
                volume.isbn = result.isbn

            # Kapak yoksa ekle
            if not volume.cover_url and result.image_url:
                volume.cover_url = result.image_url

            return volume

        # 3) Yoksa oluştur
        volume = Volume(
            series_id=series.id,
            volume_number=result.volume_number,
            isbn=result.isbn,
            cover_url=result.image_url,
        )

        self.session.add(volume)
        self.session.flush()

        return volume
        
        
    def get_store(self, store_name: str) -> Store:

        store = self.session.scalar(
            select(Store).where(
                Store.name == store_name
            )
        )

        if not store:
            raise ValueError(f"Store bulunamadı: {store_name}")

        return store
        
    def upsert_store_listing(
        self,
        volume: Volume,
        store: Store,
        result: SearchResult,
    ) -> StoreListing:

        listing = (
            self.session.query(StoreListing)
            .filter_by(
                store_name=result.store_name,
                external_id=result.store_id,
            )
            .first()
        )
        

        price_changed = False

        if listing:

            if listing.price != result.price:
                price_changed = True
                listing.price = result.price

            listing.product_url = result.product_url
            listing.in_stock = result.in_stock
            listing.last_checked = datetime.utcnow()

            if price_changed:
                self.add_price_history(
                    listing,
                    result.price,
                )

            return listing

        listing = StoreListing(
            volume_id=volume.id,
            store_id=store.id,
            price=result.price,
            product_url=result.product_url,
            in_stock=result.in_stock,
        )

        self.session.add(listing)
        self.session.flush()
        self.add_price_history(
            listing,
            result.price,
        )


        return listing
        
    def add_price_history(
        self,
        listing: StoreListing,
        price: Decimal,
    ):

        history = PriceHistory(
            listing_id=listing.id,
            price=price,
        )

        self.session.add(history)
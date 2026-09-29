"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
``create_all`` and migrations see the full schema.
"""

from .publisher import Publisher
from .publisher_alias import PublisherAlias
from .series import Series
from .volume import Volume
from .store import Store
from .store_listing import StoreListing
from .listing_exclusion import ListingExclusion
from .price_history import PriceHistory
from .import_record import ImportRecord
from .wishlist_item import WishlistItem
from .price_alert import PriceAlert
from .catalog_series import CatalogSeries
from .catalog_exclusion import CatalogExclusion
from .user import User, UserSession
from .user_volume_collection import UserVolumeCollection

__all__ = [
    "Publisher",
    "PublisherAlias",
    "Series",
    "Volume",
    "Store",
    "StoreListing",
    "ListingExclusion",
    "PriceHistory",
    "ImportRecord",
    "WishlistItem",
    "PriceAlert",
    "CatalogSeries",
    "CatalogExclusion",
    "User",
    "UserSession",
    "UserVolumeCollection",
]

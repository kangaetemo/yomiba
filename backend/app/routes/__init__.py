"""API routers, combined into a single ``api_router``."""

from fastapi import APIRouter

from . import catalog as catalog_routes
from . import auth as auth_routes
from . import drops as drops_routes
from . import import_ as import_routes
from . import me as me_routes
from . import search as search_routes
from . import series as series_routes
from . import volume as volume_routes

api_router = APIRouter()
api_router.include_router(auth_routes.router)
api_router.include_router(search_routes.router)
api_router.include_router(drops_routes.router)
api_router.include_router(series_routes.router)
api_router.include_router(volume_routes.router)
api_router.include_router(import_routes.router)
api_router.include_router(me_routes.router)
api_router.include_router(catalog_routes.router)

__all__ = ["api_router"]

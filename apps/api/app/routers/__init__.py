"""Routers package."""

from app.routers.assets import router as assets
from app.routers.assets import speaker_assets_router as speaker_assets
from app.routers.brand_templates import router as brand_templates
from app.routers.clips import router as clips
from app.routers.derivatives import router as derivatives
from app.routers.files import router as files
from app.routers.projects import router as projects
from app.routers.speakers import router as speakers

__all__ = [
    "assets",
    "brand_templates",
    "clips",
    "derivatives",
    "files",
    "projects",
    "speakers",
    "speaker_assets",
]

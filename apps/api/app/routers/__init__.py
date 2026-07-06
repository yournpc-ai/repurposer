"""Routers package."""

from app.routers.assets import router as assets
from app.routers.assets import speaker_assets_router as speaker_assets
from app.routers.brand_templates import router as brand_templates
from app.routers.chat import router as chat
from app.routers.clips import router as clips
from app.routers.derivatives import router as derivatives
from app.routers.files import router as files
from app.routers.intent import router as intent
from app.routers.library import router as library
from app.routers.projects import router as projects
from app.routers.speakers import router as speakers

__all__ = [
    "assets",
    "brand_templates",
    "chat",
    "clips",
    "derivatives",
    "files",
    "intent",
    "library",
    "projects",
    "speakers",
    "speaker_assets",
]

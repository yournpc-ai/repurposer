"""Routers package."""

from app.routers.assets import router as assets
from app.routers.assets import speaker_assets_router as speaker_assets
from app.routers.auth import router as auth
from app.routers.brand_templates import router as brand_templates
from app.routers.chat import router as chat
from app.routers.distribution import router as distribution
from app.routers.files import router as files
from app.routers.intent import router as intent
from app.routers.library import router as library
from app.routers.music import router as music
from app.routers.outputs import router as outputs
from app.routers.projects import router as projects
from app.routers.speakers import router as speakers

__all__ = [
    "assets",
    "auth",
    "brand_templates",
    "chat",
    "distribution",
    "files",
    "intent",
    "library",
    "music",
    "outputs",
    "projects",
    "speakers",
    "speaker_assets",
]

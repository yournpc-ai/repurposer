"""Pipeline routes package."""

from app.pipeline.routes.assets import router as assets
from app.pipeline.routes.assets import persona_assets_router as persona_assets
from app.pipeline.routes.library import router as library
from app.pipeline.routes.music import router as music
from app.pipeline.routes.outputs import router as outputs
from app.pipeline.routes.projects import router as projects
from app.pipeline.routes.staging import router as staging
from app.pipeline.routes.voices import router as voices

__all__ = [
    "assets",
    "library",
    "music",
    "outputs",
    "persona_assets",
    "projects",
    "staging",
    "voices",
]

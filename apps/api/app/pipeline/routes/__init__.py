"""Pipeline routes package."""

from app.pipeline.routes.assets import router as assets
from app.pipeline.routes.assets import speaker_assets_router as speaker_assets
from app.pipeline.routes.library import router as library
from app.pipeline.routes.music import router as music
from app.pipeline.routes.outputs import router as outputs
from app.pipeline.routes.projects import router as projects
from app.pipeline.routes.runs import router as runs

__all__ = [
    "assets",
    "library",
    "music",
    "outputs",
    "projects",
    "runs",
    "speaker_assets",
]

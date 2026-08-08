"""Pipeline routes package."""

from app.pipeline.routes.assets import router as assets
from app.pipeline.routes.assets import persona_assets_router as persona_assets
from app.pipeline.routes.music import router as music
from app.pipeline.routes.outputs import router as outputs
from app.pipeline.routes.projects import router as projects
from app.pipeline.routes.recipes import router as recipes
from app.pipeline.routes.runs import router as runs

__all__ = [
    "assets",
    "music",
    "outputs",
    "persona_assets",
    "projects",
    "recipes",
    "runs",
]

"""Recipe catalogue router.

Endpoints (prefix ``/api/v1/recipes``):

- ``GET ""`` — the public card catalogue: ``{id, status, input_slots}`` only.
  No auth — the landing audience is anonymous and reads the same cards
  (RECIPES §7.1). Pin substance (outputs / dub_languages) never leaves the
  server (prohibition #7, docs/tasks/recipe-mention.md).
"""

from fastapi import APIRouter

from app.pipeline.recipes import RecipePublic, list_public_recipes

router = APIRouter()


@router.get("", response_model=list[RecipePublic])
async def list_recipes() -> list[RecipePublic]:
    """List the registered recipe cards (public, read-only)."""
    return list_public_recipes()

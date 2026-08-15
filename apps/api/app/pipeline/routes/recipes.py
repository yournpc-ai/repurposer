"""Recipe catalogue router.

Endpoints (prefix ``/api/v1/recipes``):

- ``GET ""`` — the public card catalogue: the public projection of the
  Recipe data package (base structure / flow / example_* / input_slots,
  RECIPES §7.1). No auth — the landing audience is anonymous and reads the
  same cards. Pin substance (the ``tasks`` compile shape) never leaves the
  server (prohibition #7, docs/tasks/recipe-mention.md).
"""

from fastapi import APIRouter

from app.pipeline.recipes import RecipePublic, list_public_recipes

router = APIRouter()


@router.get("", response_model=list[RecipePublic])
async def list_recipes() -> list[RecipePublic]:
    """List the registered recipe cards (public, read-only)."""
    return list_public_recipes()

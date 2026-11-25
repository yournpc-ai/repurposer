"""Authenticated studio catalog outlines."""

from fastapi import APIRouter, Depends, Query

from app.catalog.search import SearchArgs, SoundArgs, search_catalog
from app.catalog.sync import ensure_builtin_catalog
from app.dependencies import DBDep, get_current_user_required
from app.models.tables import User

router = APIRouter()


def outline_endpoint(kind):
    async def outlines(
        db: DBDep,
        filters: SearchArgs = Depends(SoundArgs if kind == "sfx" else SearchArgs),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_current_user_required),
    ):
        await ensure_builtin_catalog(db)
        return await search_catalog(db, user.id, kind, filters, offset=offset, gallery=True)

    return outlines


for path, kind in (("blocks", "block"), ("text-presets", "text_preset"), ("sfx", "sfx")):
    router.add_api_route(
        "/" + path, outline_endpoint(kind), methods=["GET"], name="catalog_" + kind
    )

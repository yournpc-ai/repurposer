"""Catalog synchronization, tenant visibility and deterministic SQL projections."""

import pytest
from sqlalchemy import func, select

from app.catalog.search import BlockArgs, SearchArgs, catalog_details, search_catalog
from app.catalog.sync import sync_builtin_catalog
from app.models.tables import SoundEffect, User, VisualPreset
from test.support.db_helpers import _user, full_api_client

pytestmark = [pytest.mark.infra, pytest.mark.asyncio]


async def test_catalog_sync_visibility_and_gallery(database):
    owner, outsider = await _user(database), await _user(database)
    async with database.begin() as db:
        await sync_builtin_catalog(db)
        row = await db.scalar(select(VisualPreset).where(VisualPreset.preset_id == "logo_wall"))
        row.use_count = 42
        await db.flush()
        await sync_builtin_catalog(db)
        await db.refresh(row)
        assert row.use_count == 42
        assert dict(
            (
                await db.execute(
                    select(VisualPreset.asset_kind, func.count()).group_by(VisualPreset.asset_kind)
                )
            ).all()
        ) == {"block": 17, "transition": 5, "text_preset": 24}
        assert await db.scalar(select(func.count()).select_from(SoundEffect)) == 22
        db.add_all(
            [
                VisualPreset(
                    preset_id=slug,
                    asset_kind="block",
                    domain="product",
                    category="private",
                    scope="user",
                    owner_id=owner,
                    status=status,
                    name="Private",
                    summary="Tenant-owned",
                )
                for slug, status in (("own", "ready"), ("hidden", "archived"))
            ]
        )
        await db.flush()
        assert (await catalog_details(db, owner, "block", ["own", "hidden"]))["items"][0][
            "id"
        ] == "own"
        assert not (await catalog_details(db, outsider, "block", ["own", "hidden"]))["items"]
        assert not (await search_catalog(db, outsider, "block", BlockArgs(category="private")))[
            "items"
        ]
        hidden = SoundEffect(
            slug="private_take",
            engine_kind="sample",
            name="Private take",
            category="private",
            summary="Owner's recording",
            duration_ms=230,
            scope="user",
            owner_id=owner,
            status="ready",
        )
        db.add(hidden)
        await db.flush()
        assert not (await catalog_details(db, outsider, "sfx", [hidden.slug]))["items"]
        assert not (await search_catalog(db, outsider, "sfx", SearchArgs(query=hidden.slug)))[
            "items"
        ]
        assert (await catalog_details(db, owner, "sfx", [hidden.slug]))["items"][0][
            "storage_ready"
        ] is False
        user = await db.get(User, owner)
    async with full_api_client(database, user) as client:
        for path, key in (
            ("blocks", "logo_wall"),
            ("text-presets", "neon_pulse"),
            ("sfx", "dsp_deep_hit"),
        ):
            r = await client.get(f"/api/v1/catalog/{path}", params={"query": key, "limit": 1})
            assert r.status_code == 200 and r.json()["items"][0]["id"] == key
            assert not (
                {"preview_spec", "example_props", "props_schema", "params_schema"}
                & r.json()["items"][0].keys()
            )
        r = await client.get("/api/v1/catalog/blocks", params={"category": "private"})
        assert [row["id"] for row in r.json()["items"]] == ["own"]

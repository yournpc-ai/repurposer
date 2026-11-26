"""Unit tests for the owner-scoped TOS asset library routes (/api/v1/assets)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.main import app
from app.models.schemas import AssetStatus, AssetType, RenderStatus
from app.pipeline.routes.library import download_asset, get_asset_library


def _scalars_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    result.__iter__.return_value = iter(rows)
    return result


def test_asset_library_routes_are_mounted() -> None:
    paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/assets/library" in paths
    assert "/api/v1/assets/{asset_id}/download" in paths


@pytest.mark.asyncio
async def test_get_asset_library_aggregates_owned_entities_and_filters_undelivered() -> None:
    owner_id = uuid4()
    proj_id = uuid4()
    asset_id = uuid4()
    output_ok_id = uuid4()
    output_draft_id = uuid4()
    comp_id = uuid4()
    ver_id = uuid4()
    music_id = uuid4()
    voice_id = uuid4()
    now = datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc)

    asset_row = SimpleNamespace(
        id=asset_id,
        user_id=owner_id,
        project_id=proj_id,
        type=AssetType.VIDEO,
        file_url=f"{owner_id}/uploads/projects/{proj_id}/clip.mp4",
        display_name="Product Demo.mp4",
        duration_seconds=18,
        meta={"size_bytes": 4_200_000, "width": 1920, "height": 1080},
        processing_status=AssetStatus.COMPLETED,
        created_at=now,
    )
    export_key = f"tos://test-bucket/exports/{owner_id}/{proj_id}/{output_ok_id}.mp4"
    delivered_output = SimpleNamespace(
        id=output_ok_id,
        project_id=proj_id,
        type="video",
        render_status=RenderStatus.COMPLETED,
        composition_id=comp_id,
        composition_version_id=ver_id,
        payload={"name": "Launch Cut", "composition_digest": "sha256:abc", "duration_seconds": 25.0},
        files={"video": export_key, "poster": f"{owner_id}/outputs/projects/{proj_id}/poster.jpg"},
        render_spec={
            "family": "video",
            "provenance": {
                "composition_id": str(comp_id),
                "composition_version_id": str(ver_id),
                "content_digest": "sha256:abc",
            },
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
        },
        created_at=now,
    )
    undelivered_output = SimpleNamespace(
        id=output_draft_id,
        project_id=proj_id,
        type="video",
        render_status=RenderStatus.PENDING,
        composition_id=comp_id,
        composition_version_id=ver_id,
        payload={},
        files={},
        render_spec={},
        created_at=now,
    )
    project_row = SimpleNamespace(id=proj_id, user_id=owner_id, title="OxValue Promo")
    version_row = SimpleNamespace(id=ver_id, version=3)
    music_row = SimpleNamespace(
        id=music_id,
        title="Obsidian Pulse",
        mood="energetic",
        prompt="minimalist dark electronic beat",
        duration_seconds=32.5,
        size_bytes=520_000,
        tags=["electronic", "tech"],
        use_count=2,
        created_at=now,
    )
    voice_row = SimpleNamespace(
        id=voice_id,
        name="Studio Narrator",
        description="Warm confident narrator",
        design_prompt=None,
        preview_audio_key=f"{owner_id}/voices/{voice_id}.mp3",
        reference_audio_key=None,
        tone_tags=["warm", "calm"],
        use_count=1,
        created_at=now,
    )

    db = MagicMock()
    db.scalars = AsyncMock(
        side_effect=[
            _scalars_result([asset_row]),
            _scalars_result([delivered_output, undelivered_output]),
            _scalars_result([project_row]),
            _scalars_result([version_row]),
            _scalars_result([music_row]),
            _scalars_result([voice_row]),
            _scalars_result([]),
        ]
    )

    current_user = SimpleNamespace(id=owner_id)
    with (
        patch("app.pipeline.routes.library.matches_export_location", return_value=True),
        patch(
            "app.pipeline.routes.library.resolve_stored_url",
            side_effect=lambda val: f"https://cdn.example/{val}",
        ),
        patch(
            "app.pipeline.routes.library.stream_url",
            side_effect=lambda val: f"https://cdn.example/{val}",
        ),
    ):
        resp = await get_asset_library(db=db, current_user=current_user)

    assert len(resp.projects) == 1
    assert resp.projects[0].title == "OxValue Promo"
    assert resp.projects[0].upload_count == 1
    assert resp.projects[0].export_count == 1

    assert len(resp.uploads) == 1
    assert resp.uploads[0].title == "Product Demo.mp4"
    assert resp.uploads[0].size_bytes == 4_200_000

    assert len(resp.exports) == 1
    assert resp.exports[0].id == output_ok_id
    assert resp.exports[0].composition_version_number == 3
    assert resp.exports[0].title == "Launch Cut"

    assert len(resp.audio) == 2
    assert {item.kind for item in resp.audio} == {"music", "voice"}


@pytest.mark.asyncio
async def test_download_asset_enforces_ownership_and_presigns() -> None:
    owner_id = uuid4()
    asset_id = uuid4()
    current_user = SimpleNamespace(id=owner_id)

    # 1. Missing or foreign asset returns 404
    db_missing = MagicMock()
    db_missing.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await download_asset(
            asset_id=asset_id,
            db=db_missing,
            response=Response(),
            current_user=current_user,
        )
    assert exc.value.status_code == 404

    # 2. Owned asset returns presigned attachment URL with preserved extension + private cache header
    owned_asset = SimpleNamespace(
        id=asset_id,
        user_id=owner_id,
        file_url=f"{owner_id}/uploads/projects/{uuid4()}/shot-1234.mp4",
        display_name="Hero Shot",
    )
    db_owned = MagicMock()
    db_owned.scalar = AsyncMock(return_value=owned_asset)
    response = Response()
    with patch(
        "app.pipeline.routes.library.presign_download",
        new=AsyncMock(return_value="https://tos.example/signed-url"),
    ) as presign_mock:
        result = await download_asset(
            asset_id=asset_id,
            db=db_owned,
            response=response,
            current_user=current_user,
        )

    assert result.url == "https://tos.example/signed-url"
    assert result.expires_in == 300
    assert response.headers["Cache-Control"] == "private, no-store"
    presign_mock.assert_awaited_once_with(
        owned_asset.file_url,
        ttl=300,
        filename="Hero Shot.mp4",
    )

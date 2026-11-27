"""Catalog synchronization, tenant visibility and deterministic SQL projections."""

import json
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update

from app.catalog.search import BlockArgs, SearchArgs, catalog_details, search_catalog
from app.catalog.sfx_ingest import Recording, ingest_recording
from app.config import settings
from app.catalog.sync import ensure_builtin_catalog, sync_builtin_catalog
from app.editing.catalog import MOTION_BLOCK_CATALOG, SOUND_ACOUSTICS
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
        ) == {"block": len(MOTION_BLOCK_CATALOG), "transition": 5, "text_preset": 24}
        assert await db.scalar(select(func.count()).select_from(SoundEffect)) == 80
        assert not await db.scalar(select(func.count()).select_from(SoundEffect).where(
            SoundEffect.engine_kind == "dsp_recipe", func.jsonb_array_length(SoundEffect.waveform_peaks) != 0))
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
        for kind, args in (("block", BlockArgs(query="logo_wall")), ("text_preset", SearchArgs(query="neon_pulse"))):
            outline = (await search_catalog(db, owner, kind, args, gallery=False))["items"][0]
            assert outline["id"] == args.query
            assert {"preview_spec", "props_schema", "example_props"}.isdisjoint(outline)
        user = await db.get(User, owner)
    async with full_api_client(database, user) as client:
        for path, key in (
            ("blocks", "logo_wall"),
            ("text-presets", "neon_pulse"),
            ("sfx", "dsp_deep_hit"),
        ):
            r = await client.get(f"/api/v1/catalog/{path}", params={"query": key, "limit": 1})
            assert r.status_code == 200 and r.json()["items"][0]["id"] == key
            item = r.json()["items"][0]
            assert {"example_props", "props_schema", "params_schema"}.isdisjoint(item)
            if path == "sfx":
                assert "preview_spec" not in item
                assert item["waveform_peaks"] == SOUND_ACOUSTICS[item["recipe_id"]]["waveform_peaks"]
            else:
                spec = item["preview_spec"]
                assert item["name_zh"] and spec["width"] > 0 and spec["height"] > 0
                assert spec["duration_frames"] * spec["fps"]["den"] / spec["fps"]["num"] == item["preview_duration_s"] > 0
                obj = spec["tracks"][0]["clips"][0]["object"]
                if path == "blocks":
                    assert obj["kind"] == "motion_block" and obj["block_id"] == key
                    assert item["recommended_sfx"] == ["dsp_velvet_pass"]
                else:
                    assert obj["kind"] == "text" and obj["text"] and spec["fonts"]
                    assert "recommended_sfx" not in item
        r = await client.get("/api/v1/catalog/blocks", params={"category": "private"})
        assert [row["id"] for row in r.json()["items"]] == ["own"]


async def test_recorded_switch_waveform_reaches_sound_gallery(database, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    pack = Path(__file__).resolve().parents[2] / "assets/sfx"
    entry = next(e for e in json.loads((pack / "manifest.json").read_bytes()) if e["file"] == "switch.wav")
    owner_id = await _user(database)
    async with database.begin() as db:
        await ingest_recording(db, Recording.model_validate(entry), pack)
    async with database() as db:
        user = await db.get(User, owner_id)
        sample = await db.scalar(select(SoundEffect).where(SoundEffect.slug == entry["slug"]))
        peaks = sample.waveform_peaks
        assert len(peaks) == 32 and max(peaks) == pytest.approx(1.0)
        assert min(peaks) < max(peaks)
        assert all(0 <= p <= 1 and p == round(p, 3) for p in peaks)
    async with full_api_client(database, user) as client:
        response = await client.get("/api/v1/catalog/sfx", params={"domain": "interface", "query": entry["slug"]})
        assert response.status_code == 200
        match = next(row for row in response.json()["items"] if row["id"] == entry["slug"])
        assert match["engine_kind"] == "sample" and match["waveform_peaks"] == peaks


async def test_ensure_builtin_catalog_backfills_sounds_when_visual_catalog_exists(database):
    async with database.begin() as db:
        await sync_builtin_catalog(db)
        await db.execute(delete(SoundEffect).where(SoundEffect.slug != "dsp_click"))
        await db.execute(update(SoundEffect).values(domain="video"))

    async with database() as db:
        await ensure_builtin_catalog(db)

    async with database() as db:
        sounds = dict((await db.execute(
            select(SoundEffect.slug, SoundEffect.domain).where(SoundEffect.engine_kind == "dsp_recipe")
        )).all())
        assert len(sounds) == 80
        assert sounds["dsp_click"] == "interface"
        assert sounds["dsp_tension_radar"] == "video"


def _write_test_mp3(path: Path, seconds: int = 3) -> bytes:
    """Encode a deterministic short stereo MP3 via PyAV for catalog import tests."""
    import av
    import numpy as np

    sample_rate = 44100
    t = np.linspace(0, seconds, sample_rate * seconds, endpoint=False, dtype=np.float32)
    # Rhythmic pulse so BeatGrid and waveform peaks are non-trivial.
    envelope = (0.35 + 0.65 * (np.sin(2 * np.pi * 2.0 * t) > 0).astype(np.float32))
    wave = (0.3 * envelope * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    stereo = np.stack([wave, wave], axis=0)
    with av.open(str(path), mode="w", format="mp3") as container:
        stream = container.add_stream("mp3", rate=sample_rate, layout="stereo")
        frame = av.AudioFrame.from_ndarray(stereo, format="fltp", layout="stereo")
        frame.sample_rate = sample_rate
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path.read_bytes()


async def test_selective_music_import_reconciles_searchable_recording(database, monkeypatch, tmp_path):
    from app.pipeline.music import search_music_library, seed_default_music
    from scripts.import_library_music import _main

    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path / 'storage'}")
    music_dir = tmp_path / "music_src"
    music_dir.mkdir()
    sample_bytes = _write_test_mp3(music_dir / "vlog-nagoya-citypop.mp3", seconds=12)
    assert await _main(music_dir, ["vlog-nagoya-citypop"]) == 0
    assert await _main(music_dir, ["vlog-nagoya-citypop"]) == 0
    async with database() as db:
        created = await seed_default_music(db)
        assert [row.mood for row in created] == ["vlog-nagoya-citypop"]
        track, = await search_music_library(db, genre="city pop", bpm=116, query="Sojourn")
        assert track.id == created[0].id
        assert (tmp_path / "storage" / track.file_path).read_bytes() == sample_bytes
        assert track.meta["category"] == "vlog"
        assert track.meta["format_kind"] == "arc_90s"
        assert len(track.meta["sections"]) == 4
        assert len(track.meta["waveform_peaks"]) == 72
        assert track.meta["origin"] == "estimated" and track.meta["beats"]


async def test_music_clips_for_window_source_start_offset_and_wrap():
    from uuid import uuid4

    from app.editing.schemas import VersionSettings
    from app.editing.timing import SOURCE_TIMEBASE
    from app.skills.blueprint import music_clips_for_window

    settings_obj = VersionSettings(width=1920, height=1080, timebase=3000)
    src_id = uuid4()
    digest = "a" * 64
    # 120s source, start at 30s for a 45s video -> single clip [30s, 75s] without looping
    clips = music_clips_for_window(
        settings=settings_obj,
        start=0,
        end=45 * 3000,
        source_id=src_id,
        digest=digest,
        source_ticks=120 * SOURCE_TIMEBASE,
        id_stem="promo_mid",
        gain_db=-16.0,
        fade_in_seconds=0.8,
        fade_out_seconds=1.5,
        source_start_ticks=30 * SOURCE_TIMEBASE,
    )
    assert len(clips) == 1
    assert clips[0].source.source_range.start == 30 * SOURCE_TIMEBASE
    assert clips[0].source.source_range.end == 75 * SOURCE_TIMEBASE

    # 120s source, start at 100s for a 45s video -> [100s, 120s] then wraps to [0s, 25s]
    wrapped = music_clips_for_window(
        settings=settings_obj,
        start=0,
        end=45 * 3000,
        source_id=src_id,
        digest=digest,
        source_ticks=120 * SOURCE_TIMEBASE,
        id_stem="promo_wrap",
        gain_db=-16.0,
        fade_in_seconds=0.5,
        fade_out_seconds=1.0,
        source_start_ticks=100 * SOURCE_TIMEBASE,
    )
    assert len(wrapped) == 2
    assert wrapped[0].source.source_range.start == 100 * SOURCE_TIMEBASE
    assert wrapped[0].source.source_range.end == 120 * SOURCE_TIMEBASE
    assert wrapped[1].source.source_range.start == 0
    assert wrapped[1].source.source_range.end == 25 * SOURCE_TIMEBASE

"""Focused Batch 1 core contract tests: MotionBlockObject, sound catalog, and audio editing."""

import json
import subprocess
from pathlib import Path
from typing import get_args
from uuid import uuid4

import pytest

import app.models.schemas  # noqa: F401 - rebuilds CompositionContent forward refs
from app.editing.catalog import (
    MOTION_BLOCK_CATALOG,
    SOUND_RECIPE_CATALOG,
    VERIFIED_VOICE_IDS,
    SoundRecipeId,
    build_sound_spec,
    sound_spec_digest,
)
from app.editing.edits import apply_ops
from app.editing.revisions import motion_block_ops
from app.editing.schemas import (
    CompositionContent,
    MotionBlockObject,
    Scene,
    TimeRange,
    Track,
    VersionSettings,
)
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec


def _base_content(with_caption: bool = True) -> CompositionContent:
    tracks = [
        Track(track_id="trk_main", kind="visual", role="main", order=0, clips=[]),
    ]
    if with_caption:
        tracks.append(Track(track_id="trk_caption", kind="visual", role="caption", order=1, clips=[]))
    return CompositionContent(
        settings=VersionSettings(width=1920, height=1080, fps={"num": 30}, background="#080A0F"),
        scenes=[Scene(scene_id="scene_1", range=TimeRange(start=0, end=540000), intent="Opening")],
        timeline={"tracks": tracks, "transitions": []},
    )


def test_sound_catalog_and_cache_keys_match_typescript():
    """Use the same TS entry point as POST /synthesize-sfx, once per catalog."""
    engine = Path(__file__).resolve().parents[4] / "packages" / "sound-engine"
    script = """
        import { createHash } from 'node:crypto';
        import { SOUND_RECIPES, buildSoundSpec, canonicalSoundSpecJson } from './src/index.ts';
        const rows = SOUND_RECIPES.map(recipe => {
          const variants = [{}, ...['min', 'max'].map(bound =>
            Object.fromEntries(Object.entries(recipe.params).map(([k,p]) => [k,p[bound]]))),
            {pitch: recipe.params.pitch.min + 0.5, length: recipe.params.length.max + 10}];
          const cases = variants.map((params, i) => {
            const seed = [undefined, 0, 0xffffffff, 17][i];
            const canonical = canonicalSoundSpecJson(buildSoundSpec({recipeId: recipe.id, params, seed}));
            return {params, seed, canonical, sha: createHash('sha256').update(canonical).digest('hex')};
          });
          return {recipe, cases};
        });
        console.log(JSON.stringify(rows));
    """
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", script],
        cwd=engine, check=True, capture_output=True, text=True,
    )
    rows = json.loads(result.stdout)
    assert len(rows) == len(SOUND_RECIPE_CATALOG) == 22
    assert {row["recipe"]["id"] for row in rows} == set(get_args(SoundRecipeId)) == set(SOUND_RECIPE_CATALOG)
    for row in rows:
        recipe = row["recipe"]
        recipe_id = recipe["id"]
        assert recipe == SOUND_RECIPE_CATALOG[recipe_id]
        for case in row["cases"]:
            spec = build_sound_spec(recipe_id, case["params"], case.get("seed"))
            assert spec["engine_version"] == 2
            assert json.dumps(spec, sort_keys=True, separators=(",", ":")).encode() == case["canonical"].encode()
            assert sound_spec_digest(spec) == case["sha"]


def test_sound_spec_digest_excludes_discovery_metadata():
    spec_a = build_sound_spec("impact", params={"pitch": 82, "tone": 38}, seed=1248)
    digest_a = sound_spec_digest(spec_a)

    # Mutating discovery metadata must not affect spec digest.
    old_desc = SOUND_RECIPE_CATALOG["impact"]["desc"]
    try:
        SOUND_RECIPE_CATALOG["impact"]["desc"] = "Completely rewritten marketing description"
        spec_b = build_sound_spec("impact", params={"pitch": 82, "tone": 38}, seed=1248)
        assert sound_spec_digest(spec_b) == digest_a
    finally:
        SOUND_RECIPE_CATALOG["impact"]["desc"] = old_desc

    # Parameter changes MUST change spec digest.
    spec_c = build_sound_spec("impact", params={"pitch": 68, "tone": 38}, seed=1248)
    assert sound_spec_digest(spec_c) != digest_a
    assert len(VERIFIED_VOICE_IDS) >= 8
    assert {"kinetic_title", "product_showcase"} <= set(MOTION_BLOCK_CATALOG)


def test_motion_block_z_order_below_captions_and_compiles_video_spec():
    content = _base_content(with_caption=True)
    img_id = uuid4()
    img_digest = "a" * 64
    snapshots = {
        img_id: {
            "kind": "image",
            "digest": img_digest,
            "storage_key": "uploads/oxvalue-hero.png",
            "meta": {"content_type": "image/png"},
        }
    }

    # Insert kinetic_title FIRST, then product_showcase SECOND — Z-order must still be
    # product_showcase (main) < kinetic_title (title) < trk_caption (caption).
    title_ops = motion_block_ops(
        content,
        block_id="kinetic_title",
        props={"headline": "AI-Native Valuation", "eyebrow": "OXVALUE AI", "entrance_duration_s": 0.8},
        resources=[],
        clip_id="clp_title",
        object_id="obj_title",
        scene_id="scene_1",
        start=30000,
        end=480000,
    )
    content = apply_ops(content, title_ops, bound_digests={img_id: img_digest})

    showcase_ops = motion_block_ops(
        content,
        block_id="product_showcase",
        props={"url_bar": "agent.oxvalue.ai", "theme": "dark"},
        resources=[{
            "path": "media/img_0.png",
            "snapshot_id": str(img_id),
            "snapshot_digest": img_digest,
            "content_type": "image/png",
        }],
        clip_id="clp_showcase",
        object_id="obj_showcase",
        scene_id="scene_1",
        start=0,
        end=540000,
    )
    content = apply_ops(content, showcase_ops, bound_digests={img_id: img_digest})

    validate_content(content, snapshots)
    orders = {t.track_id: t.order for t in content.timeline.tracks}
    assert orders["trk_mg_main"] < orders["trk_mg_title"] < orders["trk_caption"]

    spec = compile_video_spec(
        content,
        snapshots,
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest="b" * 64,
    )
    assert spec["fonts"], "motion_block must pin Noto Sans SC fonts for Linux rendering"
    compiled_clips = {
        c["clip_id"]: c
        for t in spec["tracks"]
        for c in t["clips"]
    }
    assert compiled_clips["clp_showcase"]["object"]["kind"] == "motion_block"
    assert compiled_clips["clp_showcase"]["object"]["block_id"] == "product_showcase"
    assert compiled_clips["clp_showcase"]["source"] == {
        "url": "uploads/oxvalue-hero.png",
        "digest": img_digest,
    }
    assert compiled_clips["clp_title"]["object"]["block_id"] == "kinetic_title"
    assert compiled_clips["clp_title"]["source"] is None


def test_product_showcase_requires_image_resource():
    with pytest.raises(ValueError, match="at least one pinned image resource"):
        MotionBlockObject(
            kind="motion_block",
            object_id="obj_bad",
            block_id="product_showcase",
            props={"url_bar": "agent.oxvalue.ai"},
            resources=[],
            layout={"x": 0, "y": 0, "width": 1920, "height": 1080},
        )


def test_motion_block_translate_safe_bounds():
    from app.chat.editor import validate_motion_block_translate
    from app.editing.schemas import LayoutBox

    title = MotionBlockObject(
        kind="motion_block",
        object_id="obj_title_1",
        block_id="kinetic_title",
        layout=LayoutBox(x=0, y=0, width=1920, height=1080),
        props={"headline": "OxValue", "position": "bottom_left"},
    )
    # Region-select upward adjustment and reset to 0 are allowed
    validate_motion_block_translate(title, x=0.0, y=0.0, width=1920.0, height=1080.0)
    validate_motion_block_translate(title, x=40.0, y=-80.0, width=1920.0, height=1080.0)
    # Pushing bottom_left card off the bottom edge (+110px) is blocked
    with pytest.raises(ValueError, match="safe area"):
        validate_motion_block_translate(title, x=0.0, y=110.0, width=1920.0, height=1080.0)


@pytest.mark.asyncio
async def test_execute_generate_sfx_stop_fence_blocks_late_write(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.chat import editor_media
    from app.chat.editor import GenerateSfxArgs
    from app.chat.service import TurnStopped
    from app.tools.video import sfx_synthesis

    turn_id = uuid4()
    conv_id = uuid4()
    user_id = uuid4()
    project_id = uuid4()
    opening = SimpleNamespace(
        id=turn_id,
        conversation_id=conv_id,
        role="user",
        turn_state="in_flight",
        intent={},
    )
    created_messages: list = []
    sse_events: list = []

    class FakeDb:
        async def scalar(self, *_a, **_kw):
            return SimpleNamespace(id=project_id) if not hasattr(self, "_called") and not setattr(self, "_called", True) else None

        async def get(self, *_a, **_kw):
            return SimpleNamespace(id=project_id)

        async def commit(self):
            pass

    @asynccontextmanager
    async def fake_session():
        yield FakeDb()

    async def fake_lock(_db, _tid):
        return opening

    async def fake_create(*args, **kwargs):
        created_messages.append((args, kwargs))
        return SimpleNamespace(id=uuid4(), intent=kwargs.get("intent") or {})

    async def fake_synth(**_kw):
        # Simulate user clicking Stop while HTTP synthesis is in flight.
        opening.turn_state = "stopped"
        return {"snapshot_id": str(uuid4()), "digest": "a" * 64}

    monkeypatch.setattr(editor_media, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(editor_media, "_lock_turn_for_transcript_write", fake_lock)
    monkeypatch.setattr(editor_media, "_create_message", fake_create)
    monkeypatch.setattr(editor_media, "current_call_id", lambda: "call_stop_sfx_1")
    monkeypatch.setattr(sfx_synthesis, "synthesize_project_sfx", fake_synth)

    turn = SimpleNamespace(
        turn_id=turn_id,
        conversation_id=conv_id,
        user_id=user_id,
        project=SimpleNamespace(id=project_id, user_id=user_id),
        db=SimpleNamespace(execute=AsyncMock()),
        on_row_append=AsyncMock(side_effect=lambda row: sse_events.append(row)),
    )

    with pytest.raises(TurnStopped):
        await editor_media.execute_generate_sfx(
            turn, GenerateSfxArgs(recipe_id="whoosh"), None, None
        )
    assert created_messages == []
    assert sse_events == []

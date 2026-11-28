"""Layer 0 pure contracts: sound-engine recipes & 13 Motion Blocks Py<->TS parity, z-order, transitions, envelopes."""

from __future__ import annotations
import pytest

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
    SOUND_ACOUSTICS,
    TUNE_SCHEMA,
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


def _mg1_base_content(with_caption: bool = True) -> CompositionContent:
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


@pytest.mark.parity
def test_sound_catalog_and_cache_keys_match_typescript():
    """Use the same TS entry point as POST /synthesize-sfx, once per catalog."""
    engine = Path(__file__).resolve().parents[4] / "packages" / "sound-engine"
    script = """
        import { createHash } from 'node:crypto';
        import { SOUND_RECIPES, TUNE_SCHEMA, synthesizeSound, buildSoundSpec, canonicalSoundSpecJson } from './src/index.ts';
        const rows = SOUND_RECIPES.map(recipe => {
          const variants = [{}, ...['min', 'max'].map(bound =>
            Object.fromEntries(Object.entries(recipe.params).map(([k,p]) => [k,p[bound]]))),
            recipe.params.pitch ? {pitch: recipe.params.pitch.min + 0.5, length: recipe.params.length.max + 10} : {}];
          const cases = variants.map((params, i) => {
            const seed = [undefined, 0, 0xffffffff, 17][i];
            const tune = [undefined, {}, Object.fromEntries(Object.entries(TUNE_SCHEMA).map(([k,v])=>[k,v.max])),
              {length_scale: 0.67123901, pitch_st: -3.25, volume_db: -80, punch_pct: 19.5}][i];
            const canonical = canonicalSoundSpecJson(buildSoundSpec({recipeId: recipe.id, params, seed, tune}));
            return {params, seed, tune, canonical, sha: createHash('sha256').update(canonical).digest('hex')};
          });
          return {recipe, cases, schema: TUNE_SCHEMA, acoustics: synthesizeSound({recipeId:recipe.id}).acoustics};
        });
        console.log(JSON.stringify(rows));
    """
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", script],
        cwd=engine, check=True, capture_output=True, text=True,
    )
    rows = json.loads(result.stdout)
    assert len(rows) == len(SOUND_RECIPE_CATALOG) == 80
    assert {row["recipe"]["id"] for row in rows} == set(get_args(SoundRecipeId)) == set(SOUND_RECIPE_CATALOG)
    for row in rows:
        recipe = row["recipe"]
        recipe_id = recipe["id"]
        assert recipe == SOUND_RECIPE_CATALOG[recipe_id]
        assert TUNE_SCHEMA == row["schema"]
        assert SOUND_ACOUSTICS[recipe_id] == row["acoustics"]
        for case in row["cases"]:
            spec = build_sound_spec(recipe_id, case["params"], case.get("seed"), case.get("tune"))
            assert spec["engine_version"] == 3
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
    content = _mg1_base_content(with_caption=True)
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


# --- Multi-scene transitions & audio gain envelopes ---

from uuid import uuid4


import pytest


from app.editing.catalog import build_sound_spec, sound_spec_digest


from app.editing.revisions import build_audio_gain_animation, motion_block_ops


from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    Scene,
    SourceBinding,
    TimeRange,
    Timeline,
    Track,
    Transition,
    VersionSettings,
)


from app.editing.validators import validate_content


from app.editing.video_spec import compile_video_spec


def _b2_base_content(total_seconds: int = 36) -> CompositionContent:
    tb = 90000
    return CompositionContent(
        settings=VersionSettings(width=1920, height=1080, timebase=tb),
        sources=[],
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=total_seconds * tb))],
        timeline=Timeline(tracks=[], transitions=[]),
    )


def test_new_motion_blocks_and_opaque_crossfade_compile():
    from app.editing.edits import apply_ops

    tb = 90000
    img_id = uuid4()
    img_digest = "a" * 64
    logo_id = uuid4()
    logo_digest = "b" * 64
    snapshots = {
        img_id: {"kind": "image", "digest": img_digest, "storage_key": "uploads/ui.png", "meta": {}},
        logo_id: {"kind": "image", "digest": logo_digest, "storage_key": "uploads/logo.png", "meta": {}},
    }
    digests = {sid: info["digest"] for sid, info in snapshots.items()}

    content = _b2_base_content(24)
    ops = []
    # Act 1: statement_hook (0-5s, no resources -> clip.source is None)
    ops.extend(motion_block_ops(
        content,
        block_id="statement_hook",
        props={
            "eyebrow": "OXVALUE.AI",
            "headline": "Institutional Valuation\nIn Minutes",
            "highlight_phrase": "In Minutes",
            "subheadline": "Evidence-grounded AI for venture and tech transfer.",
            "theme": "dark",
            "layout_variant": "centered",
        },
        resources=[],
        clip_id="clp_hook",
        object_id="obj_hook",
        scene_id="scn_1",
        start=0,
        end=5 * tb,
    ))
    content = apply_ops(content, ops, digests)

    # Act 2: product_showcase with callout + frameless (5-12s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="product_showcase",
        props={
            "theme": "light",
            "chrome_mode": "frameless",
            "callout": {"x": 0.15, "y": 0.2, "width": 0.5, "height": 0.35, "label": "Valuation Engine"},
        },
        resources=[{
            "path": "media/img_0.png",
            "snapshot_id": str(img_id),
            "snapshot_digest": img_digest,
            "content_type": "image/png",
        }],
        clip_id="clp_ui",
        object_id="obj_ui",
        scene_id="scn_1",
        start=5 * tb,
        end=12 * tb,
    ), digests)

    # Act 3: metric_grid (12-18s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="metric_grid",
        props={
            "eyebrow": "PROVEN SCALE",
            "title": "Built for institutional rigor",
            "items": [
                {"value": "10×", "label": "Faster Reports", "detail": "Automated diligence pipeline"},
                {"value": "98.4%", "label": "Source Traceability", "badge": "Audited"},
                {"value": "6", "label": "Valuation Models", "detail": "DCF, comparables & IP scoring"},
            ],
            "columns": 3,
            "count_up": True,
        },
        resources=[],
        clip_id="clp_metrics",
        object_id="obj_metrics",
        scene_id="scn_1",
        start=12 * tb,
        end=18 * tb,
    ), digests)

    # Act 4: closing_cta with protected light_pill logo (18-24s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="closing_cta",
        props={
            "brand_name": "OxValue.AI",
            "tagline": "Trusted valuation intelligence for deep tech.",
            "cta_label": "Explore the platform",
            "url_text": "agent.oxvalue.ai",
            "logo_surface": "light_pill",
            "theme": "dark",
        },
        resources=[{
            "path": "media/logo_0.png",
            "snapshot_id": str(logo_id),
            "snapshot_digest": logo_digest,
            "content_type": "image/png",
        }],
        clip_id="clp_cta",
        object_id="obj_cta",
        scene_id="scn_1",
        start=18 * tb,
        end=24 * tb,
    ), digests)

    # Overlay pill_caption on Act 2 (lives on trk_mg_title, does not block main track crossfades)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="kinetic_title",
        props={
            "eyebrow": "LIVE INTERFACE",
            "headline": "Real-time Evidence Graph",
            "surface_style": "pill_caption",
            "position": "bottom_left",
        },
        resources=[],
        clip_id="clp_pill",
        object_id="obj_pill",
        scene_id="scn_1",
        start=5 * tb,
        end=12 * tb,
    ), digests)

    # Add centered crossfades across all 4 adjacent opaque main acts
    content = content.model_copy(update={
        "timeline": content.timeline.model_copy(update={
            "transitions": [
                Transition(transition_id="trn_1", from_clip_id="clp_hook", to_clip_id="clp_ui", kind="crossfade", duration=int(0.4 * tb)),
                Transition(transition_id="trn_2", from_clip_id="clp_ui", to_clip_id="clp_metrics", kind="crossfade", duration=int(0.4 * tb)),
                Transition(transition_id="trn_3", from_clip_id="clp_metrics", to_clip_id="clp_cta", kind="crossfade", duration=int(0.4 * tb)),
            ]
        })
    })

    validate_content(content, snapshots)
    spec = compile_video_spec(
        content,
        snapshots,
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest="d" * 64,
    )
    assert len(spec["transitions"]) == 3
    by_id = {c["clip_id"]: c for t in spec["tracks"] for c in t["clips"]}
    assert by_id["clp_hook"]["source"] is None
    assert by_id["clp_hook"]["end_frame"] == 150 + 6
    assert by_id["clp_ui"]["start_frame"] == 150 - 6
    assert by_id["clp_cta"]["object"]["props"]["logo_surface"] == "light_pill"
    assert by_id["clp_pill"]["object"]["props"]["surface_style"] == "pill_caption"


def test_transparent_motion_block_rejects_crossfade():
    from app.editing.edits import apply_ops

    tb = 90000
    content = _b2_base_content(10)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="statement_hook",
        props={"headline": "Transparent opener", "show_backdrop": False},
        resources=[],
        clip_id="clp_a",
        object_id="obj_a",
        scene_id="scn_1",
        start=0,
        end=5 * tb,
    ), {})
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="closing_cta",
        props={"brand_name": "OxValue", "tagline": "End", "show_backdrop": True},
        resources=[],
        clip_id="clp_b",
        object_id="obj_b",
        scene_id="scn_1",
        start=5 * tb,
        end=10 * tb,
    ), {})
    content = content.model_copy(update={
        "timeline": content.timeline.model_copy(update={
            "transitions": [
                Transition(transition_id="trn_bad", from_clip_id="clp_a", to_clip_id="clp_b", kind="crossfade", duration=int(0.4 * tb)),
            ]
        })
    })
    with pytest.raises(ValueError, match="show_backdrop=True"):
        compile_video_spec(
            content, {}, composition_id=uuid4(), version_id=uuid4(), content_digest="e" * 64
        )


def test_audio_gain_envelope_fades_and_ducking_compile_without_collapsed_frames():
    tb = 90000
    bgm_id = uuid4()
    bgm_digest = "f" * 64
    snapshots = {
        bgm_id: {
            "kind": "audio",
            "digest": bgm_digest,
            "storage_key": "music/bgm.mp3",
            "duration_ticks": 40 * tb,
            "meta": {},
        }
    }
    anim_dict = build_audio_gain_animation(
        object_id="obj_bgm",
        clip_start_ticks=0,
        clip_end_ticks=36 * tb,
        timebase=tb,
        fps_num=30,
        fps_den=1,
        fade_in_seconds=1.2,
        fade_out_seconds=2.0,
        duck_windows=[
            {"start_seconds": 1.0, "end_seconds": 8.0, "duck_db": -6.0, "ramp_seconds": 0.3},
            {"start_seconds": 10.0, "end_seconds": 18.0, "duck_db": -8.0, "ramp_seconds": 0.3},
        ],
    )
    assert anim_dict is not None
    anim = Animation.model_validate(anim_dict)
    assert anim.keyframes[0].at == 0 and anim.keyframes[0].value == 0.0
    assert anim.keyframes[-1].at == 36 * tb and anim.keyframes[-1].value == 0.0
    assert all(0.0 <= float(kf.value) <= 1.0 for kf in anim.keyframes)

    content = CompositionContent(
        settings=VersionSettings(width=1920, height=1080, timebase=tb),
        sources=[SourceBinding(snapshot_id=bgm_id, snapshot_digest=bgm_digest)],
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=36 * tb))],
        timeline=Timeline(tracks=[
            Track(
                track_id="trk_editor_music",
                kind="audio",
                role="music",
                order=0,
                clips=[
                    Clip(
                        clip_id="clp_bgm",
                        range=TimeRange(start=0, end=36 * tb),
                        scene_id=None,
                        source=ClipSource(
                            snapshot_id=bgm_id,
                            snapshot_digest=bgm_digest,
                            source_range=TimeRange(start=0, end=36 * tb),
                        ),
                        object=AudioObject(kind="audio", object_id="obj_bgm", gain_db=-24.0),
                        animations=[anim],
                    )
                ],
            )
        ]),
    )
    validate_content(content, snapshots)
    spec = compile_video_spec(
        content, snapshots, composition_id=uuid4(), version_id=uuid4(), content_digest="1" * 64
    )
    compiled_anim = spec["tracks"][0]["clips"][0]["animations"][0]
    assert compiled_anim["property"] == "audio.gain"
    frames = [kf["at"] for kf in compiled_anim["keyframes"]]
    assert frames == sorted(set(frames))


def test_swoosh_cut_catalog_and_digest_isolation():
    spec_a = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 560}, seed=99)
    spec_b = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 560}, seed=99)
    spec_c = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 420}, seed=99)
    assert sound_spec_digest(spec_a) == sound_spec_digest(spec_b)
    assert sound_spec_digest(spec_a) != sound_spec_digest(spec_c)


# --- Narrative Motion Block closed props & device resources ---

from types import SimpleNamespace


from uuid import UUID


import pytest


from pydantic import ValidationError


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.schemas import CompositionContent, MOTION_BLOCK_PROP_MODELS, MotionBlockObject


from app.editing.store import apply_composition_edits, content_of, get_video_version, snapshot_facts


from app.editing.video_spec import compile_video_spec


from app.models.tables import Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import (
    InstantiateSkillBlueprintArgs, SkillBlueprintV1, instantiate_skill_blueprint, save_composition_as_skill,
)


from test.support.db_helpers import _project, _user


def materials(label, metric):
    return {
        "chat_demo": dict(title=label, messages=[dict(role=r, text=label) for r in ("user", "assistant")],
                          work_steps=[dict(label=label)], result_card=dict(title=label, subtitle=label, badge=label)),
        "device_mockup": dict(eyebrow=label, headline=label, caption=label),
        "flow_diagram": dict(title=label, nodes=[dict(title=label, detail=label, step_label=label, badge=label) for _ in range(3)]),
        "split_compare": dict(left_heading=label, right_heading=label, left_items=[dict(text=label) for _ in range(2)],
                              right_items=[dict(text=label) for _ in range(3)]),
        "step_timeline": dict(steps=[dict(number=label, title=label, detail=label) for _ in range(3)]),
        "bento_features": dict(cards=[dict(tag=label, title=label, detail=label) for _ in range(4)]),
        "data_chart": dict(title=label, subtitle=label, unit=label, points=[
            dict(label=label, value=metric+i, display_value=label) for i in range(4)]),
        "quote_proof": dict(quote=label, author=label, role_or_source=label, verification_badge=label, highlight_phrase=label),
    }


STYLES = {
    "chat_demo": {}, "device_mockup": {"layout": "dual", "reveal_at_s": 1.5},
    "flow_diagram": {}, "split_compare": {"dim_left": False},
    "step_timeline": {"active_step": 2}, "bento_features": {"highlight_index": 3},
    "data_chart": {"chart_type": "bar", "highlight_index": 3}, "quote_proof": {"highlight_at_s": 1.4},
}


BOX = dict(x=0, y=0, width=1920, height=1080)


@pytest.mark.parametrize(("block", "invalid"), [
    ("chat_demo", dict(messages=[dict(role="system", text="x")]*2)),
    ("chat_demo", dict(work_steps=[])), ("device_mockup", dict(layout="tablet")),
    ("flow_diagram", dict(nodes=[dict(title="x", url="private")] * 3)),
    ("split_compare", dict(left_items=[])), ("step_timeline", dict(active_step=0)),
    ("step_timeline", dict(active_step=4)), ("bento_features", dict(highlight_index=4)),
    ("data_chart", dict(highlight_index=-1)), ("data_chart", dict(highlight_index=4)),
    ("data_chart", dict(points=[dict(label="x", value=float("inf"))]*3)),
    ("quote_proof", dict(author="  ")), ("quote_proof", dict(highlight_at_s=-1)),
])
def test_narrative_props_are_closed(block, invalid):
    valid = {**materials("Source", 2)[block], **STYLES[block]}
    model = MOTION_BLOCK_PROP_MODELS[block]
    assert model.model_validate(valid).show_backdrop
    for patch in [invalid, {"unregistered": "field"}]:
        with pytest.raises(ValidationError):
            model.model_validate({**valid, **patch})


def test_device_accepts_one_or_two_ordered_images():
    obj = dict(kind="motion_block", object_id="device", block_id="device_mockup", props={}, layout=BOX)
    images = [dict(path=f"media/{i}.png", snapshot_id=UUID(int=i+1),
                   snapshot_digest="e"*64, content_type="image/png") for i in range(3)]
    for count in (1, 2):
        assert len(MotionBlockObject(**obj, resources=images[:count]).resources) == count
    for invalid in ([], images, [{**images[0], "content_type": "video/mp4"}]):
        with pytest.raises(ValidationError):
            MotionBlockObject(**obj, resources=invalid)


# --- Capture target & step window validation ---

from types import SimpleNamespace


from uuid import UUID


import pytest


from pydantic import ValidationError


from app.chat.editor import SetTransitionArgs


from app.editing.schemas import CompositionContent, ProductShowcaseProps


from app.editing.store import apply_composition_edits, content_of, get_video_version, snapshot_facts


from app.editing.video_spec import compile_video_spec


from app.models.tables import Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import (
    InstantiateSkillBlueprintArgs, SkillBlueprintV1, instantiate_skill_blueprint, save_composition_as_skill,
)


from test.support.db_helpers import _project, _user


def test_capture_targets_and_step_windows_are_unambiguous():
    view = {"view_id": "new", "elements": [{"id": "missing-box"}]}
    for target in ({"element_id": "old"}, {"element_id": "missing-box"}, {"element_id": "old", "x": 0.5}):
        for props in ({"cursor": target}, {"callout_steps": [target]}):
            with pytest.raises(ValueError):
                ProductShowcaseProps.resolve_props(props, [view], "new")
    step = dict(x=0, y=0, width=0.2, height=0.1, label="Region", start_s=0.2, end_s=0.7)
    for steps in ([step] * 5, [step, step], [{**step, "end_s": 0.1}]):
        with pytest.raises(ValidationError):
            ProductShowcaseProps(callout_steps=steps)
    assert SetTransitionArgs(from_clip_id="left", to_clip_id="right").kind == "crossfade"
    with pytest.raises(ValidationError):
        SetTransitionArgs(from_clip_id="left", to_clip_id="right", kind="unknown")


# --- Three-column metric grid compilation ---

from uuid import UUID, uuid4


import pytest


import pytest_asyncio


from app.chat.editor import InsertAudioArgs, InsertMotionBlockArgs, edit_clip


from app.editing.edits import apply_ops


from app.editing.revisions import motion_block_ops


from app.editing.store import apply_composition_edits, content_of


from app.editing.video_spec import compile_video_spec


from app.models.tables import CompositionVersion, Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import load_blueprint_from_skill_version, music_clips_for_window, save_composition_as_skill


from app.tools.video.preparation import canonical_resource


from test.support.composition_fixtures import base_content as _base_content


from test.support.db_helpers import _create, _project, _snapshots, _user



@pytest.mark.parametrize("detail", [None, "Published valuation methods"])
def test_three_column_metrics_compile_with_optional_supporting_copy(detail):
    content = _base_content(4)
    items = [{"value": str(i), "label": label} for i, label in enumerate(("Evidence", "Models", "Reports"), 1)]
    if detail:
        items[1]["detail"] = detail
    ops = motion_block_ops(content, block_id="metric_grid", props={"columns": 3, "items": items},
                           clip_id="clp_metrics", object_id="obj_metrics", scene_id="scn_1",
                           start=0, end=360000, resources=[])
    spec = compile_video_spec(apply_ops(content, ops, {}), {}, composition_id=uuid4(),
                              version_id=uuid4(), content_digest="d" * 64)
    clip, = spec["tracks"][0]["clips"]
    props = clip["object"]["props"]
    assert (clip["object"]["block_id"], props["columns"], clip["end_frame"]) == ("metric_grid", 3, 120)
    assert [(i["label"], i["value"], i.get("detail")) for i in props["items"]] == [
        ("Evidence", "1", None), ("Models", "2", detail), ("Reports", "3", None),
    ]


# --- All 13 Motion Blocks slot-preview & Zod parity ---

import hashlib


import io


import json


import subprocess


from pathlib import Path


from types import SimpleNamespace


from uuid import UUID, uuid4


import httpx


import pytest


from httpx import ASGITransport, AsyncClient


from PIL import Image


from app.chat.activity_receipts import skill_saved_receipt


from app.dependencies import get_current_user_required, get_db


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.styles import CompositionStyle, STYLE_PRESETS


from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks


from app.main import app


from app.models.tables import User


from app.skills import SKILL_REGISTRY


from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    BLUEPRINT_PATH,
    BlueprintAct,
    BlueprintAudioProfile,
    BlueprintOverlay,
    BlueprintSfxCue,
    BlueprintTransition,
    SkillBlueprintV1,
)


from app.skills.external import (
    SkillCapabilityReport,
    SkillDraft,
    SkillPolicy,
    SkillSource,
)


from app.skills.resolution import (
    _external_option,
    get_builtin_skill_option,
    list_available_skills,
)


from app.skills.slot_preview import (
    ALLOWED_FONT_FILENAMES,
    build_slot_preview_video_spec,
    compile_blueprint_slot_preview,
    count_blueprint_slots,
    format_slot_checklist,
)


from app.skills.store import import_external_skill


REPO_ROOT = Path(__file__).resolve().parents[4]


def _make_all_13_blocks_blueprint() -> SkillBlueprintV1:
    acts = [
        BlueprintAct(
            act_id="act_1",
            block_id="statement_hook",
            role="opener",
            target_duration_s=4.0,
            min_duration_s=2.5,
            required_slots=["headline"],
            optional_slots=["subheadline"],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_2",
            block_id="kinetic_title",
            role="title",
            target_duration_s=3.0,
            min_duration_s=2.0,
            required_slots=["headline"],
            optional_slots=["subheadline"],
        ),
        BlueprintAct(
            act_id="act_3",
            block_id="product_showcase",
            role="showcase",
            target_duration_s=6.0,
            min_duration_s=3.5,
            style_defaults={"camera_preset": "tilt_left", "chrome_mode": "browser"},
            required_slots=["image_resource"],
            optional_slots=["url_bar", "callout_steps"],
            callout_windows_s=[(1.0, 2.8), (3.1, 5.2)],
            cursor_click_at_s=2.0,
            overlays=[
                BlueprintOverlay(
                    overlay_id="act_3_overlay_1",
                    rel_start_s=0.6,
                    rel_end_s=3.4,
                    style_defaults={"surface_style": "pill_caption", "position": "bottom_left"},
                )
            ],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_4",
            block_id="device_mockup",
            role="showcase",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"layout": "dual", "reveal_at_s": 1.2},
            required_slots=["image_resource", "mobile_image_resource"],
            transition_after=BlueprintTransition(kind="whip_pan", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_5",
            block_id="chat_demo",
            role="demo",
            target_duration_s=6.0,
            min_duration_s=3.5,
            required_slots=["messages", "preview_resource"],
            optional_slots=["work_steps", "result_card"],
            item_reveals_s=[0.4, 1.4, 2.6, 3.6],
            secondary_reveals_s=[1.8, 2.2],
            transition_after=BlueprintTransition(kind="zoom_through", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_6",
            block_id="metric_grid",
            role="metrics",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["items"],
            metric_reveals_s=[0.5, 1.1, 1.7],
            transition_after=BlueprintTransition(kind="iris_focus", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_7",
            block_id="bento_features",
            role="features",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"highlight_index": 1},
            required_slots=["cards"],
            item_reveals_s=[0.4, 1.0, 1.6, 2.2],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_8",
            block_id="flow_diagram",
            role="workflow",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["nodes"],
            item_reveals_s=[0.4, 1.1, 1.8, 2.5],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_9",
            block_id="step_timeline",
            role="roadmap",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"active_step": 2},
            required_slots=["steps"],
            item_reveals_s=[0.5, 1.3, 2.1],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_10",
            block_id="split_compare",
            role="compare",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"dim_left": True},
            required_slots=["left_heading", "left_items", "right_heading", "right_items"],
            item_reveals_s=[0.4, 1.0, 1.6],
            secondary_reveals_s=[0.8, 1.4, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_11",
            block_id="data_chart",
            role="data",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"chart_type": "bar", "highlight_index": 3},
            required_slots=["title", "points"],
            item_reveals_s=[0.5, 1.0, 1.5, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_12",
            block_id="quote_proof",
            role="proof",
            target_duration_s=4.5,
            min_duration_s=3.0,
            style_defaults={"highlight_at_s": 1.2},
            required_slots=["quote", "author"],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_13",
            block_id="closing_cta",
            role="closing",
            target_duration_s=4.5,
            min_duration_s=3.0,
            required_slots=["brand_name", "tagline"],
        ),
    ]
    sfx_cues = [
        BlueprintSfxCue(cue_id="sfx_1", recipe_id="sub_swell", act_index=0, anchor="act_start", offset_s=0.0, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_2", recipe_id="callout_ping", act_index=2, anchor="act_start", offset_s=1.0, gain_db=-11.0),
        BlueprintSfxCue(cue_id="sfx_3", recipe_id="swoosh_cut", act_index=5, anchor="cut_after", offset_s=-0.15, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_4", recipe_id="stinger", act_index=12, anchor="act_start", offset_s=0.2, gain_db=-11.0),
    ]
    return SkillBlueprintV1(
        canvas={"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "background": "#0A0F16"},
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(has_bgm=False),
        sfx_cues=sfx_cues,
    )


def _make_6_act_blueprint() -> SkillBlueprintV1:
    full = _make_all_13_blocks_blueprint()
    picked_ids = {
        "product_showcase",
        "metric_grid",
        "bento_features",
        "data_chart",
        "quote_proof",
        "closing_cta",
    }
    acts = [a for a in full.acts if a.block_id in picked_ids]
    return SkillBlueprintV1(
        canvas=full.canvas,
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(),
        sfx_cues=[
            BlueprintSfxCue(cue_id="sfx_open", recipe_id="title_bloom", act_index=0, anchor="act_start", offset_s=0.0),
            BlueprintSfxCue(cue_id="sfx_cut", recipe_id="velvet_pass", act_index=1, anchor="cut_after", offset_s=-0.1),
            BlueprintSfxCue(cue_id="sfx_close", recipe_id="stinger", act_index=5, anchor="act_start", offset_s=0.2),
        ],
    )


def _skill_draft_for_blueprint(name: str, bp: SkillBlueprintV1) -> SkillDraft:
    bp_json = bp.model_dump_json(indent=2)
    bp_digest = hashlib.sha256(bp_json.encode("utf-8")).hexdigest()
    skill_md = f"---\nname: {name}\ndescription: Test blueprint\n---\nUse this template.\n"
    return SkillDraft(
        name=name,
        description="Test slot blueprint template",
        instructions=skill_md,
        references=[
            SkillSource(
                path=BLUEPRINT_PATH,
                role="reference",
                digest=bp_digest,
                text=bp_json,
            )
        ],
        media=[],
        declared_inputs=[],
        capability_report=SkillCapabilityReport(
            supported=[BLUEPRINT_CAPABILITY, "native_motion_graphics"]
        ),
        policy=SkillPolicy(),
        source_uri=f"composition://test-{name}@v1",
        source_revision="v1",
        source_hash=bp_digest,
    )


@pytest.mark.parity
def test_compile_all_20_motion_blocks_and_zod_video_spec_parity():
    bp = _make_all_13_blocks_blueprint()
    from typing import get_args
    from app.editing.catalog import MotionBlockId
    from app.editing.styles import INHERITABLE_BLOCK_STYLE_KEYS

    bp.acts.extend([
        BlueprintAct(act_id="act_14", block_id="kinetic_beat", role="beat", target_duration_s=0.25, min_duration_s=0.2),
        BlueprintAct(act_id="act_16", block_id="code_terminal", role="console", target_duration_s=2, min_duration_s=1),
        BlueprintAct(act_id="act_17", block_id="logo_wall", role="partners", target_duration_s=2, min_duration_s=1),
        BlueprintAct(act_id="act_15", block_id="ui_montage", role="screens", target_duration_s=0.35, min_duration_s=0.2),
    ])
    for index, block in enumerate(("cursor_magnetic_click", "zoom_follows_click", "browser_url_load"), 18):
        bp.acts.append(BlueprintAct(act_id=f"act_{index}", block_id=block, role="interaction",
                                    target_duration_s=3, min_duration_s=1))
    assert len(set(get_args(MotionBlockId))) == 20
    assert set(MOTION_BLOCK_PROP_MODELS) == set(get_args(MotionBlockId))
    assert {a.block_id for a in bp.acts} == set(MOTION_BLOCK_CATALOG) == set(get_args(MotionBlockId)) == set(INHERITABLE_BLOCK_STYLE_KEYS)

    # Provide synthetic SFX snapshots for all 4 blueprint SFX cues
    sfx_snapshots: dict[str, tuple[UUID, str, int, str]] = {}
    for cue in bp.sfx_cues:
        digest = hashlib.sha256(cue.cue_id.encode()).hexdigest()
        sfx_snapshots[cue.cue_id] = (
            uuid4(),
            digest,
            seconds_to_ticks(0.6, SOURCE_TIMEBASE),
            f"http://127.0.0.1:9999/sfx/{cue.cue_id}.wav",
        )

    expected_count = count_blueprint_slots(bp)
    specs_to_validate: list[dict] = []

    for preset_id in STYLE_PRESETS:
        for locale in ("zh", "en"):
            spec, slots, assets, duration_s = build_slot_preview_video_spec(
                bp,
                skill_version_id=uuid4(),
                style_preset=preset_id,
                locale=locale,
                sfx_snapshots=sfx_snapshots,
            )
            assert len(slots) == expected_count
            assert [s.slot_number for s in slots] == list(range(1, expected_count + 1))
            assert [s.code for s in slots] == [f"[{i:02d}]" for i in range(1, expected_count + 1)]
            assert spec["style"]["preset_id"] == preset_id
            assert duration_s > 50.0

            # Verify Pillow wireframe PNGs exist for product_showcase (16:9),
            # device_mockup dual (16:9 + 9:16), and chat_demo preview (16:9)
            assert len(assets) == 9
            assert sum(asset.width == 640 for asset in assets) == 3
            dims = [(a.width, a.height) for a in assets]
            assert (1280, 720) in dims
            assert (540, 960) in dims
            for asset in assets:
                with Image.open(io.BytesIO(asset.png_bytes)) as im:
                    assert im.format == "PNG"
                    assert im.size == (asset.width, asset.height)

            # Verify HUD track has 1 corner TextObject badge per act
            hud_track = next(t for t in spec["tracks"] if t["track_id"] == "trk_slot_hud")
            assert len(hud_track["clips"]) == 20
            for clip in hud_track["clips"]:
                assert clip["object"]["kind"] == "text"
                assert clip["object"]["style"]["background_mode"] == "pill"

            # Verify transitions & SFX audio tracks preserved
            assert len(spec.get("transitions") or []) >= 9
            effect_clips = [
                c
                for t in spec["tracks"]
                if t["kind"] == "audio" and t["role"] == "effect"
                for c in t["clips"]
            ]
            assert len(effect_clips) == 4

            # Verify checklist text contains every [NN] code
            checklist = format_slot_checklist(slots, locale=locale, template_name="demo")
            for s in slots:
                assert s.code in checklist

            # Verify font URLs point to /api/v1/skills/fonts/...
            assert all(f["url"].startswith("/api/v1/skills/fonts/") for f in spec["fonts"])

            if preset_id in ("vox_editorial", "institutional_dark"):
                specs_to_validate.append(spec)

    # Pass serialized Python models with the optional timing fields through the real TS consumer too.
    from copy import deepcopy
    from app.editing.schemas import validate_motion_block_props

    timed = deepcopy(specs_to_validate[0])
    for track in timed["tracks"]:
        for clip in track["clips"]:
            obj = clip["object"]
            if obj["kind"] != "motion_block":
                continue
            block, props = obj["block_id"], obj["props"]
            if block in {"zoom_follows_click", "cursor_magnetic_click"}:
                props["click_at_s"] = 0
            elif block == "browser_url_load":
                props.update(type_at_s=0.15, load_at_s=1.4)
            elif block == "product_showcase" and props.get("callout_steps"):
                props["callout_steps"][0]["zoom_scale"] = 2.2
            elif block == "statement_hook":
                props.update(headline="First act", word_reveals_s=[0.2, 1.4])
            elif block == "kinetic_beat":
                props.update(mode="slot_flip", words=["Verify", "Ship"], word_reveals_s=[0.2, 0.7])
            obj["props"] = validate_motion_block_props(block, props).model_dump(mode="json")
    specs_to_validate.append(timed)
    from app.tools.video.presets import MOTION_PREVIEW_CATALOG, build_motion_preview_spec
    specs_to_validate.extend(build_motion_preview_spec(key) for key in MOTION_PREVIEW_CATALOG)
    # Verify exact parity against packages/video-spec Zod videoSpecSchema.parse!
    node_script = (
        'import { videoSpecSchema, motionBlockIds } from "./src/index.ts";'
        'import { assertVideoSupported } from "../video-remotion/src/capabilities.ts";'
        'import fs from "node:fs";'
        'const specs = JSON.parse(fs.readFileSync(0, "utf-8"));'
        'for (const s of specs) { assertVideoSupported(videoSpecSchema.parse(s)); }'
        'console.log(JSON.stringify({count: specs.length, ids: motionBlockIds}));'
    )
    proc = subprocess.run(
        ["node", "--import", "tsx", "-e", node_script],
        cwd=str(REPO_ROOT / "packages" / "video-spec"),
        input=json.dumps(specs_to_validate),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Zod videoSpecSchema validation failed:\n{proc.stderr}\n{proc.stdout}"
    validated = json.loads(proc.stdout)
    assert validated["count"] == len(specs_to_validate)
    assert set(validated["ids"]) == set(MOTION_BLOCK_CATALOG)


def test_skill_saved_receipt_validation():
    vid = str(uuid4())
    sid = str(uuid4())
    receipt = skill_saved_receipt({
        "skill_id": sid,
        "skill_version_id": vid,
        "name": "saas-promo",
        "version": 1,
        "acts_count": 6,
        "sfx_cues_count": 4,
    })
    assert receipt is not None
    assert receipt.kind == "skill_saved"
    assert receipt.skill_version_id == vid
    assert receipt.acts_count == 6



@pytest.mark.parametrize("mode,valid,invalid", [
    ("impact_cut", {"headline": "Go"}, {"headline": " "}),
    ("typewriter_swap", {"words": ["设计", "Play"]}, {"words": ["only"]}),
    ("slot_flip", {"words": ["A", "B"]}, {"words": ["A", "x" * 49]}),
    ("inline_badge_split", {"left_text": "Make", "right_text": "waves"}, {"left_text": "Half"}),
    ("marquee_wall", {"items": [{"text": "Go"}] * 3}, {"items": [{"text": " "}] * 3}),
])
def test_kinetic_mode_copy_contract(mode, valid, invalid):
    from app.editing.schemas import KineticBeatProps
    props = KineticBeatProps(mode=mode, **valid)
    if mode == "inline_badge_split":
        assert props.badge_icon == "sparkle"
    for missing in ({}, invalid):
        with pytest.raises(ValueError):
            KineticBeatProps(mode=mode, **missing)


@pytest.mark.parametrize("mode", ["rapid_cut", "fan_slide", "cascade_3d"])
def test_montage_interval_contract(mode):
    from app.editing.schemas import UiMontageProps
    assert UiMontageProps(layout_mode=mode, cut_interval_s=0.35).layout_mode == mode
    with pytest.raises(ValueError):
        UiMontageProps(layout_mode=mode, cut_interval_s=0.17)


@pytest.mark.parametrize("name", ["create_video", "insert_motion_block", "update_motion_block"])
def test_motion_tool_schema_discovers_blocks_at_call_time(name):
    from app.agents.tool_loop import tool_spec
    from app.chat.editor import EDITOR_TOOLS

    tool = next(tool for tool in EDITOR_TOOLS if tool.name == name)
    parameters = tool_spec(tool)["function"]["parameters"]
    if name == "create_video":
        item = parameters["properties"]["motion_blocks"]["items"]["$ref"].rsplit("/", 1)[1]
        fields = parameters["$defs"][item]["properties"]
    else:
        fields = parameters["properties"]
    if name == "update_motion_block":
        assert set(fields) == {"clip_id", "props_patch"}
    else:
        assert fields["block_id"].get("type") == "string"
        assert "enum" not in fields["block_id"]
        bad = {"block_id": "unknown", "props": {}}
        if name == "create_video":
            arguments = {"name": "Test", "motion_blocks": [dict(bad, duration_seconds=2)]}
        else:
            arguments = dict(bad, start_seconds=0, end_seconds=2)
        with pytest.raises(ValueError, match="search_blocks.*get_blocks"):
            tool.params_model.model_validate(arguments)
    assert all(f'"{block_id}"' not in json.dumps(parameters) for block_id in MOTION_BLOCK_CATALOG)


@pytest.mark.parametrize(("block_id", "sfx"), [
    ("cursor_magnetic_click", ["dsp_tap_glass", "dsp_select_pill"]),
    ("zoom_follows_click", ["dsp_click", "dsp_whoosh_micro"]),
    ("browser_url_load", ["dsp_type_soft_key", "dsp_nav_forward"]),
])
def test_interactive_catalog_and_blueprint_replacement(block_id, sfx):
    from app.catalog.sync import builtin_rows
    from app.skills.blueprint import extract_skill_draft_from_composition

    visuals, sounds = builtin_rows()
    row = next(row for row in visuals if row["preset_id"] == block_id)
    assert row["recommended_sfx"] == sfx
    assert set(sfx) <= {sound["slug"] for sound in sounds}
    assert row["props_schema"]["additionalProperties"] is False
    clip = row["preview_spec"]["tracks"][0]["clips"][0]
    assert clip["source"] is None
    assert bool(clip["object"]["resources"]) == (block_id != "cursor_magnetic_click")
    props = row["example_props"]
    with pytest.raises(ValueError, match="get_blocks"):
        MotionBlockObject(kind="motion_block", object_id="bad", layout=BOX, block_id=block_id,
                          props={**props, "unexpected": True})

    content = CompositionContent(settings=VersionSettings(width=1280, height=720))
    resources = []
    if block_id != "cursor_magnetic_click":
        resources = [dict(path="media/private.png", snapshot_id=str(uuid4()),
                          snapshot_digest="a" * 64, content_type="image/png")]
        with pytest.raises(ValueError, match="pinned image"):
            MotionBlockObject(kind="motion_block", object_id="missing", layout=BOX,
                              block_id=block_id, props=props)
    ops = motion_block_ops(content, block_id=block_id, props=props, resources=resources,
                           scene_id=None, clip_id="test", object_id="obj", start=0, end=180000)
    bound = {UUID(r["snapshot_id"]): r["snapshot_digest"] for r in resources}
    content = apply_ops(content, ops, bound_digests=bound)
    _, bp = extract_skill_draft_from_composition(composition_id=uuid4(), version_number=1,
            content=content, snapshot_origins={}, name="interactive", description="Product demo")
    act = bp.acts[0]
    copy = {"headline", "eyebrow", "subcopy", "cta_label", "callout_label", "url_text", "badge"} & props.keys()
    assert copy <= set(act.required_slots + act.optional_slots)
    assert all(props[key] not in bp.model_dump_json() for key in copy)
    assert not {"target_x", "target_y"} & act.style_defaults.keys()
    spec, slots, _, _ = build_slot_preview_video_spec(bp, skill_version_id=uuid4(), locale="en")
    assert [slot.code for slot in slots] == [f"[{n:02d}]" for n in range(1, len(slots) + 1)]
    assert copy <= {slot.slot_key for slot in slots}
    obj = next(c["object"] for t in spec["tracks"] for c in t["clips"] if c["object"]["kind"] == "motion_block")
    for slot in slots:
        if slot.slot_key in copy:
            assert slot.code in obj["props"][slot.slot_key]
    assert len(obj["resources"]) == len(resources)


def test_coerce_motion_block_props_normalizes_details_alias_and_long_eyebrow():
    from app.editing.revisions import coerce_motion_block_props
    from app.editing.schemas import validate_motion_block_props

    raw = {
        "eyebrow": "GOVERNED EVIDENCE ARCHITECTURE OVERVIEW",
        "title": "Why OxValue",
        "cards": [
            {"tag": "01", "title": "VEST Theory", "details": "Original valuation theory."},
            {"tag": "02", "title": "8 Databases", "details": "Sector market anchors."},
            {"tag": "03", "title": "27 Algorithms", "details": "Defensible AI models."},
        ],
    }
    coerced = coerce_motion_block_props("bento_features", raw)
    assert len(coerced["eyebrow"]) <= 32
    assert all("detail" in c and "details" not in c for c in coerced["cards"])
    validated = validate_motion_block_props("bento_features", coerced)
    assert len(validated.cards) == 3

    url_coerced = coerce_motion_block_props(
        "browser_url_load",
        {"url_text": "agent.oxvalue.ai", "type_at_s": "0.4", "load_at_s": "1.5"},
    )
    assert url_coerced["type_at_s"] == 0.4
    assert url_coerced["load_at_s"] == 1.5
    url_validated = validate_motion_block_props("browser_url_load", url_coerced)
    assert url_validated.type_at_s == 0.4
    assert url_validated.load_at_s == 1.5


def test_voiceover_block_ranges_tolerates_shared_boundary_phrase():
    from app.chat.editor_create import FirstMotionBlock, _voiceover_block_ranges

    text = "OxValue was built for that gap: a governed intelligence layer for patents."
    cues = [{
        "text": text,
        "time_begin": 0,
        "time_end": 4000,
        "words": [
            {"word": "OxValue ", "time_begin": 0, "time_end": 500},
            {"word": "was ", "time_begin": 500, "time_end": 800},
            {"word": "built ", "time_begin": 800, "time_end": 1200},
            {"word": "for ", "time_begin": 1200, "time_end": 1400},
            {"word": "that ", "time_begin": 1400, "time_end": 1700},
            {"word": "gap: ", "time_begin": 1700, "time_end": 2000},
            {"word": "a ", "time_begin": 2100, "time_end": 2250},
            {"word": "governed ", "time_begin": 2250, "time_end": 2800},
            {"word": "intelligence ", "time_begin": 2800, "time_end": 3400},
            {"word": "layer ", "time_begin": 3400, "time_end": 3700},
            {"word": "for ", "time_begin": 3700, "time_end": 3850},
            {"word": "patents.", "time_begin": 3850, "time_end": 4000},
        ],
    }]
    blocks = [
        FirstMotionBlock(
            block_id="statement_hook", props={"headline": "A"}, duration_seconds=2.0,
            start_cue_phrase="OxValue was built", end_cue_phrase="a governed intelligence layer",
        ),
        FirstMotionBlock(
            block_id="statement_hook", props={"headline": "B"}, duration_seconds=2.0,
            start_cue_phrase="a governed intelligence layer",
        ),
    ]
    ranges = _voiceover_block_ranges(blocks, text, cues, 4.0, 0, 1000)
    assert ranges[0][1] == ranges[1][0] == 2250  # 0.15s lead + 2.1s onset


def test_parse_tool_arguments_repairs_comma_slips_but_rejects_truncation():
    from app.providers.llm.base import LLMSchemaError
    from app.providers.llm.openai_chat import _parse_tool_arguments

    repaired = _parse_tool_arguments(
        "create_video",
        '{"name":"OxValue" "fps":30,"items":[{"a":1 "b":"x, }"},],}',
        "tool_calls",
    )
    assert repaired == {"name": "OxValue", "fps": 30, "items": [{"a": 1, "b": "x, }"}]}

    with pytest.raises(LLMSchemaError):
        _parse_tool_arguments("create_video", '{"name":"truncated', "tool_calls")

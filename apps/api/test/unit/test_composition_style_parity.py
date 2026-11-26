"""Layer 0 pure contracts: 4 CompositionStyle presets, WCAG contrast, and Py<->TS parity."""

from __future__ import annotations
import pytest

import json


import subprocess


from pathlib import Path


from types import SimpleNamespace


from uuid import UUID, uuid4


import pytest


from app.chat.editor import SetCompositionStyleArgs, edit_clip


from app.editing.catalog import catalog_prompt_index


from app.editing.revisions import apply_composition_style


from app.editing.schemas import (
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    LayoutBox,
    MotionBlockObject,
    SourceBinding,
    SourceCaptionDerivation,
    TextObject,
    TextShadow,
    TextStroke,
    TextStyle,
    TimeRange,
    Timeline,
    Track,
    Transition,
    VersionSettings,
    speech_text_digest,
)


from app.editing.store import (
    apply_composition_edits,
    content_digest_of,
    content_of,
    get_video_version,
    snapshot_facts,
)


from app.editing.styles import (
    STYLE_PRESETS,
    CompositionStyle,
    contrast_ratio,
    resolve_style_tokens,
)


from app.editing.video_spec import compile_video_spec


from app.models.tables import Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import (
    InstantiateSkillBlueprintArgs,
    SkillBlueprintV1,
    instantiate_skill_blueprint,
    save_composition_as_skill,
)


from test.support.db_helpers import _project, _user


REPO_ROOT = Path(__file__).resolve().parents[4]


BOX = LayoutBox(x=0, y=0, width=1920, height=1080)


def _node_eval_ts(code: str, payload: dict) -> dict:
    proc = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", code],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT / "packages" / "video-spec"),
        check=True,
    )
    return json.loads(proc.stdout)


@pytest.mark.parity
def test_python_and_ts_style_presets_and_contrast_algorithm_zero_drift():
    cases = [
        {"preset_id": "institutional_dark"},
        {"preset_id": "swiss_paper"},
        {"preset_id": "vox_editorial"},
        {"preset_id": "kinetic_anime"},
        {"preset_id": "institutional_dark", "backdrop_style": "studio_spotlight"},
        {"preset_id": "institutional_dark", "backdrop_style": "warm_obsidian"},
        {"preset_id": "swiss_paper", "backdrop_style": "editorial_studio"},
        # Custom accent colors including bright yellow, neon green, deep navy, royal blue
        {"preset_id": "vox_editorial", "accent_color": "#facc15"},
        {"preset_id": "swiss_paper", "accent_color": "#00FF00"},
        {"preset_id": "institutional_dark", "accent_color": "#1E3A8A"},
        {"preset_id": "kinetic_anime", "accent_color": "#FFE600"},
        {"preset_id": "vox_editorial", "theme": "dark", "accent_color": "#2563EB"},
        {"preset_id": "institutional_dark", "theme": "light", "backdrop_style": "architectural_grid"},
        {"preset_id": "swiss_paper", "backdrop_style": "clean", "accent_color": "#0D9488"},
    ]

    py_results = [
        resolve_style_tokens(CompositionStyle.model_validate(case))
        for case in cases
    ]

    ts_script = """
import { readFileSync } from "node:fs";
import { STYLE_PRESETS, resolveStyleTokens } from "../video-remotion/src/engine/styles.ts";
const { cases } = JSON.parse(readFileSync(0, "utf8"));
const results = cases.map((c) => resolveStyleTokens(c));
process.stdout.write(JSON.stringify({ presets: STYLE_PRESETS, results }));
"""
    ts_out = _node_eval_ts(ts_script, {"cases": cases})

    assert ts_out["presets"] == STYLE_PRESETS
    assert ts_out["results"] == py_results

    # Verify WCAG contrast guardrails across every resolved style token set
    for case, tokens in zip(cases, py_results):
        min_fill_ratio = 4.2 if case.get("accent_color") else 3.5
        assert contrast_ratio(tokens["accent"], tokens["accent_ink"]) >= min_fill_ratio
        assert contrast_ratio(tokens["accent_text"], tokens["canvas_bg"]) >= 4.5
        assert contrast_ratio(tokens["accent_text"], tokens["surface_bg"]) >= 4.5
        assert contrast_ratio(tokens["ink"], tokens["canvas_bg"]) >= 7.0
        assert contrast_ratio(tokens["ink"], tokens["surface_bg"]) >= 7.0
    assert contrast_ratio(STYLE_PRESETS["vox_editorial"]["accent"], STYLE_PRESETS["vox_editorial"]["accent_ink"]) >= 12.0
    assert contrast_ratio(STYLE_PRESETS["institutional_dark"]["accent"], STYLE_PRESETS["institutional_dark"]["accent_ink"]) >= 7.0

    # Verify preset-level accent_ink & caption background laws
    assert STYLE_PRESETS["institutional_dark"]["caption_style"]["background"] is None
    assert STYLE_PRESETS["swiss_paper"]["caption_style"]["background"] == "#FFFFFF"
    assert STYLE_PRESETS["swiss_paper"]["caption_style"]["background_mode"] == "pill"
    assert STYLE_PRESETS["kinetic_anime"]["caption_style"]["background"] is None
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["background"] == "#141413"
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["color"] == "#FFFDF7"


def test_legacy_style_none_preserves_zero_digest_drift_and_loads_900_font():
    settings_legacy = VersionSettings(width=1920, height=1080, background="#000000")
    dumped = settings_legacy.model_dump(mode="json")
    assert "style" not in dumped

    content = CompositionContent(
        settings=settings_legacy,
        timeline=Timeline(
            tracks=[
                Track(
                    track_id="trk_mg_main",
                    kind="visual",
                    role="main",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_hook",
                            range=TimeRange(start=0, end=270000),
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_hook",
                                block_id="statement_hook",
                                props={"headline": "Legacy draft stays byte-identical"},
                                layout=BOX,
                                fit="cover",
                            ),
                        )
                    ],
                )
            ]
        ),
    )
    digest_before = content_digest_of(content)
    # Re-validating from serialized JSON keeps identical digest
    reloaded = CompositionContent.model_validate(content.model_dump(mode="json"))
    assert content_digest_of(reloaded) == digest_before
    assert "style" not in reloaded.settings.model_dump(mode="json")

    spec = compile_video_spec(
        content,
        {},
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest=digest_before,
    )
    assert "style" not in spec
    # Motion blocks load weights 400, 700, and 900 (NotoSansSC-Black.otf)
    noto_weights = {f["weight"] for f in spec["fonts"] if f["family"] == "Noto Sans SC"}
    assert noto_weights == {400, 700, 900}

    # Validate compiled video-spec against Zod schema in @repurposer/video-spec
    styled_content, _ = apply_composition_style(content, preset_id="vox_editorial")
    styled_spec = compile_video_spec(
        styled_content,
        {},
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest=content_digest_of(styled_content),
    )
    assert styled_spec["style"]["preset_id"] == "vox_editorial"
    assert styled_spec["style"]["heading_weight"] == 900

    zod_check = """
import { readFileSync } from "node:fs";
import { videoSpecSchema } from "./src/schema.ts";
const { legacySpec, styledSpec } = JSON.parse(readFileSync(0, "utf8"));
const a = videoSpecSchema.parse(legacySpec);
const b = videoSpecSchema.parse(styledSpec);
process.stdout.write(JSON.stringify({ legacyHasStyle: "style" in a && a.style !== undefined, styledPreset: b.style?.preset_id }));
"""
    checked = _node_eval_ts(zod_check, {"legacySpec": spec, "styledSpec": styled_spec})
    assert checked == {"legacyHasStyle": False, "styledPreset": "vox_editorial"}


def test_catalog_prompt_index_exposes_style_presets():
    index = catalog_prompt_index()
    ids = [item["id"] for item in index["style_presets"]]
    assert ids == ["institutional_dark", "swiss_paper", "vox_editorial", "kinetic_anime"]
    for item in index["style_presets"]:
        assert item["bgm_mood"]
        assert len(item["sfx_palette"]) >= 5


def test_set_composition_style_adapts_only_unreadable_unbacked_titles():
    audio_id = uuid4()
    audio_digest = "f" * 64
    white_heading = Clip(
        clip_id="clp_white_heading",
        range=TimeRange(start=0, end=180000),
        object=TextObject(
            kind="text",
            object_id="obj_white_heading",
            text="Hero Title",
            layout=LayoutBox(x=160, y=420, width=1600, height=140),
            style=TextStyle(font_size=64, color="#F8FAFC", background=None, weight=700, align="center"),
            caption=None,
        ),
    )
    white_sub = Clip(
        clip_id="clp_white_sub",
        range=TimeRange(start=0, end=180000),
        object=TextObject(
            kind="text",
            object_id="obj_white_sub",
            text="Supporting line",
            layout=LayoutBox(x=160, y=580, width=1600, height=80),
            style=TextStyle(font_size=32, color="#F8FAFC", background=None, weight=500, align="center"),
            caption=None,
        ),
    )
    readable_navy = Clip(
        clip_id="clp_readable_navy",
        range=TimeRange(start=0, end=180000),
        object=TextObject(
            kind="text",
            object_id="obj_readable_navy",
            text="Already readable on cream",
            layout=LayoutBox(x=160, y=100, width=1600, height=80),
            style=TextStyle(font_size=36, color="#123456", background=None, weight=700, align="left"),
            caption=None,
        ),
    )
    pill_tag = Clip(
        clip_id="clp_pill_tag",
        range=TimeRange(start=0, end=180000),
        object=TextObject(
            kind="text",
            object_id="obj_pill_tag",
            text="CHAPTER 01",
            layout=LayoutBox(x=160, y=900, width=800, height=100),
            style=TextStyle(
                font_size=32,
                color="#F8FAFC",
                background="#0F172A",
                background_mode="pill",
                background_opacity=0.86,
                background_padding=(22.0, 10.0),
                background_radius=6.0,
                weight=700,
                align="left",
            ),
            caption=None,
        ),
    )
    independent_cap = Clip(
        clip_id="clp_ind_cap",
        range=TimeRange(start=0, end=180000),
        object=TextObject(
            kind="text",
            object_id="obj_ind_cap",
            text="Manual white caption stays untouched",
            layout=LayoutBox(x=160, y=920, width=1600, height=110),
            style=TextStyle(font_size=42, color="#F8FAFC", background=None, weight=700, align="center"),
            caption=SourceCaptionDerivation(
                snapshot_id=audio_id,
                snapshot_digest=audio_digest,
                sentence_id="s1",
                source_range=TimeRange(start=0, end=180000),
                source_text_digest=speech_text_digest("Original"),
                state="independent",
            ),
        ),
    )
    audio_clip = Clip(
        clip_id="clp_vo",
        range=TimeRange(start=0, end=180000),
        source=ClipSource(
            snapshot_id=audio_id,
            snapshot_digest=audio_digest,
            source_range=TimeRange(start=0, end=180000),
        ),
        object=AudioObject(kind="audio", object_id="obj_vo", gain_db=-2.0),
    )

    dark_content = CompositionContent(
        settings=VersionSettings(
            width=1920,
            height=1080,
            background="#0A0F16",
            style=CompositionStyle(preset_id="institutional_dark"),
        ),
        sources=[SourceBinding(snapshot_id=audio_id, snapshot_digest=audio_digest)],
        timeline=Timeline(
            tracks=[
                Track(track_id="trk_t1", kind="visual", role="title", order=0, clips=[white_heading]),
                Track(track_id="trk_t2", kind="visual", role="title", order=1, clips=[white_sub]),
                Track(track_id="trk_t3", kind="visual", role="title", order=2, clips=[readable_navy]),
                Track(track_id="trk_t4", kind="visual", role="title", order=3, clips=[pill_tag]),
                Track(track_id="trk_cap", kind="visual", role="caption", order=4, clips=[independent_cap]),
                Track(track_id="trk_audio", kind="audio", role="dialogue", order=0, clips=[audio_clip]),
            ]
        ),
    )

    # Dark -> Light (vox_editorial #F4EFE2): only the two unbacked low-contrast white titles adapt!
    light_content, light_summary = apply_composition_style(dark_content, preset_id="vox_editorial")
    assert light_summary["title_texts_contrast_adapted"] == 2
    assert light_summary["independent_captions_preserved"] == 1
    light_clips = {c.clip_id: c for t in light_content.timeline.tracks for c in t.clips}
    assert light_clips["clp_white_heading"].object.style.color == "#141413"
    assert light_clips["clp_white_sub"].object.style.color == "#3E3D39"
    # Readable unbacked title, pill-backed title, independent caption, and audio stay 100% untouched!
    assert light_clips["clp_readable_navy"].model_dump(mode="json") == readable_navy.model_dump(mode="json")
    assert light_clips["clp_pill_tag"].model_dump(mode="json") == pill_tag.model_dump(mode="json")
    assert light_clips["clp_ind_cap"].model_dump(mode="json") == independent_cap.model_dump(mode="json")
    assert light_clips["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")

    # Light -> Dark (institutional_dark #0A0F16): now the 3 dark unbacked titles auto-adapt to light ink!
    back_dark, dark_summary = apply_composition_style(light_content, preset_id="institutional_dark")
    assert dark_summary["title_texts_contrast_adapted"] == 3
    dark_clips = {c.clip_id: c for t in back_dark.timeline.tracks for c in t.clips}
    assert dark_clips["clp_white_heading"].object.style.color == "#F4F7FA"
    assert dark_clips["clp_white_sub"].object.style.color == "#B8C7D4"
    assert dark_clips["clp_readable_navy"].object.style.color == "#F4F7FA"
    assert dark_clips["clp_pill_tag"].model_dump(mode="json") == pill_tag.model_dump(mode="json")
    assert dark_clips["clp_ind_cap"].model_dump(mode="json") == independent_cap.model_dump(mode="json")
    assert dark_clips["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")


"""Layer 0 pure contracts: 24 TextStyle presets, bilingual cinema, caption defaults, and Py<->TS parity."""

from __future__ import annotations
import pytest

import json


import subprocess


from pathlib import Path


from types import SimpleNamespace


from uuid import UUID, uuid4


import pytest


from app.chat.editor import (
    ClipArgs,
    EditTextArgs,
    InsertTextArgs,
    InspectTimelineArgs,
    edit_clip,
    execute_editor,
)


from app.chat.prompts import assemble_video_round


from app.editing.alignment import NarrationPayload, NarrationSentence, NarrationWord


from app.editing.catalog import catalog_prompt_index


from app.editing.narration_audio import narration_audio_ops


from app.editing.presets import expand_preset


from app.editing.revisions import RevisionInputError, edit_text


from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    Easing,
    Keyframe,
    LayoutBox,
    Scene,
    SourceBinding,
    SourceCaptionDerivation,
    SpeechObject,
    TextObject,
    TextShadow,
    TextStroke,
    TextStyle,
    TimeRange,
    Timeline,
    Track,
    Transform,
    VersionSettings,
    speech_text_digest,
)


from app.editing.source_captions import source_caption_ops


from app.editing.source_selection import SourceSentence


from app.editing.store import (
    apply_composition_edits,
    content_digest_of,
    content_of,
    get_video_version,
)


from app.editing.styles import STYLE_PRESETS, CompositionStyle


from app.editing.text_presets import TEXT_STYLE_PRESETS


from app.editing.video_spec import compile_video_spec


from app.models.tables import (
    Conversation,
    Message,
    NarrationAlignment,
    Project,
    SourceSnapshot,
)


from app.tools.project_context import load_project_context


from test.support.db_helpers import _project, _user


REPO_ROOT = Path(__file__).resolve().parents[4]


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
def test_python_and_ts_24_text_presets_and_style_captions_zero_drift():
    ts_script = """
import { readFileSync } from "node:fs";
import { TEXT_STYLE_PRESETS } from "../video-remotion/src/engine/textPresets.ts";
import { STYLE_PRESETS } from "../video-remotion/src/engine/styles.ts";
readFileSync(0, "utf8");
const styleCaptions = Object.fromEntries(
  Object.entries(STYLE_PRESETS).map(([k, v]) => [k, v.caption_style]),
);
process.stdout.write(JSON.stringify({ textPresets: TEXT_STYLE_PRESETS, styleCaptions }));
"""
    ts_out = _node_eval_ts(ts_script, {})

    expected_ids = [
        "clean_broadcast",
        "cinema_glass",
        "minimal_light",
        "vox_label",
        "vox_highlighter",
        "creator_pop",
        "kinetic_impact",
        "editorial_callout",
        "lower_third_tag",
        "karaoke_focus",
        "bilingual_cinema",
        "apple_minimal_dark",
        "apple_minimal_light",
        "chrome_cinema",
        "neon_pulse",
        "frosted_badge",
        "editorial_serif",
        "brutal_stamp",
        "terminal_mono",
        "soft_gradient_pill",
        "outline_ghost",
        "split_accent_hook",
        "news_ticker_bar",
        "subtitle_netflix_clean",
    ]
    assert list(TEXT_STYLE_PRESETS.keys()) == expected_ids
    assert ts_out["textPresets"] == TEXT_STYLE_PRESETS

    py_style_captions = {k: v["caption_style"] for k, v in STYLE_PRESETS.items()}
    assert ts_out["styleCaptions"] == py_style_captions
    assert STYLE_PRESETS["vox_editorial"]["caption_style"] == TEXT_STYLE_PRESETS["vox_label"]
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["background_mode"] == "line"
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["background"] == "#141413"
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["background_padding"] == [20.0, 8.0]
    assert STYLE_PRESETS["vox_editorial"]["caption_style"]["background_radius"] == 4.0
    assert STYLE_PRESETS["institutional_dark"]["caption_style"] == TEXT_STYLE_PRESETS["clean_broadcast"]
    assert STYLE_PRESETS["swiss_paper"]["caption_style"] == TEXT_STYLE_PRESETS["minimal_light"]
    assert STYLE_PRESETS["kinetic_anime"]["caption_style"] == TEXT_STYLE_PRESETS["kinetic_impact"]


def test_legacy_text_style_zero_digest_drift_and_zod_validation():
    legacy_style = TextStyle(
        font_size=42,
        color="#FFFFFF",
        background=None,
        weight=600,
        align="center",
        line_height=1.3,
    )
    dumped = legacy_style.model_dump(mode="json")
    for omitted_key in (
        "background_mode",
        "background_opacity",
        "background_padding",
        "background_radius",
        "border",
        "text_transform",
        "secondary_line_scale",
        "secondary_line_opacity",
    ):
        assert omitted_key not in dumped

    content = CompositionContent(
        settings=VersionSettings(width=1920, height=1080, background="#000000"),
        timeline=Timeline(
            tracks=[
                Track(
                    track_id="trk_cap",
                    kind="visual",
                    role="caption",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_legacy_txt",
                            range=TimeRange(start=0, end=180000),
                            object=TextObject(
                                kind="text",
                                object_id="obj_legacy_txt",
                                text="Legacy caption stays byte-identical",
                                layout=LayoutBox(x=160, y=900, width=1600, height=120),
                                style=legacy_style,
                            ),
                        )
                    ],
                )
            ]
        ),
    )
    digest_before = content_digest_of(content)
    reloaded = CompositionContent.model_validate(content.model_dump(mode="json"))
    assert content_digest_of(reloaded) == digest_before

    spec = compile_video_spec(
        content,
        {},
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest=digest_before,
    )
    compiled_style = spec["tracks"][0]["clips"][0]["object"]["style"]
    assert "background_mode" not in compiled_style

    zod_script = """
import { readFileSync } from "node:fs";
import { videoSpecSchema } from "./src/schema.ts";
const { spec } = JSON.parse(readFileSync(0, "utf8"));
const parsed = videoSpecSchema.parse(spec);
const st = parsed.tracks[0].clips[0].object.style;
process.stdout.write(JSON.stringify({
  background_mode: st.background_mode,
  background_opacity: st.background_opacity,
  background_padding: st.background_padding,
  background_radius: st.background_radius,
  border: st.border,
  text_transform: st.text_transform,
  secondary_line_scale: st.secondary_line_scale,
  secondary_line_opacity: st.secondary_line_opacity,
}));
"""
    parsed = _node_eval_ts(zod_script, {"spec": spec})
    assert parsed == {
        "background_mode": "box",
        "background_opacity": 1,
        "background_padding": [0, 0],
        "background_radius": 0,
        "border": None,
        "text_transform": "none",
        "secondary_line_scale": 1,
        "secondary_line_opacity": 1,
    }


def test_caption_creation_defaults_inherit_style_or_clean_broadcast_without_black_box():
    audio_id = uuid4()
    audio_digest = "b" * 64
    alignment_id = uuid4()
    alignment_digest = "c" * 64

    def _base_content(style: CompositionStyle | None) -> CompositionContent:
        return CompositionContent(
            settings=VersionSettings(width=1920, height=1080, background="#0A0F16", style=style),
            sources=[SourceBinding(snapshot_id=audio_id, snapshot_digest=audio_digest)],
            scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=270000), intent="demo")],
            timeline=Timeline(
                tracks=[
                    Track(
                        track_id="trk_speech",
                        kind="audio",
                        role="dialogue",
                        order=0,
                        clips=[
                            Clip(
                                clip_id="clp_speech",
                                range=TimeRange(start=0, end=180000),
                                scene_id="scn_1",
                                source=ClipSource(
                                    snapshot_id=audio_id,
                                    snapshot_digest=audio_digest,
                                    source_range=TimeRange(start=0, end=180000),
                                ),
                                object=SpeechObject(
                                    kind="speech",
                                    object_id="obj_speech",
                                    text="Hello Rookie Cut.",
                                    provider=None,
                                    model=None,
                                    voice_id=None,
                                    alignment={
                                        "alignment_id": alignment_id,
                                        "content_digest": alignment_digest,
                                        "audio_snapshot_id": audio_id,
                                        "audio_digest": audio_digest,
                                    },
                                ),
                            )
                        ],
                    ),
                    Track(track_id="trk_cap", kind="visual", role="caption", order=0, clips=[]),
                ]
            ),
        )

    payload = NarrationPayload(
        source_timebase=90000,
        duration_ticks=180000,
        sentences=[
            NarrationSentence(
                sentence_id="s1",
                text="Hello Rookie Cut.",
                text_start=0,
                text_end=17,
                start_tick=0,
                end_tick=180000,
                match=1.0,
                status="aligned",
                words=[
                    NarrationWord(word_id="w1", text="Hello", text_start=0, text_end=5, start_tick=0, end_tick=60000, timing="anchored"),
                    NarrationWord(word_id="w2", text="Rookie", text_start=6, text_end=12, start_tick=60000, end_tick=120000, timing="anchored"),
                    NarrationWord(word_id="w3", text="Cut.", text_start=13, text_end=17, start_tick=120000, end_tick=180000, timing="anchored"),
                ],
            )
        ],
    )
    alignment_ref = {
        "alignment_id": alignment_id,
        "content_digest": alignment_digest,
        "audio_snapshot_id": audio_id,
        "audio_digest": audio_digest,
    }

    ops_none = expand_preset(
        "caption-phrases",
        _base_content(None),
        {"track_id": "trk_cap", "payload": payload, "alignment": alignment_ref, "cue": "sentence"},
    )
    cap_style_none = ops_none[0].clip.object.style
    assert cap_style_none.background is None
    assert cap_style_none.color == "#F8FAFC"
    assert cap_style_none.weight == 700
    assert cap_style_none.stroke == TextStroke(color="#0A0F16", width=3.0)
    assert cap_style_none.shadow == TextShadow(color="#0A0F16", offset=(0.0, 2.0), blur=8.0)

    ops_vox = expand_preset(
        "caption-phrases",
        _base_content(CompositionStyle(preset_id="vox_editorial")),
        {"track_id": "trk_cap", "payload": payload, "alignment": alignment_ref, "cue": "sentence"},
    )
    cap_style_vox = ops_vox[0].clip.object.style
    assert cap_style_vox.background == "#141413"
    assert cap_style_vox.background_mode == "line"
    assert cap_style_vox.background_padding == (20.0, 8.0)
    assert cap_style_vox.background_radius == 4.0
    assert cap_style_vox.color == "#FFFDF7"

    src_ops_none = source_caption_ops(
        _base_content(None),
        scene_id="scn_1",
        snapshot_id=audio_id,
        snapshot_digest=audio_digest,
        source_range=TimeRange(start=0, end=180000),
        sentences=(SourceSentence(sentence_id="s1", text="Real ASR line", start=0.0, end=2.0),),
    )
    src_cap_style = src_ops_none[1].clip.object.style
    assert src_cap_style.background is None
    assert src_cap_style.stroke == TextStroke(color="#0A0F16", width=3.0)
    assert src_cap_style.shadow == TextShadow(color="#0A0F16", offset=(0.0, 2.0), blur=8.0)

    src_ops_vox = source_caption_ops(
        _base_content(CompositionStyle(preset_id="vox_editorial")),
        scene_id="scn_1",
        snapshot_id=audio_id,
        snapshot_digest=audio_digest,
        source_range=TimeRange(start=0, end=180000),
        sentences=(SourceSentence(sentence_id="s1", text="Vox ASR line", start=0.0, end=2.0),),
    )
    assert src_ops_vox[1].clip.object.style.background_mode == "line"
    assert src_ops_vox[1].clip.object.style.background == "#141413"

    nar_alignment = SimpleNamespace(
        id=alignment_id,
        audio_snapshot_id=audio_id,
        audio_digest=audio_digest,
        status="READY",
        content_digest=alignment_digest,
        algorithm="faster-whisper-script-v1",
        payload=payload.model_dump(mode="json"),
    )
    nar_base = CompositionContent(
        settings=VersionSettings(
            width=1920, height=1080, background="#0A0F16",
            style=CompositionStyle(preset_id="swiss_paper"),
        ),
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=270000), intent="demo")],
        timeline=Timeline(tracks=[Track(track_id="trk_main", kind="visual", role="main", order=0, clips=[])]),
    )
    nar_ops = narration_audio_ops(
        nar_base,
        scene_id="scn_1",
        snapshot_id=audio_id,
        snapshot_digest=audio_digest,
        alignment=nar_alignment,
    )
    nar_cap_clip = next(op.clip for op in nar_ops if op.op == "add_clip" and op.clip.object.kind == "text")
    assert nar_cap_clip.object.style.color == "#111820"
    assert nar_cap_clip.object.style.stroke == TextStroke(color="#F6F5F0", width=4.0)


def test_catalog_prompt_index_exposes_all_24_text_style_presets():
    index = catalog_prompt_index()
    ids = [item["id"] for item in index["text_style_presets"]]
    assert len(ids) == 24
    assert ids == list(TEXT_STYLE_PRESETS.keys())
    for item in index["text_style_presets"]:
        assert item["name"]
        assert item["use_for"]
        assert item["visual_signature"]


@pytest.mark.parity
def test_bilingual_cinema_theme_awareness_and_py_ts_resolver_parity():
    from app.editing.edits import apply_ops
    from app.editing.revisions import insert_text_ops
    from app.editing.styles import resolve_style_tokens
    from app.editing.text_presets import resolve_text_preset_token

    def _make_content(style: CompositionStyle | None) -> CompositionContent:
        bg = resolve_style_tokens(style)["canvas_bg"] if style else "#0A0F16"
        return CompositionContent(
            settings=VersionSettings(width=1920, height=1080, background=bg, style=style),
            timeline=Timeline(tracks=[Track(track_id="trk_main", kind="visual", role="main", order=0, clips=[])]),
        )

    # 1. insert_text with bilingual_cinema on light themes -> crisp tight dark-ink pill (zero edge bleed)
    for preset_id in ("vox_editorial", "swiss_paper"):
        base = _make_content(CompositionStyle(preset_id=preset_id))
        ops, _ = insert_text_ops(
            base,
            text="双语字幕清晰可读\nCrisp bilingual captions on light paper",
            start=0,
            end=180000,
            clip_id="clp_bi",
            object_id="obj_bi",
            role="caption",
            preset_id="bilingual_cinema",
        )
        updated = apply_ops(base, ops, {})
        st = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bi").object.style
        assert st.color == "#F8FAFC"
        assert st.background == "#111318"
        assert st.background_mode == "pill"
        assert st.background_opacity == 0.82
        assert st.background_padding == (20.0, 10.0)
        assert st.background_radius == 10.0
        assert st.stroke is None
        assert st.shadow is None
        assert st.weight == 700
        assert st.secondary_line_scale == 0.74
        assert st.secondary_line_opacity == 0.88

        # edit_text produces the exact same light-theme bilingual_cinema tight pill style
        re_styled, _ = edit_text(
            updated, scope="clip", clip_id="clp_bi", preset_id="clean_broadcast"
        )
        re_bi, _ = edit_text(
            re_styled, scope="clip", clip_id="clp_bi", preset_id="bilingual_cinema"
        )
        st2 = next(c for t in re_bi.timeline.tracks for c in t.clips if c.clip_id == "clp_bi").object.style
        assert st2.color == "#F8FAFC"
        assert st2.background == "#111318"
        assert st2.background_mode == "pill"
        assert st2.background_opacity == 0.82
        assert st2.background_padding == (20.0, 10.0)
        assert st2.background_radius == 10.0
        assert st2.stroke is None
        assert st2.shadow is None

    # 2. Dark theme and style=None keep white ink + tight dark-ink pill + subtle shadow
    for style in (CompositionStyle(preset_id="institutional_dark"), None):
        base = _make_content(style)
        ops, _ = insert_text_ops(
            base,
            text="双语字幕\nBilingual on dark",
            start=0,
            end=180000,
            clip_id="clp_bi_dark",
            object_id="obj_bi_dark",
            role="caption",
            preset_id="bilingual_cinema",
        )
        updated = apply_ops(base, ops, {})
        st = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bi_dark").object.style
        assert st.color == "#FFFFFF"
        assert st.background == "#111318"
        assert st.background_mode == "pill"
        assert st.background_opacity == 0.76
        assert st.background_padding == (20.0, 10.0)
        assert st.background_radius == 10.0
        assert st.stroke is None
        assert st.shadow == TextShadow(color="#0A0F16", offset=(0.0, 1.0), blur=4.0)
        assert st.secondary_line_scale == 0.74
        assert st.secondary_line_opacity == 0.88

    # 3. Guardrail: setting background on a caption/box clip without explicit background_mode='box' auto-upgrades to tight pill
    base_dark = _make_content(CompositionStyle(preset_id="institutional_dark"))
    ins_ops, _ = insert_text_ops(
        base_dark,
        text="Clean caption with auto-upgraded pill",
        start=0,
        end=180000,
        clip_id="clp_guard_ins",
        object_id="obj_guard_ins",
        role="caption",
        preset_id="clean_broadcast",
        background="#000000",
    )
    ins_updated = apply_ops(base_dark, ins_ops, {})
    ins_style = next(c for t in ins_updated.timeline.tracks for c in t.clips if c.clip_id == "clp_guard_ins").object.style
    assert ins_style.background == "#000000"
    assert ins_style.background_mode == "pill"
    assert ins_style.background_padding == (20.0, 10.0)
    assert ins_style.background_radius == 10.0
    assert ins_style.background_opacity == 0.78

    # edit_text on a clean_broadcast clip (which has background_mode='box', background=None) upgrades to tight pill
    raw_ops, _ = insert_text_ops(
        base_dark,
        text="Caption edited to add dark backing",
        start=0,
        end=180000,
        clip_id="clp_guard_edit",
        object_id="obj_guard_edit",
        role="caption",
        preset_id="clean_broadcast",
    )
    raw_updated = apply_ops(base_dark, raw_ops, {})
    edited_pill, _ = edit_text(raw_updated, scope="clip", clip_id="clp_guard_edit", background="#111318")
    ed_style = next(c for t in edited_pill.timeline.tracks for c in t.clips if c.clip_id == "clp_guard_edit").object.style
    assert ed_style.background == "#111318"
    assert ed_style.background_mode == "pill"
    assert ed_style.background_padding == (20.0, 10.0)
    assert ed_style.background_radius == 10.0
    assert ed_style.background_opacity == 0.78

    # Explicit background_mode='box' is still respected when deliberately requested
    edited_box, _ = edit_text(
        raw_updated, scope="clip", clip_id="clp_guard_edit", background="#111318", background_mode="box"
    )
    box_style = next(c for t in edited_box.timeline.tracks for c in t.clips if c.clip_id == "clp_guard_edit").object.style
    assert box_style.background_mode == "box"

    # 4. Verify Python <-> TS zero drift for resolve_text_preset_token across styles
    cases = [
        ("bilingual_cinema", None),
        ("bilingual_cinema", resolve_style_tokens(CompositionStyle(preset_id="vox_editorial"))),
        ("bilingual_cinema", resolve_style_tokens(CompositionStyle(preset_id="swiss_paper"))),
        ("bilingual_cinema", resolve_style_tokens(CompositionStyle(preset_id="institutional_dark"))),
        ("lower_third_tag", resolve_style_tokens(CompositionStyle(preset_id="vox_editorial"))),
    ]
    py_resolved = [resolve_text_preset_token(pid, tok) for pid, tok in cases]
    ts_resolved = _node_eval_ts(
        """
import { readFileSync } from "node:fs";
import { resolveTextPresetToken } from "../video-remotion/src/engine/textPresets.ts";
const { cases } = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify({ results: cases.map(([id, tok]) => resolveTextPresetToken(id, tok)) }));
""",
        {"cases": cases},
    )["results"]
    assert ts_resolved == py_resolved


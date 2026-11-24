"""Core deterministic contracts for the 11-preset text & caption system."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.chat.editor import ApplyTextStyleArgs, edit_clip
from app.editing.alignment import NarrationPayload, NarrationSentence, NarrationWord
from app.editing.catalog import catalog_prompt_index
from app.editing.edits import apply_ops
from app.editing.narration_audio import narration_audio_ops
from app.editing.presets import expand_preset
from app.editing.revisions import RevisionInputError, apply_text_style
from app.editing.schemas import (
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    LayoutBox,
    Scene,
    SourceBinding,
    SourceCaptionDerivation,
    SpeechObject,
    TextBorder,
    TextObject,
    TextShadow,
    TextStroke,
    TextStyle,
    TimeRange,
    Timeline,
    Track,
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
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
from app.models.tables import Conversation, Message, Project, SourceSnapshot
from test.core.test_compositions import _project, _user

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


def test_python_and_ts_11_text_presets_and_style_captions_zero_drift():
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
    ]
    assert list(TEXT_STYLE_PRESETS.keys()) == expected_ids
    assert ts_out["textPresets"] == TEXT_STYLE_PRESETS

    py_style_captions = {k: v["caption_style"] for k, v in STYLE_PRESETS.items()}
    assert ts_out["styleCaptions"] == py_style_captions
    # Vox editorial uses tight per-line sticker chips (vox_label), never a full-width black box
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

    # 1. caption-phrases with style=None falls back to clean_broadcast (NO #000000 box!)
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

    # 2. caption-phrases with vox_editorial inherits vox_label (tight line chips)
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

    # 3. source_caption_ops with style=None uses clean_broadcast (not bare unstroked white)
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

    # 4. source_caption_ops with vox_editorial inherits vox_label
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

    # 5. narration_audio_ops also inherits style / clean_broadcast
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


@pytest.mark.asyncio
async def test_apply_text_style_atomic_commit_protection_bilingual_and_karaoke(database):
    owner = await _user(database)
    project_id = await _project(database, owner, title="Text Caption System Test")
    audio_id = uuid4()
    audio_digest = "e" * 64

    async with database() as db:
        audio_snap = SourceSnapshot(
            id=audio_id,
            owner_id=owner,
            origin_project_id=project_id,
            kind="audio",
            digest=audio_digest,
            storage_key="voice.wav",
            duration_ticks=540000,
        )
        chat = Conversation(user_id=owner, project_id=project_id)
        db.add_all([audio_snap, chat])
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Style captions", turn_state="in_flight")
        db.add(opening)
        await db.flush()

        derived_en = Clip(
            clip_id="clp_cap_en",
            range=TimeRange(start=0, end=180000),
            object=TextObject(
                kind="text",
                object_id="obj_cap_en",
                text="Ship faster every single week",
                layout=LayoutBox(x=160, y=880, width=1600, height=130),
                style=TextStyle(font_size=46, color="#FFFFFF", background=None, weight=700, align="center"),
                caption=SourceCaptionDerivation(
                    snapshot_id=audio_id,
                    snapshot_digest=audio_digest,
                    sentence_id="s1",
                    source_range=TimeRange(start=0, end=180000),
                    source_text_digest=speech_text_digest("Ship faster every single week"),
                    state="derived",
                ),
            ),
        )
        derived_zh = Clip(
            clip_id="clp_cap_zh",
            range=TimeRange(start=180000, end=360000),
            object=TextObject(
                kind="text",
                object_id="obj_cap_zh",
                text="一行指令搞定全片剪辑",
                layout=LayoutBox(x=160, y=880, width=1600, height=130),
                style=TextStyle(font_size=46, color="#FFFFFF", background=None, weight=700, align="center"),
                caption=SourceCaptionDerivation(
                    snapshot_id=audio_id,
                    snapshot_digest=audio_digest,
                    sentence_id="s2",
                    source_range=TimeRange(start=180000, end=360000),
                    source_text_digest=speech_text_digest("一行指令搞定全片剪辑"),
                    state="derived",
                ),
            ),
        )
        independent_cap = Clip(
            clip_id="clp_cap_ind",
            range=TimeRange(start=360000, end=540000),
            object=TextObject(
                kind="text",
                object_id="obj_cap_ind",
                text="User hand-edited caption",
                layout=LayoutBox(x=160, y=880, width=1600, height=130),
                style=TextStyle(font_size=44, color="#FF9900", background="#222222", weight=800, align="center"),
                caption=SourceCaptionDerivation(
                    snapshot_id=audio_id,
                    snapshot_digest=audio_digest,
                    sentence_id="s3",
                    source_range=TimeRange(start=360000, end=540000),
                    source_text_digest=speech_text_digest("Original"),
                    state="independent",
                ),
            ),
        )
        bilingual_title = Clip(
            clip_id="clp_bilingual",
            range=TimeRange(start=0, end=180000),
            object=TextObject(
                kind="text",
                object_id="obj_bilingual",
                text="让每一帧都像大片一样干净\nMake every single frame look cinematic",
                layout=LayoutBox(x=160, y=820, width=1600, height=180),
                style=TextStyle(font_size=48, color="#FFFFFF", background=None, weight=700, align="center"),
                caption=None,
            ),
        )
        audio_clip = Clip(
            clip_id="clp_vo",
            range=TimeRange(start=0, end=540000),
            source=ClipSource(
                snapshot_id=audio_id,
                snapshot_digest=audio_digest,
                source_range=TimeRange(start=0, end=540000),
            ),
            object=AudioObject(kind="audio", object_id="obj_vo", gain_db=-1.5),
        )

        initial = CompositionContent(
            settings=VersionSettings(width=1920, height=1080, background="#0A0F16"),
            sources=[SourceBinding(snapshot_id=audio_id, snapshot_digest=audio_digest)],
            timeline=Timeline(
                tracks=[
                    Track(track_id="trk_title", kind="visual", role="title", order=0, clips=[bilingual_title]),
                    Track(
                        track_id="trk_caption",
                        kind="visual",
                        role="caption",
                        order=1,
                        clips=[derived_en, derived_zh, independent_cap],
                    ),
                    Track(track_id="trk_audio", kind="audio", role="dialogue", order=0, clips=[audio_clip]),
                ]
            ),
        )
        comp, v1, _ = await apply_composition_edits(
            db, owner_id=owner, origin_project_id=project_id, content=initial
        )
        project = await db.get(Project, project_id)
        base_v1 = {
            "composition_id": str(comp.id),
            "composition_version_id": str(v1.id),
            "content_digest": v1.content_digest,
        }

        # 1. Apply karaoke_focus to all_derived_captions -> updates EN (word parts) & ZH (grapheme chunks),
        # protects independent caption, non-caption text, and audio!
        res_k = await edit_clip(
            db,
            name="apply_text_style",
            project=project,
            opening_id=opening.id,
            conversation_id=chat.id,
            call_id="call_karaoke",
            base=base_v1,
            args=ApplyTextStyleArgs(scope="all_derived_captions", preset_id="karaoke_focus"),
        )
        assert res_k["text_style_summary"]["clips_updated"] == 2
        assert res_k["text_style_summary"]["independent_captions_preserved"] == 1
        assert res_k["text_style_summary"]["non_caption_text_preserved"] == 1
        assert res_k["text_style_summary"]["karaoke_clips_updated"] == 2

        _, v2 = await get_video_version(db, owner_id=owner, version_id=UUID(res_k["version_id"]))
        c2 = content_of(v2)
        clips_v2 = {c.clip_id: c for t in c2.timeline.tracks for c in t.clips}
        en_anims = clips_v2["clp_cap_en"].animations
        zh_anims = clips_v2["clp_cap_zh"].animations
        assert len([a for a in en_anims if a.property == "text.color"]) == 5
        assert len([a for a in en_anims if a.property == "transform.scale"]) == 5
        assert all(a.text_part and a.text_part.kind == "word" for a in en_anims)
        # Unspaced CJK falls back to compact 2-char grapheme chunks (10 chars -> 5 chunks)
        assert len([a for a in zh_anims if a.property == "text.color"]) == 5
        assert all(a.text_part and a.text_part.kind == "grapheme" for a in zh_anims)
        # Independent caption, non-caption title, and audio track strictly untouched
        assert clips_v2["clp_cap_ind"].model_dump(mode="json") == independent_cap.model_dump(mode="json")
        assert clips_v2["clp_bilingual"].model_dump(mode="json") == bilingual_title.model_dump(mode="json")
        assert clips_v2["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")

        # Validate compiled karaoke video-spec against Zod schema!
        spec_v2 = compile_video_spec(
            c2,
            {audio_id: {"kind": "audio", "digest": audio_digest, "storage_key": "voice.wav", "duration_ticks": 540000}},
            composition_id=comp.id,
            version_id=v2.id,
            content_digest=v2.content_digest,
        )
        zod_ok = _node_eval_ts(
            """
import { readFileSync } from "node:fs";
import { videoSpecSchema } from "./src/schema.ts";
const { spec } = JSON.parse(readFileSync(0, "utf8"));
const parsed = videoSpecSchema.parse(spec);
const enClip = parsed.tracks.find((t) => t.track_id === "trk_caption").clips.find((c) => c.clip_id === "clp_cap_en");
process.stdout.write(JSON.stringify({ animCount: enClip.animations.length, wordParts: enClip.object.parts.filter((p) => p.kind === "word").length }));
""",
            {"spec": spec_v2},
        )
        assert zod_ok == {"animCount": 10, "wordParts": 5}

        # 2. Switch derived captions away from karaoke_focus -> cinema_glass clears karaoke_* animations!
        base_v2 = {
            "composition_id": str(comp.id),
            "composition_version_id": str(v2.id),
            "content_digest": v2.content_digest,
        }
        res_glass = await edit_clip(
            db,
            name="apply_text_style",
            project=project,
            opening_id=opening.id,
            conversation_id=chat.id,
            call_id="call_glass",
            base=base_v2,
            args=ApplyTextStyleArgs(scope="all_derived_captions", preset_id="cinema_glass"),
        )
        assert res_glass["text_style_summary"]["karaoke_clips_cleared"] == 2
        _, v3 = await get_video_version(db, owner_id=owner, version_id=UUID(res_glass["version_id"]))
        c3 = content_of(v3)
        clips_v3 = {c.clip_id: c for t in c3.timeline.tracks for c in t.clips}
        assert clips_v3["clp_cap_en"].animations == []
        assert clips_v3["clp_cap_zh"].animations == []
        assert clips_v3["clp_cap_en"].object.style.background_mode == "pill"
        assert clips_v3["clp_cap_en"].object.style.background_opacity == 0.72
        assert clips_v3["clp_cap_en"].object.style.background_padding == (26.0, 10.0)
        assert clips_v3["clp_cap_en"].object.style.background_radius == 12.0
        assert clips_v3["clp_cap_ind"].model_dump(mode="json") == independent_cap.model_dump(mode="json")

        # 3. Apply bilingual_cinema to single clip (non-caption bilingual title) with optional glass pill overlay
        base_v3 = {
            "composition_id": str(comp.id),
            "composition_version_id": str(v3.id),
            "content_digest": v3.content_digest,
        }
        res_bi = await edit_clip(
            db,
            name="apply_text_style",
            project=project,
            opening_id=opening.id,
            conversation_id=chat.id,
            call_id="call_bilingual",
            base=base_v3,
            args=ApplyTextStyleArgs(
                scope="clip",
                clip_id="clp_bilingual",
                preset_id="bilingual_cinema",
                font_size=50,
            ),
        )
        assert res_bi["text_style_summary"]["clips_updated"] == 1
        _, v4 = await get_video_version(db, owner_id=owner, version_id=UUID(res_bi["version_id"]))
        c4 = content_of(v4)
        bi_style = next(c for t in c4.timeline.tracks for c in t.clips if c.clip_id == "clp_bilingual").object.style
        assert bi_style.secondary_line_scale == 0.72
        assert bi_style.secondary_line_opacity == 0.86
        assert bi_style.font_size == 50
        assert bi_style.stroke == TextStroke(color="#0A0F16", width=3.5)

        # 4. Audio track rejection guard
        with pytest.raises(RevisionInputError):
            apply_text_style(c4, scope="track", track_id="trk_audio", preset_id="vox_label")
        with pytest.raises(RevisionInputError):
            apply_text_style(c4, scope="clip", clip_id="clp_vo", preset_id="vox_label")


def test_catalog_prompt_index_exposes_all_11_text_style_presets():
    index = catalog_prompt_index()
    ids = [item["id"] for item in index["text_style_presets"]]
    assert len(ids) == 11
    assert ids == list(TEXT_STYLE_PRESETS.keys())
    for item in index["text_style_presets"]:
        assert item["name"]
        assert item["use_for"]
        assert item["visual_signature"]

"""Core deterministic contracts for the 11-preset text & caption system, symmetric insert_text/edit_text tools, and observability."""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_insert_text_direct_and_from_audio_clip_modes(database):
    owner = await _user(database)
    project_id = await _project(database, owner, title="Insert Text Symmetry Test")
    vo_id = uuid4()
    vo_digest = "1" * 64
    unaligned_id = uuid4()
    unaligned_digest = "2" * 64
    alignment_id = uuid4()
    alignment_digest = "3" * 64

    payload = NarrationPayload(
        source_timebase=90000,
        duration_ticks=270000,
        sentences=[
            NarrationSentence(
                sentence_id="s1",
                text="Ship faster every week",
                text_start=0,
                text_end=22,
                start_tick=0,
                end_tick=135000,
                match=1.0,
                status="aligned",
                words=[
                    NarrationWord(word_id="w1", text="Ship", text_start=0, text_end=4, start_tick=0, end_tick=27000, timing="anchored"),
                    NarrationWord(word_id="w2", text="faster", text_start=5, text_end=11, start_tick=27000, end_tick=63000, timing="anchored"),
                    NarrationWord(word_id="w3", text="every", text_start=12, text_end=17, start_tick=63000, end_tick=99000, timing="anchored"),
                    NarrationWord(word_id="w4", text="week", text_start=18, text_end=22, start_tick=99000, end_tick=135000, timing="anchored"),
                ],
            ),
            NarrationSentence(
                sentence_id="s2",
                text="一行指令搞定全片",
                text_start=23,
                text_end=31,
                start_tick=135000,
                end_tick=270000,
                match=1.0,
                status="aligned",
                words=[
                    NarrationWord(word_id="w5", text="一行", text_start=23, text_end=25, start_tick=135000, end_tick=168000, timing="anchored"),
                    NarrationWord(word_id="w6", text="指令", text_start=25, text_end=27, start_tick=168000, end_tick=201000, timing="anchored"),
                    NarrationWord(word_id="w7", text="搞定", text_start=27, text_end=29, start_tick=201000, end_tick=234000, timing="anchored"),
                    NarrationWord(word_id="w8", text="全片", text_start=29, text_end=31, start_tick=234000, end_tick=270000, timing="anchored"),
                ],
            ),
        ],
    )

    async with database() as db:
        vo_snap = SourceSnapshot(
            id=vo_id, owner_id=owner, origin_project_id=project_id, kind="audio",
            digest=vo_digest, storage_key="vo.wav", duration_ticks=270000,
        )
        unaligned_snap = SourceSnapshot(
            id=unaligned_id, owner_id=owner, origin_project_id=project_id, kind="audio",
            digest=unaligned_digest, storage_key="bgm.wav", duration_ticks=270000,
        )
        alignment_row = NarrationAlignment(
            id=alignment_id,
            owner_id=owner,
            audio_snapshot_id=vo_id,
            text="Ship faster every week\n一行指令搞定全片",
            text_digest=speech_text_digest("Ship faster every week\n一行指令搞定全片"),
            audio_digest=vo_digest,
            algorithm="faster-whisper-script-v1",
            normalization_version="v1",
            provider="faster-whisper",
            model="large-v3",
            source_timebase=90000,
            timing_digest="4" * 64,
            content_digest=alignment_digest,
            payload=payload.model_dump(mode="json"),
            status="READY",
        )
        chat = Conversation(user_id=owner, project_id=project_id)
        db.add_all([vo_snap, unaligned_snap, chat])
        await db.flush()
        db.add(alignment_row)
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Add captions and titles", turn_state="in_flight")
        db.add(opening)
        await db.flush()

        initial = CompositionContent(
            settings=VersionSettings(
                width=1920, height=1080, background="#0A0F16",
                style=CompositionStyle(preset_id="institutional_dark"),
            ),
            sources=[
                SourceBinding(snapshot_id=vo_id, snapshot_digest=vo_digest),
                SourceBinding(snapshot_id=unaligned_id, snapshot_digest=unaligned_digest),
            ],
            scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=270000), intent="intro")],
            timeline=Timeline(
                tracks=[
                    Track(
                        track_id="trk_vo", kind="audio", role="dialogue", order=0,
                        clips=[
                            Clip(
                                clip_id="clp_vo",
                                range=TimeRange(start=0, end=270000),
                                scene_id="scn_1",
                                source=ClipSource(
                                    snapshot_id=vo_id,
                                    snapshot_digest=vo_digest,
                                    source_range=TimeRange(start=0, end=270000),
                                ),
                                object=AudioObject(kind="audio", object_id="obj_vo", gain_db=0.0),
                            )
                        ],
                    ),
                    Track(
                        track_id="trk_bgm", kind="audio", role="music", order=1,
                        clips=[
                            Clip(
                                clip_id="clp_bgm",
                                range=TimeRange(start=0, end=270000),
                                scene_id="scn_1",
                                source=ClipSource(
                                    snapshot_id=unaligned_id,
                                    snapshot_digest=unaligned_digest,
                                    source_range=TimeRange(start=0, end=270000),
                                ),
                                object=AudioObject(kind="audio", object_id="obj_bgm", gain_db=-24.0),
                            )
                        ],
                    ),
                ]
            ),
        )
        comp, v1, _ = await apply_composition_edits(
            db, owner_id=owner, origin_project_id=project_id, content=initial
        )
        project = await db.get(Project, project_id)

        def _ref(ver):
            return {
                "composition_id": str(comp.id),
                "composition_version_id": str(ver.id),
                "content_digest": ver.content_digest,
            }

        # 1. Direct insert_text: lower_third_tag defaults to bottom_left + left align + style accent border
        res1 = await edit_clip(
            db, name="insert_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ins_tag", base=_ref(v1),
            args=InsertTextArgs(
                text="Chapter 01 · Launch",
                start_seconds=0.0, end_seconds=2.5,
                role="title", preset_id="lower_third_tag",
            ),
        )
        assert res1["text_summary"]["position"] == "bottom_left"
        _, v2 = await get_video_version(db, owner_id=owner, version_id=UUID(res1["version_id"]))
        c2 = content_of(v2)
        tag_clip = next(c for t in c2.timeline.tracks for c in t.clips if c.clip_id == res1["text_summary"]["clip_ids"][0])
        assert tag_clip.object.style.align == "left"
        assert tag_clip.object.style.text_transform == "uppercase"
        assert tag_clip.object.style.border is not None
        assert tag_clip.object.style.border.color == "#14B8A6"  # institutional_dark accent
        assert tag_clip.object.layout.x < 200 and tag_clip.object.layout.y > 800

        # 2. Direct insert_text: bilingual caption placed on caption track above title track
        res2 = await edit_clip(
            db, name="insert_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ins_bi", base=_ref(v2),
            args=InsertTextArgs(
                text="让每一帧都干净\nMake every frame clean",
                start_seconds=0.0, end_seconds=1.5,
                role="caption", preset_id="bilingual_cinema",
            ),
        )
        _, v3 = await get_video_version(db, owner_id=owner, version_id=UUID(res2["version_id"]))
        c3 = content_of(v3)
        visual_orders = {t.role: t.order for t in c3.timeline.tracks if t.kind == "visual"}
        assert visual_orders["caption"] > visual_orders["title"]

        # 3. Overlapping direct caption creates a second non-overlapping caption track
        res3 = await edit_clip(
            db, name="insert_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ins_k", base=_ref(v3),
            args=InsertTextArgs(
                text="Fast bold hook",
                start_seconds=0.5, end_seconds=2.0,
                role="caption", position="top", preset_id="karaoke_focus",
            ),
        )
        assert res3["text_summary"]["karaoke_active"] is True
        assert res3["text_summary"]["track_id"] != res2["text_summary"]["track_id"]
        _, v4 = await get_video_version(db, owner_id=owner, version_id=UUID(res3["version_id"]))

        # 4. from_audio_clip_id with READY NarrationAlignment + karaoke_focus uses measured word timings!
        res4 = await edit_clip(
            db, name="insert_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ins_aligned", base=_ref(v4),
            args=InsertTextArgs(from_audio_clip_id="clp_vo", preset_id="karaoke_focus"),
        )
        assert res4["text_summary"]["mode"] == "from_audio_clip"
        assert res4["text_summary"]["clips_inserted"] == 2
        assert res4["text_summary"]["karaoke_clips"] == 2
        _, v5 = await get_video_version(db, owner_id=owner, version_id=UUID(res4["version_id"]))
        c5 = content_of(v5)
        aligned_clips = [
            c for t in c5.timeline.tracks for c in t.clips
            if c.clip_id in set(res4["text_summary"]["clip_ids"])
        ]
        assert len(aligned_clips) == 2
        assert all(c.object.caption is not None and c.object.caption.state == "derived" for c in aligned_clips)
        # First sentence (English, 4 words) has exact measured word timings: word 2 starts at 27000 ticks (0.3s = frame 9)
        en_cap = next(c for c in aligned_clips if "Ship" in c.object.text)
        word2_color = [a for a in en_cap.animations if a.property == "text.color"][1]
        assert word2_color.keyframes[1].at == 27000
        # Second sentence (Chinese, 4 measured 2-char words) uses grapheme span matching
        zh_cap = next(c for c in aligned_clips if "一行" in c.object.text)
        zh_colors = [a for a in zh_cap.animations if a.property == "text.color"]
        assert len(zh_colors) == 4
        assert all(a.text_part and a.text_part.kind == "grapheme" for a in zh_colors)

        # Validate compiled video-spec against Zod schema
        spec_v5 = compile_video_spec(
            c5,
            {
                vo_id: {"kind": "audio", "digest": vo_digest, "storage_key": "vo.wav", "duration_ticks": 270000},
                unaligned_id: {"kind": "audio", "digest": unaligned_digest, "storage_key": "bgm.wav", "duration_ticks": 270000},
            },
            composition_id=comp.id,
            version_id=v5.id,
            content_digest=v5.content_digest,
        )
        parsed_ok = _node_eval_ts(
            """
import { readFileSync } from "node:fs";
import { videoSpecSchema } from "./src/schema.ts";
const { spec } = JSON.parse(readFileSync(0, "utf8"));
const parsed = videoSpecSchema.parse(spec);
process.stdout.write(JSON.stringify({ tracks: parsed.tracks.length }));
""",
            {"spec": spec_v5},
        )
        assert parsed_ok["tracks"] >= 4

        # 5. from_audio_clip_id on unaligned BGM fails closed with actionable error
        with pytest.raises(ValueError, match="align_recording"):
            await edit_clip(
                db, name="insert_text", project=project, opening_id=opening.id,
                conversation_id=chat.id, call_id="ins_unaligned", base=_ref(v5),
                args=InsertTextArgs(from_audio_clip_id="clp_bgm"),
            )


@pytest.mark.asyncio
async def test_edit_text_content_position_clear_background_protection_and_observability(database, monkeypatch):
    owner = await _user(database)
    project_id = await _project(database, owner, title="Edit Text & Observability Test")
    audio_id = uuid4()
    audio_digest = "e" * 64

    async with database() as db:
        audio_snap = SourceSnapshot(
            id=audio_id, owner_id=owner, origin_project_id=project_id, kind="audio",
            digest=audio_digest, storage_key="voice.wav", duration_ticks=540000,
        )
        chat = Conversation(user_id=owner, project_id=project_id)
        db.add_all([audio_snap, chat])
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Edit captions", turn_state="in_flight")
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
                transform=Transform(x=40.0, y=-20.0),
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
        plain_title = Clip(
            clip_id="clp_title",
            range=TimeRange(start=0, end=180000),
            object=TextObject(
                kind="text",
                object_id="obj_title",
                text="Opening Title",
                layout=LayoutBox(x=160, y=120, width=1600, height=140),
                style=TextStyle(font_size=56, color="#FFFFFF", background=None, weight=700, align="center"),
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
            animations=[
                Animation(
                    animation_id="anm_vo_fade",
                    target_object_id="obj_vo",
                    property="audio.gain",
                    keyframes=[
                        Keyframe(at=0, value=0.0, easing=Easing(kind="linear")),
                        Keyframe(at=30000, value=1.0, easing=Easing(kind="linear")),
                    ],
                )
            ],
        )

        initial = CompositionContent(
            settings=VersionSettings(
                width=1920, height=1080, background="#0A0F16",
                style=CompositionStyle(preset_id="institutional_dark"),
            ),
            sources=[SourceBinding(snapshot_id=audio_id, snapshot_digest=audio_digest)],
            timeline=Timeline(
                tracks=[
                    Track(track_id="trk_title", kind="visual", role="title", order=0, clips=[plain_title]),
                    Track(
                        track_id="trk_caption", kind="visual", role="caption", order=1,
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

        def _ref(ver):
            return {
                "composition_id": str(comp.id),
                "composition_version_id": str(ver.id),
                "content_digest": ver.content_digest,
            }

        # 1. Apply karaoke_focus to all_derived_captions (protects independent caption, plain title, audio)
        res_k = await edit_clip(
            db, name="edit_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ed_karaoke", base=_ref(v1),
            args=EditTextArgs(scope="all_derived_captions", preset_id="karaoke_focus", highlight_color="#00F0FF"),
        )
        assert res_k["text_summary"]["clips_updated"] == 2
        assert res_k["text_summary"]["independent_captions_preserved"] == 1
        assert res_k["text_summary"]["non_caption_text_preserved"] == 1
        _, v2 = await get_video_version(db, owner_id=owner, version_id=UUID(res_k["version_id"]))
        c2 = content_of(v2)
        clips_v2 = {c.clip_id: c for t in c2.timeline.tracks for c in t.clips}
        assert len([a for a in clips_v2["clp_cap_en"].animations if a.property == "text.color"]) == 5
        assert len([a for a in clips_v2["clp_cap_zh"].animations if a.property == "text.color"]) == 5
        assert clips_v2["clp_cap_ind"].model_dump(mode="json") == independent_cap.model_dump(mode="json")
        assert clips_v2["clp_title"].model_dump(mode="json") == plain_title.model_dump(mode="json")
        assert clips_v2["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")

        # 2. Edit text on active karaoke clip with keep_derived=True -> keeps derived & rebuilds karaoke with #00F0FF!
        res_txt_keep = await edit_clip(
            db, name="edit_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ed_txt_keep", base=_ref(v2),
            args=EditTextArgs(
                scope="clip",
                clip_id="clp_cap_en",
                text="Ship twice as fast",
                keep_derived=True,
                position="top",
            ),
        )
        assert res_txt_keep["text_summary"]["text_updated"] is True
        assert res_txt_keep["text_summary"]["promoted_independent"] == 0
        _, v3 = await get_video_version(db, owner_id=owner, version_id=UUID(res_txt_keep["version_id"]))
        c3 = content_of(v3)
        cap_en_v3 = next(c for t in c3.timeline.tracks for c in t.clips if c.clip_id == "clp_cap_en")
        assert cap_en_v3.object.caption.state == "derived"
        assert cap_en_v3.object.text == "Ship twice as fast"
        assert cap_en_v3.object.layout.y < 120  # moved to top safe area
        assert cap_en_v3.object.transform.x == 0.0 and cap_en_v3.object.transform.y == 0.0
        # Rebuilt karaoke animations match the 4 new words and preserve #00F0FF highlight!
        rebuilt_colors = [a for a in cap_en_v3.animations if a.property == "text.color"]
        assert len(rebuilt_colors) == 4
        assert any(kf.value == "#00F0FF" for kf in rebuilt_colors[1].keyframes)

        # 3. Edit text on derived_zh with keep_derived=False (default) -> promotes to independent + bilingual!
        res_txt_ind = await edit_clip(
            db, name="edit_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ed_txt_ind", base=_ref(v3),
            args=EditTextArgs(
                scope="clip",
                clip_id="clp_cap_zh",
                text="一行指令搞定全片\nOne prompt edits the whole film",
                preset_id="bilingual_cinema",
            ),
        )
        assert res_txt_ind["text_summary"]["promoted_independent"] == 1
        assert res_txt_ind["text_summary"]["karaoke_clips_cleared"] == 1
        _, v4 = await get_video_version(db, owner_id=owner, version_id=UUID(res_txt_ind["version_id"]))
        c4 = content_of(v4)
        cap_zh_v4 = next(c for t in c4.timeline.tracks for c in t.clips if c.clip_id == "clp_cap_zh")
        assert cap_zh_v4.object.caption.state == "independent"
        assert cap_zh_v4.object.style.secondary_line_scale == 0.72
        assert cap_zh_v4.animations == []

        # 4. Switch all_derived_captions to cinema_glass -> updates clp_cap_en only (skips both independent captions!)
        res_glass = await edit_clip(
            db, name="edit_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ed_glass", base=_ref(v4),
            args=EditTextArgs(scope="all_derived_captions", preset_id="cinema_glass"),
        )
        assert res_glass["text_summary"]["clips_updated"] == 1
        assert res_glass["text_summary"]["updated_clip_ids"] == ["clp_cap_en"]
        assert res_glass["text_summary"]["independent_captions_preserved"] == 2
        assert res_glass["text_summary"]["karaoke_clips_cleared"] == 1
        _, v5 = await get_video_version(db, owner_id=owner, version_id=UUID(res_glass["version_id"]))

        # 5. clear_background=True strips pill background cleanly
        res_clear = await edit_clip(
            db, name="edit_text", project=project, opening_id=opening.id,
            conversation_id=chat.id, call_id="ed_clear", base=_ref(v5),
            args=EditTextArgs(scope="clip", clip_id="clp_cap_en", clear_background=True),
        )
        _, v6 = await get_video_version(db, owner_id=owner, version_id=UUID(res_clear["version_id"]))
        c6 = content_of(v6)
        cap_en_v6 = next(c for t in c6.timeline.tracks for c in t.clips if c.clip_id == "clp_cap_en")
        assert cap_en_v6.object.style.background is None
        assert cap_en_v6.object.style.background_mode == "box"
        assert cap_en_v6.object.style.background_padding == (0.0, 0.0)
        assert cap_en_v6.object.style.background_radius == 0.0
        assert cap_en_v6.object.style.border is None

        # 6. Audio track rejection guard
        with pytest.raises(RevisionInputError):
            edit_text(c6, scope="track", track_id="trk_audio", preset_id="vox_label")
        with pytest.raises(RevisionInputError):
            edit_text(c6, scope="clip", clip_id="clp_vo", preset_id="vox_label")

        # 7. Observability: project_context + assemble_video_round project composition_style on Turn 1
        ctx_snapshot = await load_project_context(db, project_id=project_id, owner_id=owner)
        comp_res = next(r for _, r in ctx_snapshot.resources if r.get("kind") == "composition")
        assert comp_res["composition_style"]["preset_id"] == "institutional_dark"
        assert comp_res["composition_style"]["accent"] == "#14B8A6"
        assert comp_res["background"] == "#0A0F16"

        from app.chat.editor import EDITOR_TOOLS

        assembly = assemble_video_round({
            "snapshot": ctx_snapshot,
            "tools": list(EDITOR_TOOLS),
            "user_text": "Change caption style",
        })
        raw_ctx = assembly.context
        prompt_ctx = json.loads(raw_ctx.split("\n", 1)[1] if "\n" in raw_ctx and not raw_ctx.lstrip().startswith("{") else raw_ctx)
        assert prompt_ctx["composition_style"]["preset_id"] == "institutional_dark"
        assert prompt_ctx["composition_style"]["theme"] == "dark"
        await db.commit()

    # 8. Observability: execute_editor inspect_timeline, inspect_clip, and recently_edited_clips
    monkeypatch.setattr("app.chat.editor.AsyncSessionLocal", database)
    turn = SimpleNamespace(
        project=project,
        conversation_id=chat.id,
        turn_id=opening.id,
        db=None,
        _video_base_ref=_ref(v6),
    )
    obs_tl = await execute_editor(turn, "inspect_timeline", InspectTimelineArgs(offset=0))
    tl_data = json.loads(obs_tl.text)
    assert tl_data["background"] == "#0A0F16"
    assert tl_data["composition_style"]["preset_id"] == "institutional_dark"
    by_id = {c["clip_id"]: c for c in tl_data["clips"]}
    assert by_id["clp_cap_zh"]["caption_state"] == "independent"
    assert by_id["clp_cap_zh"]["style"]["secondary_line_scale"] == 0.72
    assert by_id["clp_cap_zh"]["style"]["has_stroke"] is True
    assert by_id["clp_cap_zh"]["karaoke_active"] is False
    assert by_id["clp_title"]["caption_state"] is None
    assert by_id["clp_vo"]["has_gain_automation"] is True

    obs_clip = await execute_editor(turn, "inspect_clip", ClipArgs(clip_id="clp_cap_zh"))
    clip_data = json.loads(obs_clip.text)
    assert clip_data["composition_style"]["preset_id"] == "institutional_dark"
    assert clip_data["background"] == "#0A0F16"

    # Also verify recently_edited_clips records rich text metadata after edit_text
    monkeypatch.setattr("app.chat.editor.current_call_id", lambda: "ed_obs_title")
    async with database() as db:
        turn.db = db
        obs_edit = await execute_editor(
            turn,
            "edit_text",
            EditTextArgs(scope="clip", clip_id="clp_title", preset_id="vox_highlighter"),
        )
        assert obs_edit.version_saved is True
        focused_title = turn._editor_recent["clips"]["clp_title"]
        assert focused_title["text"] == "Opening Title"
        assert focused_title["style"]["background_mode"] == "line"
        assert focused_title["style"]["has_border"] is True
        assert focused_title["caption_state"] is None
        assert focused_title["karaoke_active"] is False


def test_catalog_prompt_index_exposes_all_11_text_style_presets():
    index = catalog_prompt_index()
    ids = [item["id"] for item in index["text_style_presets"]]
    assert len(ids) == 11
    assert ids == list(TEXT_STYLE_PRESETS.keys())
    for item in index["text_style_presets"]:
        assert item["name"]
        assert item["use_for"]
        assert item["visual_signature"]


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

    # 1. insert_text with bilingual_cinema on light themes -> dark ink + light canvas halo + shadow=None
    for preset_id, expected_ink, expected_bg in (
        ("vox_editorial", "#141413", "#F4EFE2"),
        ("swiss_paper", "#111820", "#F6F5F0"),
    ):
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
        assert st.color == expected_ink
        assert st.stroke == TextStroke(color=expected_bg, width=3.5)
        assert st.shadow is None
        assert st.weight == 700
        assert st.background is None
        assert st.secondary_line_scale == 0.72
        assert st.secondary_line_opacity == 0.86

        # edit_text produces the exact same light-theme bilingual_cinema style
        re_styled, _ = edit_text(
            updated, scope="clip", clip_id="clp_bi", preset_id="clean_broadcast"
        )
        re_bi, _ = edit_text(
            re_styled, scope="clip", clip_id="clp_bi", preset_id="bilingual_cinema"
        )
        st2 = next(c for t in re_bi.timeline.tracks for c in t.clips if c.clip_id == "clp_bi").object.style
        assert st2.color == expected_ink
        assert st2.stroke == TextStroke(color=expected_bg, width=3.5)
        assert st2.shadow is None

    # 2. Dark theme and style=None keep white ink + dark halo + soft shadow
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
        assert st.stroke == TextStroke(color="#0A0F16", width=3.5)
        assert st.shadow == TextShadow(color="#0A0F16", offset=(0.0, 2.0), blur=10.0)
        assert st.secondary_line_scale == 0.72
        assert st.secondary_line_opacity == 0.86

    # 3. Verify Python <-> TS zero drift for resolve_text_preset_token across styles
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

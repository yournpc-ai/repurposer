"""Layer 1A Chat-Origin: style switching, symmetric text/caption editing, motion-block auto-extend, and atomic SFX placement."""

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


@pytest.mark.asyncio
async def test_set_composition_style_atomic_commit_caption_and_audio_laws(database):
    owner = await _user(database)
    project_id = await _project(database, owner, title="Style Switch Test")
    audio_id = uuid4()
    audio_digest = "a" * 64

    async with database() as db:
        audio_snap = SourceSnapshot(
            id=audio_id,
            owner_id=owner,
            origin_project_id=project_id,
            kind="audio",
            digest=audio_digest,
            storage_key="narration.wav",
            duration_ticks=540000,
        )
        chat = Conversation(user_id=owner, project_id=project_id)
        db.add_all([audio_snap, chat])
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Switch style", turn_state="in_flight")
        db.add(opening)
        await db.flush()

        derived_cap = Clip(
            clip_id="clp_cap_derived",
            range=TimeRange(start=0, end=180000),
            object=TextObject(
                kind="text",
                object_id="obj_cap_derived",
                text="Derived caption follows style",
                layout=LayoutBox(x=240, y=920, width=1440, height=100),
                style=TextStyle(font_size=42, color="#FFFFFF", background=None, weight=600, align="center"),
                caption=SourceCaptionDerivation(
                    snapshot_id=audio_id,
                    snapshot_digest=audio_digest,
                    sentence_id="s1",
                    source_range=TimeRange(start=0, end=180000),
                    source_text_digest=speech_text_digest("Derived caption follows style"),
                    state="derived",
                ),
            ),
        )
        independent_cap = Clip(
            clip_id="clp_cap_independent",
            range=TimeRange(start=180000, end=360000),
            object=TextObject(
                kind="text",
                object_id="obj_cap_independent",
                text="User-edited independent caption",
                layout=LayoutBox(x=240, y=920, width=1440, height=100),
                style=TextStyle(
                    font_size=44,
                    color="#FF9900",
                    background="#222222",
                    weight=800,
                    align="center",
                    stroke=TextStroke(color="#000000", width=2.0),
                    shadow=TextShadow(color="#000000", offset=(1.0, 1.0), blur=2.0),
                ),
                caption=SourceCaptionDerivation(
                    snapshot_id=audio_id,
                    snapshot_digest=audio_digest,
                    sentence_id="s2",
                    source_range=TimeRange(start=180000, end=360000),
                    source_text_digest=speech_text_digest("Original ASR text before user edit"),
                    state="independent",
                ),
            ),
        )
        plain_text = Clip(
            clip_id="clp_plain_title",
            range=TimeRange(start=0, end=180000),
            object=TextObject(
                kind="text",
                object_id="obj_plain_title",
                text="Manual title stays untouched",
                layout=LayoutBox(x=100, y=80, width=600, height=80),
                style=TextStyle(font_size=36, color="#123456", background=None, weight=700, align="left"),
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
            object=AudioObject(kind="audio", object_id="obj_vo", gain_db=-2.5),
        )

        initial = CompositionContent(
            settings=VersionSettings(width=1920, height=1080, background="#000000"),
            sources=[SourceBinding(snapshot_id=audio_id, snapshot_digest=audio_digest)],
            timeline=Timeline(
                tracks=[
                    Track(
                        track_id="trk_mg_main",
                        kind="visual",
                        role="main",
                        order=0,
                        clips=[
                            Clip(
                                clip_id="clp_1",
                                range=TimeRange(start=0, end=270000),
                                object=MotionBlockObject(
                                    kind="motion_block",
                                    object_id="obj_1",
                                    block_id="statement_hook",
                                    props={
                                        "headline": "Orthogonal Style System",
                                        "theme": "dark",
                                        "accent_color": "#0D9488",
                                        "backdrop_style": "ambient_mesh",
                                    },
                                    layout=BOX,
                                    fit="cover",
                                ),
                            ),
                            Clip(
                                clip_id="clp_2",
                                range=TimeRange(start=270000, end=540000),
                                object=MotionBlockObject(
                                    kind="motion_block",
                                    object_id="obj_2",
                                    block_id="closing_cta",
                                    props={
                                        "brand_name": "Rookie Cut",
                                        "tagline": "Template x Style",
                                        "theme": "dark",
                                        "accent_color": "#14B8A6",
                                    },
                                    layout=BOX,
                                    fit="cover",
                                ),
                            ),
                        ],
                    ),
                    Track(
                        track_id="trk_mg_title",
                        kind="visual",
                        role="title",
                        order=1,
                        clips=[
                            Clip(
                                clip_id="clp_kt",
                                range=TimeRange(start=0, end=180000),
                                object=MotionBlockObject(
                                    kind="motion_block",
                                    object_id="obj_kt",
                                    block_id="kinetic_title",
                                    props={
                                        "headline": "Context",
                                        "accent_color": "#14B8A6",
                                        "text_color": "#F8FAFC",
                                        "surface_style": "glass_card",
                                    },
                                    layout=BOX,
                                    fit="contain",
                                ),
                            ),
                        ],
                    ),
                    Track(
                        track_id="trk_title_plain",
                        kind="visual",
                        role="title",
                        order=2,
                        clips=[plain_text],
                    ),
                    Track(
                        track_id="trk_caption",
                        kind="visual",
                        role="caption",
                        order=3,
                        clips=[derived_cap, independent_cap],
                    ),
                    Track(
                        track_id="trk_audio",
                        kind="audio",
                        role="dialogue",
                        order=0,
                        clips=[audio_clip],
                    ),
                ],
                transitions=[
                    Transition(
                        transition_id="trn_1",
                        from_clip_id="clp_1",
                        to_clip_id="clp_2",
                        kind="crossfade",
                        duration=36000,
                    )
                ],
            ),
        )
        comp, v1, _ = await apply_composition_edits(
            db, owner_id=owner, origin_project_id=project_id, content=initial
        )
        project = await db.get(Project, project_id)
        base_ref = {
            "composition_id": str(comp.id),
            "composition_version_id": str(v1.id),
            "content_digest": v1.content_digest,
        }

        # 1. Switch to vox_editorial (override_block_styles=True, update_captions=True, update_transitions=False)
        res_vox = await edit_clip(
            db,
            name="set_composition_style",
            project=project,
            opening_id=opening.id,
            conversation_id=chat.id,
            call_id="call_vox",
            base=base_ref,
            args=SetCompositionStyleArgs(preset_id="vox_editorial"),
        )
        assert res_vox["style_summary"]["blocks_updated"] == 3
        assert res_vox["style_summary"]["captions_updated"] == 1
        assert res_vox["style_summary"]["independent_captions_preserved"] == 1
        assert res_vox["style_summary"]["transitions_updated"] == 0

        _, v2 = await get_video_version(db, owner_id=owner, version_id=UUID(res_vox["version_id"]))
        c2 = content_of(v2)
        assert c2.settings.style == CompositionStyle(preset_id="vox_editorial")
        assert c2.settings.background == "#F4EFE2"
        clips_v2 = {c.clip_id: c for t in c2.timeline.tracks for c in t.clips}
        # Local overrides stripped from all 3 motion blocks
        for cid, forbidden in (
            ("clp_1", {"theme", "accent_color", "backdrop_style"}),
            ("clp_2", {"theme", "accent_color", "backdrop_style"}),
            ("clp_kt", {"accent_color", "text_color", "surface_style"}),
        ):
            assert not (forbidden & set(clips_v2[cid].object.props))
        # Derived caption got Vox compact dark pill; independent caption & plain text untouched!
        assert clips_v2["clp_cap_derived"].object.style.background == "#141413"
        assert clips_v2["clp_cap_derived"].object.style.color == "#FFFDF7"
        assert clips_v2["clp_cap_derived"].object.style.font_size == 42
        assert clips_v2["clp_cap_independent"].object.model_dump(mode="json") == independent_cap.object.model_dump(mode="json")
        assert clips_v2["clp_plain_title"].object.model_dump(mode="json") == plain_text.object.model_dump(mode="json")
        # Audio track byte-identical; transition preserved when update_transitions=False
        assert clips_v2["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")
        assert c2.timeline.transitions[0].kind == "crossfade"

        # 2. Switch to kinetic_anime with update_transitions=True & verify background=None on derived caption
        base_ref_v2 = {
            "composition_id": str(comp.id),
            "composition_version_id": str(v2.id),
            "content_digest": v2.content_digest,
        }
        res_kin = await edit_clip(
            db,
            name="set_composition_style",
            project=project,
            opening_id=opening.id,
            conversation_id=chat.id,
            call_id="call_kin",
            base=base_ref_v2,
            args=SetCompositionStyleArgs(preset_id="kinetic_anime", update_transitions=True),
        )
        _, v3 = await get_video_version(db, owner_id=owner, version_id=UUID(res_kin["version_id"]))
        c3 = content_of(v3)
        clips_v3 = {c.clip_id: c for t in c3.timeline.tracks for c in t.clips}
        assert c3.settings.background == "#0D0B14"
        assert clips_v3["clp_cap_derived"].object.style.background is None
        assert clips_v3["clp_cap_derived"].object.style.weight == 900
        assert clips_v3["clp_cap_independent"].object.model_dump(mode="json") == independent_cap.object.model_dump(mode="json")
        assert clips_v3["clp_vo"].model_dump(mode="json") == audio_clip.model_dump(mode="json")
        assert c3.timeline.transitions[0].kind == "whip_pan"

        # 3. Verify override_block_styles=False preserves explicit per-block override
        c_with_local, _ = apply_composition_style(
            initial, preset_id="swiss_paper", override_block_styles=False
        )
        local_clips = {c.clip_id: c for t in c_with_local.timeline.tracks for c in t.clips}
        assert local_clips["clp_1"].object.props["theme"] == "dark"
        assert c_with_local.settings.style == CompositionStyle(preset_id="swiss_paper")
        assert local_clips["clp_cap_derived"].object.style.background is None
        assert local_clips["clp_cap_derived"].object.style.color == "#111820"


@pytest.mark.asyncio
async def test_template_x_style_orthogonal_skill_blueprint(database, monkeypatch):
    owner = await _user(database)
    master_id = await _project(database, owner, title="Master Styled")
    remake_id = await _project(database, owner, title="Cross-Style Remake")

    async with database() as db:
        chat = Conversation(user_id=owner, project_id=remake_id)
        db.add(chat)
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Remake in Vox style", turn_state="in_flight")
        db.add(opening)
        await db.flush()
        remake_project = await db.get(Project, remake_id)
        turn = SimpleNamespace(project=remake_project, conversation_id=chat.id, turn_id=opening.id)

        master = CompositionContent(
            settings=VersionSettings(
                width=1920,
                height=1080,
                background="#0A0F16",
                style=CompositionStyle(preset_id="institutional_dark"),
            ),
            timeline=Timeline(
                tracks=[
                    Track(
                        track_id="trk_mg_main",
                        kind="visual",
                        role="main",
                        order=0,
                        clips=[
                            Clip(
                                clip_id="clp_1",
                                range=TimeRange(start=0, end=270000),
                                object=MotionBlockObject(
                                    kind="motion_block",
                                    object_id="obj_1",
                                    block_id="statement_hook",
                                    props={"headline": "Master headline", "highlight_phrase": "Master"},
                                    layout=BOX,
                                    fit="cover",
                                ),
                            ),
                            Clip(
                                clip_id="clp_2",
                                range=TimeRange(start=270000, end=540000),
                                object=MotionBlockObject(
                                    kind="motion_block",
                                    object_id="obj_2",
                                    block_id="closing_cta",
                                    props={"brand_name": "MasterCo", "tagline": "Original tagline"},
                                    layout=BOX,
                                    fit="cover",
                                ),
                            ),
                        ],
                    )
                ]
            ),
        )
        comp, version, _ = await apply_composition_edits(
            db, owner_id=owner, origin_project_id=master_id, content=master
        )
        saved = await save_composition_as_skill(
            db,
            owner_id=owner,
            project_id=master_id,
            composition_id=comp.id,
            version_id=version.id,
            name="orthogonal-style-template",
            description="Reusable template with first-class style.",
        )
        skill = await db.get(SkillVersion, UUID(saved["skill_version_id"]))
        bp = SkillBlueprintV1.model_validate_json(skill.references[0]["text"])
        assert bp.style == CompositionStyle(preset_id="institutional_dark")
        assert "theme" not in bp.acts[0].style_defaults
        assert "accent_color" not in bp.acts[0].style_defaults
        assert "backdrop_style" not in bp.acts[0].style_defaults

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    result = await instantiate_skill_blueprint(
        turn=turn,
        call_id="cross_style",
        args=InstantiateSkillBlueprintArgs(
            skill_version_id=skill.id,
            name="Vox Remake",
            style_preset="vox_editorial",
            acts=[
                {"props": {"headline": "Fresh Vox Headline", "highlight_phrase": "Vox"}},
                {"props": {"brand_name": "NewBrand", "tagline": "Bold editorial explainer"}},
            ],
        ),
    )
    async with database() as db:
        _, remake_ver = await get_video_version(db, owner_id=owner, version_id=UUID(result["version_id"]))
        remake_content = content_of(remake_ver)
        assert remake_content.settings.style == CompositionStyle(preset_id="vox_editorial")
        assert remake_content.settings.background == "#F4EFE2"
        spec = compile_video_spec(
            remake_content,
            await snapshot_facts(db, {s.snapshot_id for s in remake_content.sources}),
            composition_id=remake_ver.composition_id,
            version_id=remake_ver.id,
            content_digest=remake_ver.content_digest,
        )
        assert spec["style"]["preset_id"] == "vox_editorial"
        assert spec["style"]["headline_treatment"] == "highlight_tape"


# --- Symmetric insert_text & edit_text contracts ---

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


# --- Motion block auto-extend & atomic SFX placement ---

from datetime import UTC, datetime


from types import SimpleNamespace


from uuid import UUID, uuid4


import httpx


import pytest


from pydantic import ValidationError


from sqlalchemy import func, select


from app.agents.tool_loop import BatchDeclared, BatchMember, ContextSnapshot, ReadExecuting


from app.agents.tool_progress import bind_progress


from app.chat.activity import (
    KIND_STEPS,
    ActivityProjector,
    finalize_steps,
    frame_persistence,
    sanitize_steps,
)


from app.chat.context import conversation_messages


from app.chat.editor import (
    GenerateSfxArgs,
    InsertMotionBlockArgs,
    _remember_labels,
    edit_clip,
    project_editor_reply,
)


from app.chat.editor_create import CreateVideoArgs, create_video


from app.chat.editor_media import execute_generate_sfx


from app.chat.intent import intent_router


from app.chat.plan_turn import run_plan_turn


from app.chat.prompts import assemble_video_round


from app.chat.service import _create_message, prepare_chat_turn


from app.config import settings


from app.dependencies import get_current_user_required, get_db


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.store import content_of


from app.main import app


from app.models import database as database_module


from app.models.schemas import AssetStatus, AssetType, ChatMessageResponse, ChatRequest


from app.models.tables import (
    Asset,
    Composition,
    CompositionVersion,
    Conversation,
    ExportJob,
    MediaJob,
    Message,
    MessageFeedback,
    Output,
    Project,
    SourceSnapshot,
    User,
)


from app.platform.conversation_context import find_conversation


from app.providers import storage


from app.providers.llm.base import ToolCall, ToolGeneration


from test.support.db_helpers import _project, _user


class _ScriptedClient:
    model = "test-eval-model-v1"
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


def _api_client(database, user: User):
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_required] = _override_user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_h2_insert_motion_block_auto_extends_timeline_and_rejects_large_gap(database, monkeypatch):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    owner = await _user(database)
    project_id = await _project(database, owner)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id)
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "Create and extend")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
        )
        with bind_progress("create-base", None):
            created = await create_video(
                db,
                turn,
                CreateVideoArgs(
                    name="Base 5s",
                    motion_blocks=[
                        {
                            "block_id": "statement_hook",
                            "duration_seconds": 5.0,
                            "props": {"headline": "Act 1"},
                        }
                    ],
                ),
            )
        base = {
            "composition_id": created["composition_id"],
            "composition_version_id": created["version_id"],
            "content_digest": created["content_digest"],
        }

        # Reject disconnected empty gap > 2s past end (5s + 2s = 7s; 10s fails)
        with pytest.raises(ValueError, match="2 seconds"):
            await edit_clip(
                db,
                name="insert_motion_block",
                project=project,
                opening_id=opening.id,
                conversation_id=conv.id,
                call_id="insert-gap-bad",
                base=base,
                args=InsertMotionBlockArgs(
                    block_id="closing_cta",
                    start_seconds=10.0,
                    end_seconds=15.0,
                    props={"brand_name": "Rookie Cut", "tagline": "Too far"},
                ),
                inspected_version=created["version_id"],
            )

        # Seamlessly append 5s..10s past original 5s duration
        extended = await edit_clip(
            db,
            name="insert_motion_block",
            project=project,
            opening_id=opening.id,
            conversation_id=conv.id,
            call_id="insert-extend-ok",
            base=base,
            args=InsertMotionBlockArgs(
                block_id="closing_cta",
                start_seconds=5.0,
                end_seconds=10.0,
                props={"brand_name": "Rookie Cut", "tagline": "Extended cleanly"},
            ),
            inspected_version=created["version_id"],
        )

    assert extended["version"] == 2
    assert extended["timeline_duration_seconds"] == pytest.approx(10.0)
    assert extended["extended_timeline"] is True
    async with database() as db:
        v2 = await db.get(CompositionVersion, UUID(extended["version_id"]))
        content = content_of(v2)
        assert len(content.scenes) == 2
        assert max(s.range.end for s in content.scenes) == 10 * content.settings.timebase


@pytest.mark.asyncio
async def test_h3_generate_sfx_atomic_placement_and_unplaced_next_step(database, monkeypatch, tmp_path):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor_media.AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "s3_public_url", "http://127.0.0.1:8000/_local_storage")

    owner = await _user(database)
    project_id = await _project(database, owner)

    async def _fake_synthesize(*, owner_id, project_id, recipe_id, params, seed):
        import hashlib

        snap_id = uuid4()
        key = f"sfx/{snap_id}.wav"
        digest = hashlib.sha256(snap_id.bytes).hexdigest()
        await storage.save(key, b"RIFF0000WAVEfmt ", content_type="audio/wav")
        async with database() as sdb:
            snap = SourceSnapshot(
                id=snap_id,
                owner_id=owner_id,
                origin_project_id=project_id,
                kind="audio",
                digest=digest,
                storage_key=key,
                duration_ticks=90000,  # 1.0s at SOURCE_TIMEBASE (90000)
                meta={
                    "content_type": "audio/wav",
                    "origin": {
                        "kind": "sound_recipe",
                        "recipe_id": recipe_id,
                        "params": params,
                        "seed": seed,
                    },
                },
            )
            sdb.add(snap)
            await sdb.commit()
        return {
            "snapshot": {"snapshot_id": str(snap_id), "digest": digest},
            "media": {"storage_key": key, "digest": digest, "duration_seconds": 1.0},
            "analysis": {"analysis_digest": f"ana_{snap_id.hex[:8]}", "peaks": [0.7]},
            "cache_hit": False,
            "sound_recipe": {
                "recipe_id": recipe_id,
                "recipe_version": 2,
                "params": params,
                "seed": seed,
                "spec_sha256": f"spec_{snap_id.hex[:12]}",
            },
            "acoustics": {"duration_ms": 1000, "peak_offset_ms": 120, "peak_dbfs": -2.1},
        }

    async def _fake_playback_item(_db, _project, _role, result, _request):
        return {
            "snapshot_id": result["snapshot"]["snapshot_id"],
            "digest": result["snapshot"]["digest"],
            "duration_seconds": 1.0,
            "analysis_digest": result["analysis"]["analysis_digest"],
            "peaks": [0.7],
        }

    monkeypatch.setattr("app.tools.video.sfx_synthesis.synthesize_project_sfx", _fake_synthesize)
    monkeypatch.setattr("app.chat.editor_media.playback_item", _fake_playback_item)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner, project_id=project_id)
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "加个转场音效")
        opening.turn_state = "in_flight"
        await db.commit()
        turn = SimpleNamespace(
            db=db,
            user_id=owner,
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
            on_row_append=None,
        )
        with bind_progress("create-for-sfx", None):
            created = await create_video(
                db,
                turn,
                CreateVideoArgs(
                    name="SFX Base",
                    motion_blocks=[
                        {
                            "block_id": "statement_hook",
                            "duration_seconds": 6.0,
                            "props": {"headline": "Hello"},
                        }
                    ],
                ),
            )
        comp = await db.get(Composition, UUID(created["composition_id"]))
        ver = await db.get(CompositionVersion, UUID(created["version_id"]))

        # 1) Without place_at_seconds -> placed=False + next_step
        with bind_progress("sfx-unplaced", None):
            obs_unplaced = await execute_generate_sfx(
                turn, GenerateSfxArgs(recipe_id="whoosh"), comp, ver
            )
        import json

        data_unplaced = json.loads(obs_unplaced.text)
        assert obs_unplaced.ok is True
        assert obs_unplaced.version_saved is False
        assert data_unplaced["placed"] is False
        assert "insert_audio" in data_unplaced["next_step"]

        # 2) With place_at_seconds -> atomic placement onto effect track!
        with bind_progress("sfx-placed", None):
            obs_placed = await execute_generate_sfx(
                turn,
                GenerateSfxArgs(recipe_id="impact", place_at_seconds=2.5, gain_db=-10.0),
                comp,
                ver,
            )
        data_placed = json.loads(obs_placed.text)
        assert obs_placed.ok is True
        assert obs_placed.version_saved is True
        assert data_placed["placed"] is True
        assert data_placed["version"] == 2
        assert data_placed["start_seconds"] == pytest.approx(2.5)
        assert data_placed["end_seconds"] == pytest.approx(3.5)
        assert turn._video_base_ref["composition_version_id"] == data_placed["version_id"]

        v2 = await db.get(CompositionVersion, UUID(data_placed["version_id"]))
        effect_clips = [
            c
            for t in content_of(v2).timeline.tracks
            if t.kind == "audio" and t.role == "effect"
            for c in t.clips
        ]
        assert len(effect_clips) == 1
        assert effect_clips[0].object.gain_db == pytest.approx(-10.0)


# --- SFX stop-fence ---

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



# --- Flagship Real HTTP POST /api/v1/chat Multi-Turn Style & Text Editing Journey ---


@pytest.mark.asyncio
async def test_chat_endpoint_sse_followup_switches_style_and_inserts_text(database, monkeypatch):
    """Real user door: Turn 1 creates a draft via POST /api/v1/chat (SSE); Turn 2 switches
    CompositionStyle to vox_editorial and inserts styled text via POST /api/v1/chat (SSE)."""
    from scripts.eval_chat_e2e import collect_sse_telemetry, parse_sse_frames
    from test.support.db_helpers import ScriptedToolClient, bind_test_database, full_api_client

    bind_test_database(monkeypatch, database)

    owner_id = await _user(database)
    project_id = await _project(database, owner_id, title="Chat Origin Editing")
    async with database() as db:
        owner = await db.get(User, owner_id)

    turn1_client = ScriptedToolClient(
        [
            ToolGeneration(
                content="",
                tool_calls=[
                    ToolCall(
                        id="c_create_edit_1",
                        name="create_video",
                        arguments={
                            "name": "Style Edit Cut",
                            "style_preset": "institutional_dark",
                            "motion_blocks": [
                                {
                                    "block_id": "statement_hook",
                                    "duration_seconds": 5.0,
                                    "props": {"headline": "初稿标题"},
                                }
                            ],
                        },
                    )
                ],
            ),
            ToolGeneration(
                content="已创建 5 秒初稿。",
                tool_calls=[ToolCall(id="c_ans_1", name="answer", arguments={"pending_disposition": "none"})],
            ),
        ],
        streaming=True,
    )
    monkeypatch.setattr(intent_router, "client", turn1_client)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: turn1_client)

    async with full_api_client(database, owner) as client:
        r1 = await client.post(
            "/api/v1/chat",
            json={"project_id": str(project_id), "message": "做一个 5 秒深色开场草稿"},
            headers={"Accept": "text/event-stream"},
        )
        assert r1.status_code == 200, r1.text
        t1 = collect_sse_telemetry(parse_sse_frames(r1.text))
        assert t1.done_payload is not None
        conv_id = t1.done_payload["conversation_id"]

        turn2_client = ScriptedToolClient(
            [
                ToolGeneration(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="c_style_2",
                            name="set_composition_style",
                            arguments={"preset_id": "vox_editorial"},
                        )
                    ],
                ),
                ToolGeneration(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="c_text_2",
                            name="insert_text",
                            arguments={
                                "text": "一分钟出片",
                                "start_seconds": 0.5,
                                "end_seconds": 4.5,
                                "preset_id": "editorial_callout",
                                "position": "top",
                            },
                        )
                    ],
                ),
                ToolGeneration(
                    content="已切换成 vox_editorial 风格并加上主标题「一分钟出片」。",
                    tool_calls=[ToolCall(id="c_ans_2", name="answer", arguments={"pending_disposition": "none"})],
                ),
            ],
            streaming=True,
        )
        monkeypatch.setattr(intent_router, "client", turn2_client)
        monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: turn2_client)

        r2 = await client.post(
            "/api/v1/chat",
            json={
                "project_id": str(project_id),
                "conversation_id": conv_id,
                "message": "切换成 vox_editorial 风格，顶部加上主标题「一分钟出片」",
            },
            headers={"Accept": "text/event-stream"},
        )
        assert r2.status_code == 200, r2.text
        t2 = collect_sse_telemetry(parse_sse_frames(r2.text))
        assert t2.done_payload is not None
        assert "vox_editorial" in t2.assistant_text

        wb = (await client.get(f"/api/v1/projects/{project_id}/workbench")).json()
        assert len(wb["compositions"]) == 1
        versions = wb["compositions"][0]["versions"]
        assert len(versions) == 3
        head = next(v for v in versions if v["is_head"])
        assert head["version"] == 3
        assert head["style_preset"] == "vox_editorial"

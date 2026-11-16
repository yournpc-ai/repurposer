from uuid import UUID, uuid4
from types import SimpleNamespace

import pytest

from app.editing.alignment import NarrationPayload, NarrationSentence, NarrationWord
from app.editing.edits import AddClip, AddTrack, BindSource, apply_ops
from app.editing.revisions import AddNarrationAction
from app.editing.revisions import SetTextAction, expand_revision_action, set_text_ops
from app.editing.schemas import (
    AudioObject,
    Clip,
    CompositionContent,
    Scene,
    TimeRange,
    Track,
    Transform,
    VideoObject,
)
from app.editing.source_selection import (
    SourceSelectionAnswer,
    resolve_selection,
    source_sentences,
)
from app.editing.timing import SOURCE_TIMEBASE
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
from app.tools.video.design import CompositionSceneAuthoring, _expand_scene_authoring

VIDEO_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AUDIO_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
VIDEO_DIGEST = "c" * 64
AUDIO_DIGEST = "d" * 64
COMPOSITION_ID = UUID("33333333-3333-3333-3333-333333333333")
VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


WORDS = [
    word("Welcome.", 0, 4),
    word("Today we discuss the product.", 6, 10),
    word("Pricing is the next topic.", 12, 18),
    word("Annual plans ", 18, 21),
    word("include support.", 22, 25),
    word("That closes the pricing answer.", 27, 31),
    word("Thank you.", 33, 36),
]
FACT = {
    "kind": "video",
    "digest": VIDEO_DIGEST,
    "duration_ticks": 40 * SOURCE_TIMEBASE,
    "storage_key": "snapshots/upload.mp4",
    "meta": {
        "words": WORDS,
        "media": {"width": 1920, "height": 1080, "has_audio": True},
    },
}
FACTS = {
    VIDEO_ID: FACT,
    AUDIO_ID: {
        "kind": "audio",
        "digest": AUDIO_DIGEST,
        "duration_ticks": 13 * SOURCE_TIMEBASE,
        "storage_key": "snapshots/narration.wav",
        "meta": {},
    },
}


def initial_content():
    return CompositionContent(
        settings={"width": 1080, "height": 1920},
        scenes=[Scene(
            scene_id="scn_pricing",
            range=TimeRange(start=0, end=40 * SOURCE_TIMEBASE),
            intent="Explain the pricing choice",
        )],
        timeline={"tracks": [
            {"track_id": "trk_main", "kind": "visual", "role": "main", "order": 0, "clips": []},
        ]},
    )


async def expanded_content():
    scene = CompositionSceneAuthoring(
        scene_id="scn_pricing",
        snapshot_id=VIDEO_ID,
        source_query="the pricing argument; include the previous sentence too",
        captions_asr=True,
        source_fit="cover",
        source_transform=Transform(x=12),
        source_gain_db=-18,
    )

    async def select(*, query, sentences):
        assert query and sentences
        return SourceSelectionAnswer(sentence_ids=["asr_0003", "asr_0004", "asr_0005"])

    from unittest.mock import patch

    with patch("app.tools.video.agents.source_selector.call", new=select):
        expanded = await _expand_scene_authoring(
            initial_content().model_dump(mode="json"),
            scene,
            FACTS,
        )
        return CompositionContent.model_validate(expanded)


def clip_by_id(content, clip_id):
    return next(
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == clip_id
    )


@pytest.mark.asyncio
async def test_semantic_middle_selection_captions_fixed_layout_and_dialogue_spec():
    content = await expanded_content()
    source = clip_by_id(content, "clp_scn_pricing_source")
    assert source.range.duration == 13 * SOURCE_TIMEBASE
    assert source.source.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=25 * SOURCE_TIMEBASE,
    )
    assert isinstance(source.object, VideoObject)
    assert source.object.fit == "cover"
    assert source.object.transform.x == 12
    assert source.object.gain_db == -18
    assert source.object.muted is False

    captions = [
        clip
        for track in content.timeline.tracks
        if track.role == "caption"
        for clip in track.clips
    ]
    assert len(captions) == 3
    assert all(clip.object.style.background is None for clip in captions)
    assert [clip.range.duration for clip in captions] == [
        6 * SOURCE_TIMEBASE,
        3 * SOURCE_TIMEBASE,
        3 * SOURCE_TIMEBASE,
    ]
    assert captions[0].object.caption.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=18 * SOURCE_TIMEBASE,
    )
    assert captions[1].object.caption.source_range == TimeRange(
        start=18 * SOURCE_TIMEBASE,
        end=21 * SOURCE_TIMEBASE,
    )
    assert captions[2].object.caption.source_range == TimeRange(
        start=22 * SOURCE_TIMEBASE,
        end=25 * SOURCE_TIMEBASE,
    )
    assert captions[1].object.text + " " + captions[2].object.text == "Annual plans include support."

    dub_clip = Clip(
        clip_id="clp_dub",
        range=TimeRange(start=0, end=13 * SOURCE_TIMEBASE),
        scene_id="scn_pricing",
        source={
            "snapshot_id": AUDIO_ID,
            "snapshot_digest": AUDIO_DIGEST,
            "source_range": {"start": 0, "end": 13 * SOURCE_TIMEBASE},
        },
        object=AudioObject(kind="audio", object_id="obj_dub", gain_db=-3),
        animations=[],
    )
    content = apply_ops(content, [
        BindSource(op="bind_source", snapshot_id=AUDIO_ID),
        AddTrack(
            op="add_track",
            track=Track(
                track_id="trk_dialogue",
                kind="audio",
                role="dialogue",
                order=0,
                clips=[],
            ),
        ),
        AddClip(op="add_clip", track_id="trk_dialogue", clip=dub_clip),
    ], {VIDEO_ID: VIDEO_DIGEST, AUDIO_ID: AUDIO_DIGEST})
    validate_content(content, FACTS)
    spec = compile_video_spec(
        content,
        FACTS,
        composition_id=COMPOSITION_ID,
        version_id=VERSION_ID,
        content_digest="e" * 64,
    )
    assert (spec["width"], spec["height"]) == (1080, 1920)
    compiled = {
        clip["clip_id"]: clip
        for track in spec["tracks"]
        for clip in track["clips"]
    }
    assert compiled[source.clip_id]["source"]["start_frame"] == 360
    assert compiled[source.clip_id]["source"]["end_frame"] == 750
    assert compiled["clp_dub"]["object"] == {
        "kind": "audio",
        "object_id": "obj_dub",
        "gain_db": -3.0,
    }
    assert compiled["clp_dub"]["source"]["end_frame"] == 390
    assert len([clip for clip in compiled if clip.startswith("clp_caption_")]) == 3


@pytest.mark.asyncio
async def test_hand_edited_caption_becomes_independent_without_changing_source_window():
    content = await expanded_content()
    content = apply_ops(content, set_text_ops(
        content,
        SetTextAction(
            action="set_text",
            clip_id="clp_caption_scn_pricing_asr_0003",
            text="Pricing made simple.",
        ),
    ), {VIDEO_ID: VIDEO_DIGEST})
    validate_content(content, FACTS)
    edited = clip_by_id(content, "clp_caption_scn_pricing_asr_0003")
    assert edited.object.text == "Pricing made simple."
    assert edited.object.caption.state == "independent"
    assert edited.object.caption.source_range == TimeRange(
        start=12 * SOURCE_TIMEBASE,
        end=18 * SOURCE_TIMEBASE,
    )
    source = clip_by_id(content, "clp_scn_pricing_source")
    assert source.source.source_range.duration == 13 * SOURCE_TIMEBASE
    assert source.range.duration == 13 * SOURCE_TIMEBASE


def test_selection_rejects_disconnected_and_unknown_sentences():
    sentences = source_sentences(WORDS, duration_ticks=FACT["duration_ticks"])
    with pytest.raises(ValueError, match="contiguous"):
        resolve_selection(
            sentences,
            SourceSelectionAnswer(sentence_ids=["asr_0002", "asr_0005"]),
        )
    with pytest.raises(ValueError, match="unknown"):
        resolve_selection(
            sentences,
            SourceSelectionAnswer(sentence_ids=["not-a-sentence"]),
        )


def test_narration_annotation_accepts_item_wrapped_needs():
    from app.models.schemas import AnnotateNarrationArgs

    args = AnnotateNarrationArgs(
        alignment_id=uuid4(),
        expected_timing_digest="a" * 64,
        sentences=[{
            "sentence_id": "s0001",
            "role": "evidence",
            "weight": "main",
            "entities": ["annual plan"],
            "needs": {"item": "native_text"},
            "emphasis_word_ids": [],
        }],
    )
    assert args.sentences[0].needs == ["native_text"]


def test_word_axis_preserves_zero_duration_token_text_with_real_sentence_bounds():
    sentences = source_sentences([
        word("Annual", 10, 11),
        word(" plans.", 11, 12),
        word(" We", 12.06, 12.06),
        word(" include", 12.08, 13),
        word(" support.", 13, 14),
    ], duration_ticks=FACT["duration_ticks"])
    assert len(sentences) == 2
    assert sentences[0].start == 10
    assert sentences[0].end == 12
    assert sentences[1].start == 12.06
    assert sentences[1].end == 14
    assert sentences[1].text == "We include support."

    with pytest.raises(ValueError, match="no usable"):
        source_sentences([word("Silent.", 1, 1)], duration_ticks=FACT["duration_ticks"])
    with pytest.raises(ValueError, match="non-monotonic"):
        source_sentences([word("First", 3, 4), word("Backwards", 2, 5)], duration_ticks=FACT["duration_ticks"])


def test_word_axis_rejects_overflow():
    with pytest.raises(ValueError, match="exceeds"):
        source_sentences([word("Beyond.", 39, 41)], duration_ticks=FACT["duration_ticks"])


@pytest.mark.asyncio
async def test_ready_narration_audio_and_caption_provenance():
    content = await expanded_content()
    payload = NarrationPayload(
        source_timebase=SOURCE_TIMEBASE,
        duration_ticks=13 * SOURCE_TIMEBASE,
        sentences=[
            NarrationSentence(
                sentence_id="s0001",
                text="Annual plans",
                text_start=0,
                text_end=12,
                start_tick=0,
                end_tick=5 * SOURCE_TIMEBASE,
                match=1.0,
                status="aligned",
                words=[NarrationWord(
                    word_id="w000001",
                    text="Annual plans",
                    text_start=0,
                    text_end=12,
                    start_tick=0,
                    end_tick=5 * SOURCE_TIMEBASE,
                    timing="anchored",
                )],
            ),
            NarrationSentence(
                sentence_id="s0002",
                text="include support.",
                text_start=13,
                text_end=29,
                start_tick=5 * SOURCE_TIMEBASE,
                end_tick=13 * SOURCE_TIMEBASE,
                match=1.0,
                status="aligned",
                words=[NarrationWord(
                    word_id="w000002",
                    text="include support.",
                    text_start=13,
                    text_end=29,
                    start_tick=5 * SOURCE_TIMEBASE,
                    end_tick=13 * SOURCE_TIMEBASE,
                    timing="anchored",
                )],
            ),
        ],
    )
    alignment_id = uuid4()
    alignment = SimpleNamespace(
        id=alignment_id,
        audio_snapshot_id=AUDIO_ID,
        audio_digest=AUDIO_DIGEST,
        status="READY",
        content_digest="f" * 64,
        algorithm="minimax-t2a-v2-sentence-v1",
        payload=payload.model_dump(mode="json"),
    )
    from app.editing.revisions import AddNarrationAction

    content = apply_ops(content, expand_revision_action(
        AddNarrationAction(
            action="add_narration",
            source_id=AUDIO_ID,
            alignment_id=alignment_id,
            scene_id="scn_pricing",
        ),
        content,
        facts=FACTS,
        narration_alignment=alignment,
    ), {VIDEO_ID: VIDEO_DIGEST, AUDIO_ID: AUDIO_DIGEST})
    validate_content(content, FACTS)

    narration_captions = [
        clip
        for track in content.timeline.tracks
        if track.track_id == "trk_narration_caption_scn_pricing"
        for clip in track.clips
    ]
    assert len(narration_captions) == 2
    assert narration_captions[0].object.caption.narration_alignment_id == alignment_id
    assert narration_captions[0].object.caption.narration_content_digest == "f" * 64

    dialogue = clip_by_id(content, "clp_dialogue_scn_pricing")
    assert dialogue.range.duration == 13 * SOURCE_TIMEBASE
    assert dialogue.source.source_range.duration == 13 * SOURCE_TIMEBASE
    assert narration_captions[1].range.start == 5 * SOURCE_TIMEBASE
    assert narration_captions[1].range.end == 13 * SOURCE_TIMEBASE
    spec = compile_video_spec(
        content,
        FACTS,
        composition_id=COMPOSITION_ID,
        version_id=VERSION_ID,
        content_digest="e" * 64,
    )
    compiled = next(
        clip for track in spec["tracks"] for clip in track["clips"]
        if clip["clip_id"] == "clp_dialogue_scn_pricing"
    )
    assert compiled["source"]["end_frame"] == 390

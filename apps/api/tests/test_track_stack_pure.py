"""Pure tests for app.pipeline.track_stack (ADR-113 §4 + ADR-114 NLE 轴).

No database, no LLM, no HTTP — build_track_stack maps a render_spec dict to
the deliverable card's inspection face; branch coverage lives here because
the projection is deterministic and drift risk is low.
"""

from app.pipeline.track_stack import _ruler_ticks, build_track_stack


def _spec(segments, caption_track=None, music=None, dub=None, asset_id=None):
    spec = {
        "segments": segments,
        "caption_track": caption_track or [],
        "music": music,
        "dub": dub,
    }
    if asset_id:
        spec["asset_id"] = asset_id
    return spec


def _seg(start, end, **kw):
    s = {"start": start, "end": end}
    s.update(kw)
    return s


def _word(text, start, end):
    return {"text": text, "start": start, "end": end}


# ---- video lane ------------------------------------------------------------


def test_video_lane_concatenates_kept_segments_on_the_output_clock():
    stack = build_track_stack(
        _spec(
            [
                _seg(10.0, 25.0),  # kept — 15s
                _seg(30.0, 40.0, hidden=True),  # cut — never a block
                _seg(50.0, 58.0),  # kept — 8s
            ],
            asset_id="asset-a",
        )
    )
    assert stack is not None
    lane = stack["video_lane"]
    assert [(b["out_start"], b["out_end"]) for b in lane] == [(0.0, 15.0), (15.0, 23.0)]
    # src spans keep the SOURCE clock (the cross-highlight's address).
    assert [(b["src_start"], b["src_end"]) for b in lane] == [(10.0, 25.0), (50.0, 58.0)]
    assert [b["asset_id"] for b in lane] == ["asset-a", "asset-a"]
    # Labels arrive preformatted — the client never formats time.
    assert lane[0]["src_label"] == "0:10–0:25"
    assert lane[0]["out_label"] == "0:00–0:15"
    assert lane[1]["out_label"] == "0:15–0:23"


def test_video_lane_per_segment_donor_overrides_the_spec_source():
    stack = build_track_stack(
        _spec(
            [_seg(0.0, 5.0), _seg(0.0, 5.0, asset_id="asset-b")],
            asset_id="asset-a",
        )
    )
    assert [b["asset_id"] for b in stack["video_lane"]] == ["asset-a", "asset-b"]


def test_no_kept_segments_yields_no_stack():
    assert build_track_stack(_spec([_seg(0.0, 5.0, hidden=True)])) is None
    assert build_track_stack(_spec([])) is None
    assert build_track_stack({"no_segments": True}) is None
    assert build_track_stack("not-a-dict") is None


# ---- text lane -------------------------------------------------------------


def test_text_lane_groups_words_per_segment_and_shifts_to_the_output_axis():
    stack = build_track_stack(
        _spec(
            [_seg(10.0, 20.0), _seg(30.0, 40.0)],
            caption_track=[
                _word("你好", 10.0, 11.0),
                _word("世界", 11.0, 12.0),
                _word("再见", 30.0, 31.0),
            ],
        )
    )
    assert stack is not None
    blocks = stack["text_lane"]
    # Segment 1's words group into one cue, shifted by −10 (its out offset 0);
    # segment 2's lone word lands at out 20..21 (30 → 10 + out offset 10).
    assert len(blocks) == 2
    assert blocks[0]["text"] == "你好世界"
    assert (blocks[0]["out_start"], blocks[0]["out_end"]) == (0.0, 2.0)
    assert blocks[0]["label"] == "0:00–0:02"
    assert blocks[1]["text"] == "再见"
    assert (blocks[1]["out_start"], blocks[1]["out_end"]) == (10.0, 11.0)
    assert blocks[1]["label"] == "0:10–0:11"


def test_text_lane_assigns_a_word_to_the_segment_its_center_falls_in():
    # A word straddling a kept segment's end (center inside it) reads within
    # that segment's kept span — clamped at the segment bounds. A word whose
    # center falls in the CUT gap belongs to no kept segment — dropped with
    # its (cut) audio, never re-homed.
    stack = build_track_stack(
        _spec(
            [_seg(0.0, 10.0), _seg(20.0, 30.0)],
            caption_track=[_word("跨", 8.0, 12.0), _word("隙", 10.0, 20.0)],
        )
    )
    blocks = stack["text_lane"]
    assert len(blocks) == 1
    assert blocks[0]["text"] == "跨"
    assert (blocks[0]["out_start"], blocks[0]["out_end"]) == (8.0, 10.0)


def test_text_lane_latin_tokens_regain_their_space():
    stack = build_track_stack(
        _spec(
            [_seg(0.0, 10.0)],
            caption_track=[_word("hello", 0.0, 1.0), _word("world", 1.0, 2.0)],
        )
    )
    assert stack["text_lane"][0]["text"] == "hello world"


# ---- ruler (ADR-114) -------------------------------------------------------


def test_ruler_short_clip_steps_by_fives_with_labeled_ends():
    ticks = _ruler_ticks(45.0)
    labeled = [t for t in ticks if t["label"] is not None]
    assert [t["t"] for t in labeled] == [float(s) for s in range(0, 46, 5)]
    assert labeled[0]["label"] == "0:00"
    assert labeled[-1]["label"] == "0:45"
    # Minor ticks carry no label (geometry only).
    assert any(t["label"] is None for t in ticks)


def test_ruler_step_law_scales_with_duration():
    # 45s → 5s majors; 400s → 60s majors (≤10 labeled ticks).
    majors = lambda total: [
        t["t"] for t in _ruler_ticks(total) if t["label"] is not None
    ]
    assert majors(45.0)[:3] == [0.0, 5.0, 10.0]
    assert majors(400.0)[:3] == [0.0, 60.0, 120.0]
    # t=total always lands labeled, even off-step.
    assert majors(47.3)[-1] == 47.3
    assert _ruler_ticks(47.3)[-1]["label"] == "0:47"


def test_ruler_never_exceeds_ten_labels_and_handles_zero():
    for total in (9.0, 59.0, 61.0, 299.0, 601.0, 3599.0):
        labeled = [t for t in _ruler_ticks(total) if t["label"] is not None]
        assert len(labeled) <= 11  # ≤10 steps + the off-step end tick
        assert labeled[0]["label"] == "0:00"
    assert _ruler_ticks(0.0) == []


def test_stack_carries_the_ruler():
    stack = build_track_stack(_spec([_seg(0.0, 45.0)]))
    assert stack is not None
    assert stack["ruler"][-1] == {"t": 45.0, "label": "0:45"}


# ---- modifiers -------------------------------------------------------------


def test_modifiers_are_presence_only():
    stack = build_track_stack(
        _spec([_seg(0.0, 5.0)], music={"enabled": True}, dub={"url": "x"})
    )
    assert stack["modifiers"] == {"music": True, "dub": True}
    stack = build_track_stack(_spec([_seg(0.0, 5.0)], music={"enabled": False}))
    assert stack["modifiers"] == {"music": False, "dub": False}

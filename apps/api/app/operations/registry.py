"""Op registry: the Operation Model vocabulary (ADR-032 D5).

Each op maps to a params schema plus either a pure apply function
(``dict spec, params -> new dict spec``) or the ``precomputed`` marker for
LLM-backed ops whose endpoint computes the new spec itself (translate/dub).

Spec-mutating helpers (remove_range / set_trim) live in
``app.pipeline.clip_spec`` — the Python mirror of the TS helpers in
``packages/clip/src/types.ts``; the registry only wraps them with params
validation. The server is the application authority; the frontend previews.

 Guards (ADR-032): ``snapshot``/``set_spec`` are system-internal (baseline
lazy-creation / drift self-healing) and are rejected from client calls;
``restore_range`` is deliberately absent (N-16 — captions are unrecoverable,
restore semantics live in the snapshot layer).
"""

from dataclasses import dataclass
from typing import Callable, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.schemas import ClipAnchor, ClipLayer, ClipRect, ClipSegment, ClipSpec, LayerMedia
from app.pipeline.clip_spec import remove_range, set_trim
from app.tools.music import music_file_path
from app.tools.storage import public_url


# ---- params schemas ----------------------------------------------------


class RemoveRangeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class SetTrimParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class SetTitleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    enabled: bool


class SetCaptionStyleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Literal["clean-bottom", "karaoke-highlight", "fade-in", "pop-in", "slide-up", "stacking"] | None = None
    enabled: bool | None = None
    position: dict | None = None  # {x, y} normalized center; validated via ClipSpec round-trip


class SetMusicParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    music_id: str | None = None
    enabled: bool
    gain_db: float | None = None


class SetCropParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0)


class SetAspectParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect: Literal["9:16", "1:1", "16:9"]


class SetCaptionTextParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    text: str


class SetSpecParams(BaseModel):
    """system 内部 op（漂移自愈）：整包替换，不对客户端暴露。"""

    model_config = ConfigDict(extra="forbid")

    render_spec: dict


class RestoreVersionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID


class TranslateCaptionsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_language: str


class SetDubParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    gain_db: float | None = None
    target_language: str | None = None


class RemoveFillerOpParams(BaseModel):
    """Journaled by the remove_filler runner (agent-loop-upgrade W4) — counts
    are runner-computed after the pass, kept as the semantic signal for
    calibration reflux; not chat-proposable (precomputed)."""

    model_config = ConfigDict(extra="forbid")

    filler_count: int | None = None
    repeat_count: int | None = None


class ReframeClipOpParams(BaseModel):
    """Journaled by the reframe_clip runner (ADR-045) — the resolved mode and
    keyframe count are runner-computed, kept as the semantic signal for
    calibration reflux; not chat-proposable (precomputed)."""

    model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    keyframe_count: int | None = None


class SnapshotParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- 操作集闭包 ops (ADR-044 D7) — registered, NOT in the LLM vocabulary ---
# Payloads are entity references (segment ids / anchors / enums) — an LLM
# never proposes an absolute timecode; coordinate math stays in code.

TRANSITION_ENUM = Literal["none", "fade", "dip"]
# 枚举封顶 (ADR-016 L3 修订): at most this many non-none transitions per clip.
MAX_TRANSITIONS_PER_CLIP = 3


class ReorderSegmentsParams(BaseModel):
    """Full permutation of the KEPT segment ids (hidden segments keep their
    relative order at the tail — they carry no output position)."""

    model_config = ConfigDict(extra="forbid")

    order: list[str] = Field(min_length=1)


class InsertSegmentParams(BaseModel):
    """A hetero main-track splice (切): the donor asset's span. ``url`` is the
    donor's storage-seam URL, RESOLVED AT WRITE by the serving caller (the
    bake seam absolutizes it like every declared url_field)."""

    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    url: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    after_segment_id: str | None = None  # None = append at the end
    transition: TRANSITION_ENUM = "none"
    provenance: Literal["real", "generated"] | None = None


class SetTransitionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    transition: TRANSITION_ENUM


class AddLayerParams(BaseModel):
    """A layer-track item minus its id (minted on apply). The anchor may
    reference a KEPT segment only — anchors ride surviving content."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["broll", "text_callout", "pip", "motion_graphic"]
    anchor: ClipAnchor
    duration_seconds: float = Field(gt=0)
    rect: ClipRect
    z: int = 0
    source_ref: dict | None = None
    media: LayerMedia | None = None
    provenance: Literal["real", "generated"]


class RemoveLayerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer_id: str


class MoveLayerParams(BaseModel):
    """Re-anchor / re-frame / re-time an existing layer (move = address or
    geometry change; at least one of the optional fields is required)."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str
    anchor: ClipAnchor | None = None
    rect: ClipRect | None = None
    z: int | None = None
    duration_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _at_least_one(self) -> "MoveLayerParams":
        if self.anchor is None and self.rect is None and self.z is None and self.duration_seconds is None:
            raise ValueError("move_layer: nothing to move — pass anchor, rect, z, or duration_seconds")
        return self


# ---- pure apply functions (TS ports; dict in / dict out) ----------------


def _roundtrip(spec: dict) -> ClipSpec:
    """Validate the spec through the Pydantic contract."""
    return ClipSpec.model_validate(spec)


def _apply_remove_range(spec: dict, params: dict) -> dict:
    p = RemoveRangeParams.model_validate(params)
    cs = _roundtrip(spec)
    return remove_range(cs, p.start, p.end).model_dump(mode="json")


def _apply_set_trim(spec: dict, params: dict) -> dict:
    p = SetTrimParams.model_validate(params)
    cs = _roundtrip(spec)
    return set_trim(cs, p.start, p.end).model_dump(mode="json")


def _apply_set_title(spec: dict, params: dict) -> dict:
    p = SetTitleParams.model_validate(params)
    cs = _roundtrip(spec)
    cs.title.text = p.text
    cs.title.enabled = p.enabled
    return cs.model_dump(mode="json")


def _apply_set_caption_style(spec: dict, params: dict) -> dict:
    p = SetCaptionStyleParams.model_validate(params)
    cs = _roundtrip(spec)
    if p.preset is not None:
        cs.caption_style_preset = p.preset
    if p.enabled is not None:
        cs.caption_enabled = p.enabled
    if p.position is not None:
        from app.models.schemas import Point

        cs.caption_position = Point.model_validate(p.position)
    return cs.model_dump(mode="json")


def _apply_set_music(spec: dict, params: dict) -> dict:
    p = SetMusicParams.model_validate(params)
    cs = _roundtrip(spec)
    cs.music.music_id = p.music_id
    # Absolute object-storage URL, derived from the id via the uniform key
    # pattern (no table lookup): the renderer fetches spec.music.url
    # server-side, where a root-relative stream endpoint has no host — and
    # the run-time add_music morph journals through this same apply, so both
    # write paths must agree (2026-08-17: they didn't, add_music was broken).
    cs.music.url = public_url(music_file_path(p.music_id)) if p.music_id else None
    cs.music.enabled = p.enabled
    if p.gain_db is not None:
        cs.music.gain_db = p.gain_db
    return cs.model_dump(mode="json")


def _apply_set_crop(spec: dict, params: dict) -> dict:
    p = SetCropParams.model_validate(params)
    cs = _roundtrip(spec)
    cs.crop.x = p.x
    cs.crop.y = p.y
    cs.crop.scale = p.scale
    return cs.model_dump(mode="json")


def _apply_set_aspect(spec: dict, params: dict) -> dict:
    p = SetAspectParams.model_validate(params)
    cs = _roundtrip(spec)
    cs.aspect = p.aspect
    return cs.model_dump(mode="json")


def _apply_set_caption_text(spec: dict, params: dict) -> dict:
    p = SetCaptionTextParams.model_validate(params)
    cs = _roundtrip(spec)
    if p.index >= len(cs.caption_track):
        raise ValueError(f"caption index {p.index} out of range")
    cs.caption_track[p.index].text = p.text
    return cs.model_dump(mode="json")


# ---- 操作集闭包 apply functions (ADR-044 D7) --------------------------------
# Addressing = (track, item_id, op): the op's declared `writes` name the track
# (boot-reconciled against the partition); the applies below enforce item
# membership on that track — no LLM-guessed field paths, no absolute
# timecodes in payloads.


def _kept_segment(cs: ClipSpec, segment_id: str, *, op: str) -> ClipSegment:
    seg = next((s for s in cs.segments if s.id == segment_id), None)
    if seg is None:
        raise ValueError(f"{op}: segment '{segment_id}' not found on track 'main'")
    if seg.hidden:
        raise ValueError(f"{op}: segment '{segment_id}' is hidden — address kept content")
    return seg


def _layer(cs: ClipSpec, layer_id: str, *, op: str) -> ClipLayer:
    layer = next((l for l in cs.layers if l.id == layer_id), None)
    if layer is None:
        raise ValueError(f"{op}: layer '{layer_id}' not found on track 'layers'")
    return layer


def _check_anchor_resolvable(cs: ClipSpec, anchor: ClipAnchor, *, op: str) -> None:
    if anchor.kind == "segment":
        _kept_segment(cs, anchor.segment_id or "", op=op)


def _apply_reorder_segments(spec: dict, params: dict) -> dict:
    p = ReorderSegmentsParams.model_validate(params)
    cs = _roundtrip(spec)
    kept = [s for s in cs.segments if not s.hidden]
    by_id = {s.id: s for s in kept}
    if set(p.order) != set(by_id) or len(p.order) != len(kept):
        raise ValueError("reorder_segments: order must be exactly the kept segment ids")
    hidden = [s for s in cs.segments if s.hidden]
    cs.segments = [by_id[i] for i in p.order] + hidden
    return cs.model_dump(mode="json")


def _transition_count(cs: ClipSpec) -> int:
    return sum(1 for s in cs.segments if not s.hidden and s.transition != "none")


def _apply_insert_segment(spec: dict, params: dict) -> dict:
    p = InsertSegmentParams.model_validate(params)
    if p.end <= p.start:
        raise ValueError("insert_segment: end must be after start")
    cs = _roundtrip(spec)
    if p.transition != "none" and _transition_count(cs) >= MAX_TRANSITIONS_PER_CLIP:
        raise ValueError(
            f"insert_segment: at most {MAX_TRANSITIONS_PER_CLIP} transitions per clip"
        )
    seg = ClipSegment(
        asset_id=p.asset_id,
        url=p.url,
        start=p.start,
        end=p.end,
        hidden=False,
        provenance=p.provenance,
        transition=p.transition,
    )
    if p.after_segment_id is None:
        cs.segments.append(seg)
    else:
        anchor = _kept_segment(cs, p.after_segment_id, op="insert_segment")
        cs.segments.insert(cs.segments.index(anchor) + 1, seg)
    return cs.model_dump(mode="json")


def _apply_set_transition(spec: dict, params: dict) -> dict:
    p = SetTransitionParams.model_validate(params)
    cs = _roundtrip(spec)
    seg = _kept_segment(cs, p.segment_id, op="set_transition")
    if p.transition != "none" and seg.transition == "none":
        if _transition_count(cs) >= MAX_TRANSITIONS_PER_CLIP:
            raise ValueError(
                f"set_transition: at most {MAX_TRANSITIONS_PER_CLIP} transitions per clip"
            )
    seg.transition = p.transition
    return cs.model_dump(mode="json")


def _apply_add_layer(spec: dict, params: dict) -> dict:
    p = AddLayerParams.model_validate(params)
    cs = _roundtrip(spec)
    _check_anchor_resolvable(cs, p.anchor, op="add_layer")
    cs.layers.append(ClipLayer(**p.model_dump(mode="json")))
    return cs.model_dump(mode="json")


def _apply_remove_layer(spec: dict, params: dict) -> dict:
    p = RemoveLayerParams.model_validate(params)
    cs = _roundtrip(spec)
    layer = _layer(cs, p.layer_id, op="remove_layer")
    cs.layers.remove(layer)
    return cs.model_dump(mode="json")


def _apply_move_layer(spec: dict, params: dict) -> dict:
    p = MoveLayerParams.model_validate(params)
    cs = _roundtrip(spec)
    layer = _layer(cs, p.layer_id, op="move_layer")
    if p.anchor is not None:
        _check_anchor_resolvable(cs, p.anchor, op="move_layer")
        layer.anchor = p.anchor
    if p.rect is not None:
        layer.rect = p.rect
    if p.z is not None:
        layer.z = p.z
    if p.duration_seconds is not None:
        layer.duration_seconds = p.duration_seconds
    return cs.model_dump(mode="json")


# ---- registry ------------------------------------------------------------


@dataclass(frozen=True)
class OpDef:
    params_model: type[BaseModel]
    # Pure apply function, or None for "precomputed" ops (LLM endpoints hand
    # the new spec to apply_precomputed) and system-internal ops handled
    # specially by the service (snapshot / restore_version).
    apply: Callable[[dict, dict], dict] | None
    client_allowed: bool = True
    precomputed: bool = False
    # "When to use" — injected into the intent prompt's op vocabulary.
    description: str = ""
    # False keeps the op out of the LLM's proposable vocabulary (registered +
    # client-callable, but not chat-proposable yet — ADR-044 操作集闭包 ops
    # ride the skill batch later).
    llm_visible: bool = True
    # Spec top-level fields this op mutates — reconciled against the track
    # registry's fields partition at boot (ADR-044; "*" = whole-spec
    # snapshot/system ops).
    writes: tuple[str, ...] = ()


OP_REGISTRY: dict[str, OpDef] = {
    "remove_range": OpDef(
        RemoveRangeParams, _apply_remove_range,
        description="Cut/delete a source time range (params: start, end in seconds)",
        writes=("segments", "caption_track"),
    ),
    "set_trim": OpDef(
        SetTrimParams, _apply_set_trim,
        description="Move the clip's outer in/out points (params: start, end in seconds)",
        writes=("segments",),
    ),
    "set_title": OpDef(
        SetTitleParams, _apply_set_title,
        description="Set the title/hook overlay text and on/off",
        writes=("title",),
    ),
    "set_caption_style": OpDef(
        SetCaptionStyleParams, _apply_set_caption_style,
        description="Change caption style preset / visibility / position",
        writes=("caption_style_preset", "caption_enabled", "caption_position"),
    ),
    "set_music": OpDef(
        SetMusicParams, _apply_set_music,
        description="Set background music track / on/off / gain",
        writes=("music",),
    ),
    "set_crop": OpDef(
        SetCropParams, _apply_set_crop,
        description="Reframe: normalized center (x, y) + zoom scale",
        writes=("crop",),
    ),
    "set_aspect": OpDef(
        SetAspectParams, _apply_set_aspect,
        description="Switch aspect ratio between 9:16, 1:1 and 16:9",
        writes=("aspect",),
    ),
    "set_caption_text": OpDef(
        SetCaptionTextParams, _apply_set_caption_text,
        description="Fix the text of one caption cue (params: index, text)",
        writes=("caption_track",),
    ),
    "restore_version": OpDef(
        RestoreVersionParams, None,  # service resolves snapshot
        description="Restore the spec to a previous operation's snapshot (undo history)",
        writes=("*",),
    ),
    "translate_captions": OpDef(
        TranslateCaptionsParams, None, precomputed=True,
        writes=("caption_track", "translation_track", "title", "target_language"),
    ),
    "set_dub": OpDef(SetDubParams, None, precomputed=True, writes=("dub",)),
    "remove_filler": OpDef(
        RemoveFillerOpParams, None, precomputed=True,
        writes=("segments", "caption_track"),
    ),
    "reframe_clip": OpDef(
        ReframeClipOpParams, None, precomputed=True,
        writes=("crop", "crop_track"),
    ),
    # 操作集闭包 (ADR-044 D7): registered + client-callable, deliberately NOT
    # in the LLM vocabulary this batch (llm_visible=False — they ride the
    # skill batch later).
    "reorder_segments": OpDef(
        ReorderSegmentsParams, _apply_reorder_segments,
        llm_visible=False,
        description="Reorder the kept segments (params: order = kept segment ids)",
        writes=("segments",),
    ),
    "insert_segment": OpDef(
        InsertSegmentParams, _apply_insert_segment,
        llm_visible=False,
        description="Splice a donor asset's span into the main track (切)",
        writes=("segments",),
    ),
    "set_transition": OpDef(
        SetTransitionParams, _apply_set_transition,
        llm_visible=False,
        description="Set a segment's entry-edge transition (none/fade/dip)",
        writes=("segments",),
    ),
    "add_layer": OpDef(
        AddLayerParams, _apply_add_layer,
        llm_visible=False,
        description="Add a layer-track item (anchor + rect + media)",
        writes=("layers",),
    ),
    "remove_layer": OpDef(
        RemoveLayerParams, _apply_remove_layer,
        llm_visible=False,
        description="Remove a layer-track item (params: layer_id)",
        writes=("layers",),
    ),
    "move_layer": OpDef(
        MoveLayerParams, _apply_move_layer,
        llm_visible=False,
        description="Re-anchor / re-frame / re-time a layer-track item",
        writes=("layers",),
    ),
    # system-internal: baseline lazy-creation / drift self-healing (ADR-032 D7)
    "snapshot": OpDef(SnapshotParams, None, client_allowed=False, writes=("*",)),
    "set_spec": OpDef(SetSpecParams, None, client_allowed=False, writes=("*",)),
}

SOURCE_REGISTRY = frozenset({"editor", "chat", "mcp", "system"})


def validate_op(op: str, params: dict, *, client: bool) -> dict:
    """Validate an op name + params against the registry. Returns normalized
    params (model_dump). Raises KeyError / ValueError on rejection."""
    opdef = OP_REGISTRY.get(op)
    if opdef is None:
        raise KeyError(op)
    if client and not opdef.client_allowed:
        raise ValueError(f"op '{op}' is system-internal")
    return opdef.params_model.model_validate(params).model_dump(mode="json")

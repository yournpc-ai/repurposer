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

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import ClipSpec
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

    preset: Literal["clean-bottom", "karaoke-highlight", "fade-in", "pop-in", "slide-up"] | None = None
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


class SnapshotParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


OP_REGISTRY: dict[str, OpDef] = {
    "remove_range": OpDef(
        RemoveRangeParams, _apply_remove_range,
        description="Cut/delete a source time range (params: start, end in seconds)",
    ),
    "set_trim": OpDef(
        SetTrimParams, _apply_set_trim,
        description="Move the clip's outer in/out points (params: start, end in seconds)",
    ),
    "set_title": OpDef(
        SetTitleParams, _apply_set_title,
        description="Set the title/hook overlay text and on/off",
    ),
    "set_caption_style": OpDef(
        SetCaptionStyleParams, _apply_set_caption_style,
        description="Change caption style preset / visibility / position",
    ),
    "set_music": OpDef(
        SetMusicParams, _apply_set_music,
        description="Set background music track / on/off / gain",
    ),
    "set_crop": OpDef(
        SetCropParams, _apply_set_crop,
        description="Reframe: normalized center (x, y) + zoom scale",
    ),
    "set_aspect": OpDef(
        SetAspectParams, _apply_set_aspect,
        description="Switch aspect ratio between 9:16, 1:1 and 16:9",
    ),
    "set_caption_text": OpDef(
        SetCaptionTextParams, _apply_set_caption_text,
        description="Fix the text of one caption cue (params: index, text)",
    ),
    "restore_version": OpDef(
        RestoreVersionParams, None,  # service resolves snapshot
        description="Restore the spec to a previous operation's snapshot (undo history)",
    ),
    "translate_captions": OpDef(TranslateCaptionsParams, None, precomputed=True),
    "set_dub": OpDef(SetDubParams, None, precomputed=True),
    "remove_filler": OpDef(RemoveFillerOpParams, None, precomputed=True),
    # system-internal: baseline lazy-creation / drift self-healing (ADR-032 D7)
    "snapshot": OpDef(SnapshotParams, None, client_allowed=False),
    "set_spec": OpDef(SetSpecParams, None, client_allowed=False),
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

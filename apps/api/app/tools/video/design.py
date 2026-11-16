"""Incremental Composition authoring and immutable version saving.

``design_video`` merges complete settings, sources and entities into one
ConversationContext-backed working draft. Only ``save=true`` resolves and
validates the assembled Composition, then calls ``apply_composition_edits``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from copy import deepcopy
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.edits import AddClip, BindSource, ClipEntityWrite, EntityWrites, Op, apply_ops
from app.editing.schemas import (
    Clip,
    CompositionContent,
    GeneratorObject,
    ImageObject,
    LayoutBox,
    RemotionProjectSource,
    RemotionResource,
    RemotionSourceFile,
    Scene,
    SourceBinding,
    SCHEMA_VERSION,
    TimeRange,
    Track,
    Transform,
    VersionSettings,
    VideoObject,
    WebObject,
)
from app.editing.service import (
    compute_change_set,
    version_read_dict,
)
from app.editing.store import (
    apply_composition_edits,
    content_of,
    get_video_version,
    snapshot_facts,
)
from app.editing.storyboard import storyboard_payload
from app.editing.audio import MusicBed, instantiate_music_bed
from app.editing.web_shots import ViewFact
from app.editing.timing import (
    SOURCE_TIMEBASE,
    frames_to_ticks,
    output_ticks_to_source_ticks,
    seconds_to_ticks,
)
from app.editing.presets import PresetError, expand_preset
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetStatus,
    AssetType,
    BuiltInSkillReference,
    ExternalSkillReference,
    SkillReference,
    VideoDraftRef,
    VideoScrubTarget,
)
from app.models.tables import Asset, Output, Project, SourceSnapshot
from app.skills.loading import SkillCreativeContext, load_skill_creative_context
from app.agents.errors import AgentOutputError, AgentStopError
from app.agents.working_drafts import (
    WorkingDraftUpdated,
    apply_working_draft_writes,
    working_draft_arguments,
)
from app.tools.research.capture import CapturePlan, CaptureRequest, capture_plan_digest, compile_capture_request
from app.tools.video.preparation import (
    snapshot_audio_asset,
    snapshot_image_asset,
    snapshot_music_track,
    snapshot_video_asset,
    snapshot_video_output,
    snapshot_web_asset,
)

logger = structlog.get_logger()

# The capture settle wait (the film chain's same law): the design drafts
# from the captured world, so a freshly-declared URL's capture completes
# inside the design beat — bounded, honestly refused past the ceiling.
_CAPTURE_SETTLE_WAIT_S = 1800.0
_CAPTURE_SETTLE_POLL_S = 2.0


class DesignError(ValueError):
    """A design refusal whose text is model-facing (capture gap, grounding
    failure, write-door rejection)."""


class CandidateDesignError(DesignError):
    """Composition content is invalid before any version was saved."""

    def __init__(
        self,
        message: str,
        *,
        errors: list[dict] | None = None,
        working_content: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.issues = errors or [{"loc": [], "type": "content_validation", "msg": message}]
        self.working_content = deepcopy(working_content)


class CompositionCopyReference(BaseModel):
    """Display copy linked to a frozen line without re-transcribing its quote."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(
        default=None, min_length=1, max_length=9000,
        description="Omit for verbatim copy. Supply only the actual displayed wording when it differs from the frozen line.",
    )
    snapshot_id: UUID
    snapshot_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="Optional immutable digest returned with the source snapshot; when supplied, the server verifies it instead of trusting the reference.",
    )
    line_id: str = Field(min_length=1, max_length=80)


class SkillGeneratorPlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    scene_id: str
    track_id: str
    clip_id: str
    layout: LayoutBox | None = None


class CompositionScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    intent: str = Field(min_length=1, max_length=2000)
    visual_description: str | None = Field(default=None, max_length=4000)


class CompositionSceneAuthoring(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(
        min_length=1, max_length=64,
        description="Exact scene_id from next_unfilled_scene; write only that current Scene.",
    )
    snapshot_id: UUID | None = Field(
        default=None,
        description="Frozen SourceSnapshot for this Scene; omit for a native copy-only Scene.",
    )
    view_id: str | None = Field(
        default=None, max_length=80,
        description="Exact view_id belonging to snapshot_id; use the frozen source catalog.",
    )
    element_id: str | None = Field(
        default=None, max_length=80,
        description="Optional real element id inside view_id for the camera focus.",
    )
    source_start_seconds: float | None = Field(
        default=None, ge=0, allow_inf_nan=False,
        description="Explicit source-second start; omit it for a semantic source_query or to start at zero.",
    )
    source_end_seconds: float | None = Field(
        default=None, gt=0, allow_inf_nan=False,
        description="Explicit source-second end; omit it for a semantic source_query. Its duration sets this Scene's duration at 1x.",
    )
    source_query: str | None = Field(
        default=None, min_length=1, max_length=2000,
        description="Full semantic passage goal, including the topic and whether to keep the previous sentence; never merely quote the preceding sentence. The server resolves real ASR sentence ids into a validated source window; never pair this with explicit source seconds.",
    )
    captions_asr: bool = Field(
        default=False,
        description="Derive native TextObjects inside THIS source Scene on an ordinary caption track. Never create a caption-only Scene or a separate caption source.",
    )
    narration_snapshot_id: UUID | None = Field(
        default=None,
        description="Frozen audio SourceSnapshot prepared by prepare_narration; place it as an ordinary dialogue AudioObject with its aligned native captions.",
    )
    narration_alignment_id: UUID | None = Field(
        default=None,
        description="READY NarrationAlignment for narration_snapshot_id; supplies the actual narration sentence timings and provenance.",
    )
    source_gain_db: float | None = Field(
        default=None, ge=-60, le=12,
        description="Optional original-audio gain for this VideoObject; the source picture and original audio stay synchronized.",
    )
    source_muted: bool = Field(
        default=False,
        description="Mute the original audio without changing the source picture or creating a separate audio timeline.",
    )
    source_fit: Literal["cover", "contain"] = Field(
        default="contain",
        description="Fixed framing inside the full-canvas layout; use cover for a filled vertical crop, contain to preserve the whole image.",
    )
    source_transform: Transform | None = Field(
        default=None,
        description="Optional fixed transform for the source inside its layout; no frame tracking or crop_track.",
    )
    headline: str | None = Field(
        default=None, min_length=1, max_length=9000,
        description="Native headline for title-lockup. Omit headline whenever items is non-empty.",
    )
    supporting_text: str | None = Field(
        default=None, min_length=1, max_length=9000,
        description="Optional supporting line; requires headline and is not valid with items.",
    )
    items: list[str] = Field(
        default_factory=list, max_length=6,
        description="Native items for list-reveal; omit headline and supporting_text in this form.",
    )
    text_preset: Literal["title-lockup", "list-reveal"] | None = Field(
        default=None,
        description="title-lockup needs headline; list-reveal needs items. Choose the matching form before submitting.",
    )
    source_motion: Literal["hold", "push"] = "push"

    @model_validator(mode="before")
    @classmethod
    def _empty_optional_text_is_absent(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("supporting_text") == "":
            return {**data, "supporting_text": None}
        return data

    @model_validator(mode="after")
    def _expressible_scene(self) -> "CompositionSceneAuthoring":
        if self.snapshot_id is None and self.headline is None and not self.items:
            raise ValueError("a scene needs a frozen source, headline or native items")
        if self.supporting_text is not None and self.headline is None:
            raise ValueError("supporting_text needs a headline")
        if self.items and self.headline is not None:
            raise ValueError("use either a headline lockup or an item list in one scene")
        if self.text_preset == "list-reveal" and not self.items:
            raise ValueError("list-reveal needs native items")
        if self.items and self.text_preset not in {None, "list-reveal"}:
            raise ValueError("native items use the list-reveal Preset")
        if self.text_preset == "title-lockup" and self.headline is None:
            raise ValueError("title-lockup needs a headline")
        if (
            self.source_end_seconds is not None
            and self.source_end_seconds <= (self.source_start_seconds or 0)
        ):
            raise ValueError("source_end_seconds must be after source_start_seconds")
        if self.source_query is not None and (
            self.source_start_seconds is not None or self.source_end_seconds is not None
        ):
            raise ValueError("source_query and explicit source seconds are mutually exclusive")
        if (self.source_query is not None or self.captions_asr) and self.snapshot_id is None:
            raise ValueError("ASR selection and captions require a frozen video snapshot")
        if (self.narration_snapshot_id is None) != (self.narration_alignment_id is None):
            raise ValueError("narration_snapshot_id and narration_alignment_id must arrive together")
        return self


class CompositionDesignVideoArgs(EntityWrites):
    """One complete-value write into a server-side working Composition draft."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _draft_wire(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for key in EntityWrites.model_fields:
            value = normalized.get(key)
            if value is None or value == "" or value == {}:
                normalized[key] = []
            elif isinstance(value, (dict, str)):
                normalized[key] = [value]
        for key in (
            "settings", "sources", "draft_ref", "copy_references",
            "composition_id", "scene_count", "target_seconds", "aspect",
            "background", "language", "name", "pending_disposition", "scrub",
            "focus_clip_id", "focus_element_id", "verbatim_copy",
            "scene", "scene_plan", "source_ids", "music_snapshot_id",
        ):
            if normalized.get(key) in (None, ""):
                normalized.pop(key, None)
        if normalized.get("save") in (None, ""):
            normalized["save"] = False
        return normalized

    draft_ref: VideoDraftRef | None = Field(
        default=None,
        description="Latest draft_ref returned by design_video. Omit only when starting a new draft.",
    )
    scene_id: str | None = Field(
        default=None,
        description="Existing Scene for one single-scene continuation. Put that Scene's Clips in tracks[].clips; omit on initial and save-only calls.",
    )
    scene_plan: list[CompositionScenePlan] | None = Field(
        default=None,
        max_length=6,
        description="One to six narrative Scenes in playback order; merge related beats instead of exceeding six. Server derives ranges and native entities.",
    )
    source_ids: list[UUID] | None = Field(
        default=None,
        max_length=256,
        description="Frozen SourceSnapshot ids available to this draft; the server verifies and binds their digests.",
    )
    scene: CompositionSceneAuthoring | None = Field(
        default=None,
        description="One current Scene's source, framing, native copy and Preset intent; the server derives all native entities and timing.",
    )
    music_snapshot_id: UUID | None = Field(
        default=None,
        description="Prepared audio SourceSnapshot for the existing global music-bed capability.",
    )
    composition_id: UUID | None = Field(
        default=None,
        description="For an explicitly requested open redraft, initialize the working draft from this work's current saved version.",
    )
    settings: VersionSettings | None = Field(
        default=None,
        description="Complete production settings when this call changes them; omitted settings remain unchanged.",
    )
    sources: list[SourceBinding] | None = Field(
        default=None,
        max_length=256,
        description="Complete source-binding list when this call changes it; omitted sources remain unchanged.",
    )
    save: bool = Field(
        default=False,
        description="False merges this call into the working draft. True only validates and saves an existing draft_ref; put every settings, source or entity change in an earlier save=false call.",
    )
    scrub: VideoScrubTarget | None = Field(
        default=None,
        description="Only on save=true: optionally present one bounded Scene/Clip window or isolated Object when dynamic inspection helps answer the user. Omit by default; never target the complete video.",
    )
    name: str | None = Field(default=None, max_length=255)
    copy_references: list[CompositionCopyReference] | None = Field(
        default=None,
        max_length=64,
        description="Optional provenance for native text already written to a Clip. TextObject.text always contains the display string. In copy_references, give snapshot_id and line_id; omit its text field if it matches the frozen line.",
    )
    verbatim_copy: list[str] | None = Field(
        default=None,
        max_length=64,
        description="Only when the user requires exact on-screen copy: list the original phrases in playback order. Each must appear once in a native Text Clip.",
    )
    language: str | None = Field(
        default=None,
        description="The video's language when one was agreed or named; omitted language remains unchanged.",
    )
    scene_count: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="Exact scene count explicitly fixed by the user. Never infer a constraint from your own outline.",
    )
    target_seconds: float | None = Field(
        default=None,
        gt=0,
        le=118,
        description="Exact total duration explicitly fixed by the user. Never infer a fixed duration from a short-video request.",
    )
    aspect: Literal["16:9", "9:16", "1:1"] | None = Field(
        default=None,
        description="Exact canvas aspect explicitly fixed by the user.",
    )
    background: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="Exact canvas background explicitly fixed by the user.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' engages it, 'skip' declines it, and 'none' marks an unrelated interjection.",
    )
    focus_clip_id: str | None = Field(
        default=None,
        description="Repair this exact web Clip's framing from a real frozen element; pair with focus_element_id.",
    )
    focus_element_id: str | None = Field(
        default=None,
        description="A real element id in the target Clip's current view; the server computes camera animations.",
    )
    skill_resource: SkillGeneratorPlacement | None = Field(
        default=None,
        description="Place a generator_resources id from list_skill_shots onto a visual track. "
        "Supply the target Scene and visual Track in scenes and tracks if they do not exist yet. "
        "The host creates this Clip; omit it from clips. Its fixed duration must match the Scene. "
        "Omit layout for full canvas. Use save=false.",
    )
    _working_draft: dict[str, Any] | None = PrivateAttr(default=None)
    _explicit_constraints: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _draft_target(self) -> "CompositionDesignVideoArgs":
        if self.draft_ref is not None and self.composition_id is not None:
            raise ValueError("continue a draft or initialize from composition_id, not both")
        if self.scrub is not None and not self.save:
            raise ValueError("scrub belongs only on the final save=true call")
        if (self.focus_clip_id is None) != (self.focus_element_id is None):
            raise ValueError("focus_clip_id and focus_element_id must be supplied together")
        if self.focus_clip_id is not None and (
            self.entity_writes().has_changes() or self.settings is not None or self.sources is not None
            or self.skill_resource is not None or self.scene_id is not None
            or self.scene is not None or self.scene_plan is not None
        ):
            raise ValueError("a web framing repair changes only its target Clip; submit no other content writes")
        if self.scene_plan is not None:
            if (
                not self.scene_plan or self.draft_ref is not None or self.save or self.scene is not None
                or self.scene_id is not None or self.entity_writes().has_changes()
                or self.settings is not None or self.sources is not None
            ):
                raise ValueError("scene_plan starts a new draft without raw entities or a save")
            scene_ids = [scene.scene_id for scene in self.scene_plan]
            if len(scene_ids) != len(set(scene_ids)):
                raise ValueError("scene_plan scene_id values must be unique")
        if self.source_ids is not None and self.scene_plan is None:
            raise ValueError("source_ids belongs to the initial scene_plan")
        if self.scene is not None:
            if self.draft_ref is None:
                raise ValueError("a high-level scene continuation requires an existing draft_ref")
            if self.save:
                raise ValueError("save=true only commits the existing draft; omit scene")
            if (
                self.scene_id is not None or self.scene_plan is not None
                or self.entity_writes().has_changes() or self.settings is not None or self.sources is not None
            ):
                raise ValueError("a high-level scene writes creative intent only, not raw entities")
        if self.scene_id is not None:
            if self.draft_ref is None:
                raise ValueError("a single-scene continuation requires an existing draft_ref")
            if self.save:
                raise ValueError("save=true only commits the existing draft; omit scene_id")
            if (
                self.scenes or self.clips or self.transitions
                or self.remove_scene_ids or self.remove_track_ids or self.remove_clip_ids
                or self.remove_transition_ids or self.settings is not None or self.sources is not None
            ):
                raise ValueError("a single-scene continuation writes only tracks[].clips for its scene_id")
        if self.save and self.draft_ref is None:
            raise ValueError("save=true requires an existing draft_ref; create and update the draft with save=false first")
        if self.save and (
            self.entity_writes().has_changes()
            or self.settings is not None
            or self.sources is not None
            or self.focus_clip_id is not None
            or self.skill_resource is not None
            or self.scene is not None
            or self.scene_plan is not None
        ):
            raise ValueError("save=true only commits the existing draft; submit settings, sources and entity writes with save=false first")
        return self

    def entity_writes(self) -> EntityWrites:
        return EntityWrites.model_validate({
            key: getattr(self, key) for key in EntityWrites.model_fields
        })

    def bind_working_draft(self, value: dict[str, Any]) -> None:
        self._working_draft = deepcopy(value)


_EXPLICIT_CONSTRAINT_FIELDS = ("scene_count", "target_seconds", "aspect", "background")


def _affirmative_constraint(text: str, start: int) -> bool:
    prefix = text[max(0, start - 12):start]
    return not re.search(r"(?:不要|不用|不|别|避免|not|without)\s*$", prefix, re.IGNORECASE)


def _constraint_text_values(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return {}
    values: dict[str, Any] = {}
    aspect = re.search(
        r"(?:画幅(?:比例)?|画布比例|画面比例|aspect(?:\s+ratio)?|frame(?:\s+format)?)"
        r"\s*(?:固定\s*)?(?:为|是|用|使用|设为|设置为|改成|改为|到|=|:|to|is)?\s*[\"']?"
        r"(16\s*:\s*9|9\s*:\s*16|1\s*:\s*1)(?!\d)",
        text, re.IGNORECASE,
    )
    if aspect is None:
        aspect = re.search(
            r"(?<![\d:])(16\s*:\s*9|9\s*:\s*16|1\s*:\s*1)(?![\d:])",
            text, re.IGNORECASE,
        )
    if aspect and _affirmative_constraint(text, aspect.start()):
        values["aspect"] = re.sub(r"\s", "", aspect.group(1))
    scene_patterns = (
        r"\bexactly\s+(\d+)\s+(?:scenes|shots)\b",
        r"\b(\d+)\s+(?:scenes|shots)\s+exactly\b",
        r"(?:恰好|刚好|固定为|固定成|只做|做|分成|分为|总共|共)\s*(\d+)\s*(?:个)?\s*(?:幕|场景|镜头)",
    )
    for pattern in scene_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and _affirmative_constraint(text, match.start()):
            values["scene_count"] = int(match.group(1))
            break
    duration_patterns = (
        r"\bexactly\s+\d+\s+(?:scenes|shots)\s+and\s+(\d+(?:\.\d+)?)\s*(?:seconds|s)\b",
        r"\b(\d+(?:\.\d+)?)-second\s+(?:[a-z-]+\s+)*(?:storyboard|video|promo|film)\b",
        r"(?:总时长|总长度|成片时长|视频时长|total\s+duration|duration|length)"
        r"\s*(?:固定\s*)?(?:为|是|用|设为|设置为|改成|改为|到|=|:|to|is)?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:秒|seconds?|s)\b",
        r"\bexactly\s+(\d+(?:\.\d+)?)\s*(?:seconds|s)\b",
    )
    for pattern in duration_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and _affirmative_constraint(text, match.start()):
            values["target_seconds"] = float(match.group(1))
            break
    background = re.search(
        r"(?:背景(?:颜色|色)?|background(?:\s+colou?r)?)"
        r"\s*(?:固定\s*)?(?:为|是|用|使用|设为|设置为|改成|改为|=|:|to|is)?\s*[\"']?"
        r"(#[0-9a-fA-F]{6})\b",
        text, re.IGNORECASE,
    )
    if background and _affirmative_constraint(text, background.start()):
        values["background"] = background.group(1).upper()
    return values


def explicit_design_constraints(
    user_text: str = "",
    *,
    constraints=(),
    brief=None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve only user-fixed values, never the model's own creative choices."""
    resolved: dict[str, Any] = {}
    design = (draft or {}).get("design") or {}
    stored = design.get("user_constraints") or {}
    if isinstance(stored, dict):
        for field in _EXPLICIT_CONSTRAINT_FIELDS:
            if stored.get(field) is not None:
                resolved[field] = deepcopy(stored[field])
    if brief is not None:
        from app.models.schemas import Brief, BriefSlotSource

        raw_brief = brief.get("brief") if isinstance(brief, dict) and isinstance(brief.get("brief"), dict) else brief
        parsed = raw_brief if isinstance(raw_brief, Brief) else Brief.model_validate(raw_brief or {})
        for item in parsed.constraints:
            if item.value and item.source == BriefSlotSource.USER_STATED:
                resolved.update(_constraint_text_values(item.value))
    for value in constraints or ():
        if isinstance(value, str):
            resolved.update(_constraint_text_values(value))
    resolved.update(_constraint_text_values(user_text))
    return resolved


def bind_explicit_design_constraints(
    args: CompositionDesignVideoArgs,
    *,
    user_text: str = "",
    brief=None,
) -> CompositionDesignVideoArgs:
    trusted = explicit_design_constraints(
        user_text, brief=brief, draft=getattr(args, "_working_draft", None),
    )
    content = (getattr(args, "_working_draft", None) or {}).get("content")
    for field in _EXPLICIT_CONSTRAINT_FIELDS:
        supplied = getattr(args, field)
        if supplied is None:
            continue
        expected = trusted.get(field)
        matches = (
            supplied.lower() == str(expected).lower()
            if field == "background" and expected is not None
            else supplied == expected
        )
        if expected is None or not matches:
            message = (
                f"{field} was not fixed by the user; omit it and use the server default or creative freedom"
                if expected is None
                else f"{field} must preserve the user-fixed value {expected}"
            )
            raise CandidateDesignError(
                message,
                errors=[{"loc": [field], "type": "user_constraint", "msg": message, "expected": expected, "actual": supplied}],
                working_content=content if isinstance(content, dict) else None,
            )
    for field, value in trusted.items():
        setattr(args, field, value)
    args._explicit_constraints = trusted
    return args


class CaptureUnavailable(DesignError):
    """A completed/failed capture produced no usable media, not an ownership failure."""


class CaptureSettleTimeout(DesignError, AgentStopError):
    """Pages still in flight past the ceiling — the draft refuses a
    half-captured world."""


async def _await_captures_settled(
    db: AsyncSession, project_id: UUID, *, urls: set[str] | None = None, asset_ids: set[UUID] | None = None
) -> None:
    """Wait until the project's WEB_PAGE captures leave PENDING/PROCESSING
    (bounded). Reads re-fresh (populate_existing) so the worker's commits
    show through."""
    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)
    while True:
        rows = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == project_id,
                        Asset.type == AssetType.WEB_PAGE,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        in_flight = [
            a for a in rows
            if a.processing_status in (AssetStatus.PENDING, AssetStatus.PROCESSING)
            and (asset_ids is None or a.id in asset_ids)
            and (urls is None or (a.meta or {}).get("capture_url") in urls)
        ]
        if not in_flight:
            return
        if time.monotonic() >= deadline:
            raise CaptureSettleTimeout(
                f"the page capture is still running after "
                f"{_CAPTURE_SETTLE_WAIT_S:.0f}s — the design refused to "
                "draft from a half-captured world; try again in a moment"
            )
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)


async def _await_media_settled(db: AsyncSession, owner_id: UUID, asset_ids: set[UUID]) -> None:
    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)
    while True:
        rows = list(
            (
                await db.execute(
                    select(Asset)
                    .where(Asset.id.in_(asset_ids), Asset.user_id == owner_id)
                    .execution_options(populate_existing=True)
                )
            ).scalars().all()
        )
        if any(asset.processing_status == AssetStatus.FAILED for asset in rows):
            raise DesignError("a selected source asset failed during media processing")
        if rows and all(asset.processing_status == AssetStatus.COMPLETED for asset in rows):
            return
        if time.monotonic() >= deadline:
            raise CaptureSettleTimeout("selected media processing did not settle in time")
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)


async def _ready_web_pages(db, *, project_id, owner_id, asset_ids=None, urls=None):
    """Prepare existing material in code, not by asking Chat to probe readiness."""
    from sqlalchemy import update
    from app.models.tables import now_utc
    query = select(Asset).where(Asset.user_id == owner_id, Asset.type == AssetType.WEB_PAGE)
    query = query.where(Asset.id.in_(asset_ids)) if asset_ids else query.where(Asset.project_id == project_id)
    rows = list((await db.scalars(query.execution_options(populate_existing=True))).all())
    rows = [a for a in rows if (urls is None or (a.meta or {}).get("capture_url") in urls)
            and (asset_ids or not (a.meta or {}).get("capture_plan"))]
    pending = [a for a in rows if a.processing_status in (AssetStatus.PENDING, AssetStatus.PROCESSING)]
    if pending:
        # Same worker claim flag as URL birth/understanding, in its own short
        # transaction so the worker can see it while design remains open.
        async with AsyncSessionLocal() as session:
            await session.execute(update(Asset).where(
                Asset.id.in_([a.id for a in pending]), Asset.user_id == owner_id,
                Asset.processing_status == AssetStatus.PENDING,
                Asset.processing_requested_at.is_(None),
            ).values(processing_requested_at=now_utc()))
            await session.commit()
        for origin in dict.fromkeys(a.project_id for a in pending):
            await _await_captures_settled(db, origin,
                asset_ids={a.id for a in pending if a.project_id == origin})
        rows = list((await db.scalars(query.execution_options(populate_existing=True))).all())
        rows = [a for a in rows if (urls is None or (a.meta or {}).get("capture_url") in urls)
                and (asset_ids or not (a.meta or {}).get("capture_plan"))]
    ready = [a for a in rows if a.processing_status == AssetStatus.COMPLETED and (a.meta or {}).get("shots")]
    if (asset_ids and len(ready) != len(set(asset_ids))) or (rows and not ready):
        raise AgentOutputError("The existing webpage capture failed or has no usable frozen views; no storyboard was saved.")
    return ready




def _view_facts(snapshots: list[SourceSnapshot]) -> list[ViewFact]:
    """Every captured view, in preference order (fold first per page, bind
    order across pages); a view with unreadable facts is skipped, never
    invented."""
    from app.editing.director import recapturable_web_elements
    views: list[ViewFact] = []
    for page, snapshot in enumerate(snapshots):
        recapturable = recapturable_web_elements(snapshot.meta or {})
        for view in (snapshot.meta or {}).get("views") or []:
            if not view.get("storage_key") or not view.get("width") or not view.get("height"):
                continue
            views.append(
                ViewFact(
                    snapshot_id=snapshot.id,
                    snapshot_digest=snapshot.digest,
                    view_id=str(view["view_id"]),
                    width=int(view["width"]),
                    height=int(view["height"]),
                    elements=[{**element, "can_recapture": element.get("id") in recapturable}
                              for element in view.get("elements") or []],
                    heading=str(view.get("heading") or ""),
                    page=page,
                    state_id=view.get("state_id"),
                    artifact_role=view.get("artifact_role"),
                    paired_view_id=view.get("paired_view_id"),
                    target_id=view.get("target_id"),
                    target_element_id=view.get("target_element_id"),
                    route=view.get("route"),
                    actions=list(view.get("actions") or []),
                    source_y=int(view.get("source_y") or 0),
                    css_width=view.get("css_width"),
                    css_height=view.get("css_height"),
                    device_scale_factor=float(view.get("device_scale_factor") or 1.0),
                    region_text=view.get("region_text"),
                    region_text_truncated=view.get("region_text_truncated"),
                    region_visually_truncated=view.get("region_visually_truncated"),
                    source_url=str((snapshot.meta or {}).get("canonical_url") or "") or None,
                )
            )
    return views












async def _view_media_inputs(
    snapshots: list[SourceSnapshot],
    views: list[ViewFact],
    *,
    omitted: list[dict[str, str]] | None = None,
    targets: list[Any] | None = None,
) -> list[Any]:
    """Attach one representative view per page, or explicitly selected targets."""
    from app.pipeline.step_context import media_input_for_image  # deferred: execution layer

    items: list[Any] = []
    keys_by_view: dict[tuple[UUID, str], str] = {}
    for snapshot in snapshots:
        for view in (snapshot.meta or {}).get("views") or []:
            keys_by_view[(snapshot.id, str(view.get("view_id")))] = str(view.get("storage_key") or "")

    def omit(view: ViewFact, part: str, reason: str) -> None:
        if omitted is not None:
            omitted.append({
                "snapshot_id": str(view.snapshot_id),
                "view_id": view.view_id,
                "part": part,
                "reason": reason,
            })

    selected: list[ViewFact] = []
    if targets is None:
        seen_pages: set[UUID] = set()
        for view in views:
            if view.snapshot_id not in seen_pages:
                selected.append(view)
                seen_pages.add(view.snapshot_id)
    else:
        for target in targets:
            match = next(
                (
                    view
                    for view in views
                    if view.snapshot_id == target.snapshot_id
                    and (target.view_id is None or view.view_id == target.view_id)
                ),
                None,
            )
            if match is not None and match not in selected:
                selected.append(match)
    selected_ids = {(view.snapshot_id, view.view_id) for view in selected}
    for view in views:
        if (view.snapshot_id, view.view_id) not in selected_ids:
            omit(view, "view", "not attached; select it with material_targets")

    for i, view in enumerate(selected, start=1):
        key = keys_by_view.get((view.snapshot_id, view.view_id))
        if not key:
            omit(view, "view", "frozen image key unavailable")
            continue
        item = await media_input_for_image(
            key,
            caption=f"V{i} — page {view.page}, view {view.view_id} ({view.heading or 'captured view'})",
            max_px=1280,
        )
        if item is None:
            omit(view, "view", "frozen image could not be read")
        else:
            items.append(item)
        target = next(
            (
                candidate
                for candidate in targets or []
                if candidate.snapshot_id == view.snapshot_id
                and (candidate.view_id is None or candidate.view_id == view.view_id)
                and candidate.element_id is not None
            ),
            None,
        )
        element = (
            next(
                (candidate for candidate in view.elements if candidate.get("id") == target.element_id),
                None,
            )
            if target is not None
            else None
        )
        if target is not None and element is None:
            omit(view, f"element:{target.element_id}", "selected element is absent")
        if element is not None and element.get("storage_key"):
            crop = await media_input_for_image(
                str(element["storage_key"]),
                caption=(
                    f"V{i} element {element.get('id')} — the captured target crop; "
                    "its exact geometry is in selected_target.view"
                ),
                max_px=1280,
            )
            if crop is None:
                omit(view, f"element:{element.get('id')}", "element crop could not be read")
            else:
                items.append(crop)
        elif element is not None:
            omit(view, f"element:{element.get('id')}", "element has no frozen crop")
    return items


async def _fixed_media_inputs(
    snapshots: list[SourceSnapshot],
    *,
    omitted: list[dict[str, str]],
    continuous_video: bool = False,
    evidence: dict[str, Any] | None = None,
) -> list[Any]:
    """Attach bounded model evidence without changing the fixed builder source."""
    import base64

    import av

    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.schemas import MediaInput, MediaInputType
    from app.pipeline.step_context import (
        download_to_temp,
        media_input_for_image,
        media_input_for_video_source,
    )
    from app.tools.video.review import ReviewError, representative_source_frames

    items: list[Any] = []
    fixed = [snapshot for snapshot in snapshots if snapshot.kind in {"image", "video"}]
    for snapshot in fixed:
        if len(items) >= 4:
            omitted.append({
                "snapshot_id": str(snapshot.id), "view_id": "", "part": snapshot.kind,
                "reason": "media attachment budget",
            })
            continue
        if snapshot.kind == "image":
            item = await media_input_for_image(
                snapshot.storage_key,
                caption=f"Prepared image {snapshot.id} ({snapshot.digest})",
                max_px=1280,
            )
            if item is not None:
                items.append(item)
                continue
        elif continuous_video:
            item = await media_input_for_video_source(
                snapshot.storage_key,
                duration_seconds=(snapshot.duration_ticks or 0) / SOURCE_TIMEBASE,
                caption=f"Prepared continuous video {snapshot.id} ({snapshot.digest})",
            )
            if item is not None:
                items.append(item)
                if evidence is not None:
                    evidence[str(snapshot.id)] = {
                        "mode": "continuous", "continuous_review": True,
                    }
                continue
        else:
            path = await download_to_temp(snapshot.storage_key)
            if path is not None:
                try:
                    frames = await asyncio.to_thread(
                        representative_source_frames,
                        path,
                        duration_seconds=(snapshot.duration_ticks or 0) / SOURCE_TIMEBASE,
                    )
                except (ReviewError, OSError, ValueError, av.FFmpegError):
                    frames = []
                finally:
                    path.unlink(missing_ok=True)
                attached = frames[:max(0, 4 - len(items))]
                for frame in attached:
                    items.append(MediaInput(
                        type=MediaInputType.IMAGE,
                        mime="image/jpeg",
                        data_url="data:image/jpeg;base64," + base64.b64encode(frame.jpeg).decode("ascii"),
                        caption=(
                            f"Prepared video {snapshot.id} ({snapshot.digest}), representative frame "
                            f"{frame.frame_id} at actual source time {frame.time_seconds:.3f}s. "
                            "Still frames only; this is not continuous playback or a complete-video review."
                        ),
                    ))
                if attached:
                    if evidence is not None:
                        evidence[str(snapshot.id)] = {
                            "mode": "representative_frames",
                            "continuous_review": False,
                            "frames": [
                                {
                                    "frame_id": frame.frame_id,
                                    "actual_time_seconds": frame.time_seconds,
                                    "digest": frame.digest,
                                }
                                for frame in attached
                            ],
                        }
                    if len(attached) < len(frames):
                        omitted.append({
                            "snapshot_id": str(snapshot.id), "view_id": "", "part": "video_frames",
                            "reason": "media attachment budget",
                        })
                    continue
        omitted.append({
            "snapshot_id": str(snapshot.id), "view_id": "", "part": snapshot.kind,
            "reason": "media unreadable or outside the direct-observation limit",
        })
    return items






async def _execute_capture_plan(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    plan: CapturePlan,
) -> tuple[Asset, SourceSnapshot]:
    """Create only the final Asset here; the existing worker owns all I/O."""
    from app.pipeline.assets import create_capture_plan_asset_committed

    asset_id = await create_capture_plan_asset_committed(project_id, owner_id, plan)
    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    while True:
        asset = await db.get(Asset, asset_id, populate_existing=True)
        if asset is None or asset.user_id != owner_id or asset.project_id != project_id:
            raise DesignError("the final capture asset is inaccessible")
        if asset.processing_status == AssetStatus.COMPLETED:
            if not (asset.meta or {}).get("shots"):
                raise CaptureUnavailable("the final webpage capture completed without any usable views")
            snapshot = await snapshot_web_asset(db, asset, owner_id=owner_id)
            await db.flush()
            return asset, snapshot
        if asset.processing_status == AssetStatus.FAILED:
            raise CaptureUnavailable(
                "the final webpage capture failed: "
                + str(asset.processing_error or "no usable view was obtained")
            )
        if time.monotonic() >= deadline:
            raise CaptureSettleTimeout("the final webpage capture is still running; no storyboard version was written")
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)




















async def _direct_copy_evidence(
    db: AsyncSession,
    *,
    owner_id: UUID,
    references: list[CompositionCopyReference],
    candidate: CompositionContent,
) -> list[dict[str, Any]]:
    """Resolve display copy to immutable source text by stable line identity."""
    from app.tools.video.preparation import resolve_frozen_line

    displayed: dict[str, list[dict[str, str]]] = {}
    for track in candidate.timeline.tracks:
        for clip in track.clips:
            if clip.object.kind == "text":
                displayed.setdefault(clip.object.text, []).append({
                    "object_id": clip.object.object_id,
                    "text": clip.object.text,
                })
    evidence: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for index, reference in enumerate(references):
        snapshot = await db.get(SourceSnapshot, reference.snapshot_id)
        if snapshot is None or snapshot.owner_id != owner_id:
            raise CandidateDesignError("copy reference snapshot is not accessible to this user")
        if reference.snapshot_digest is not None and reference.snapshot_digest != snapshot.digest:
            raise CandidateDesignError("copy reference snapshot_digest does not match the immutable snapshot")
        line = resolve_frozen_line(snapshot, reference.line_id)
        text = reference.text if reference.text is not None else line["text"]
        if text not in displayed:
            folded = text.casefold()
            candidates = [
                item
                for objects in displayed.values()
                for item in objects
                if folded in item["text"].casefold() or item["text"].casefold() in folded
            ][:4]
            mismatches.append({
                "loc": ["copy_references", index, "text"],
                "type": "copy_reference_mismatch",
                "msg": f"copy reference {reference.line_id!r} does not exactly match a native TextObject",
                "reference_text": text,
                "line_id": reference.line_id,
                "candidate_text_objects": candidates,
            })
            continue
        evidence.append({
            "text": text,
            "snapshot_id": str(snapshot.id),
            "line_id": line["line_id"],
            "quote": line["text"],
        })
    if mismatches:
        raise CandidateDesignError(
            "copy references do not exactly match native TextObjects",
            errors=mismatches,
        )
    return evidence


def _complete_direct_generator_outputs(composition: dict[str, Any]) -> dict[str, Any]:
    """Derive omitted controlled-generator rasters from their exact clip window."""
    normalized = deepcopy(composition)
    settings = normalized.get("settings")
    timeline = normalized.get("timeline")
    tracks = timeline.get("tracks") if isinstance(timeline, dict) else None
    if not isinstance(settings, dict) or not isinstance(tracks, list):
        return normalized
    raw_fps = settings.get("fps")
    fps = raw_fps if isinstance(raw_fps, dict) else {}
    fps_num = fps.get("num", 30)
    fps_den = fps.get("den", 1)
    timebase = settings.get("timebase", 90000)
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in (fps_num, fps_den, timebase)):
        return normalized
    if fps_num % fps_den:
        return normalized
    output_fps = fps_num // fps_den
    for track in tracks:
        clips = track.get("clips") if isinstance(track, dict) else None
        if not isinstance(clips, list):
            continue
        for clip in clips:
            obj = clip.get("object") if isinstance(clip, dict) else None
            time_range = clip.get("range") if isinstance(clip, dict) else None
            if (
                not isinstance(obj, dict)
                or obj.get("kind") != "generator"
                or obj.get("producer") not in {"draw-2d", "remotion-project"}
                or obj.get("output") is not None
                or not isinstance(time_range, dict)
            ):
                continue
            start, end = time_range.get("start"), time_range.get("end")
            if (
                not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)
            ):
                continue
            frame_ticks = (end - start) * fps_num
            tick_denominator = timebase * fps_den
            if frame_ticks <= 0 or frame_ticks % tick_denominator:
                continue
            obj["output"] = {
                "width": settings.get("width"),
                "height": settings.get("height"),
                "fps": output_fps,
                "duration_frames": frame_ticks // tick_denominator,
                "background": settings.get("background", "#000000"),
            }
    return normalized


def _native_copy_text(candidate: CompositionContent) -> list[str]:
    from app.editing.schemas import TextObject

    native_text = sorted(
        (
            (clip.range.start, track.order, clip.object.text)
            for track in candidate.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, TextObject) and clip.object.caption is None
        ),
        key=lambda item: item[:2],
    )
    return [text for _, _, text in native_text]


def _validate_scene_verbatim_copy(
    *, args: CompositionDesignVideoArgs, composition: dict[str, Any]
) -> None:
    if args.verbatim_copy is None:
        return
    candidate = CompositionContent.model_validate(composition)
    actual = _native_copy_text(candidate)
    covered = {
        clip.scene_id
        for track in candidate.timeline.tracks if track.kind == "visual"
        for clip in track.clips
    }
    complete = bool(candidate.scenes) and all(
        scene.scene_id in covered for scene in candidate.scenes
    )
    expected = args.verbatim_copy
    if actual == (expected if complete else expected[:len(actual)]):
        return
    raise CandidateDesignError(
        "the native Text Clips must contain only the requested exact copy in playback order",
        errors=[{
            "loc": ["verbatim_copy"],
            "type": "verbatim_copy_mismatch",
            "msg": "correct the native Text Clips to match the requested phrases exactly once and in order",
            "expected": expected,
            "actual": actual,
        }],
    )


def _validate_direct_design(
    *,
    args: CompositionDesignVideoArgs,
    composition: dict[str, Any],
) -> CompositionContent:
    """Validate the direct final object and explicit user constraints."""
    from app.config import settings
    from app.editing.timing import ticks_to_frames, ticks_to_seconds
    from app.editing.video_spec import VIDEO_MAX_FRAMES

    composition = _complete_direct_generator_outputs(composition)
    try:
        candidate = CompositionContent.model_validate(composition)
    except ValidationError as exc:
        from app.agents.arguments import resolve_error_path

        errors = json.loads(exc.json(include_input=False, include_url=False))
        schema = CompositionContent.model_json_schema()
        for error in errors:
            error["loc"] = list(resolve_error_path(composition, error["loc"], schema))
        raise CandidateDesignError(
            "the assembled Composition is invalid",
            errors=errors,
        ) from exc
    if args.scene_count is not None and len(candidate.scenes) != args.scene_count:
        raise CandidateDesignError(f"the user fixed scene_count={args.scene_count}; candidate has {len(candidate.scenes)}")
    if isinstance(args, CompositionDesignVideoArgs) and args.verbatim_copy is not None:
        actual = _native_copy_text(candidate)
        if actual != args.verbatim_copy:
            raise CandidateDesignError(
                "the native Text Clips must contain only the requested exact copy in playback order",
                errors=[{
                    "loc": ["verbatim_copy"],
                    "type": "verbatim_copy_mismatch",
                    "msg": "correct the native Text Clips to match the requested phrases exactly once and in order",
                    "expected": args.verbatim_copy,
                    "actual": actual,
                }],
            )
    duration = ticks_to_seconds(
        max((scene.range.end for scene in candidate.scenes), default=0),
        candidate.settings.timebase,
    )
    if args.target_seconds is not None and abs(duration - args.target_seconds) > 1 / 30:
        raise CandidateDesignError(f"the user fixed target_seconds={args.target_seconds}; candidate has {float(duration):g}")
    total_ticks = max(
        (clip.range.end for track in candidate.timeline.tracks for clip in track.clips),
        default=0,
    )
    total_frames = ticks_to_frames(
        total_ticks,
        candidate.settings.timebase,
        candidate.settings.fps.num,
        candidate.settings.fps.den,
    )
    if total_frames > VIDEO_MAX_FRAMES:
        fps = candidate.settings.fps.num / candidate.settings.fps.den
        raise CandidateDesignError(
            f"the current video production policy allows at most {VIDEO_MAX_FRAMES} frames "
            f"({VIDEO_MAX_FRAMES / fps:g} seconds at {fps:g} fps); the candidate has "
            f"{total_frames} frames ({total_frames / fps:g} seconds). Shorten the timeline "
            "and keep every scene, clip and animation inside the shortened work."
        )
    if args.background is not None and candidate.settings.background.lower() != args.background.lower():
        raise CandidateDesignError("candidate background must equal the user's exact requested color")
    if args.aspect is not None:
        ratios = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1)}
        numerator, denominator = ratios[args.aspect]
        if candidate.settings.width * denominator != candidate.settings.height * numerator:
            raise CandidateDesignError(f"candidate settings must use the requested {args.aspect} canvas")
    generator_objects = [
        clip.object
        for track in candidate.timeline.tracks
        for clip in track.clips
        if isinstance(clip.object, GeneratorObject)
    ]
    if not settings.component_bake_enabled and any(
        obj.producer == "remotion-project" for obj in generator_objects
    ):
        raise CandidateDesignError("remotion-project is unavailable in this deployment")
    return candidate


async def _save_composition_version(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    args: CompositionDesignVideoArgs,
    request_id: str | None,
    composition: Any,
    base_version: Any,
    base_content: CompositionContent | None,
    direct_composition: dict[str, Any],
    direct_candidate: CompositionContent,
    provenance: dict[str, Any],
    name: str,
    skill: SkillCreativeContext | None,
    builtin_skill: BuiltInSkillReference | None,
    route_builtin_id: str | None,
) -> dict[str, Any]:
    """Save one fully resolved and validated assembled Composition."""
    if base_version is not None:
        provenance = deepcopy(base_version.skill_provenance or {})
    if skill is not None:
        provenance["external_skill"] = skill.provenance
        provenance["skill_reference"] = ExternalSkillReference(
            kind="external", skill_version_id=skill.version.id
        ).model_dump(mode="json")
    if builtin_skill is not None:
        provenance["skill_version"] = builtin_skill.version
        provenance["skill_reference"] = builtin_skill.model_dump(mode="json")
    provenance.setdefault("language", args.language or ((base_version.skill_provenance or {}).get("language") if base_version else None))
    resource_snapshot_ids = {
        resource.snapshot_id
        for track in direct_candidate.timeline.tracks
        for clip in track.clips
        if isinstance(clip.object, GeneratorObject) and clip.object.project is not None
        for resource in clip.object.project.resources
    }
    preflight_facts = await snapshot_facts(db, resource_snapshot_ids)
    if any(
        snapshot_id not in preflight_facts
        or preflight_facts[snapshot_id].get("owner_id") != owner_id
        for snapshot_id in resource_snapshot_ids
    ):
        raise DesignError("component resources must be owned by this user")
    if composition is None:
        composition, version, replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            content=direct_composition,
            request_id=request_id,
            name=name,
            skill_provenance=provenance,
        )
        base_content = None
    else:
        composition, version, replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            composition_id=composition.id,
            base_version_id=base_version.id,
            base_digest=base_version.content_digest,
            content=direct_composition,
            request_id=request_id,
            skill_provenance=provenance,
        )

    new_content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in new_content.sources})
    payload = storyboard_payload(
        new_content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    if base_content is not None:
        read["change_set"] = compute_change_set(base_content, new_content)
    if skill is not None:
        read["skill_adaptation"] = skill.presentation
    read["replayed"] = replayed
    return read


def _apply_focus_write(
    content: dict[str, Any], args: CompositionDesignVideoArgs, facts: dict[str, Any]
) -> dict[str, Any]:
    if args.focus_clip_id is None:
        return content
    from app.editing.grounding import camera_keyframes, resolve_focus
    from app.editing.validators import validate_content

    updated = deepcopy(content)
    clip = next(
        (
            clip for track in (updated.get("timeline") or {}).get("tracks") or []
            for clip in track.get("clips") or []
            if clip.get("clip_id") == args.focus_clip_id
        ),
        None,
    )
    if clip is None or (clip.get("object") or {}).get("kind") != "web":
        raise DesignError("focus_clip_id must name an existing web Clip in the current draft")
    snapshot_id = str((clip.get("source") or {}).get("snapshot_id") or "")
    fact = facts.get(UUID(snapshot_id)) or {}
    view = next(
        (
            view for view in (fact.get("meta") or {}).get("views") or []
            if view.get("view_id") == clip["object"].get("view_id")
        ),
        None,
    )
    if view is None:
        raise DesignError("the target Clip's frozen view is unavailable")
    focus = resolve_focus(view.get("elements") or [], args.focus_element_id)
    settings = updated["settings"]
    clip_ticks = int(clip["range"]["end"]) - int(clip["range"]["start"])
    zoom, positions = camera_keyframes(
        focus,
        view_width=int(view["width"]),
        view_height=int(view["height"]),
        canvas_width=int(settings["width"]),
        canvas_height=int(settings["height"]),
        clip_ticks=clip_ticks,
        arrival_frac=0.45,
    )
    animations = [
        animation for animation in clip.get("animations") or []
        if animation.get("property") not in {"transform.scale", "transform.position"}
    ]
    existing = {
        animation.get("property"): animation.get("animation_id")
        for animation in clip.get("animations") or []
    }
    animations.extend([
        {
            "animation_id": existing.get("transform.scale") or f"{clip['clip_id']}_focus_scale",
            "target_object_id": clip["object"]["object_id"],
            "property": "transform.scale",
            "keyframes": [
                {"at": 0, "value": 1.08},
                {"at": positions[1][0], "value": zoom},
                {"at": clip_ticks, "value": round(min(zoom * 1.01, 2.05), 3)},
            ],
        },
        {
            "animation_id": existing.get("transform.position") or f"{clip['clip_id']}_focus_position",
            "target_object_id": clip["object"]["object_id"],
            "property": "transform.position",
            "keyframes": [
                {"at": at, "value": [float(value[0]), float(value[1])]}
                for at, value in positions
            ],
        },
    ])
    clip["animations"] = animations
    validated = CompositionContent.model_validate(updated)
    validate_content(validated, facts)
    return validated.model_dump(mode="json")


async def _place_skill_generator(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    content: dict[str, Any],
    placement: SkillGeneratorPlacement,
    skill: SkillCreativeContext | None,
    package: Any,
) -> tuple[dict[str, Any], str]:
    from sqlalchemy.dialects.postgresql import insert

    from app.tools.video.components import (
        _MAX_RESOURCE_BYTES,
        _MAX_TOTAL_RESOURCE_BYTES,
        assert_component_bake_enabled,
    )
    from app.tools.video.preparation import store_source_bytes

    assert_component_bake_enabled()
    if skill is None or package is None or (
        package.owner_id != owner_id or package.package_identity != skill.version.id
    ):
        raise DesignError("select a Generator from the current bound external Skill version")
    declaration, declaration_digest = await package.generator_declaration(placement.resource_id)
    scene = next((s for s in content["scenes"] if s["scene_id"] == placement.scene_id), None)
    track = next(
        (t for t in content["timeline"]["tracks"] if t["track_id"] == placement.track_id),
        None,
    )
    if scene is None or track is None or track.get("kind") != "visual":
        raise DesignError(
            f"skill_resource requires Scene {placement.scene_id!r} and visual Track "
            f"{placement.track_id!r}; create missing entities in scenes and tracks in this write"
        )
    settings = VersionSettings.model_validate(content.get("settings"))
    output = declaration.output
    span = scene["range"]
    if (span["end"] - span["start"]) * output.fps != output.duration_frames * settings.timebase:
        raise DesignError("the target Scene duration must match the declared Skill Generator duration")

    files = []
    for path in declaration.files:
        if not path.startswith(("demos/", "template/")):
            raise DesignError("Skill Generator source must be declared under demos/ or template/")
        source = await package.reader.read_text(path)
        files.append(RemotionSourceFile(path=path, content=source.text, digest=source.digest))
    bindings = {
        path: await package.fixed_image_binding(package_path)
        for path, package_path in declaration.resources.items()
    }
    if (
        any(b["byte_size"] > _MAX_RESOURCE_BYTES for b in bindings.values())
        or sum(b["byte_size"] for b in bindings.values()) > _MAX_TOTAL_RESOURCE_BYTES
    ):
        raise DesignError("declared Skill Generator images exceed the component resource budget")
    project = RemotionProjectSource(
        entry=declaration.entry,
        composition_id=declaration.composition_id,
        files=files,
        props_schema={},
        resources=[
            RemotionResource(
                path=path,
                snapshot_id=binding["snapshot_id"],
                snapshot_digest=binding["snapshot_digest"],
                content_type=binding["content_type"],
            )
            for path, binding in bindings.items()
        ],
    )
    clip = Clip(
        clip_id=placement.clip_id,
        scene_id=placement.scene_id,
        range=span,
        object=GeneratorObject(
            kind="generator",
            object_id=placement.clip_id,
            producer="remotion-project",
            project=project,
            output=output,
            layout=placement.layout or LayoutBox(x=0, y=0, width=settings.width, height=settings.height),
        ),
    )
    candidate = apply_working_draft_writes(
        content, EntityWrites(clips=[ClipEntityWrite(track_id=placement.track_id, clip=clip)])
    )
    for resource in project.resources:
        binding = bindings[resource.path]
        data = await package.reader.read_media(binding["path"])
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[resource.content_type]
        key, digest = await store_source_bytes(data, suffix, resource.content_type)
        await db.execute(insert(SourceSnapshot).values(
            id=resource.snapshot_id,
            owner_id=owner_id,
            origin_project_id=project_id,
            kind="image",
            storage_key=key,
            digest=digest,
            meta={
                "content_type": resource.content_type,
                "origin": "external_skill_package",
                "skill_version_id": str(skill.version.id),
                "package_path": binding["path"],
            },
        ).on_conflict_do_nothing(index_elements=[SourceSnapshot.id]))
    return candidate, declaration_digest


def _scene_plan_write(
    content: dict[str, Any], plan: list[CompositionScenePlan]
) -> dict[str, Any]:
    updated = deepcopy(content)
    settings = VersionSettings.model_validate(updated["settings"])
    start = 0
    scenes = []
    for item in plan:
        duration = frames_to_ticks(
            120, settings.timebase, settings.fps.num, settings.fps.den
        )
        scenes.append(Scene(
            scene_id=item.scene_id,
            range=TimeRange(start=start, end=start + duration),
            intent=item.intent,
            visual_description=item.visual_description,
        ).model_dump(mode="json"))
        start += duration
    updated["scenes"] = scenes
    tracks = updated["timeline"]["tracks"]
    if not any(track.get("track_id") == "trk_main" for track in tracks):
        tracks.append(Track(
            track_id="trk_main", kind="visual", role="main", order=0, clips=[]
        ).model_dump(mode="json"))
    return updated


def _scene_reading_ticks(
    scene: CompositionSceneAuthoring, settings: VersionSettings
) -> int:
    if scene.source_end_seconds is not None:
        return seconds_to_ticks(
            scene.source_end_seconds - (scene.source_start_seconds or 0),
            settings.timebase,
        )
    characters = len(scene.headline or "") + len(scene.supporting_text or "") + sum(
        len(item) for item in scene.items
    )
    minimum = 4.0 if scene.snapshot_id is not None else 3.0
    seconds = min(max(minimum, 1.2 + characters / 18.0), 8.0)
    return frames_to_ticks(
        round(seconds * 30), settings.timebase, settings.fps.num, settings.fps.den
    )


def _set_current_scene_timing(
    content: dict[str, Any], scene_id: str, duration: int
) -> None:
    scenes = content["scenes"]
    index = next(
        (index for index, scene in enumerate(scenes) if scene["scene_id"] == scene_id),
        None,
    )
    if index is None:
        raise CandidateDesignError(
            "scene_id is absent from the current scene_plan",
            errors=[{"loc": ["scene", "scene_id"], "type": "target_not_found", "msg": "choose a Scene from scene_plan"}],
            working_content=content,
        )
    covered = {
        clip.get("scene_id")
        for track in content["timeline"]["tracks"] if track.get("kind") == "visual"
        for clip in track.get("clips") or []
    }
    current = next((scene for scene in scenes if scene["scene_id"] not in covered), None)
    if current is None or current["scene_id"] != scene_id:
        complete = current is None
        message = (
            "every planned Scene is filled; submit only the current draft_ref with save=true"
            if complete else
            "scene writes must follow scene_plan order and target the current unfilled Scene"
        )
        raise CandidateDesignError(
            message,
            errors=[{
                "loc": ["save" if complete else "scene", "scene_id"],
                "type": "scene_order",
                "msg": message,
                "expected": current["scene_id"] if current else None,
                "actual": scene_id,
            }],
            working_content=content,
        )
    start = scenes[index - 1]["range"]["end"] if index else 0
    new_end = start + duration
    delta = new_end - scenes[index]["range"]["end"]
    scenes[index]["range"] = {"start": start, "end": new_end}
    for following in scenes[index + 1:]:
        following["range"] = {
            "start": following["range"]["start"] + delta,
            "end": following["range"]["end"] + delta,
        }


async def _resolve_scene_source(
    scene: CompositionSceneAuthoring,
    facts: dict[UUID, dict[str, Any]],
) -> tuple[CompositionSceneAuthoring, tuple]:
    if scene.snapshot_id is None:
        return scene, ()
    fact = facts.get(scene.snapshot_id)
    if fact is None:
        return scene, ()
    words = (fact.get("meta") or {}).get("words") or []
    duration_ticks = int(fact.get("duration_ticks") or 0)
    if scene.source_query is not None:
        from app.editing.source_selection import resolve_source_query
        from app.tools.video.agents import source_selector

        window = await resolve_source_query(
            scene.source_query,
            words,
            duration_ticks=duration_ticks,
            selector=source_selector.call,
        )
        return scene.model_copy(update={
            "source_start_seconds": window.start,
            "source_end_seconds": window.end,
        }), window.sentences
    if not scene.captions_asr:
        return scene, ()
    from app.editing.source_selection import source_sentences

    start = scene.source_start_seconds or 0.0
    end = scene.source_end_seconds
    if end is None:
        end = duration_ticks / 90000
    sentences = source_sentences(words, duration_ticks=duration_ticks)
    return scene, tuple(
        sentence for sentence in sentences if sentence.end > start and sentence.start < end
    )


async def _expand_scene_authoring(
    content: dict[str, Any],
    scene: CompositionSceneAuthoring,
    facts: dict[UUID, dict[str, Any]],
    owner_id: UUID | None = None,
) -> dict[str, Any]:
    scene, caption_sentences = await _resolve_scene_source(scene, facts)
    settings = VersionSettings.model_validate(content["settings"])
    _set_current_scene_timing(content, scene.scene_id, _scene_reading_ticks(scene, settings))
    candidate = CompositionContent.model_validate(content)
    current = next(item for item in candidate.scenes if item.scene_id == scene.scene_id)
    digests = {snapshot_id: fact["digest"] for snapshot_id, fact in facts.items()}
    ops: list[Op] = []

    def reject(message: str, loc: list[str], kind: str = "invalid_scene_input") -> None:
        raise CandidateDesignError(
            message,
            errors=[{"loc": loc, "type": kind, "msg": message}],
            working_content=content,
        )

    if scene.snapshot_id is not None:
        source = scene
        snapshot_id = source.snapshot_id
        fact = facts.get(snapshot_id)
        if fact is None or not fact.get("storage_key"):
            reject("source snapshot is missing or not prepared", ["scene", "snapshot_id"], "source_not_ready")
        kind = fact.get("kind")
        if kind == "image" and (fact.get("meta") or {}).get("origin") == "web_view":
            derived = fact.get("meta") or {}
            parent = derived.get("web_snapshot_id")
            if not parent:
                reject("derived web view has no immutable parent", ["scene", "snapshot_id"], "source_not_ready")
            if source.view_id is not None and str(derived.get("view_id")) != source.view_id:
                reject("derived web view and view_id disagree", ["scene", "view_id"], "target_not_found")
            snapshot_id = UUID(str(parent))
            fact = facts.get(snapshot_id)
            kind = fact.get("kind") if fact else None
        if fact is None or kind not in {"web", "image", "video"}:
            reject("scene source must be a frozen webpage, image or video", ["scene", "snapshot_id"], "source_kind")
        width = height = None
        view = None
        source_range = None
        if kind == "web":
            view_id = source.view_id
            views = (fact.get("meta") or {}).get("views") or []
            view = next((item for item in views if str(item.get("view_id")) == view_id), None)
            if view is None or not view.get("storage_key") or not view.get("digest"):
                reject("view_id is absent or has no immutable bytes", ["scene", "view_id"], "target_not_found")
            width, height = view.get("width"), view.get("height")
        else:
            if source.view_id is not None or source.element_id is not None:
                reject("view_id and element_id apply only to webpage sources", ["scene"], "unsupported_target")
            media = fact.get("meta") or {}
            dimensions = media.get("media") or media
            width, height = dimensions.get("width"), dimensions.get("height")
        if kind != "video" and (
            source.source_start_seconds is not None or source.source_end_seconds is not None
        ):
            reject("only video sources accept a source window", ["scene", "source_end_seconds"], "unsupported_target")
        if kind == "video":
            source_start = seconds_to_ticks(source.source_start_seconds or 0, SOURCE_TIMEBASE)
            source_end = (
                seconds_to_ticks(source.source_end_seconds, SOURCE_TIMEBASE)
                if source.source_end_seconds is not None
                else source_start + output_ticks_to_source_ticks(
                    current.range.duration, settings.timebase,
                )
            )
            if source_start >= (fact.get("duration_ticks") or 0) or source_end > (
                fact.get("duration_ticks") or 0
            ):
                reject("video source window exceeds the frozen source's real duration", ["scene", "source_end_seconds"], "source_too_short")
            if source_end - source_start != output_ticks_to_source_ticks(
                current.range.duration, settings.timebase,
            ):
                reject("video source window must match the Scene duration at 1x", ["scene", "source_end_seconds"], "source_duration_mismatch")
            source_range = TimeRange(start=source_start, end=source_end)
        animations = []
        object_id = f"obj_{scene.scene_id}_source"
        if scene.source_motion == "push":
            if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
                reject("source lacks probed dimensions for a camera push", ["scene"], "source_not_ready")
            from app.editing.grounding import camera_keyframes, resolve_focus

            try:
                focus = resolve_focus((view or {}).get("elements") or [], source.element_id)
            except ValueError as exc:
                reject(str(exc), ["scene", "element_id"], "target_not_found")
            duration = current.range.duration
            zoom, positions = camera_keyframes(
                focus,
                view_width=width,
                view_height=height,
                canvas_width=settings.width,
                canvas_height=settings.height,
                clip_ticks=duration,
                arrival_frac=0.45,
            )
            animations = [
                {
                    "animation_id": f"anm_{scene.scene_id}_scale",
                    "target_object_id": object_id,
                    "property": "transform.scale",
                    "keyframes": [
                        {"at": 0, "value": 1.08},
                        {"at": positions[1][0], "value": zoom},
                        {"at": duration, "value": round(min(zoom * 1.01, 2.05), 3)},
                    ],
                },
                {
                    "animation_id": f"anm_{scene.scene_id}_position",
                    "target_object_id": object_id,
                    "property": "transform.position",
                    "keyframes": [
                        {"at": at, "value": [float(point[0]), float(point[1])]}
                        for at, point in positions
                    ],
                },
            ]
        layout = LayoutBox(x=0, y=0, width=settings.width, height=settings.height)
        media_object = (
            WebObject(kind="web", object_id=object_id, view_id=source.view_id, layout=layout, fit="cover")
            if kind == "web"
            else VideoObject(
                kind="video",
                object_id=object_id,
                layout=layout,
                fit=scene.source_fit,
                transform=scene.source_transform or Transform(),
                gain_db=scene.source_gain_db if scene.source_gain_db is not None else 0.0,
                muted=scene.source_muted,
            )
            if kind == "video"
            else ImageObject(kind="image", object_id=object_id, layout=layout, fit="contain")
        )
        ops.extend([
            BindSource(op="bind_source", snapshot_id=snapshot_id),
            AddClip.model_validate({
                "op": "add_clip", "track_id": "trk_main",
                "clip": {
                    "clip_id": f"clp_{scene.scene_id}_source",
                    "range": current.range.model_dump(mode="json"),
                    "scene_id": scene.scene_id,
                    "source": {
                        "snapshot_id": str(snapshot_id),
                        "snapshot_digest": fact["digest"],
                        "source_range": source_range.model_dump(mode="json") if source_range else None,
                    },
                    "object": media_object.model_dump(mode="json"),
                    "animations": animations,
                },
            }),
        ])

    reveal = frames_to_ticks(18, settings.timebase, settings.fps.num, settings.fps.den)
    stagger = frames_to_ticks(12, settings.timebase, settings.fps.num, settings.fps.den)
    try:
        if scene.headline is not None:
            height = 260.0 if scene.snapshot_id is not None else 400.0
            ops.extend(expand_preset(scene.text_preset or "title-lockup", candidate, {
                "title": scene.headline,
                "subtitle": scene.supporting_text,
                "range": current.range.model_dump(mode="json"),
                "scene_id": scene.scene_id,
                "layout": {
                    "x": settings.width * 0.08,
                    "y": settings.height * (0.68 if scene.snapshot_id is not None else 0.30),
                    "width": settings.width * 0.84,
                    "height": height,
                },
                "reveal": reveal,
                "stagger": stagger,
                "hold": current.range.duration - reveal - stagger,
            }))
        elif scene.items:
            reveal_total = reveal + (len(scene.items) - 1) * stagger
            height = min(settings.height * 0.70, max(160.0, len(scene.items) * 96.0))
            ops.extend(expand_preset("list-reveal", candidate, {
                "items": [{"text": item} for item in scene.items],
                "range": current.range.model_dump(mode="json"),
                "scene_id": scene.scene_id,
                "layout": {
                    "x": settings.width * 0.10,
                    "y": (settings.height - height) / 2,
                    "width": settings.width * 0.80,
                    "height": height,
                },
                "reveal": reveal,
                "stagger": stagger,
                "hold": current.range.duration - reveal_total,
            }))
        bound = {binding.snapshot_id for binding in candidate.sources}
        ops = [
            op for op in ops
            if not isinstance(op, BindSource) or op.snapshot_id not in bound
        ]
        candidate = apply_ops(candidate, ops, digests)
        if scene.captions_asr:
            from app.editing.source_captions import source_caption_ops

            if source_range is None:
                raise ValueError("ASR captions require a video source window")
            candidate = apply_ops(candidate, source_caption_ops(
                candidate,
                scene_id=scene.scene_id,
                snapshot_id=snapshot_id,
                snapshot_digest=fact["digest"],
                source_range=source_range,
                sentences=caption_sentences,
            ), digests)
        if scene.narration_snapshot_id is not None:
            from app.editing.narration_audio import narration_audio_ops
            from app.models.tables import NarrationAlignment

            narration_fact = facts.get(scene.narration_snapshot_id)
            if narration_fact is None or narration_fact.get("kind") != "audio" or not narration_fact.get("storage_key"):
                raise ValueError("narration_snapshot_id is not a prepared audio source")
            async with AsyncSessionLocal() as db:
                alignment = await db.get(NarrationAlignment, scene.narration_alignment_id)
            if alignment is None:
                raise ValueError("narration alignment does not exist")
            if owner_id is not None and alignment.owner_id != owner_id:
                raise PermissionError("narration alignment belongs to another user")
            candidate = apply_ops(candidate, narration_audio_ops(
                candidate,
                scene_id=scene.scene_id,
                snapshot_id=scene.narration_snapshot_id,
                snapshot_digest=narration_fact["digest"],
                alignment=alignment,
            ), digests)
    except (PresetError, ValueError) as exc:
        reject(str(exc), ["scene", "text_preset"] if scene.headline or scene.items else ["scene"])
    return candidate.model_dump(mode="json")


def _music_bed_write(
    content: dict[str, Any],
    music_snapshot_id: UUID | None,
    facts: dict[UUID, dict[str, Any]],
) -> dict[str, Any]:
    if music_snapshot_id is None:
        return content
    if not isinstance(music_snapshot_id, UUID):
        music_snapshot_id = UUID(str(music_snapshot_id))
    music = facts.get(music_snapshot_id)
    if music is None or music.get("kind") != "audio" or not music.get("storage_key") or not music.get("duration_ticks"):
        raise CandidateDesignError(
            "music_snapshot_id must be a prepared audio snapshot with real duration",
            errors=[{"loc": ["music_snapshot_id"], "type": "source_not_ready", "msg": "choose a prepared music snapshot"}],
            working_content=content,
        )
    updated = deepcopy(content)
    updated["timeline"]["tracks"] = [
        track for track in updated["timeline"]["tracks"] if track.get("track_id") != "trk_music"
    ]
    total_ticks = max((scene["range"]["end"] for scene in updated["scenes"]), default=0)
    candidate = CompositionContent.model_validate(updated)
    ops = TypeAdapter(list[Op]).validate_python(instantiate_music_bed(
        MusicBed(
            snapshot_id=music_snapshot_id,
            snapshot_digest=music["digest"],
            duration_ticks=music["duration_ticks"],
        ),
        total_ticks=total_ticks,
        timebase=candidate.settings.timebase,
    ))
    bound = {binding.snapshot_id for binding in candidate.sources}
    ops = [
        op for op in ops
        if not isinstance(op, BindSource) or op.snapshot_id not in bound
    ]
    return apply_ops(candidate, ops, {music_snapshot_id: music["digest"]}).model_dump(mode="json")


def _fit_scene_plan_target(
    content: dict[str, Any], target_seconds: float
) -> dict[str, Any]:
    updated = deepcopy(content)
    settings = VersionSettings.model_validate(updated["settings"])
    target = seconds_to_ticks(target_seconds, settings.timebase)
    natural = max((scene["range"]["end"] for scene in updated["scenes"]), default=0)
    if target < natural:
        raise CandidateDesignError(
            "target_seconds is shorter than the scenes' minimum reading time",
            errors=[{
                "loc": ["target_seconds"], "type": "duration_too_short",
                "msg": f"the current scenes need {natural / settings.timebase:g} seconds",
            }],
            working_content=content,
        )
    extra = target - natural
    if extra and updated["scenes"]:
        final_id = updated["scenes"][-1]["scene_id"]
        updated["scenes"][-1]["range"]["end"] = target
        for track in updated["timeline"]["tracks"]:
            for clip in track.get("clips") or []:
                if clip.get("scene_id") == final_id:
                    clip["range"]["end"] += extra
    return updated


async def _design_composition_locked(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    args: CompositionDesignVideoArgs,
    request_id: str | None,
    skill: SkillCreativeContext | None,
    builtin_skill: BuiltInSkillReference | None,
    skill_package: Any,
) -> dict[str, Any] | WorkingDraftUpdated:
    """Merge high-level creative intent or complete entities, then save."""
    state = args._working_draft
    skill_resources = deepcopy((state or {}).get("design", {}).get("skill_resources") or {})
    if state is not None:
        update = deepcopy(state.get("design") or {})
        update.pop("skill_resources", None)
        update.pop("authoring", None)
        for field in (*_EXPLICIT_CONSTRAINT_FIELDS, "user_constraints"):
            update.pop(field, None)
        explicit_constraints = args._explicit_constraints
        args = args.model_copy(update=update)
        args._working_draft = state
        args._explicit_constraints = explicit_constraints

    composition = None
    base_version = None
    base_content = None
    if args.composition_id is not None:
        composition, base_version = await get_video_version(
            db, owner_id=owner_id, composition_id=args.composition_id
        )
        base_content = content_of(base_version)

    from app.editing.store import _raw_snapshot_ids, _resolve_raw_snapshot_references

    high_level_draft = (
        getattr(args, "scene_plan", None) is not None or getattr(args, "scene", None) is not None
        or (state or {}).get("design", {}).get("authoring") == "high_level_scene"
    )
    if state is not None:
        content = deepcopy(state["content"])
    else:
        content = (
            base_content.model_dump(mode="json")
            if base_content is not None
            else {
                "schema_version": SCHEMA_VERSION,
                "sources": [],
                "scenes": [],
                "timeline": {"tracks": [], "transitions": []},
            }
        )
        content = apply_working_draft_writes(
            content,
            args.entity_writes(),
            settings=args.settings,
            sources=args.sources,
        )
    if args.scene_plan is not None:
        source_ids = set(args.source_ids or [])
        if args.music_snapshot_id is not None:
            source_ids.add(args.music_snapshot_id)
        if args.scene is not None and args.scene.narration_snapshot_id is not None:
            source_ids.add(args.scene.narration_snapshot_id)
        facts = await snapshot_facts(db, source_ids)
        if any(
            snapshot_id not in facts or facts[snapshot_id].get("owner_id") != owner_id
            for snapshot_id in source_ids
        ):
            raise DesignError("a referenced source snapshot is not accessible to this user")
        dimensions = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
        aspect = args.aspect or "16:9"
        width, height = dimensions[aspect]
        derived_settings = args.settings or VersionSettings(
            width=width,
            height=height,
            background=args.background or "#F8FAFC",
        )
        bindings = [
            SourceBinding(snapshot_id=snapshot_id, snapshot_digest=facts[snapshot_id]["digest"])
            for snapshot_id in args.source_ids or []
        ]
        content = apply_working_draft_writes(
            {
                "schema_version": SCHEMA_VERSION,
                "sources": [],
                "scenes": [],
                "timeline": {"tracks": [], "transitions": []},
            },
            EntityWrites(),
            settings=derived_settings,
            sources=bindings,
        )
        content = _scene_plan_write(content, args.scene_plan)
    original_scene_content = deepcopy(content) if args.scene is not None else None
    try:
        if args.scene is not None:
            facts = await snapshot_facts(db, _raw_snapshot_ids(content))
            parent_ids = {
                UUID(str(parent))
                for fact in facts.values()
                if (parent := (fact.get("meta") or {}).get("web_snapshot_id"))
            }
            if parent_ids - set(facts):
                facts = await snapshot_facts(db, set(facts) | parent_ids)
            if any(facts[snapshot_id].get("owner_id") != owner_id for snapshot_id in facts):
                raise DesignError("a referenced source snapshot is not accessible to this user")
            content = await _expand_scene_authoring(content, args.scene, facts, owner_id=owner_id)
            _validate_scene_verbatim_copy(args=args, composition=content)
        if high_level_draft and not args.save and args.music_snapshot_id is not None:
            content = _music_bed_write(content, args.music_snapshot_id, facts)
    except CandidateDesignError as exc:
        if original_scene_content is not None:
            exc.working_content = original_scene_content
        raise
    if args.skill_resource is not None:
        try:
            content, declaration_digest = await _place_skill_generator(
                db, owner_id=owner_id, project_id=project_id, content=content,
                placement=args.skill_resource, skill=skill, package=skill_package,
            )
        except CandidateDesignError as exc:
            exc.working_content = deepcopy(content)
            raise
        clip_id = args.skill_resource.clip_id
        skill_resources[clip_id] = {
            "resource_id": args.skill_resource.resource_id,
            "declaration_digest": declaration_digest,
            "skill_version_id": str(skill.version.id),
        }
    facts = await snapshot_facts(db, _raw_snapshot_ids(content))
    if any(
        snapshot_id not in facts or facts[snapshot_id].get("owner_id") != owner_id
        for snapshot_id in _raw_snapshot_ids(content)
    ):
        raise DesignError("a referenced source snapshot is not accessible to this user")
    content = _apply_focus_write(content, args, facts)
    if args.skill_resource is not None:
        content = _resolve_raw_snapshot_references(content, facts, owner_id=owner_id)
        await db.commit()
    args._working_draft = working_draft_arguments(args, content)
    if skill_resources:
        args._working_draft["design"]["skill_resources"] = skill_resources
    if not args.save:
        return WorkingDraftUpdated(args._working_draft)

    if args.save and high_level_draft:
        if args.target_seconds is not None:
            content = _fit_scene_plan_target(content, args.target_seconds)
        content = _music_bed_write(content, args.music_snapshot_id, facts)
        facts = await snapshot_facts(db, _raw_snapshot_ids(content))

    if args.save:
        from app.agents.working_drafts import assert_working_draft_review_ready

        assert_working_draft_review_ready(args._working_draft or {})
    try:
        direct_composition = _complete_direct_generator_outputs(content)
        direct_composition = _resolve_raw_snapshot_references(
            direct_composition, facts, owner_id=owner_id
        )
        builtin_id = builtin_skill.skill_id if builtin_skill is not None else None
        inherited_provenance = base_version.skill_provenance or {} if base_version else {}
        inherited_reference = inherited_provenance.get("skill_reference")
        inherited_builtin_id = (
            inherited_reference.get("skill_id")
            if isinstance(inherited_reference, dict) and inherited_reference.get("kind") == "builtin"
            else None
        )
        route_builtin_id = builtin_id or inherited_builtin_id
        arc_id = getattr(args, "arc_id", None) or inherited_provenance.get("arc_id")
        direct_candidate = _validate_direct_design(args=args, composition=direct_composition)
        references = args.copy_references or []
        provenance = {
            "skill": route_builtin_id,
            "mode": "composition",
            "language": args.language,
            **({"arc_id": arc_id} if arc_id is not None else {}),
            "copy_evidence": await _direct_copy_evidence(
                db, owner_id=owner_id, references=references, candidate=direct_candidate,
            ),
        }
        if skill_resources:
            provenance["skill_generator_resources"] = skill_resources
        name = (args.name or "").strip()[:255]
    except CandidateDesignError as exc:
        exc.working_content = deepcopy(content)
        raise
    return await _save_composition_version(
        db,
        owner_id=owner_id,
        project_id=project_id,
        args=args,
        request_id=request_id,
        composition=composition,
        base_version=base_version,
        base_content=base_content,
        direct_composition=direct_composition,
        direct_candidate=direct_candidate,
        provenance=provenance,
        name=name,
        skill=skill,
        builtin_skill=builtin_skill,
        route_builtin_id=route_builtin_id,
    )


async def prepare_video_materials(
    *,
    owner_id: UUID,
    project_id: UUID,
    args: Any,
) -> tuple[dict[str, Any], list[Any]]:
    """Commit immutable source preparation independently of any later design."""
    from app.pipeline.assets import create_web_page_assets_committed_from_urls
    from app.tools.video.preparation import canonical_resource, snapshot_web_generator_resources

    async with AsyncSessionLocal() as db:
        snapshots: list[SourceSnapshot] = []
        referenced_assets: list[Asset] = []
        if args.material_asset_ids:
            referenced_assets = list((await db.scalars(select(Asset).where(
                Asset.id.in_(args.material_asset_ids), Asset.user_id == owner_id,
            ))).all())
            if len(referenced_assets) != len(set(args.material_asset_ids)):
                raise DesignError("every selected material asset must be accessible to this user")
            referenced_assets.sort(key=lambda item: args.material_asset_ids.index(item.id))
        supported = {AssetType.WEB_PAGE, AssetType.IMAGE, AssetType.VIDEO, AssetType.AUDIO}
        if any(asset.type not in supported for asset in referenced_assets):
            raise DesignError("video authoring accepts captured webpages, images, videos and audio")
        pending = [
            asset for asset in referenced_assets
            if asset.type != AssetType.WEB_PAGE
            and asset.processing_status in (AssetStatus.PENDING, AssetStatus.PROCESSING)
        ]
        if pending:
            from sqlalchemy import update
            from app.models.tables import now_utc

            async with AsyncSessionLocal() as session:
                await session.execute(update(Asset).where(
                    Asset.id.in_([asset.id for asset in pending]),
                    Asset.user_id == owner_id,
                    Asset.processing_status == AssetStatus.PENDING,
                    Asset.processing_requested_at.is_(None),
                ).values(processing_requested_at=now_utc()))
                await session.commit()
            await _await_media_settled(db, owner_id, {asset.id for asset in pending})
            referenced_assets = list((await db.scalars(select(Asset).where(
                Asset.id.in_(args.material_asset_ids), Asset.user_id == owner_id,
            ))).all())
            referenced_assets.sort(key=lambda item: args.material_asset_ids.index(item.id))
        if any(
            asset.type != AssetType.WEB_PAGE and asset.processing_status != AssetStatus.COMPLETED
            for asset in referenced_assets
        ):
            raise DesignError("every selected source asset must be processed and readable")

        if args.material_urls:
            await create_web_page_assets_committed_from_urls(
                project_id, owner_id, args.material_urls,
            )
        web_ids = {asset.id for asset in referenced_assets if asset.type == AssetType.WEB_PAGE}
        web_assets = await _ready_web_pages(
            db,
            project_id=project_id,
            owner_id=owner_id,
            asset_ids=web_ids or None,
            urls={url.strip() for url in args.material_urls} if args.material_urls else None,
        ) if (web_ids or args.material_urls) else []
        if args.material_urls:
            requested = {url.strip() for url in args.material_urls}
            if {(asset.meta or {}).get("capture_url") for asset in web_assets} != requested:
                raise DesignError("the requested website has no usable completed capture")
        if any(not (asset.meta or {}).get("shots") for asset in web_assets):
            raise DesignError("every webpage must have real captured views")
        for asset in web_assets:
            web_snapshot = await snapshot_web_asset(db, asset, owner_id=owner_id)
            snapshots.append(web_snapshot)
            snapshots.extend(await snapshot_web_generator_resources(
                db, owner_id=owner_id, web_snapshot=web_snapshot,
            ))
        for asset in referenced_assets:
            if asset.type == AssetType.WEB_PAGE:
                continue
            snapshots.append(await (
                snapshot_image_asset(db, asset, owner_id=owner_id)
                if asset.type == AssetType.IMAGE
                else snapshot_video_asset(db, asset, owner_id=owner_id)
                if asset.type == AssetType.VIDEO
                else snapshot_audio_asset(db, asset, owner_id=owner_id)
            ))
        if args.material_output_ids:
            outputs = list((await db.scalars(
                select(Output).join(Project, Output.project_id == Project.id).where(
                    Output.id.in_(args.material_output_ids), Project.user_id == owner_id,
                )
            )).all())
            if len(outputs) != len(set(args.material_output_ids)):
                raise DesignError("every selected Output must be accessible to this user")
            outputs.sort(key=lambda item: args.material_output_ids.index(item.id))
            snapshots.extend([
                await snapshot_video_output(db, output, owner_id=owner_id)
                for output in outputs
            ])
        music_ids = getattr(args, "material_music_ids", None)
        if music_ids:
            from app.models.tables import Music
            tracks = list((await db.scalars(select(Music).where(
                Music.id.in_(music_ids),
                (Music.is_public.is_(True)) | (Music.generated_by_user_id == owner_id),
            ))).all())
            if len(tracks) != len(set(music_ids)):
                raise DesignError("every selected Music id must name a public or user-owned library piece; Music ids are distinct from Asset ids")
            tracks.sort(key=lambda track: music_ids.index(track.id))
            for track in tracks:
                snapshot = await snapshot_music_track(db, track, owner_id=owner_id)
                if snapshot.origin_project_id is None:
                    snapshot.origin_project_id = project_id
                snapshots.append(snapshot)
        targets = list(getattr(args, "material_targets", None) or [])
        if targets:
            selected = list((await db.scalars(select(SourceSnapshot).where(
                SourceSnapshot.id.in_({target.snapshot_id for target in targets}),
                SourceSnapshot.owner_id == owner_id,
            ))).all())
            if len(selected) != len({target.snapshot_id for target in targets}):
                raise DesignError("every selected source target must be accessible to this user")
            for target in targets:
                source = next(item for item in selected if item.id == target.snapshot_id)
                if source.kind != "web" and (target.view_id or target.element_id):
                    raise DesignError("view_id/element_id targets apply only to web snapshots")
            snapshots.extend(selected)
        snapshots = list({snapshot.id: snapshot for snapshot in snapshots}.values())
        await db.commit()
        omitted: list[dict[str, str]] = []
        evidence: dict[str, Any] = {}
        images = await _view_media_inputs(
            [snapshot for snapshot in snapshots if snapshot.kind == "web"],
            _view_facts([snapshot for snapshot in snapshots if snapshot.kind == "web"]),
            omitted=omitted,
            targets=targets or None,
        )
        images.extend(await _fixed_media_inputs([
            snapshot for snapshot in snapshots
            if not (snapshot.kind == "image" and (snapshot.meta or {}).get("origin") == "web_view")
        ],
            omitted=omitted,
            continuous_video=getattr(args, "video_observation", "representative_frames") == "continuous",
            evidence=evidence,
        ))
        resources = []
        for snapshot in snapshots:
            resource = canonical_resource(
                snapshot,
                target=next(
                    (target for target in targets if target.snapshot_id == snapshot.id),
                    None,
                ),
            )
            if str(snapshot.id) in evidence:
                resource["model_evidence"] = evidence[str(snapshot.id)]
            resources.append(resource)
        return {
            "resources": resources,
            "context_keys": [f"snapshot:{snapshot.id}:{snapshot.digest}" for snapshot in snapshots],
            "media_files": len(images),
            "media_omitted": omitted,
        }, images


async def capture_video_web(
    *,
    owner_id: UUID,
    project_id: UUID,
    request: CaptureRequest,
) -> tuple[dict[str, Any], list[Any]]:
    """Bind and mechanically compile a generic CaptureRequest, then return partials."""
    from app.tools.video.preparation import canonical_resource, snapshot_web_generator_resources

    async with AsyncSessionLocal() as db:
        source = await db.get(SourceSnapshot, request.source_snapshot_id)
        if source is None or source.owner_id != owner_id or source.kind != "web":
            raise DesignError("CaptureRequest source snapshot is not an accessible frozen webpage")
        bound = compile_capture_request(
            request,
            snapshots=[{
                "id": source.id,
                "kind": source.kind,
                "digest": source.digest,
                "meta": source.meta or {},
            }],
        )
        _asset, snapshot = await _execute_capture_plan(
            db, owner_id=owner_id, project_id=project_id, plan=bound,
        )
        derivation_issues: list[dict[str, str]] = []
        snapshots = [snapshot]
        snapshots.extend(await snapshot_web_generator_resources(
            db, owner_id=owner_id, web_snapshot=snapshot, issues=derivation_issues,
        ))
        await db.commit()
        omitted: list[dict[str, str]] = []
        images = await _view_media_inputs([snapshot], _view_facts([snapshot]), omitted=omitted)
        snapshot_meta = snapshot.meta or {}
        snapshot_issues = list(snapshot_meta.get("capture_issues") or [])
        all_issues = snapshot_issues + derivation_issues
        issues = all_issues[:64]
        source_issue_count = int(
            snapshot_meta.get("capture_issue_count") or len(snapshot_issues)
        )
        issue_count = source_issue_count + len(derivation_issues)
        resources: list[dict[str, Any]] = []
        for item in snapshots:
            resource = canonical_resource(item)
            resource.pop("artifact_role", None)
            resource.pop("paired_view_id", None)
            role = str((item.meta or {}).get("artifact_role") or "view")
            resource["capture_kind"] = {
                "cutout": "elements", "blank_plate": "blank_plate",
            }.get(role, "page")
            if item.kind == "web":
                resource.pop("lines", None)
                for view in resource.get("views") or []:
                    view.pop("artifact_role", None)
                    view.pop("paired_view_id", None)
                    view_role = str(next(
                        candidate.get("artifact_role") or "view"
                        for candidate in (item.meta or {}).get("views") or []
                        if candidate.get("view_id") == view.get("view_id")
                    ))
                    view["capture_kind"] = {
                        "cutout": "elements", "blank_plate": "blank_plate",
                    }.get(view_role, "page")
                    view["elements"] = [
                        element for element in view.get("elements") or []
                        if element.get("target_id") is not None or element.get("member_id") is not None
                    ]
            resources.append(resource)
        return {
            "resources": resources,
            "context_keys": [f"snapshot:{item.id}:{item.digest}" for item in snapshots],
            "capture_request_digest": capture_plan_digest(bound),
            "source_snapshot_id": str(source.id),
            "snapshot_id": str(snapshot.id),
            "snapshot_digest": snapshot.digest,
            "refreshed": True,
            "partial": bool(all_issues),
            "issues": issues,
            "issue_count": issue_count,
            "issues_truncated": bool(snapshot_meta.get("capture_issues_truncated")) or issue_count > len(issues),
            "media_files": len(images),
            "media_omitted": omitted,
        }, images




async def design_video(
    *,
    owner_id: UUID,
    project_id: UUID,
    args: CompositionDesignVideoArgs,
    request_id: str | None,
    skill_version_id: UUID | None = None,
    skill_reference: SkillReference | None = None,
    skill_package: Any = None,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any] | WorkingDraftUpdated:
    """The incremental Composition design entry, optionally Skill-bound."""
    context = request_context or {}
    args = bind_explicit_design_constraints(
        args, user_text=str(context.get("user_text") or ""), brief=context.get("brief"),
    )
    if skill_reference is not None and skill_version_id is not None:
        raise DesignError("bind one Skill reference, not two")
    builtin_skill = None
    if isinstance(skill_reference, BuiltInSkillReference):
        from app.skills.resolution import SkillResolutionError, get_builtin_skill_option

        try:
            option = get_builtin_skill_option(skill_reference.skill_id, version=skill_reference.version)
        except SkillResolutionError as exc:
            raise DesignError(str(exc)) from exc
        if option.reference != skill_reference:
            raise DesignError("built-in Skill version is unavailable")
        builtin_skill = skill_reference
    elif isinstance(skill_reference, ExternalSkillReference):
        skill_version_id = skill_reference.skill_version_id
    async with AsyncSessionLocal() as db:
        skill = (
            await load_skill_creative_context(
                db,
                owner_id=owner_id,
                skill_version_id=skill_version_id,
            )
            if skill_version_id is not None
            else None
        )
        try:
            return await _design_composition_locked(
                db,
                owner_id=owner_id,
                project_id=project_id,
                args=args,
                request_id=request_id,
                skill=skill,
                builtin_skill=builtin_skill,
                skill_package=skill_package,
            )
        except AgentStopError as exc:
            active_package = skill.package if skill is not None else None
            if active_package is not None:
                exc.facts = active_package.execution_facts
            raise

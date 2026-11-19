"""Pydantic models for Repurposer API."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationInfo,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
import structlog

from app.editing.edits import ClipEntityWrite
from app.editing.revisions import RevisionOp
from app.editing.schemas import CompositionContent, Scene, Track, Transition

logger = structlog.get_logger(__name__)


def canonical_json_hash(value: dict) -> str:
    """sha256 of the canonical JSON (sorted keys, tight separators).

    The chain-integrity hash for the Operation Model (ADR-032) — server-side
    single source; clients use the server-provided ``spec_hash`` as their
    ``base_hash`` rather than reimplementing this (float formatting differs
    across JS/Python).
    """
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class MediaInputType(StrEnum):
    """Media types that can be fed directly to a multimodal LLM."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class MediaInput(BaseModel):
    """A single media snippet passed to the analyzer alongside source text assets.

    Uses OpenAI-compatible content parts (image_url / video_url / audio_url).
    The URL may be a base64 data URL or an HTTP URL depending on model/provider
    capabilities and deployment constraints.
    """

    model_config = ConfigDict(extra="forbid")

    type: MediaInputType
    mime: str
    data_url: str
    caption: str | None = None


class AssetType(StrEnum):
    """Asset types."""

    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    SLIDES = "slides"
    IMAGE = "image"
    VOICE_SAMPLE = "voice_sample"
    PAST_MATERIAL = "past_material"
    # A user-named URL captured server-side (copy manifest + screenshot) —
    # born through ``assets.create_web_page_asset_from_url``, never through
    # the file-upload route (no bytes exist at birth).
    WEB_PAGE = "web_page"


class AssetStatus(StrEnum):
    """Asset processing statuses.

    Drives the async processing pipeline: an asset is created ``PENDING`` on
    upload, a worker flips it to ``PROCESSING`` while it runs, then to
    ``COMPLETED`` or ``FAILED``. Replaces the previous ``processed_at IS NULL``
    overload that could not distinguish "not yet processed" from "failed".
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WebPageResearch(BaseModel):
    """The grounding manifest a WEB_PAGE capture produces (``meta.research``).

    Every on-screen string a downstream skill quotes must trace to one of
    these lists. Bounds are capture-side (``tools/research/capture.py``):
    items are 2–90 chars, deduped, capped per field.
    """

    model_config = ConfigDict(extra="forbid")

    url: str  # the final URL after redirects
    title: str = ""
    description: str = ""
    h1: list[str] = Field(default_factory=list)
    h2: list[str] = Field(default_factory=list)
    h3: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    # Paragraph copy (<p>) — the hero claims / feature blurbs a film quotes.
    # Longer per-item bound than CTA copy (capture.py _PARAGRAPH_MAX_LEN);
    # absent on pre-paragraphs captures (read tolerance).
    paragraphs: list[str] = Field(default_factory=list)
    # Visible rendered-body lines that the structured HTML inventory missed.
    # Dynamic clients can therefore ground copy in the DOM the user actually saw.
    body: list[str] = Field(default_factory=list)
    body_truncated: bool = False


class CaptureBox(BaseModel):
    """A rectangle in either CSS-page or image-pixel coordinates."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float
    height: float


class PageElement(BaseModel):
    """One visible element in a section shot — the ui scene's camera-target
    inventory (ADR-121 B2: the model names element ids, never coordinates).
    Box is viewport-normalized within its shot; ``covered`` = visually
    occluded at capture time (the model should pick another target)."""

    model_config = ConfigDict(extra="forbid")

    id: str  # s<shot>e<j> — assigned capture-side
    # CaptureRequest lineage lives on the element as well as its containing
    # ShotRef: collection members need stable identities for paired geometry
    # and derived-resource provenance.
    target_id: str | None = None
    member_id: str | None = None
    member_digest: str | None = None
    kind: str  # heading / text / button / image / video / pinned
    text: str = ""
    selector: str | None = None  # bounded CSS identity used by a later CapturePlan
    x: float
    y: float
    w: float
    h: float
    covered: bool = False
    # Absolute CSS-page box of the visible element region. ``pixel_box`` is
    # the same region in the full-page image; the element crop starts at its
    # own (0, 0). Old captures carry neither enhancement.
    css_box: CaptureBox | None = None
    full_css_box: CaptureBox | None = None
    pixel_box: CaptureBox | None = None
    device_scale_factor: float = 1.0
    region_text: str | None = None
    region_text_truncated: bool | None = None
    region_visually_truncated: bool | None = None
    image_key: str | None = None
    image_width: int | None = None
    image_height: int | None = None


class ShotRef(BaseModel):
    """One captured view of the page (ADR-121 B1): ``shots[0]`` = the fold,
    the rest are section stops picked from heading anchors. ``key`` = the
    screenshot's relative object key; ``elements`` = the camera-target
    inventory at this stop."""

    model_config = ConfigDict(extra="forbid")

    key: str
    y: int = 0  # page-absolute scroll offset the shot was taken at
    heading: str = ""  # the anchor's text ("(top)"/"(step)" = code seats)
    elements: list[PageElement] = Field(default_factory=list)
    css_width: int | None = None
    css_height: int | None = None
    device_scale_factor: float = 1.0
    view_id: str | None = None
    state_id: str | None = None
    output_id: str | None = None
    artifact_role: Literal["view", "full", "cutout", "blank_plate", "hero"] | None = None
    paired_view_id: str | None = None
    target_id: str | None = None
    target_ids: list[str] | None = None
    target_element_id: str | None = None
    member_id: str | None = None
    transparent: bool | None = None
    route: str | None = None
    actions: list[dict] | None = None
    page_height: int | None = None
    region_text: str | None = None
    region_text_truncated: bool | None = None
    region_visually_truncated: bool | None = None


class PageImageRef(BaseModel):
    """The settled full-page image and its CSS-to-pixel mapping."""

    model_config = ConfigDict(extra="forbid")

    key: str
    width: int
    height: int
    css_width: int
    css_height: int
    device_scale_factor: float


class WebPageMeta(BaseModel):
    """``meta`` shape of a WEB_PAGE asset: the source URL, the research
    manifest, and the screenshot's storage key (absent when the screenshot
    half degraded honestly).

    ``extra="allow"``: the row's meta dict also carries the generic chain
    keys (``content_sha256`` / ``processing_stage`` / dims), which are not
    this type's contract. Pre-ADR-121 rows carry no ``shots`` — readers
    tolerate the empty list (fold-only capture)."""

    model_config = ConfigDict(extra="allow")

    capture_url: str
    research: WebPageResearch | None = None
    screenshot_key: str | None = None
    shots: list[ShotRef] = Field(default_factory=list)
    page: PageImageRef | None = None


class ProjectStatus(StrEnum):
    """Project statuses."""

    DRAFT = "draft"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    REVIEW = "review"
    COMPLETED = "completed"


class WorkflowStatus(StrEnum):
    """Workflow run statuses."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatAttachment(BaseModel):
    """File attached to a chat message."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: Literal["file", "image", "video", "audio"]
    url: str | None = None
    size: int | None = None
    status: Literal["uploading", "uploaded", "failed"] = "uploaded"


class ConversationResponse(BaseModel):
    """Chat session response.

    ``pending_question`` is the conversation's latest unanswered question
    (NULL answer = pending) — the dock's zero-in-memory-state rebuild source.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    asset_id: UUID | None = None
    asset_type: Literal["clip", "derivative"] | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    pending_question: ChatMessageResponse | None = None
    context: dict[str, Any] | None = None


class MessageRole(StrEnum):
    """Chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMentionGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ChatMentionPixelSize(ChatMentionGeometry):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ChatMentionPixelRect(ChatMentionGeometry):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ChatMentionFloatRect(ChatMentionGeometry):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class ChatMentionNormalizedRect(ChatMentionGeometry):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class ChatMentionRegion(ChatMentionGeometry):
    """A user-drawn region on one exact frame of an output video."""

    coordinateSpace: Literal["source_pixels"]
    mediaTimeMs: int = Field(ge=0)
    sourceSize: ChatMentionPixelSize
    sourceRect: ChatMentionPixelRect
    normalizedRect: ChatMentionNormalizedRect
    viewportRect: ChatMentionFloatRect

    @model_validator(mode="after")
    def region_stays_inside_the_source(self):
        if (self.sourceRect.x + self.sourceRect.width > self.sourceSize.width
                or self.sourceRect.y + self.sourceRect.height > self.sourceSize.height):
            raise ValueError("Selected region exceeds the source video dimensions")
        if (self.normalizedRect.x + self.normalizedRect.width > 1 + 1e-6
                or self.normalizedRect.y + self.normalizedRect.height > 1 + 1e-6):
            raise ValueError("Normalized region exceeds the video frame")
        return self


class ChatMention(BaseModel):
    """An @ entity reference pinned to a definite id (CHAT_ARCH §7).

    The contract and the column (messages.mentions) are the seat; the picker
    UI is the registry-driven composer surface (MENTIONS §4). ``recipe`` is
    retired (MENTIONS §3 — a recipe is just a prompt: the card's prefilled
    template IS the entire launch payload); the type member stays so
    historical messages still render their chips.
    ``workflow_step`` follows the N-15 rename (one concept, one name across
    the stack).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["asset", "output", "transcript_segment", "workflow_step", "recipe"]
    id: str
    label: str
    # 段落级指认 (2026-09-11 — 选区引用): an output mention may pin the exact
    # PASSAGE the user selected on the card face ("把这段改狠一点" — the agent
    # never guesses which sentence). Absent = the whole output is the referent
    # (the pre-quote behavior; old rows read tolerantly).
    quote: str | None = None
    # Spatial + temporal scope on one exact output frame. Old rows omit it.
    region: ChatMentionRegion | None = None

    @model_validator(mode="after")
    def region_belongs_to_an_output(self):
        if self.region is not None and self.type != "output":
            raise ValueError("A selected region can only ride an output mention")
        return self


class BuiltInSkillReference(BaseModel):
    """A deployed, versioned video Skill; never a hidden recipe id."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["builtin"]
    skill_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)


class ExternalSkillReference(BaseModel):
    """An immutable owner-scoped SkillVersion, pinned before design begins."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["external"]
    skill_version_id: UUID


SkillReference = Annotated[
    BuiltInSkillReference | ExternalSkillReference,
    Field(discriminator="kind"),
]


class SkillOption(BaseModel):
    """Picker metadata around the exact reference sent by composer/Home."""

    model_config = ConfigDict(extra="forbid")

    reference: SkillReference
    skill_id: str
    name: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    version_number: int | None = None


class FocusRef(BaseModel):
    """The canvas product a turn was pointed at (ADR-041 D8 焦点注入).

    WRITE-RETIRED (ADR-058): pointing is an @-mention chip now — the mention
    registry is the one definite-reference channel. The shape stays so old
    message rows still validate on READ (messages.focus_output → the rebuilt
    history's gray focus prefix row); nothing writes it anymore.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str


class Option(BaseModel):
    """结构化问题中的一个选项。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_null_description(cls, data: Any) -> Any:
        # 打字机律牙①: the model writes null when an option carries no reason
        # line — pop the key so the "" default applies instead of rejecting
        # the call (a rejection burns a loop iteration that never streams).
        if isinstance(data, dict) and data.get("description") is None:
            data = dict(data)
            data.pop("description", None)
        return data

    id: str = Field(
        description="本题内的选项 ID。固定选项按当前工具规范使用数字，服务端管理的实体目标保留稳定 ID。"
    )
    label: str
    # 一问拍一体化 (2026-09-27, Claude-Card parity): the option's one-line
    # reason rides the card under the label — bare labels forced the
    # "which do you recommend?" follow-up tax. "" on legacy rows and
    # code-built options (asset_role) — 读容忍.
    description: str = Field(
        default="",
        description="用一行说明选择该项的理由，给出用户可以判断的结论，不展示推理过程。",
    )


def resolve_recommended_id(
    recommended_id: str | None, options: list[Option]
) -> str | None:
    """The 推荐标记's ONE validation (一问拍一体化 2026-09-27), shared by the
    ask executions on both paths: at most one, and it must name an option
    that actually shipped — a stale or imagined id drops silently (cosmetic,
    never worth a rejection round; the asset_role code-built options
    invalidate any LLM-written id the same way)."""
    if recommended_id in {o.id for o in options}:
        return recommended_id
    return None


BriefQuestionSlot = Literal[
    "topic", "audience", "tone", "production_direction", "purpose", "target_seconds", "narrative_mode",
    "narration_language", "subtitle_languages", "aspect", "voice_requirements",
    "must_include", "avoid", "success_criteria",
]


class BriefDecisionPage(BaseModel):
    """由服务端固定并展示的一组相关 Brief 字段。"""

    slots: list[BriefQuestionSlot]
    title: str
    choices: list[dict[str, str]]  # atom slot -> frozen option id


class BriefQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("options"), list):
            options = []
            values = {}
            for index, raw in enumerate(data["options"], start=1):
                # Website briefing authors a display setting and an editorial
                # treatment together, but the dock and the Brief own one answer.
                if data.get("slot") == "production_direction" and (
                    data.get("question_language") or isinstance(raw, dict) and ("use_case" in raw or "treatment" in raw)
                ):
                    parts = (raw.get("use_case"), raw.get("treatment")) if isinstance(raw, dict) else (None, None)
                    if not all(isinstance(part, str) and part.strip() for part in parts):
                        raise ValueError("Each direction needs a release setting and a storytelling treatment")
                    direction = " · ".join(part.strip() for part in parts)
                    raw = {"label": direction, "value": direction}
                elif data.get("slot") == "target_seconds" and type(raw) is int:
                    raw = str(raw)
                option = raw
                if isinstance(raw, str):
                    option = {"id": str(index), "label": raw}
                elif isinstance(raw, dict) and "value" in raw:
                    option = {**raw, "id": str(raw.get("id", index))}
                    values[option["id"]] = option.pop("value")
                options.append(option)
            data = {**data, "options": options}
            if values:
                data["option_values"] = values
        return tolerate_null_keys(data, "options", "recommended_id", "default_path")

    slot: BriefQuestionSlot
    # Used when freezing a localized website form. Stored questions carry
    # the resulting display text, including their BriefDecisionPage title.
    question_language: SkipJsonSchema[str | None] = Field(default=None, exclude=True)
    decision_page: BriefDecisionPage | None = None
    option_values: dict[str, str | int | list[str]] | None = None
    question: str
    options: list[Option] = Field(default_factory=list)
    recommended_id: str | None = None
    allow_freeform: bool = True
    required: bool = True
    default_path: str = ""


class BriefAnswerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_slots: list[BriefQuestionSlot] | None = None

    slot: BriefQuestionSlot | Literal["constraints"]
    kind: Literal["option", "freeform"]
    option_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _value_matches_kind(self) -> "BriefAnswerItem":
        if self.kind == "option" and not self.option_id:
            raise ValueError("an option answer needs option_id")
        if self.kind == "freeform" and not (self.text or "").strip():
            raise ValueError("a freeform answer needs non-empty text")
        return self


class AnswerPayload(BaseModel):
    """The typed ``answer`` payload on a message.

    ``bail`` is a first-class answer kind — a graceful exit, never a failure.
    ``start`` is the plan confirmation (the answer that starts the run)
    — a kind of its own, not a magic option id (C1).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["option", "freeform", "bail", "start", "group"]
    option_id: str | None = None
    text: str | None = None
    group_digest: str | None = None
    answers: list[BriefAnswerItem] = Field(default_factory=list)
    answered_at: datetime


class OptionAnswerRequest(BaseModel):
    """Pick one of the question's options (choice questions)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["option"]
    option_id: str


class FreeformAnswerRequest(BaseModel):
    """Free-text answer (choice questions with ``allow_freeform``)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["freeform"]
    text: str


class GroupAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["group"]
    group_digest: str = Field(min_length=64, max_length=64)
    answers: list[BriefAnswerItem] = Field(min_length=1, max_length=13)


class StartAnswerRequest(BaseModel):
    """Confirm the docked plan and start the run (task_book questions).

    Replaces the phase-1 magic ``option_id="start"`` — the confirmation is a
    kind of its own, so the kind-specific field (the review panel's edited
    plan) is only valid here, never silently ignored on other kinds (C2).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["start"]
    autonomy: Literal["auto", "review"] | None = None
    # The review panel's edited plan (hand-edited slots marked explicit).
    # Wins over the stored pending brief, so panel edits reach the run;
    # None = use the stored pending brief.
    intent: InferredIntent | None = None


class BailAnswerRequest(BaseModel):
    """Bail — a graceful exit (back to draft / stop the parked run), never an error.

    A clarification group may include its already-selected answers; remaining
    fields follow the server-owned task defaults. Legacy bails omit both.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bail"]
    group_digest: str | None = Field(default=None, min_length=64, max_length=64)
    answers: list[BriefAnswerItem] = Field(default_factory=list, max_length=13)


# Request body for ``POST /chat/messages/{id}/answer`` — discriminated on
# ``kind`` so kind-specific fields can't ride along where they're ignored.
AnswerRequest = Annotated[
    OptionAnswerRequest
    | FreeformAnswerRequest
    | GroupAnswerRequest
    | StartAnswerRequest
    | BailAnswerRequest,
    Field(discriminator="kind"),
]


class SuggestionRef(BaseModel):
    """The structured provenance of a suggestion pick (ADR-099 §4): a pick
    is a control event, not fresh user input — the visible message text
    stays the option's label, the ref rides structured alongside (the
    mentions pattern: visible text + structured reference). ``source_turn``
    is the assistant row that carried the suggestion; ``suggestion_id`` the
    option's id on that row."""

    model_config = ConfigDict(extra="forbid")

    source_turn: UUID
    suggestion_id: str


class SuggestionRecord(BaseModel):
    """One persisted suggestion on an assistant row (messages.suggestions —
    the 消息 JSONB 交互块): the option plus its code-stamped provenance.
    ``source_turn`` = the carrying row's own id (the ref's lookup anchor);
    ``source_state`` = the stale-check snapshot at stamp time (the asset
    ids the suggestion was grounded against — ADR-099 §4, zero counters).
    All-default fields = wire read tolerance."""

    id: str = ""
    label: str = ""
    description: str = ""
    recommended: bool = False
    source_turn: str = ""
    source_state: dict = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    """A single chat message returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _read_skill_reference(cls, data: Any) -> Any:
        """Skill rides the user row's existing JSONB metadata, not mentions."""
        if isinstance(data, dict):
            if data.get("role") == "user" and data.get("skill") is None:
                skill = (data.get("intent") or {}).get("skill")
                if skill is not None:
                    return {**data, "skill": skill}
            return data
        if getattr(data, "role", None) == "user" and getattr(data, "skill", None) is None:
            skill = (getattr(data, "intent", None) or {}).get("skill")
            if skill is not None:
                return {**getattr(data, "__dict__", {}), "skill": skill}
        return data

    @field_validator("question", mode="before")
    @classmethod
    def _normalize_question_kind(cls, q: Any) -> Any:
        """API-boundary read tolerance (never written): rows stored before
        the kind convergence spell ``choice`` — the wire speaks the current
        spelling (``question``)."""
        if isinstance(q, dict) and q.get("kind") == "choice":
            return {**q, "kind": "question"}
        return q

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)
    mentions: list[ChatMention] = Field(default_factory=list)
    skill: SkillReference | None = None
    focus_output: FocusRef | None = None
    workflow_run_id: UUID | None = None
    # Opening user-message identity for rows born in that turn; NULL on old
    # rows and independent world facts.
    turn_id: UUID | None = None
    turn_state: str | None = None
    intent: dict | None = None
    question: dict | None = None
    answer: dict | None = None
    # 建议谱系交互块 (ADR-099 §4): non-blocking next-step options this
    # assistant row offered, provenance included — the OptionDock renders
    # them under the prose; a pick rides back as suggestion_ref.
    suggestions: list[SuggestionRecord] = Field(default_factory=list)
    # Server-stamped structured additions: domain component references and
    # system notices. Assistant prose stays in content; absent/[] on legacy rows.
    blocks: list[dict] = Field(default_factory=list)
    # 点选引用 (ADR-099 §4): a user row that IS a suggestion pick carries
    # its structured ref — the visible content stays the picked label.
    suggestion_ref: SuggestionRef | None = None
    # Transcript 数组位置 (ADR-108): per-conversation monotonic; the client
    # renders in seq order and never re-derives interleaving from clocks.
    seq: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


    @model_validator(mode="after")
    def _automatic_audio_progress(self):
        """Project old automatic playback receipts as progress on history and SSE."""
        if not (self.intent or {}).get("media_journey"):
            return self
        playback = next((block for block in self.blocks if block.get("kind") == "audio_playback"), None)
        if playback is not None:
            items = playback.get("items") or []
            if items and isinstance(items[0], dict) and "prepared_audio" not in self.intent:
                item = items[0]
                self.intent = {**self.intent, "prepared_audio": {
                    key: item.get(key) for key in ("role", "scene_id", "duration_seconds", "snapshot_id", "digest")
                }}
            self.blocks = [block for block in self.blocks if block.get("kind") != "audio_playback"]
        return self


class MessageListResponse(BaseModel):
    """List of chat messages in a session."""

    items: list[ChatMessageResponse]


class TaskListProposal(BaseModel):
    """Intent agent output, state A: run new tasks (→ compile_graph mode②).

    ``tasks=[]`` is the legal "ask back" state (CHAT_ARCH §7) — an ambiguous
    instruction gets a plain reply in ``summary``, not a run.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_null_name(cls, data: Any) -> Any:
        """读容忍 (打字机律牙①): the LLM writes "name": null when it means
        to skip it — a rejection here costs the funnel's repair round,
        which never streams (the prose would pop in as one blob)."""
        if isinstance(data, dict) and data.get("name") is None:
            data = dict(data)
            data.pop("name", None)
        return data

    type: Literal["task_list"] = "task_list"
    tasks: list[TaskItem] = Field(default_factory=list)
    summary: str
    # LLM 建图时命名 (2026-09-09, ADR-058): a compact noun phrase naming the
    # run's deliverable, in the interface language ("中文 LinkedIn 帖子" /
    # "Chinese LinkedIn post"). It titles the run's receipt and completion
    # line — display copy comes from the proposer's FRESH reading of the
    # turn, never from a frozen-params template. "" = unnamed (readers fall
    # back to the chain-derived label).
    name: str = ""


class QuestionProposal(BaseModel):
    """Intent agent output, state C: a structured question (→ QuestionDock).

    N-18 (overturning N-14): the structured-question payload is orthogonal to
    task_list / edit_ops, so the union gains a third state. The pre-N-18
    "tasks=[] ask back" migrates here as an ``options=[]`` + ``allow_freeform``
    question. The LLM only ever raises a plain question — a task_book question
    is raised by the chat plan path, never by the agent.

    ADR-071 ⑤ 方向裁定 (2026-09-11): the provider call sends
    ``response_format: json_object`` — this schema NEVER reaches the model;
    it is the parse-side contract only. The model-facing field spec lives in
    the prompt templates (``app/prompts/chat/plan_mode.j2``'s ask
    rule / ``conversation_mode.j2``'s shape C) — those are the single
    source; the comments here MIRROR them for humans. Edit the templates
    first, then sync this mirror.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_kind(cls, data: Any) -> Any:
        """The pre-convergence schema carried a ``kind`` field ('choice' was
        the only value the LLM ever produced) and the LLM keeps the habit —
        the field is gone (every agent question is a plain question), so the
        key drops on read. Loose nulls read as their empty defaults (读容忍):
        the model writes ``"prose": null`` / ``"options": null`` when it
        means to skip them, and a schema rejection there costs the funnel's
        repair round — which never streams (打字机律 2026-09-08: the prose
        would pop in as one blob at the envelope)."""
        if isinstance(data, dict):
            data = dict(data)
            data.pop("kind", None)
            for nullable in ("prose", "default_path"):
                if data.get(nullable) is None:
                    data[nullable] = ""
            if data.get("options") is None:
                data["options"] = []
        return data

    type: Literal["ask"] = "ask"
    # 框架散文 (2026-09-08, ask 三分解剖 ①): the agent's speech around the
    # question — 认领 the request + why this clarification decides quality.
    # The default path is NEVER woven in (ADR-103: what happens without an
    # answer rides the parameter alone — machine-readable, never spoken).
    # Streams as the turn's echo; the question field stays the bare
    # question (the dock title). Empty only on code-composed questions
    # (caption mode, interrupts) — an LLM ask with empty prose is
    # guardrail-REJECTED into the repair iteration (the bare-call family
    # has no silent dock).
    prose: str = ""
    question: str
    # Options (提问策略 ② mirror): 3 concrete one-word values sourced from the
    # user's persona / project context, TRANSLATED into the interface language
    # (drop to 2 only for a genuinely binary choice); empty only when no
    # sensible options exist (a freeform ask). Freeform input always stays
    # available alongside.
    options: list[Option] = Field(default_factory=list)
    allow_freeform: bool = True
    # 推荐标记 (2026-09-27 一问拍一体化): at most ONE option id the agent
    # recommends — the card marks it, and the prose's lean names the same
    # pick (one judgment, one voice). None = no recommendation.
    recommended_id: str | None = None
    # ADR-052 B2 (ask 一等动作, the shared question shape): ``slot`` names the
    # brief slot this question fills (the pre-run router sets it; the
    # chat loop's shape C leaves it null — post-run questions never backfill
    # a brief). ADR-078 判词④ adds ``asset_role``: the 角色消歧 ask — which
    # uploaded video is the source and which the reference case. Its options
    # are CODE-BUILT (id = asset id, _build_role_question) so the answer
    # settles the PendingPlan pins deterministically; the LLM only frames
    # the speech. ``default_path`` is 提问策略 ③'s schema tooth: the skip
    # path, consumed by the dock's × and the interjection reminder tail —
    # machine-readable only, the prose never carries it.
    slot: BriefQuestionSlot | Literal["asset_role"] | None = None
    default_path: str = ""


class AnswerProposal(BaseModel):
    """Intent agent output, state D: a direct informational answer (G-4).

    Pure information — capability questions, run-progress readouts (the
    context carries the per-step status section, G-2), explanations of
    existing outputs, small talk. Nothing is dispatched, no run starts, no
    question docks: the text lands as a plain assistant message, the same
    archival shape as a plan-path answer turn (B1). The boundary against
    the other states is a prompt rule: work requests go to task_list /
    edit_ops, ambiguous readings go to ask — answer is never the lazy out.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["answer"] = "answer"
    text: str




IntentProposal = Annotated[
    TaskListProposal | QuestionProposal | AnswerProposal,
    Field(discriminator="type"),
]
"""The five-state discriminated union the chat intent agent returns (§3, N-18 + N-21; state E = ADR-057 wiring ops)."""


class IntentResult(BaseModel):
    """Envelope for the single tool-calling-style LLM call (MiniMax JSON mode
    needs a concrete model, so the union lives one level down). Tolerates a
    bare proposal (models sometimes drop the wrapper)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _wrap_bare_proposal(cls, data: Any) -> Any:
        if isinstance(data, dict) and "proposal" not in data and "type" in data:
            return {"proposal": data}
        return data

    proposal: IntentProposal
    # 插话支持 (ADR-053 R2): when the context shows a pending question, the
    # agent's judgment on whether THIS message settles it — judgment is the
    # LLM's, settlement is code's (the retired autoResume freeform
    # masking's honest successor). "answer" = the message ENGAGES the
    # question (2026-09-27 一问拍一体化 — 原话一视同仁: answers it, hands
    # the choice back to the agent, or discusses its options — the code
    # settles the row freeform with the user's own words verbatim; a parked
    # interrupt's answer wakes its run); "skip" = an explicit decline (code
    # settles it as a bail — the text question's only ×, since it docks no
    # pill); "none" = a clearly unrelated interjection (the question stays
    # pending and the reply gets the code-composed reminder tail).
    pending_disposition: Literal["answer", "skip", "none"] = "none"


# ---------------------------------------------------------------------------
# Chat tool params (ADR-077 判词② — action union 的机械翻译)
# ---------------------------------------------------------------------------
# The action unions above (InferredIntent / IntentResult) translated into
# tool-call parameters: the type field = the tool's name, the per-state
# fields = the params. The ADR-071 ⑤ signpost INVERTS on this wire: under
# json_object the schema never reached the model (prompt literals were the
# only spec); under native tool_calls these models compile into the tool
# schemas the provider sees — the Field descriptions here ARE model-facing
# documentation, keep them in lockstep with the system templates.
#
# Speech moved channels: prose / summary / answer text ride the content
# channel (it streams — the typewriter law holds natively), so these models
# carry NO speech field. A misplaced "prose"/"type"/"kind" habit key is
# read-tolerated at the loop boundary (agents/tool_loop.py), never here.
# The envelope seats ride the call they belong to: brief / material_text on
# the plan-path tools, pending_disposition on both paths' tools (2026-09-27
# 一问拍一体化 — the plan path gained its seats in the zombie-card fix).


def tolerate_null_keys(data: Any, *keys: str) -> Any:
    """Null-means-skip tolerance (打字机律牙①'s tool form): the model writes
    null when it means to skip a field — dropping the key lets the default
    apply instead of rejecting the call (a rejection burns a loop
    iteration)."""
    if isinstance(data, dict):
        data = dict(data)
        for key in keys:
            if data.get(key) is None:
                data.pop(key, None)
    return data


def is_null_token(value: Any) -> bool:
    """The plan emission's null-as-string dialect (``"language": "null"``):
    True only for the bare token, exact-match — real content (a focus text
    mentioning null) never equals it. One predicate shared by the proposal
    boundary (TaskItem's param scrub) and the display boundary
    (OutputResponse.language normalization)."""
    return isinstance(value, str) and value.strip().lower() == "null"


def wrap_single_object_list(data: Any, key: str) -> Any:
    """顺形律 dialect absorption (probe E 实测 2026-09-24): the provider
    emits a one-item list as the BARE OBJECT and never recovers across
    repair rounds — the schema wraps it (the bare-int plan_ref / kind-less
    edit_output precedents). One law one home: every list-of-models tool
    field absorbs here."""
    if isinstance(data, dict) and isinstance(data.get(key), dict):
        return {**data, key: [data[key]]}
    return data


def _drop_bad_brief(data: Any) -> Any:
    """校验分层律 (ADR-064) at the tool boundary: the brief is
    ADVISORY bookkeeping — if it still fails shape after its own
    normalization, drop the field and let the call live (never spend a loop
    iteration on bookkeeping). Logged, never silent."""
    if isinstance(data, dict) and data.get("brief") is not None:
        try:
            Brief.model_validate(data["brief"])
        except Exception:
            logger.warning(
                "brief_dropped",
                brief=json.dumps(data["brief"], default=str)[:500],
            )
            data = dict(data)
            data["brief"] = None
    return data


class PlanAskArgs(BaseModel):
    """方案阶段的 ask_user 参数，沿用 QuestionProposal 的澄清结构，面向用户的正文通过消息发送。slot 指明所填的 Brief 字段，仅方案阶段使用，运行后的问题不回填 Brief。本轮的 Brief 更新和素材提升与该调用一并且只提交一次。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(
            tolerate_null_keys(data, "options", "items", "default_path", "slot", "material_text", "material_urls", "recommended_id", "pending_disposition")
        )

    question: str = Field(
        description="仅用界面语言写问题或问题组标题，不附引言或默认路径说明。"
    )
    options: list[Option] = Field(
        default_factory=list,
        description="从用户人设或上下文提取三个能用一个词回答的具体选项，并翻译为界面语言。只有真正的二选一才减为两项。每项在 description 中附一行理由。没有合理选项时可留空供自由回答；有选项时也始终允许自由输入。",
    )
    items: list[BriefQuestionItem] = Field(
        default_factory=list,
        max_length=13,
        description="可选，提供一组澄清问题。仅含缺失的 Brief 字段，每项一次。服务端会滤除已知值并签发 group_digest。",
    )
    allow_freeform: bool = True
    recommended_id: str | None = Field(
        default=None,
        description="唯一推荐的选项 ID，最多一个，须与正文倾向一致。没有推荐时填 null。",
    )
    default_path: str = Field(
        default="",
        description="用一个短句说明用户跳过时将如何继续。跳过必须是安全的。",
    )
    slot: BriefQuestionSlot | Literal["asset_role"] | None = Field(
        default=None,
        description="本题填充的 Brief 字段，用于运行前的意图路由。asset_role 不属于 Brief：至少附有两个视频且无法从消息区分用户原素材与参考样片时，才询问素材角色。"
                    "选项由服务端根据视频生成，不自行写选项 ID。系统根据回答绑定原素材与样片。",
    )
    brief: Brief | None = Field(
        default=None,
        description="本轮 Brief 更新。只填你有依据的字段，并标明各自来源。仅当用户原话明确陈述了该值时可用 user-stated。省略的字段保留已存值。",
    )
    material_text: str | None = Field(
        default=None,
        description="用户本轮明确声明为自有素材的逐字原文（如“这是我的逐字稿……”）。其他情况为 null，单纯请求不属于素材。",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="用户此轮明确作为制作素材提供的网页 URL。逐字复制各 URL，系统会采集为项目素材。仅供讨论的链接不计入。其他情况填 null。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )


class PresentPlanArgs(BaseModel):
    """方案阶段的 present_plan 参数。展示草案并等待确认，此调用本身不会启动 Run。引出方案的说明写在消息正文中，不放入参数。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(
            tolerate_null_keys(
                data, "tasks", "specific_instruction", "tasks_explicit", "name", "material_text", "material_urls", "pending_disposition", "production_intent"
            )
        )

    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="已获授权的任务链：produce_video、prepare_narration、prepare_visual_assets 或 prepare_music。",
    )
    specific_instruction: str | None = Field(
        default=None,
        description="从提示中提炼的自由文本指令。",
    )
    tasks_explicit: bool = Field(
        default=False,
        description="用户自己明确点名作品时为 true。任务链源于默认提案时为 false。",
    )
    name: str = Field(
        default="",
        description="用界面语言以 2–6 个词组成简短名词短语，命名方案交付的作品。它会作为 Run 回执标题，不使用工具名。",
    )
    brief: Brief | None = Field(
        default=None,
        description="本轮 Brief 更新。仅填写有依据的字段并注明来源，只有用户原话明确陈述了该值时才用 user-stated。",
    )
    material_text: str | None = Field(
        default=None,
        description="用户本轮明确声明为自有素材的逐字原文。其他情况填 null。",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="用户此轮明确作为制作素材提供的网页 URL。逐字复制各 URL，系统会采集为项目素材。仅供讨论的链接不计入。其他情况填 null。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )
    production_intent: bool | None = Field(
        default=None,
        description=(
            "用户是否要求现在制作该作品？只有明确请求或委托制作时才填 true，例如“按这版制作”“go ahead”“直接做，细节你决定”。纯修改、仅审阅（如“先给我看方案”）或讨论均填 false。"
            "auto/ask 设置只影响是否需要单独批准，不会产生制作意图。没有制作请求时，已展示的方案等待用户表态，保留开始按钮。视频分镜设计或修订若无当前制作意图，完整展示后用 answer 结束，不展示制作方案。必须填写此判断。"
        ),
    )




# ---------------------------------------------------------------------------
# Video Project (ADR-145 phase B): the CompositionVersion chain's chat tools.
# design_video / revise_video are NON-terminal beats — the system designs /
# revises inside the call, saves an immutable CompositionVersion through the
# content write door, and hands the canonical storyboard payload back; the
# model's ONE next message presents it (the structured card carries the
# table — the model introduces, never re-transcribes it).
# ---------------------------------------------------------------------------


class VideoVersionRef(BaseModel):
    """明确的修订基准（§2.2），包括作品、版本及设计时读到的内容标识。从该版本自身的展示记录或 get_video_version 结果中原样复制。"""

    model_config = ConfigDict(extra="forbid")

    composition_id: UUID
    composition_version_id: UUID
    content_digest: str = Field(min_length=64, max_length=64)


class VideoSegmentScrubTarget(BaseModel):
    """一个明确的 Scene/Clip 时间窗，不可指定整条时间线。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["segment"] = "segment"
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)
    clip_id: str | None = Field(default=None, min_length=1, max_length=64)
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _segment_shape(self) -> "VideoSegmentScrubTarget":
        if (self.scene_id is None) == (self.clip_id is None):
            raise ValueError("a segment names exactly one scene_id or clip_id")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("scrub end_seconds must be after start_seconds")
        return self


class VideoObjectScrubTarget(BaseModel):
    """单独查看一个已编排对象，与场景的其他轨道隔离。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["object"] = "object"
    object_id: str = Field(min_length=1, max_length=64)


VideoScrubTarget = Annotated[
    VideoSegmentScrubTarget | VideoObjectScrubTarget,
    Field(discriminator="kind"),
]


class VideoDraftRef(BaseModel):
    """保留在 ConversationContext 中、尚未提交的 Composition 工作草稿。"""

    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1, max_length=80)
    draft_digest: str = Field(min_length=64, max_length=64)


class VideoPresetChoice(BaseModel):
    """A previously shown Preset member; media and Preset identity are server-resolved."""

    model_config = ConfigDict(extra="forbid")

    candidate_set_id: UUID
    member_index: int = Field(ge=0)




class AnalyzeBrandArgs(BaseModel):
    """准备有来源佐证的 BrandProfile。证据和 PNG 由服务端读取。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(tolerate_null_keys(data, "brief"))

    @field_validator("brief")
    @classmethod
    def _keep_stated_direction(cls, brief: Brief | None) -> Brief | None:
        if brief is None:
            return None
        # The user's decision and the brand agent's creative recommendation
        # have separate homes. Never use a recommendation to satisfy the form.
        unstated = {
            name: BriefSlot() for name in ("purpose", "narrative_mode", "production_direction")
            if (slot := getattr(brief, name)).value and slot.source != BriefSlotSource.USER_STATED
        }
        return brief.model_copy(update=unstated) if unstated else brief

    brief: Brief | None = Field(
        default=None,
        description=(
            "记录用户明确提出的制作约束。网站和受众是品牌证据。用户点名发布场合后才设 purpose；同时说明叙事方式时才设 production_direction。"
        ),
    )


class PrepareVideoMaterialTarget(BaseModel):
    """需要获取确切事实或媒体的一个已列出来源。"""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    view_id: str | None = Field(default=None, min_length=1, max_length=64)
    element_id: str | None = Field(default=None, min_length=1, max_length=64)


class PrepareVideoMaterialsArgs(BaseModel):
    """在分步编排 Composition 前，固定明确选定的素材。"""

    model_config = ConfigDict(extra="forbid")

    material_urls: list[str] | None = Field(
        default=None,
        max_length=4,
        description="逐字复制用户提供的新网页 URL，已固定的网页无需重新采集。",
    )
    material_asset_ids: list[UUID] | None = Field(
        default=None,
        max_length=12,
        description="用户或当前作品明确选中的、归当前用户所有的素材。",
    )
    material_output_ids: list[UUID] | None = Field(
        default=None,
        max_length=12,
        description="明确用作新素材、归当前用户所有的已交付视频 Output。",
    )

    material_music_ids: list[UUID] | None = Field(
        default=None,
        max_length=12,
        description="search_music 返回的曲库音乐 ID，不填 Asset ID。导入公开或用户自有曲库的已有音频，以供剪辑；返回确切的 SourceSnapshot 标识，不合成或渲染。",
    )
    material_targets: list[PrepareVideoMaterialTarget] | None = Field(
        default=None,
        max_length=4,
        description="附上并返回选定的现有快照、视图或元素的确切事实。普通图片或视频快照省略 view_id 和 element_id。",
    )
    video_observation: Literal["representative_frames", "continuous"] = Field(
        default="representative_frames",
        description="默认 representative_frames 为每段视频附最多三张真实源帧。仅当用户明确要求连续检查符合条件的短源视频播放或运动时，才用 continuous。已交付的 Output 用 review_video。",
    )

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "material_urls", "material_asset_ids", "material_output_ids", "material_music_ids", "material_targets", "video_observation")

    @model_validator(mode="after")
    def _some_material(self) -> "PrepareVideoMaterialsArgs":
        if not (self.material_urls or self.material_asset_ids or self.material_output_ids or self.material_music_ids or self.material_targets):
            raise ValueError("select at least one URL, asset, Output, music-library piece or existing source target; existing project resources are already in context")
        if len(self.material_asset_ids or []) + len(self.material_output_ids or []) + len(self.material_music_ids or []) > 12:
            raise ValueError("one preparation call accepts at most 12 assets, Outputs and music-library pieces")
        return self


class ReviewVideoArgs(BaseModel):
    """对照用户明确的要求审阅一个确切的已交付 Output。"""

    model_config = ConfigDict(extra="forbid")

    output_id: UUID = Field(
        description="从视频卡片或 @output 引用取得的确切已交付视频 Output ID，不默认指向作品最近的 Output。"
    )
    requirements: str = Field(
        min_length=1,
        max_length=4000,
        description="忠实提取当前请求和对话中相关的用户要求，不预写审阅结论。",
    )
    at_seconds: list[float] | None = Field(
        default=None,
        max_length=4,
        description="需要检查的具体成片时点。提供后按这些时点取样，尤其适用于复核先前发现。"
    )
    motion_scene_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="此 Output 已执行 render_spec 中的确切 Scene ID，用于一段有序运动帧审阅，不取 Composition 最新版本中的场景。与 at_seconds 互斥。",
    )
    refresh: bool = Field(
        default=False,
        description="true 表示重新解码并审阅；false 在已有报告时复用此确切 Output 的报告。新 Output 须独立审阅。"
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示回应原问题，'skip' 表示明确拒答，'none' 表示明显无关的插话。",
    )

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(
            data, "at_seconds", "motion_scene_id", "refresh", "pending_disposition"
        )

    @model_validator(mode="after")
    def _one_sampling_mode(self) -> ReviewVideoArgs:
        if self.at_seconds is not None and self.motion_scene_id is not None:
            raise ValueError("at_seconds and motion_scene_id are mutually exclusive")
        return self


class ReviseVideoOpsArgs(BaseModel):
    """One atomic batch of direct Ops; Chat binds the current work's base."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "base_ref", "pending_disposition", "scrub")

    base_ref: VideoVersionRef | None = Field(
        default=None,
        description="服务端根据已解析的当前作品绑定，Chat 调用省略。",
    )
    ops: list[RevisionOp] = Field(min_length=1, max_length=32)
    scrub: VideoScrubTarget | None = Field(
        default=None,
        description="保存后可检查一个受影响的 Scene/Clip 时间窗或一个独立对象。仅有静态修改时省略，不指定整片。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示回应原问题，'skip' 表示明确拒答，'none' 表示明显无关的插话。",
    )
    _request_context: dict[str, Any] | None = PrivateAttr(default=None)

    def bind_request_context(
        self, *, user_text: str, pending_question: dict[str, Any] | None,
    ) -> None:
        self._request_context = {
            "user_text": user_text,
            "pending_question": pending_question,
        }


class ReviseVideoArgs(BaseModel):
    """对一个确切的保存版本提交完整实体。每项写入都是实体的完整最终值，服务端原子应用整批改动，验证整个 Composition 后保存。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        data = tolerate_null_keys(
            data, "base_ref", "pending_disposition", "scrub",
            "scenes", "tracks", "clips", "transitions",
            "remove_scene_ids", "remove_track_ids", "remove_clip_ids",
            "remove_transition_ids",
        )
        if isinstance(data, dict):
            for key in ("scenes", "tracks", "clips", "transitions"):
                if data.get(key) == "" or data.get(key) == {}:
                    data = {**data, key: []}
        for key in ("scenes", "tracks", "clips", "transitions"):
            data = wrap_single_object_list(data, key)
        return data

    base_ref: VideoVersionRef = Field(
        description="已保存版本的确切当前引用，从版本读取结果中原样复制。",
    )
    scrub: VideoScrubTarget | None = Field(
        default=None,
        description="保存后可检查一个受影响的 Scene/Clip 时间窗或一个独立对象。仅有静态修改时省略，不指定整片。",
    )

    scenes: list[Scene] = Field(default_factory=list, max_length=64)
    tracks: list[Track] = Field(default_factory=list, max_length=64)
    clips: list[ClipEntityWrite] = Field(default_factory=list, max_length=256)
    transitions: list[Transition] = Field(default_factory=list, max_length=64)
    remove_scene_ids: list[str] = Field(default_factory=list, max_length=64)
    remove_track_ids: list[str] = Field(default_factory=list, max_length=64)
    remove_clip_ids: list[str] = Field(default_factory=list, max_length=256)
    remove_transition_ids: list[str] = Field(default_factory=list, max_length=64)
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示回应原问题，'skip' 表示明确拒答，'none' 表示明显无关的插话。",
    )

    @model_validator(mode="after")
    def _shape(self) -> "ReviseVideoArgs":
        if not self.entity_writes().has_changes():
            raise ValueError("supply at least one complete entity write or stable-id removal")
        return self

    def entity_writes(self):
        from app.editing.edits import EntityWrites

        return EntityWrites.model_validate({
            key: getattr(self, key) for key in EntityWrites.model_fields
        })


class ReviseVideoTextArgs(BaseModel):
    """Replace the text of one independent native Text Clip."""

    model_config = ConfigDict(extra="forbid")

    base_ref: VideoVersionRef
    clip_id: str
    text: str = Field(min_length=1, max_length=9000)
    pending_disposition: Literal["answer", "skip", "none"] = "none"


class ShowVideoPresetsArgs(BaseModel):
    """展示 2–4 个已注册的原生 Preset，各候选的事实由服务端提供。"""

    model_config = ConfigDict(extra="forbid")

    preset_ids: list[str] = Field(min_length=2, max_length=4)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class SelectVideoPresetArgs(BaseModel):
    """将一个已展示的 Preset 标记为选中，不改版本或启动 Run。"""

    model_config = ConfigDict(extra="forbid")

    candidate_set_id: UUID
    member_index: int = Field(ge=0)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class SearchSfxArgs(BaseModel):
    """搜索真实的 Freesound CC0 音效，候选仅在本轮结束时持久化。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class ImportSfxArgs(BaseModel):
    """只按已保存候选的标识导入，不使用 URL 或供应商元数据。"""

    model_config = ConfigDict(extra="forbid")

    candidate_set_id: UUID
    member_index: int = Field(ge=0)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class ShowMusicCandidatesArgs(BaseModel):
    """展示本地曲库的可播放候选，不创建 Asset 或版本。"""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=200)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "query", "pending_disposition")


class SelectMusicArgs(BaseModel):
    """用服务端标识选择之前已保存的一个 Music 候选。"""

    model_config = ConfigDict(extra="forbid")

    candidate_set_id: UUID
    member_index: int = Field(ge=0)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class PrepareNarrationArgs(BaseModel):
    """固定最终音频和确切文稿，然后将确定性对齐任务加入队列。"""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=9000)
    audio_asset_id: UUID | None = Field(
        default=None,
        description="用户为本次录音显式 @ 引用的确切 AUDIO 素材。",
    )
    voice_id: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    draft_ref: VideoDraftRef | None = Field(
        default=None,
        description="当前工作草稿，配合 scene_id 由代码解析其确切的待准备旁白。",
    )
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)
    pending_disposition: Literal["answer", "skip", "none"] = "none"
    _working_draft: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(
            data, "text", "audio_asset_id", "voice_id", "language",
            "draft_ref", "scene_id", "pending_disposition",
        )

    @model_validator(mode="after")
    def _source(self) -> "PrepareNarrationArgs":
        scene_form = self.draft_ref is not None or self.scene_id is not None
        if scene_form:
            if self.draft_ref is None or self.scene_id is None:
                raise ValueError("scene narration needs both draft_ref and scene_id")
            if any((
                self.text is not None,
                self.audio_asset_id is not None,
                self.voice_id is not None,
                self.language is not None,
            )):
                raise ValueError("scene narration resolves text, voice and language from its draft")
            return self
        if self.text is None or not self.text.strip():
            raise ValueError("the final narration script must not be blank")
        if self.audio_asset_id is not None:
            if self.voice_id is not None:
                raise ValueError("an existing recording does not take a TTS voice")
        elif self.voice_id is None or self.language is None:
            raise ValueError("TTS preparation needs voice_id and language, or name an AUDIO asset")
        return self

    def bind_working_draft(self, value: dict[str, Any]) -> None:
        self._working_draft = deepcopy(value)


class GetNarrationAlignmentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alignment_id: UUID
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class NarrationSentenceSemanticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str = Field(min_length=1, max_length=64)
    role: Literal["definition", "process", "comparison", "evidence", "example", "summary", "transition"]
    weight: Literal["main", "sub"]
    entities: list[str] = Field(default=[], max_length=12)
    needs: list[Literal["native_text", "diagram", "real_media", "data", "generator"]] = Field(
        default=[], max_length=5,
        description="媒体或能力字符串构成的 JSON 数组，如 [\"native_text\"]。",
    )

    @field_validator("needs", mode="before")
    @classmethod
    def _needs_list(cls, value):
        from app.editing.schemas import _list_wire

        return _list_wire(value)

    emphasis_word_ids: list[str] = Field(default=[], max_length=24)


class AnnotateNarrationArgs(BaseModel):
    """只补全逐句语义。不提供用于修改文本或时间刻度的工具字段。"""

    model_config = ConfigDict(extra="forbid")

    alignment_id: UUID
    expected_timing_digest: str = Field(min_length=64, max_length=64)
    sentences: list[NarrationSentenceSemanticsArgs] = Field(min_length=1)
    pending_disposition: Literal["answer", "skip", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")


class GetVideoVersionParams(BaseModel):
    """get_video_version 的参数，用来读取明确指定的版本（§2.2）。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(
            data, "version_id", "composition_id", "output_id", "present", "scrub",
            "purpose", "scene_id", "clip_id",
        )

    version_id: UUID | None = Field(
        default=None, description="读取分镜卡或先前读取结果指向的确切版本。"
    )
    composition_id: UUID | None = Field(
        default=None, description="读取此作品的当前版本。"
    )
    output_id: UUID | None = Field(
        default=None, description="将用户拥有的 @output 解析为它实际交付的确切版本，支持跨 Chat。"
    )
    purpose: Literal["read", "edit"] = Field(
        default="read", description="edit 只读取当前最新版本的 base_ref 及相关 Scene/Clip 的值。"
    )
    scene_id: str | None = Field(default=None, description="purpose=edit 时，将现值限定到此 Scene。")
    clip_id: str | None = Field(default=None, description="purpose=edit 时，将现值限定到此 Clip。")
    present: bool = Field(default=False, description="再次展示该保存版本的标准分镜卡，供审阅或恢复。")
    scrub: VideoScrubTarget | None = Field(
        default=None,
        description="present=true 时可选一个限定的 Scene/Clip 时间窗或一个独立对象，不得请求整片。",
    )

    @model_validator(mode="after")
    def _one_address(self) -> "GetVideoVersionParams":
        if sum(v is not None for v in (self.version_id, self.composition_id, self.output_id)) != 1:
            raise ValueError("name exactly one of version_id / composition_id / output_id")
        if self.scrub is not None and not self.present:
            raise ValueError("scrub requires present=true")
        if self.purpose == "edit" and (
            self.composition_id is None or self.present or self.scrub is not None
        ):
            raise ValueError("purpose=edit reads only a work's current head without presentation")
        if self.purpose != "edit" and (self.scene_id is not None or self.clip_id is not None):
            raise ValueError("scene_id/clip_id narrowing requires purpose=edit")
        return self


# 建议谱系 (ADR-100): one wire shape, one seat — the trigger dock's wrap_up
# options (the answer+suggestions form is retired: every pickable option
# docks as a real question, the message flow carries zero options). The
# class body stays byte-identical to its pre-move form (零 diff 律 — the
# docstring is model-facing wire text).
class SuggestionItem(BaseModel):
    """One next-step option on the trigger dock (一问拍一体化 2026-09-27 —
    the pre-integration wire shape was a bare label string, read in as
    ``label``): the label is the dock row AND the words that ride into the
    conversation on a pick; ``description`` is the one-line reason under it;
    ``recommended`` marks the agent's ONE lean (at most one survives)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _upgrade_bare_label(cls, data: Any) -> Any:
        # 读容忍: the model's old habit emits a bare string per option — it
        # reads in as the label, never a repair round for a cosmetic upgrade.
        # A null description means "no reason line" (打字机律牙①) — pop the
        # key so the "" default applies instead of rejecting the call.
        if isinstance(data, str):
            return {"label": data}
        if isinstance(data, dict) and data.get("description") is None:
            data = dict(data)
            data.pop("description", None)
        return data

    label: str = Field(
        description="选项行的文字。以用户口吻和界面语言写成对方可能输入的完整短指令，最多 40 个字符。",
    )
    description: str = Field(
        default="",
        description="用一行说明选择该项的理由，给出用户可以判断的结论，不展示推理过程。",
    )
    recommended: bool = Field(
        default=False,
        description="仅对唯一推荐项填 true（全表最多一项），与正文表达的倾向一致。",
    )


def dock_worthy_suggestions(items: list[SuggestionItem]) -> list[SuggestionItem]:
    """The wrap_up suggestions validator (校验分层律 — WrapUpArgs consumes
    it): a label is the option row's visible text AND
    the user's pick riding into the continuation — blank labels are dropped
    (the model means "fewer options"), an overlong one rejects into the loop
    (the option row cannot carry it). Extra recommendation marks drop
    silently (cosmetic — never worth a repair round)."""
    cleaned = []
    for item in items:
        item.label = item.label.strip()
        if item.label:
            cleaned.append(item)
    if any(len(item.label) > 40 for item in cleaned):
        raise ValueError("a suggestion label is at most 40 characters")
    recommended_seen = False
    for item in cleaned:
        if item.recommended and recommended_seen:
            item.recommended = False
        recommended_seen = recommended_seen or item.recommended
    return cleaned


class StartRunArgs(BaseModel):
    """方案阶段的 start_run 参数，用于启动已确认方案的 Run。"""

    model_config = ConfigDict(extra="forbid")
class PlanAnswerArgs(BaseModel):
    """方案阶段的 answer 参数，只提供信息。答复本身在消息正文中，相关附带数据随本次调用提交。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(tolerate_null_keys(data, "material_text", "material_urls", "pending_disposition"))

    brief: Brief | None = Field(
        default=None,
        description="本轮 Brief 更新（如有），规则与其他工具一致。",
    )
    material_text: str | None = Field(
        default=None,
        description="用户本轮明确声明为自有素材的逐字原文，其他情况填 null。",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="用户此轮明确作为制作素材提供的网页 URL。逐字复制各 URL，系统会采集为项目素材。仅供讨论的链接不计入。其他情况填 null。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )


class ProposeTasksArgs(BaseModel):
    """对话阶段的 propose_tasks 参数，采用 TaskListProposal 的结构，摘要写入消息正文。可用空 tasks 表示回问；一个问题就能作出判断时优先用 ask_user。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "tasks", "name", "specific_instruction", "material_urls", "pending_disposition", "production_intent")

    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="按执行顺序排列的提案工具链，每个作品对应一个任务。",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="用户此轮明确作为制作素材提供的网页 URL。逐字复制各 URL，系统会采集为项目素材。仅供讨论的链接不计入。其他情况填 null。",
    )
    specific_instruction: str | None = Field(
        default=None,
        description=(
            "为生成器提炼的简短额外指令。只写任务参数尚未表达的约束或重点，不复述请求本身。没有额外内容时省略。"
        ),
    )
    name: str = Field(
        default="",
        description="用界面语言以 2–6 个词组成简短名词短语，命名这次运行交付的作品，不用工具名。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )
    production_intent: bool | None = Field(
        default=None,
        description=(
            "用户是否要求现在制作该作品？只有明确请求或委托制作时才填 true，例如“按这版制作”“go ahead”“直接做，细节你决定”。纯修改、仅审阅（如“先给我看方案”）或讨论均填 false。"
            "auto/ask 设置只影响是否需要单独批准，不会产生制作意图。没有制作请求时，已展示的方案等待用户表态，保留开始按钮。视频分镜设计或修订若无当前制作意图，完整展示后用 answer 结束，不展示制作方案。必须填写此判断。"
        ),
    )


class ManualNodeSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    prototype: Literal["manual"]
    text: str | None = None
    title: str | None = None
    prompt: str | None = None


class AddManualNodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_node"]
    id: UUID | None = None
    type: Literal["text", "table", "image", "video", "audio"]
    spec: ManualNodeSpec
    after: list[UUID] = Field(
        default_factory=list,
        description="本节点入边的父节点 ID。在本次 edit_graph 调用中一并提交所需的全部连接。",
    )
    layout: dict[str, Any] | None = None


class ManualEdgeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: UUID
    to_node: UUID
    edge_type: Literal["video", "audio", "text"] | None = None
    from_port: str | None = None
    to_port: str | None = None


class ConnectManualNodeArgs(ManualEdgeArgs):
    op: Literal["connect"]


class DisconnectManualNodeArgs(ManualEdgeArgs):
    op: Literal["disconnect"]


class EditManualNodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["edit_prompt"]
    node: UUID
    prompt: str


class DeleteManualNodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["delete_node"]
    node: UUID


ManualGraphOp = Annotated[
    AddManualNodeArgs | ConnectManualNodeArgs | DisconnectManualNodeArgs | EditManualNodeArgs | DeleteManualNodeArgs,
    Field(discriminator="op"),
]


class EditGraphArgs(BaseModel):
    """对普通手动画布节点及其有类型的连接进行增删改查。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        if isinstance(data, dict) and any(
            isinstance(op, dict) and op.get("op") == "run" for op in data.get("ops") or []
        ):
            raise ValueError("manual Graph CRUD never starts a Run")
        return tolerate_null_keys(data, "ops", "name", "pending_disposition", "production_intent")

    ops: list[ManualGraphOp] = Field(
        default_factory=list,
        description="add_node 需要 type 和 spec.prototype='manual'；连接需要 from_node/to_node。",
    )

    @field_validator("ops")
    @classmethod
    def _manual_graph_only(cls, ops: list[ManualGraphOp]) -> list[dict]:
        if any(op.op == "run" for op in ops):
            raise ValueError("manual Graph CRUD never starts a Run")
        return [op.model_dump(mode="json", exclude_none=True, exclude_unset=True) for op in ops]

    name: str = ""
    pending_disposition: Literal["answer", "skip", "none"] = "none"
    production_intent: bool | None = None


class ChatAskArgs(BaseModel):
    """对话阶段的 ask_user 参数。与方案阶段使用同一澄清结构，省略 Brief 字段，运行后的提问不回填 Brief。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "options", "items", "default_path", "recommended_id", "pending_disposition")

    question: str = Field(
        description="仅用界面语言写问题或问题组标题，不加引言或默认路径说明。"
    )
    options: list[Option] = Field(
        default_factory=list,
        description="从用户人设或上下文提取三个能用一个词回答的具体值，翻译为界面语言。只有真正的二选一才减为两项。每项在 description 中附一行理由。仅自由作答时才留空。",
    )
    items: list[BriefQuestionItem] = Field(
        default_factory=list,
        max_length=13,
        description="可选，提供一组澄清问题，只含缺失的 Brief 字段。",
    )
    allow_freeform: bool = True
    recommended_id: str | None = Field(
        default=None,
        description="唯一推荐的选项 ID，最多一个，与正文倾向一致。没有推荐时填 null。",
    )
    default_path: str = Field(
        default="",
        description="用一个短句说明用户跳过时将如何继续。跳过必须是安全的。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )


class ChatAnswerArgs(BaseModel):
    """对话阶段的 answer 参数，采用 AnswerProposal 的结构，回答文本写进消息正文。若有待回答的问题，其处理方式也随本调用提交。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")

    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )


class RetryUploadArgs(BaseModel):
    """retry_upload 参数，用于重传已渲染完成但上传失败的成片。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "output_id", "pending_disposition")

    output_id: UUID | None = Field(
        default=None,
        description="@output 指向的确切 ID。最近失败的 Run 只有一个上传失败项时可省略，由系统解析。不得编造 ID。",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="有待回答问题时，'answer' 表示用户回答、讨论选项或将选择交给你，用用户原话结清问题；'skip' 表示明确拒答；'none' 表示明显无关的插话，问题继续待答。",
    )


class WrapUpArgs(BaseModel):
    """``wrap_up`` params (trigger turns only) — the proactive turn's ONE
    terminal call. The review itself is your spoken message (the content
    channel); only the next-step option labels ride here.

    选项语法统一律 (ADR-081, 2026-09-17): suggestions dock as a real options
    question (OptionDock, numbered 1/2/3), never as pills; the pill form
    (send/download actions) is retired, a landed output's download lives on
    its canvas card's factsbar. 一问拍一体化 (2026-09-27): each suggestion
    carries its one-line reason and at most one is marked recommended — the
    dock carries the judgment, the speech's verdict names the same lean."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "suggestions")

    @field_validator("suggestions")
    @classmethod
    def _labels_are_dock_worthy(cls, items: list[SuggestionItem]) -> list[SuggestionItem]:
        return dock_worthy_suggestions(items)

    suggestions: list[SuggestionItem] = Field(
        default_factory=list,
        max_length=3,
        description="提供 0–3 个有实际阅读依据的下一步选项。每项用用户口吻写不超过 40 字符的标签，附一行理由，只标记唯一推荐项。不要套用通用清单。",
    )


class AnswerResponse(BaseModel):
    """Result of ``POST /chat/messages/{id}/answer``.

    The answer endpoint doubles as the resume mechanism (NAMING: answer =
    resume): ``answered_question`` is the settled question (same name as
    ``ChatResponse.answered_question``, same role), and
    ``follow_up`` is the assistant's continuation when the answer unblocks
    the conversation (the pick rides into the next turn).
    """

    answered_question: ChatMessageResponse
    follow_up: ChatMessageResponse | None = None


class VisibleProseFrontier(BaseModel):
    """One server-owned assistant row and its actually displayed prefix."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    visible_chars: int = Field(ge=0, description="Visible prefix length in Unicode code points")


class ChatTurnStopRequest(BaseModel):
    """The client-visible frontier at the user's Stop gesture.

    IDs only address rows already persisted in this Turn. The server clamps
    each prefix to its own stored content; clients never upload replacement
    prose.
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["turn", "media_preparation"] = "turn"
    prose: list[VisibleProseFrontier] = Field(default_factory=list, max_length=128)
    activity_ids: list[UUID] = Field(default_factory=list, max_length=128)
    structure_ids: list[UUID] = Field(default_factory=list, max_length=128)


class ChatRequest(BaseModel):
    """Send a message to the project's chat.

    The backend locates or creates the project conversation, builds the
    context, and dispatches any background work. Asset-scoped conversations
    are retired (ADR-041 D8 — 产物对话归 dock); pointing at a product is an
    @-mention chip on the message (ADR-058 — focus_output write-retired, old
    rows still read back on the history response), never a separate
    conversation scope.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    message: str
    attachments: list[ChatAttachment] = Field(default_factory=list)
    mentions: list[ChatMention] = Field(default_factory=list)
    # One explicit first-design Skill binding. It rides the same intent
    # surface as the prompt; revision and production tools never accept it.
    skill: SkillReference | None = None
    # 建议点选 provenance (ADR-099 §4): present only when this message IS a
    # suggestion pick — persisted on the user row, resolved at the turn's
    # assembly (the stale check + the provenance note; a pick is never
    # silently adopted nor silently dropped).
    suggestion_ref: SuggestionRef | None = None
    # Plan-path transports (intent-surface-unification W3 — carry only, never
    # persisted on the message):
    # The review panel's current plan (the user may have hand-edited the
    # chain). Panel edits ARE task-list mutations (ADR-043) — the panel's
    # chain is shown to the intent router as the presented plan and re-emitted
    # whole on every revision, so hand edits survive unless the message
    # revises them; None = the stored pending brief is presented, if any.
    prior_intent: "InferredIntent | None" = None

    @field_validator("prior_intent", mode="before")
    @classmethod
    def _strip_policy_stamp(cls, v: Any) -> Any:
        """Read tolerance (ADR-099 戳的回声): the docked plan's intent carries
        the ``interaction_policy_version`` observation stamp (stamped by
        ``_create_message`` on every assistant row); the panel echoes the
        intent back verbatim as ``prior_intent`` — drop the stamp before the
        router shape's extra=forbid court, exactly like the auto-start
        read-back."""
        if isinstance(v, dict):
            v = {k: val for k, val in v.items() if k != "interaction_policy_version"}
        return v
    # The composer's persona choice rides the first message; written into the
    # pending brief only when the plan path docks a plan (a later turn
    # omitting it never clobbers the stored choice).
    persona_id: UUID | None = None
    # The sender's surface (2026-09-25 canvas↔chat 联动, user ruling): the
    # client judges it from the page width (panel form = the plan's canvas
    # lives beside the conversation). "canvas" lets the turn's review
    # invitation name that home; "chat"/None stays surface-neutral. A
    # transport fact — never persisted on the message.
    surface: Literal["canvas", "chat"] | None = None
    # 环境能力位 (ADR-118 §6 双键的客户端一半): the viewport's raw
    # can-host-canvas read (the width breakpoint — 互指 web 半座
    # lib/canvasVisibility.ts 的 canvasAvailable), NOT the panel form
    # (``surface`` keeps that seat). Stamped on the conversation every user
    # turn (last-wins, ui_language owner 同律) so the worker-born delivery
    # turn inherits the last known environment; never persisted on the
    # message. None = not reported → the context's Environment line is
    # omitted and the handoff-sentence gate stays closed (未知恒闭, 永不编
    # 造).
    canvas_available: bool | None = None
    # RETIRED (Phase 4 B7 / ADR-087 R9, D1): the autonomy tier is gone —
    # every run is an autonomous continuation. The field stays so old
    # clients keep passing it without a 422 (extra="forbid"); the value is
    # accepted and IGNORED, never carried into the run.
    autonomy: Literal["auto", "review"] | None = None


class TaskItem(BaseModel):
    """模型提出的一个任务，由注册工具及其参数组成（CHAT_ARCH §3）。compile_graph 根据 app/tools/__init__.py 检查工具是否存在、参数和拓扑是否有效。模型不写节点规格。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        # ADR-109 §5: a param-less tool comes back with params '' (or null)
        # instead of {} — normalize before validation (打字机律牙① read
        # tolerance extended to plan params: one schema rejection here used
        # to cost a whole rejected iteration and its streamed prose). The
        # null-as-string dialect ("language": "null") scrubs at the same
        # seat: a junk token must never reach spec stamps, spec prompts, or
        # a product's language column; an empty string means "absent" here
        # too (every registry param falls back to its default).
        if isinstance(data, dict):
            data = dict(data)
            if not data.get("params"):
                data.pop("params", None)
            elif isinstance(data["params"], dict):
                data["params"] = {
                    k: v
                    for k, v in data["params"].items()
                    if not (
                        isinstance(v, str) and (is_null_token(v) or not v.strip())
                    )
                }
        return data

    tool: str
    params: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Result of sending a chat message.

    ``answered_question`` is the pending question this turn settled via
    deterministic autoResume (option letter/number/label hit, or freeform)
    — the frontend archives it as a QA pair before the assistant's reply.
    """

    conversation_id: UUID
    user_message: ChatMessageResponse
    # None = the material-pending commitment was suppressed at land time
    # (the understanding beat landed mid-turn — the world-fired review turn
    # speaks next, so the stale promise never lands). SSE clients close the
    # preview bubble and wait for the review.
    assistant_message: ChatMessageResponse | None = None
    run_id: UUID | None = None
    answered_question: ChatMessageResponse | None = None


# Runtime validation set for the tone enum below (LLM extraction writes are
# normalized against this — keep in sync with the Literal).
EMOTIONAL_TONES = ("rational", "passionate", "gentle", "sharp", "humorous")


class PersonaContext(BaseModel):
    """Persona business object returned by the API and passed to agents.

    The identity module (ADR-037/038): one flat object carrying the style six,
    content strategy, identity card, voice (audio) block and brand (skin)
    block. Rendered into prompts at the agent layer via the j2 templates'
    ``context.persona``; the brand block bakes into the video-spec.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    name: str
    title: str | None = None
    language: str = "zh"
    avatar_url: str | None = None
    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str | None = ""
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] | None = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    # Voice = audio only: {"kind":"cloned", voice_id, sample_asset_id} |
    # {"kind":"stock", stock_id} | None = Auto.
    voice: dict | None = None
    # Skin block (caption/title/intro-outro/logo/keyword highlighter);
    # None = the system default skin.
    brand: dict | None = None
    learned_from: dict | None = None
    calibrated_at: datetime | None = None
    auto_created_at: datetime | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PersonaCreate(BaseModel):
    """Create persona request (bare identity card; blocks fill in later)."""

    name: str
    title: str | None = None
    language: str = "zh"
    avatar_url: str | None = None
    core_values: list[str] | None = None
    favorite_metaphors: list[str] | None = None
    sentence_style: str | None = None
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] | None = None
    typical_hooks: list[str] | None = None
    avoid_words: list[str] | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class PersonaUpdate(BaseModel):
    """Update persona request."""

    name: str | None = None
    title: str | None = None
    language: str | None = None
    avatar_url: str | None = None
    core_values: list[str] | None = None
    favorite_metaphors: list[str] | None = None
    sentence_style: str | None = None
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] | None = None
    typical_hooks: list[str] | None = None
    avoid_words: list[str] | None = None
    voice: dict | None = None
    brand: dict | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class ToneSettings(BaseModel):
    """Tone settings for generation."""

    model_config = ConfigDict(extra="forbid")

    academic_vs_casual: float = Field(default=0.5, ge=0.0, le=1.0)
    rational_vs_passionate: float = Field(default=0.5, ge=0.0, le=1.0)
    concise_vs_detailed: float = Field(default=0.5, ge=0.0, le=1.0)
    audience: Literal["academic", "industry", "general", "investor"] = "industry"


class IntentSlot(BaseModel):
    """任务槽: one line of the plan — one requested output (request layer).

    N-20 layering: the IntentSlot says WHAT the user wants; the planner's
    ``StoryboardSlot`` (派工层） says how the work is assigned. ``None`` fields
    mean "plan default": count → the per-type default (clips 1 / quotes 3
    / carousel 6). Language is a per-slot property (2026-08-05 restructure —
    the plan-level field is retired): ``None`` is legacy/read-tolerant and
    inherits the run's derived fallback. Same-type multi slots are how one run
    produces e.g. an English and a German post. With ADR-043 the slot is a
    COMPILE-TIME PROJECTION of the task chain (node ``spec.slot``), never a
    request-layer declaration.

    N-32: ``type`` is a plain ``str`` validated against the outputs registry
    (the producer nodes' ``output_type`` declarations — a new output type is
    one registry entry away, never a schema edit).
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    count: int | None = None
    focus: str | None = None
    language: str | None = None
    tone_override: str | None = None
    explicit: bool = False

    @model_validator(mode="before")
    @classmethod
    def _tolerate_bare_type(cls, data: Any) -> Any:
        """A bare type string (``"post"``) reads as a bare slot — legacy flat
        plans (pre-slot) deserialize through this; new writes never
        produce it (read tolerance, not a bridge layer)."""
        if isinstance(data, str):
            return {"type": data}
        return data

    @model_validator(mode="after")
    def _known_output_type(self) -> "IntentSlot":
        """Registry validation (N-32): the type must be a declared output
        type. Rejects exactly what the retired Literal rejected — an unknown
        type fails parse here, never silently downstream."""
        # Deferred: models is the leaf layer. Importing the registry door
        # (not bare graph) guarantees NODE_KINDS is populated regardless of
        # process entry order.
        import app.tools  # noqa: F401
        from app.pipeline.graph import known_output_types

        if self.type not in known_output_types():
            raise ValueError(f"Unknown output type: {self.type}")
        return self


# ---------------------------------------------------------------------------
# brief（DIALOG_WORKFLOW §2.4, ADR-052 B2): the dialog engine's structured
# state. Five slots, each with provenance; the intent router proposes a full
# update every plan turn and code merges by source precedence (merge_brief —
# LLM proposes, code decides; user-stated is never reverse-overwritten).
# ---------------------------------------------------------------------------


class BriefSlotSource(StrEnum):
    """单个 Brief 字段值的来源。合并优先级依次为用户陈述、推断和默认值。"""

    USER_STATED = "user-stated"
    INFERRED = "inferred"
    DEFAULT = "default"


SlotT = TypeVar("SlotT")


class BriefSlot(BaseModel, Generic[SlotT]):
    """One brief slot: a value plus its provenance.

    ``value=None`` is the empty slot (stored) and the no-opinion update
    (the router emits only slots it has a view on) — a None update never
    lands in the merge.
    """

    model_config = ConfigDict(extra="forbid")

    value: SlotT | None = None
    source: BriefSlotSource = BriefSlotSource.DEFAULT


MaterialState = Literal["none", "pasted", "attached"]


class Brief(BaseModel):
    """结构化的对话需求，合并与来源由代码管理。每个字段都有值及来源，优先级为 user-stated > inferred > default。constraints 是带来源的约束数组。material_state 和 asked 由代码根据实际状态及提问记录维护。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_constraints(cls, data: Any) -> Any:
        """归一化 constraints 的来路形状（顺形律的边界兜底）:

        1. 旧槽形状 ``{"value": [...], "source": ...}``（对象包数组，含
           存量 pending_brief 行）→ 逐项展开、来源继承；
        2. 裸字符串条目 ``["keep 1:1"]`` → 逐项包 ``{"value": s}``；
        3. 条目 source 不在枚举内（模型自造词如 "explicit"）→ 降
           ``inferred``（永不把来路不明的值升格成 user-stated）；
        4. 完全无法辨认 → 删键按无意见处理（簿记字段不杀回合）。
        """
        if not isinstance(data, dict):
            return data
        optional_slots = (
            "production_direction", "purpose", "target_seconds", "narrative_mode", "narration_language",
            "subtitle_languages", "aspect", "voice_requirements", "must_include",
            "avoid", "success_criteria",
        )
        if any(data.get(key) is None for key in optional_slots):
            data = {
                key: value for key, value in data.items()
                if key not in optional_slots or value is not None
            }
        raw = data.get("constraints")
        if raw is None:
            if "constraints" in data:
                # 打字机律牙①同律：显式 null = 无意见，删键让默认值生效，
                # 不为一个簿记槽烧修复轮。
                data = dict(data)
                data.pop("constraints")
            return data
        data = dict(data)
        items: list[Any] = []
        if isinstance(raw, dict):  # 旧槽形状：对象包数组 / 对象包字符串
            source = raw.get("source")
            value = raw.get("value")
            values = value if isinstance(value, list) else ([value] if value else [])
            items = [{"value": v, "source": source} for v in values]
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, BriefSlot):
                    # 已是类型化实例（代码侧构造路径）——原样放行。
                    items.append(item)
                elif isinstance(item, str):
                    items.append({"value": item})
                elif isinstance(item, dict):
                    items.append(item)
        else:
            data.pop("constraints")
            return data
        known_sources = {s.value for s in BriefSlotSource}
        normalized: list[Any] = []
        for item in items:
            if isinstance(item, BriefSlot):
                normalized.append(item)
                continue
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            if source is not None and source not in known_sources:
                item = {**item, "source": BriefSlotSource.INFERRED.value}
            normalized.append(item)
        data["constraints"] = normalized
        return data

    topic: BriefSlot[str] = Field(default_factory=BriefSlot)
    audience: BriefSlot[str] = Field(default_factory=BriefSlot)
    tone: BriefSlot[str] = Field(default_factory=BriefSlot)
    production_direction: BriefSlot[str] = Field(
        default_factory=BriefSlot,
        description=(
            "将视频用途与叙事方式结合为一个创作方向。两者已知时才设此字段。如果只确定一项，先用 purpose 或 narrative_mode 保留该信息。时长、旁白语言、字幕语言和画幅各用独立字段。"
        ),
    )
    purpose: BriefSlot[str] = Field(default_factory=BriefSlot)
    target_seconds: BriefSlot[int] = Field(default_factory=BriefSlot)
    narrative_mode: BriefSlot[str] = Field(default_factory=BriefSlot)
    narration_language: BriefSlot[str] = Field(default_factory=BriefSlot)
    subtitle_languages: BriefSlot[list[str]] = Field(default_factory=BriefSlot)
    aspect: BriefSlot[str] = Field(default_factory=BriefSlot)
    voice_requirements: BriefSlot[str] = Field(default_factory=BriefSlot)
    must_include: BriefSlot[list[str]] = Field(default_factory=BriefSlot)
    avoid: BriefSlot[list[str]] = Field(default_factory=BriefSlot)
    success_criteria: BriefSlot[list[str]] = Field(default_factory=BriefSlot)
    constraints: list[BriefSlot[str]] = Field(default_factory=list)
    material_state: BriefSlot[MaterialState] = Field(default_factory=BriefSlot)
    # Code-owned roll of the slots already asked once this plan phase (一轮
    # 一问决定槽， bounded: each slot asks at most once — the second rootless
    # call docks the draft-from-persona plan instead). merge_brief never
    # reads it from the LLM's proposal (禁 LLM 簿记); code stamps it when the
    # question docks.
    asked: list[str] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _preserve_legacy_shape(self, handler):
        # An untouched old Brief must still produce its original question,
        # CreativeState and composition hashes, including in nested dumps.
        payload = handler(self)
        if self.production_direction.value is None:
            payload.pop("production_direction", None)
        return payload


class BrandSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    digest: str
    view_ids: list[str] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)


class BrandClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    line_ids: list[str] = Field(default_factory=list)
    kind: Literal["fact", "inferred"] = "fact"


class BrandTagline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    line_ids: list[str] = Field(default_factory=list)


class BrandColor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    role: str = ""
    source: Literal["css", "dom", "visual", "user"] = "visual"
    confidence: Literal["confirmed", "inferred"] = "inferred"
    source_refs: list[str] = Field(default_factory=list)


class BrandTypography(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: str
    weight: str = ""
    source: Literal["css", "dom", "visual", "user"] = "visual"
    confidence: Literal["confirmed", "inferred"] = "inferred"
    source_refs: list[str] = Field(default_factory=list)


class BrandAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["logo", "wordmark", "icon", "other"]
    ref: str = ""
    source_refs: list[str] = Field(default_factory=list)


class BrandCreativeDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    media_preferences: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    provenance: Literal["inferred"] = "inferred"


class BrandProfile(BaseModel):
    """Derived brand understanding for one project's immutable web evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    source_refs: list[BrandSourceRef] = Field(default_factory=list)
    extractor_version: str
    positioning: str = ""
    claims: list[BrandClaim] = Field(default_factory=list)
    taglines: list[BrandTagline] = Field(default_factory=list)
    colors: list[BrandColor] = Field(default_factory=list)
    typography: list[BrandTypography] = Field(default_factory=list)
    brand_assets: list[BrandAsset] = Field(default_factory=list)
    creative_direction: BrandCreativeDirection = Field(
        default_factory=BrandCreativeDirection
    )
    unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    content_digest: str


class CreativeState(BaseModel):
    """The single authoring-state payload shared by plans and saved versions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    brief: Brief = Field(default_factory=Brief)
    brand_profile: BrandProfile | None = None
    source_refs: list[BrandSourceRef] = Field(default_factory=list)
    content_digest: str | None = None


def creative_state_digest(state: CreativeState) -> str:
    payload = state.model_dump(mode="json", exclude={"content_digest"})
    return canonical_json_hash(payload)


def seal_creative_state(state: CreativeState) -> CreativeState:
    return state.model_copy(update={"content_digest": creative_state_digest(state)})


CompositionContent.model_rebuild(_types_namespace={"CreativeState": CreativeState})


class InferredIntent(BaseModel):
    """Intent payload: draft, clarify, answer or confirm, plus production tasks.

    ``tasks`` is the production grammar; outputs are derived from the graph.
    ``ask`` carries one clarification interaction, potentially grouped by the
    active tool contract. ``answer`` is informational; ``start`` confirms.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_optional_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for key in ("tasks", "name", "tasks_explicit"):
            if data.get(key) is None:
                data.pop(key, None)
        brief = data.get("brief")
        if brief is not None:
            try:
                Brief.model_validate(brief)
            except Exception:
                logger.warning("brief_dropped", brief=json.dumps(brief, default=str)[:500])
                data["brief"] = None
        return data

    action: Literal["ask", "draft", "answer", "start"] = Field(
        default="draft",
        description=(
            "判断用户是在要求创作或完善方案（draft）、询问工具能力（answer）、在确认阶段明确同意执行所提方案（start，修改要求不算确认），还是必须先澄清一个最影响质量的问题（ask）。"
        ),
    )
    ask: QuestionProposal | None = Field(
        default=None,
        description=(
            "action 为 ask 时的澄清交互，包括当前规范规定的分组表单。其他操作均填 null。"
        ),
    )
    answer: str | None = Field(
        default=None,
        description=(
            "面向用户的回复。action 为 answer 时直接回答；为 draft 时用正文引出并复述方案；为 start 或 ask 时填 null。"
        ),
    )
    material_text: str | None = Field(
        default=None,
        description=(
            "用户明确声明为自有素材的逐字原文，例如“这是我的文字稿……”。未明确将粘贴文本作为素材时填 null，单纯请求不属于素材。action 为 start 或 ask 时填 null。"
        ),
    )
    tasks: list[TaskItem] = Field(
        default_factory=list,
        description=(
            "已授权的任务链，按执行顺序列出 produce_video、prepare_narration 或 prepare_visual_assets。start、answer、ask 调用留空。"
        ),
    )
    specific_instruction: str | None = Field(
        default=None,
        description="从提示中提炼的自由文本指令。answer、start、ask 时填 null。",
    )
    tasks_explicit: bool = Field(
        default=False,
        description=(
            "用户自己明确点名作品时为 true，任务链源于默认提案时为 false。"
        ),
    )
    # Advisory brief slots preserve user-stated and inferred source facts.
    # brief (ADR-052 B2): the router's full-update proposal — emit only the
    # slots you have a view on this turn, each with
    # its source (user-stated ONLY when the user's own words literally state
    # the value). Code merges by source precedence; a slot you leave out
    # (or set null) keeps its stored value. Null for start/answer calls.
    brief: Brief | None = None
    # LLM 建图时命名 (2026-09-09, ADR-058): a compact noun phrase naming the
    # plan's deliverable, in the interface language ("中文 LinkedIn 帖子" /
    # "Chinese LinkedIn post") — it titles the run's receipt and completion
    # line. Display copy comes from the proposer's FRESH reading of the
    # turn, never from a frozen-params template. "" = unnamed (readers fall
    # back to the chain-derived label). Null-equivalent for start/ask/answer.
    name: str = ""


class PlanEstimate(BaseModel):
    """Dock 载荷的估价面 (BILLING §7, ADR-055): the plan's credits
    quotation, code-supplied (the estimate fold × PRICING × the consumption
    ratio — never the LLM, never a persisted column).

    ``total`` = the whole plan's [low, high] credits. ``per_task`` aligns
    with the task list by index: each entry is the task's MARGINAL range
    (prefix-compile difference — Σ per_task ≡ total exactly, 三面同源), or
    None for a task that adds no quoted cost (an unquotable fan-out — it
    settles at capture, BILLING §3)."""

    model_config = ConfigDict(extra="forbid")

    total: list[int]
    per_task: list[list[int] | None]


class QuestionPayload(BaseModel):
    """The typed ``question`` payload on a message (the ask_user machinery —
    the question machine).

    The mechanism words live here — ``kind`` carries the *use* (plan
    confirmation vs a plain question), never combined with the mechanism
    (NAMING: use × mechanism combos are banned). ``content`` on the
    message row keeps the question's human text. Defined after the brief
    family: the task_book form stamps the merged brief (B3).
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_kind(cls, data: Any) -> Any:
        """Stored rows written before the kind convergence spell ``choice``
        (and the retired ``confirm`` seat) — upgrade on read, never written
        (读容忍, same doctrine as the brief rows)."""
        if isinstance(data, dict) and data.get("kind") in ("choice", "confirm"):
            return {**data, "kind": "question"}
        return data

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_estimate(cls, data: Any) -> Any:
        """Rows docked before the credits batch carry the never-supplied
        ``estimate: str | None`` seat (always null, shape replaced by the
        structured ``estimate_credits``) — drop it on read, never written
        (读容忍, same doctrine as ``_drop_legacy_flags``)."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k != "estimate"}
        return data

    kind: Literal["task_book", "question"]
    # The BARE question (ask 三分解剖 ②): the dock's title, the QA archive's
    # Q line, and the reminder tail's quoted question. ``content`` carries the
    # framing prose (解剖 ①) when the ask brought one, else the bare question
    # itself (legacy rows, code-composed questions — read tolerance: every
    # consumer falls back to ``content`` when this is empty).
    question: str = ""
    options: list[Option] = Field(default_factory=list)
    allow_freeform: bool = True
    # 推荐标记 (2026-09-27 一问拍一体化): at most one option id marked as
    # the agent's recommendation — the dock renders its suffix. None on
    # legacy rows / unrecommended asks (读容忍).
    recommended_id: str | None = None
    # The dock's credits quotation (BILLING §7): task_book only, stamped at
    # dock time from the estimate fold (N-34) × the consumption ratio —
    # code-supplied, structured (data, localized at render), never a
    # pre-formatted string. None until supplied / for plain questions.
    estimate_credits: PlanEstimate | None = None
    # 授权前移 (ADR-117 §4): task_book only — the confirmation conjunct
    # computed ONCE at dock time (the prefs + guardrail + quote fold). The
    # client's confirm pill renders only when ``requires_confirmation`` is
    # true — it NEVER derives the need itself; ``confirm_reason`` selects
    # the pill's label family (execution_pref → bare Start; credits_pref /
    # above_guardrail → priced Start off ``quote_high``; unquotable → the
    # deferred-price label). Absent on legacy rows = False/""/None/False
    # (读容忍 — a pre-flip dock reads as the auto regime's under-line plan).
    requires_confirmation: bool = False
    confirm_reason: str = ""
    quote_high: int | None = None
    unquotable: bool = False
    # task_book only: the needs_clarification reason KEYS (data, localized at
    # render — never baked into `content`, which is user-facing prose).
    reasons: list[str] = Field(default_factory=list)
    # ask 一等动作牙齿 (ADR-052 B2): ``slot`` is the brief slot this
    # question fills — the answer backfills it user-stated and the plan path
    # None on every question that is not a brief ask (caption mode, direction
    # interrupts, post-run shape C). ADR-078 判词④ adds ``asset_role``: the
    # 角色消歧 dock ask — its options are code-built (id = asset id) and its
    # answer settles the PendingPlan source/exemplar pins by code, never by
    # LLM re-interpretation. ``default_path`` is the schema tooth of
    # 提问策略 ③: what happens when the user skips — the framing prose
    # (``content``) carries it visibly; the field keeps it machine-readable
    # for the dock's × and the interjection reminder tail.
    slot: BriefQuestionSlot | Literal["asset_role"] | None = None
    default_path: str = ""
    items: list[BriefQuestionItem] = Field(default_factory=list)
    group_digest: str | None = None
    # 预填评审卡 (ADR-052 B3): task_book only — the merged brief at
    # dock time, so the plan card renders the agent's OWN understanding
    # (valued slots with provenance) instead of blank form fields. Frozen
    # with the question row; every re-dock stamps the fresh merge.
    brief: Brief | None = None
    # 计划行自完备 (2026-09-08, 方案 B): task_book only — the ADR-043
    # derived preview ("you'll get") stamped at dock time. With the chain on
    # the row's `intent` column and this on the payload, the docked row IS
    # the whole plan card — the SSE envelope needs no pending-brief refetch
    # (that GET stays the recovery seat). Read tolerance: absent on rows
    # docked before the seal.
    derived: list[dict] = Field(default_factory=list)
    # 决策包阅读层 (ADR-089 §4 R16, iter-2 ③, N-57): task_book only — the
    # Content Plans the docked chain was compiled from (plan_id / title /
    # outputs / state — LLM-named product semantics, user-safe, never task
    # params). 确认消费三层: this reading layer + the intent column's
    # compiled tasks (evidence layer) + estimate_credits (费用语义五面).
    # Empty on every non-exploration dock (读容忍: 旧行无此键).
    plans: list[dict] = Field(default_factory=list)


def question_group_digest(items: list[BriefQuestionItem], brief: Brief) -> str:
    # Code-owned bookkeeping is not part of the question's answer identity.
    return canonical_json_hash({
        "schema_version": 1,
        "items": [item.model_dump(mode="json", exclude_none=True) for item in items],
        "brief_baseline": brief.model_dump(
            mode="json", exclude={"asked", "material_state"}
        ),
    })


def missing_brief_question_items(
    items: list[BriefQuestionItem], brief: Brief
) -> list[BriefQuestionItem]:
    slots = [item.slot for item in items]
    if len(slots) != len(set(slots)):
        raise ValueError("a clarification group cannot contain duplicate slots")
    missing: list[BriefQuestionItem] = []
    for item in items:
        if getattr(brief, item.slot).value:
            continue
        if item.required and not item.options and not item.allow_freeform:
            raise ValueError(f"required slot {item.slot} needs options or freeform")
        missing.append(item.model_copy(update={
            "recommended_id": resolve_recommended_id(item.recommended_id, item.options),
            "decision_page": None,
        }))
    return missing


class PendingPlan(BaseModel):
    """Unconfirmed plan persisted on ``projects.pending_brief``.

    Written by the chat plan path on draft-action turns (an
    answer-action turn never overwrites the stored plan), cleared once the
    run starts. Lets a user who left the plan-confirmation chat resume it
    exactly, from any device. Ask-action turns write a brief-only row
    (``intent=None``): the merged brief persists while the clarification is
    docked, and the answer's backfill lands on it.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_flags(cls, data: Any) -> Any:
        """Rows stored before the B4 cleanup carry a redundant
        ``needs_clarification`` bool (always derivable from ``reasons``) —
        drop it on read; it is never written anymore."""
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "needs_clarification"}
        return data

    prompt: str = ""
    # Null on brief-only rows (ADR-052 B2: an ask-turn write — the brief
    # merged, no plan drafted yet). A row with intent=None is never startable
    # and never re-docked as a plan.
    intent: InferredIntent | None = None
    # brief (ADR-052 B2): the dialog's structured state — slots with
    # provenance, merged by code every plan turn (merge_brief). The task
    # chain and derived preview above stay the plan's own rows (原样).
    brief: Brief = Field(default_factory=Brief)
    creative_state: CreativeState | None = None
    reasons: list[str] = Field(default_factory=list)
    persona_id: UUID | None = None
    # 资产角色 pins (ADR-078 判词④): which attached video is the user's OWN
    # material (source) and which is the reference exemplar whose craft the
    # run reverse-compiles. Settled by CODE only — the role question's answer
    # (service._settle_role_pins) or an @-mention (plan_turn's assemble) —
    # never by the LLM; stamped verbatim onto the TaskSpec at run start.
    # Roles are reversible between runs (a fresh mention re-pins). None =
    # unsettled (a multi-video remix asks the role question first).
    source_asset_id: str | None = None
    exemplar_asset_id: str | None = None
    # Derived preview (ADR-043): the dry-run-compiled graph's user-facing
    # projection — what this chain will produce — computed at dock time
    # (outputs are derived, never declared). Rows: {"type": "video"|"clips"|
    # "post"|"quotes"|"carousel"|"article", "variant": "subs"|"dub"|None,
    # "language"?, "count"?, "bilingual"?}. Empty on legacy rows.
    derived: list[dict] = Field(default_factory=list)
    # 决策包阅读层 (iter-2 ③, ADR-089 §4 R16): the Content Plans behind the
    # compiled chain (plan_id / title / state / outputs — the LLM-named
    # product semantics), stamped at dock time so the reading layer survives
    # a refresh (the restore path reads pending_brief, never the question
    # row). Empty on the router-drafted rows (读容忍).
    plans: list[dict] = Field(default_factory=list)
    # R20 修订路由器基材 (iter-3 E1/E2, N-58): plan_id → the plan's
    # half-open task range in the docked chain — born with the dock-time
    # compile, carried verbatim into the Confirmed Scope Snapshot at Start.
    # None on router-drafted / legacy rows — the revision router degrades
    # honestly to the @output channel (读容忍).
    plan_task_map: dict[str, list[int]] | None = None
    video_presentation: dict | None = None
    # The frozen cut's other half (冻结场内切点 = 冻结时间轴同一继承律):
    # the reveal words' landing beats, one entry per scene (None per
    # non-reveal scene); consumed fail-closed by the run whenever the kept
    # cut covers a reveal scene. Read-tolerant: absent on pre-envelope
    # rows.





class ProjectBase(BaseModel):
    """Base project model."""

    title: str
    event_name: str | None = None
    language: str = "zh"


class ProjectCreate(ProjectBase):
    """Create project request."""

    persona_id: UUID | None = None


class ProjectUpdate(BaseModel):
    """Update project request."""

    title: str | None = None
    event_name: str | None = None
    language: str | None = None
    status: ProjectStatus | None = None
    tone_snapshot: ToneSettings | None = None


class BulkDeleteRequest(BaseModel):
    """Batch project deletion (the projects grid's multi-select bar). One
    request, one transaction — the client never loops the single door."""

    ids: list[UUID] = Field(min_length=1, max_length=100)


class ProjectResponse(ProjectBase):
    """Project response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persona_id: UUID | None
    status: ProjectStatus
    tone_snapshot: ToneSettings | None = None
    created_at: datetime
    updated_at: datetime | None = None
    # Representative clip for the project-list card (list endpoint only; the
    # earliest rendered clip). None while no clip has finished rendering yet.
    thumbnail_url: str | None = None
    thumbnail_duration: int | None = None
    thumbnail_aspect: str | None = None


class AssetResponse(BaseModel):
    """Asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    project_id: UUID | None = None
    persona_id: UUID | None = None
    type: AssetType
    file_url: str | None = None
    title: str | None = None
    transcript: str | None = None
    extracted_text: str | None = None
    processing_status: AssetStatus
    processing_error: str | None = None
    duration_seconds: int | None = None
    # The media's real pixels (meta.width/height — probed at upload /
    # processing; the canvas's aspect truth). Populated post-validation at
    # the serialization seats (a declared field would read the ORM's `meta`
    # column name-by-name, so the seats stamp it).
    width: int | None = None
    height: int | None = None
    # The chain's live stage (meta.processing_stage, ADR-095 §2 — asr /
    # speaker_map / prosody / …): present only while processing, cleared at
    # the terminal state. Same seat-stamped pattern as width/height; the
    # client maps the token to the user-language label (内部工序名永不上屏).
    processing_stage: str | None = None
    processed_at: datetime | None = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stream_url(self) -> str | None:
        """Browser-playable URL for this asset, resolved through the storage seam."""
        from app.providers.storage import stream_url

        return stream_url(self.file_url)


class AssetUploadUrlRequest(BaseModel):
    """Request a presigned PUT URL for direct upload to object storage."""

    filename: str
    content_type: str = "application/octet-stream"


class StagingUploadUrlRequest(AssetUploadUrlRequest):
    """Request a presigned PUT URL for a pre-project staging session (Batch A).

    ``session_id`` is client-generated (uuid); the route validates its shape
    before it ever reaches a key builder — it becomes one path segment.
    """

    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class AssetUploadUrlResponse(BaseModel):
    """Presigned PUT URL response."""

    key: str
    upload_url: str


class AssetCreateRequest(BaseModel):
    """Create an asset record after the client uploaded the file to storage."""

    key: str
    type: AssetType
    # Original upload filename, used as the display title in the UI.
    title: str | None = None
    # The canvas's aspect truth (2026-09-13 用户拍板 — 产物卡跟源比例):
    # client-probed at staging (element metadata, same probe that feeds the
    # chip), so the asset node is BORN with its real display class — the
    # chain-head probe (asset_processing) backfills API-path uploads.
    # Display-only (shapes a card, never a price), so client-reported is
    # fine; the storage object itself is still verified above.
    width: int | None = Field(default=None, gt=0, le=20000)
    height: int | None = Field(default=None, gt=0, le=20000)


class PersonaAssetCreateRequest(BaseModel):
    """Create a persona asset record after direct upload to storage."""

    key: str
    # Original upload filename, used as the display title in the UI.
    title: str | None = None
    # Persona assets come in two kinds: past materials (text extracted for
    # style learning) and voice samples (audio the persona's voice block
    # binds). Everything else is rejected.
    type: Literal["past_material", "voice_sample"] = "past_material"


class PersonaMediaCreateRequest(BaseModel):
    """Confirm a directly-uploaded persona skin media file (intro/outro card)."""

    key: str


class PersonaAssetUpdateRequest(BaseModel):
    """Rename a persona asset."""

    title: str


class ClipRevision(BaseModel):
    """Revised clip metadata returned by the reviser agent.

    Replaces the old ``ClipScript`` / ``Shot`` model: the renderer now drives
    from ``render_spec`` and ASR captions, so revision only needs the hook,
    duration, titles, and music mood.
    """

    model_config = ConfigDict(extra="forbid")

    hook: str
    duration_seconds: int = Field(default=30, ge=5, le=120)
    title_options: list[str] = Field(default_factory=list)
    music_mood: str = "calm"
    recommendation_score: int | None = Field(default=None, ge=1, le=100)
    score_reason: str | None = None


class RenderStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class KeyArgument(BaseModel):
    """演讲的一个关键论点及其在逐字稿中的位置。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="素材分析内稳定的 ID（a1、a2 等）")
    text: str
    # Display alternates (interrupt options render in the UI language,
    # never the material's): faithful English / Simplified-Chinese
    # renderings of the same argument. Empty on legacy cached payloads —
    # the display layer falls back to ``text``.
    text_en: str = ""
    text_zh: str = ""
    # Free-text location marker — the planner never sees word-level
    # timestamps, so an honest text marker instead of fake seconds.
    position: str = ""

class QuotableLine(BaseModel):
    """逐字引用的原句，其能否独立成句由代码检查并标记。"""

    model_config = ConfigDict(extra="forbid")

    text: str  # verbatim from the material
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None
    # Code-set, never the LLM's: False when the line opens with a dangling
    # pronoun / connective (it, this, but, 这/但/而且…) or trails off mid-thought.
    self_contained: bool = True

class TopicBoundary(BaseModel):
    """根据语义划分的一个演讲主题段。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="素材分析内稳定的 ID（t1、t2 等）")
    label: str = ""
    # The LLM's evidence: the verbatim first words of the segment — the
    # snapping anchor. ``approx_start`` is an optional coarse cue-second hint.
    marker: str = ""
    approx_start: float | None = None
    # Code-resolved onto the ASR word axis; None when unresolved / untimed.
    asset_id: str = ""
    start: float | None = None
    end: float | None = None

class ClimaxSpan(BaseModel):
    """一段在语义上达到高潮的内容，为高潮判断提供语义依据。"""

    model_config = ConfigDict(extra="forbid")

    text: str = ""  # the verbatim climax sentence(s)
    why: str = ""
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None

class EmphasisWord(BaseModel):
    """模型根据语义判断应重读的词，weight 为模型给出的权重。实测的基频 F0 和能量 z 分数保存在 asset.meta["prosody"]["words"]，不与语义权重合并。"""

    model_config = ConfigDict(extra="forbid")

    word: str
    weight: float = 0.5
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None

class NarrativeRoleHint(BaseModel):
    """片段在整体叙事中的作用，可为 setup、payoff、example 或 transition。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["setup", "payoff", "example", "transition"]
    note: str = ""
    marker: str = ""  # verbatim first words of the span (snapping anchor)
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None

class VisualAnchor(BaseModel):
    """模型为一张图片提取的视觉锚点语义信息。人脸、主体框和安全区等测量结果保存在素材 meta["visual_anchors"]，通过 asset_id 关联。"""

    model_config = ConfigDict(extra="forbid")

    # The image's ordinal in the media list the LLM saw ("image 2" → 2);
    # code-resolved to the asset id at persist time ("" = unresolved).
    ref: str = ""
    asset_id: str = ""
    label: str = ""  # what / whom the image shows
    # Ids of key_arguments this image visually backs.
    argument_ids: list[str] = Field(default_factory=list)

class Point(BaseModel):
    """Normalized center point in [0,1] (CSS translate / libass \\pos)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)

class MaterialUnderstanding(BaseModel):
    """素材理解: understand step — what the material says (material-scoped).

    Pure: built from source texts/media only — never persona, tone,
    instruction, or target language — so it stays reusable across runs,
    languages, and plans (asset-hash invalidation). The beat-map fields
    (期 1) extend it into the material-level beat map: semantic halves only.
    """

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_thesis: str
    key_arguments: list[KeyArgument] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    # Verbatim lines from the material, in the source language, with the
    # code-checked self-containment flag. The planning prompt's Quote Pool
    # is the derived ``[q.text for q in quotable_lines]`` view (one write).
    quotable_lines: list[QuotableLine] = Field(default_factory=list)
    topic_boundaries: list[TopicBoundary] = Field(default_factory=list)
    climax_spans: list[ClimaxSpan] = Field(default_factory=list)
    emphasis_words: list[EmphasisWord] = Field(default_factory=list)
    narrative_role_hints: list[NarrativeRoleHint] = Field(default_factory=list)
    visual_anchors: list[VisualAnchor] = Field(default_factory=list)


class VideoSpecEnvelope(BaseModel):
    """Thin read envelope for the sole online video-spec render contract.

    The schema remains owned by ``packages/video-spec``; this boundary does
    not revalidate or reinterpret the content.
    """

    model_config = ConfigDict(extra="allow")

    family: Literal["video"]


class VideoPayload(BaseModel):
    """Payload for ``outputs[type=video]`` (ADR-145) — a Composition render.

    Timeline semantics ride the pinned CompositionVersion (the output's
    ``composition_id`` / ``composition_version_id`` columns);
    ``composition_digest`` completes the §2.2 three-fact pin. The render
    pipeline uses the shared ``render_spec``/``render_status`` execution facts.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""  # the Composition's name at queue time
    duration_seconds: float = 0
    duration: float = 0
    aspect: str | None = None
    content_language: str | None = None
    execution_digest: str | None = None
    composition_digest: str = ""
    generator_media: dict[str, dict[str, Any]] = {}
    # Actual execution media, never back-written into the immutable version.
    speech_media: dict[str, dict[str, Any]] = {}
    narration_policy: dict[str, Any] | None = None


# Internal types are node artifacts, not user-facing products. Every read path
# must exclude them via ``services.outputs.visible_outputs`` — never hand-roll a
# type filter (results/library/export, and future MCP/gallery surfaces).
# ``content_plan`` stays listed so pre-Phase-2 rows remain hidden.
INTERNAL_OUTPUT_TYPES: frozenset[str] = frozenset(
    {"content_plan", "material_understanding", "storyboard", "craft_skeleton"}
)


def validate_output_payload(output_type: str, payload: dict) -> dict:
    """Validate payload against the registry schema for ``output_type``.

    Returns a normalized plain dict for the JSONB column; raises ``ValueError``
    for unknown types or malformed payloads.
    """
    model = OUTPUT_PAYLOAD_SCHEMAS.get(output_type)
    if model is None:
        raise ValueError(f"Unknown output type: {output_type}")
    return model.model_validate(payload).model_dump(mode="json")


OUTPUT_PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "video": VideoPayload,
    "material_understanding": MaterialUnderstanding,
}


class ProductionStage(BaseModel):
    """User-safe, replayable production work inside one fenced step attempt."""

    event_id: str
    kind: str
    run_id: UUID
    step_id: UUID
    attempt: int = Field(ge=0)
    seq: int = Field(ge=0)
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    reused: bool | None = None
    item_count: int | None = Field(default=None, ge=0)
    reused_count: int | None = Field(default=None, ge=0)
    scene_id: str | None = None


class StepResponse(BaseModel):
    """One node of a run's execution plan — the user-facing step (ADR-028).

    ``stage`` is an optional display hint lifted from ``node.spec["stage"]`` by
    the serializer (e.g. selecting_segments / building_specs), letting the
    stepper reuse existing i18n keys.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    seq: int
    attempt: int = 0
    error: str | None = None
    cost: dict | None = None
    stage: str | None = None
    # Quantified one-liner from the registry summary_template (e.g. "Selected
    # 3 clips · 87s total"), lifted from spec["summary"] like stage.
    summary: str | None = None
    # The runner's structured "nothing to do here" declaration (2026-09-10 —
    # the receipt's whisper tier): stamped at the same seat as the "…skipped"
    # summary line, so the client never string-matches. None ≠ False only on
    # legacy rows.
    noop: bool | None = None
    # Output row ids this node produced — the RunCard collects these on run
    # completion to inline the product cards (chat-loop-v2).
    output_refs: list[UUID] = Field(default_factory=list)
    # DAG edges: upstream step ids (the run's execution DAG, ADR-028).
    inputs: list[UUID] = Field(default_factory=list)
    # Credits derivation (ADR-055, BILLING §7 — serialization-derived, NEVER
    # persisted columns): the step's quotation / metered actual, priced USD
    # (PRICING) × the consumption ratio at read time. ``estimate_credits``
    # [low, high] is None when the node never quoted (NULL estimate);
    # ``cost_credits`` is None while nothing was metered (cost NULL).
    estimate_credits: list[int] | None = None
    cost_credits: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    scene_index: int | None = Field(default=None, ge=1)
    production_stages: list[ProductionStage] = Field(default_factory=list)


class OutputResponse(BaseModel):
    """An owned video media, execution and Composition-lineage record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    workflow_step_id: UUID | None = None
    type: str
    # None = unpinned (legacy rows, or the null-as-string plan token that
    # leaked into early rows' language column — normalized at the boundary
    # below, same posture as _derive_aspect's "original" → None).
    language: str | None = None
    status: str
    # work/version 两身份 (ADR-091, N-59): work_id = the user-semantic anchor
    # shared by every version of one work; archived_at NULL = the work's
    # active version (可空时间戳律 — the read face filters on it).
    work_id: UUID | None = None
    archived_at: datetime | None = None
    provenance: str
    payload: dict
    files: dict = Field(default_factory=dict)
    source_ref: dict | None = None
    render_spec: VideoSpecEnvelope | None = None
    render_status: RenderStatus | None = None
    render_error: str | None = None
    # Composition lineage (ADR-145): set on video-family outputs only.
    composition_id: UUID | None = None
    composition_version_id: UUID | None = None
    # The immutable content version's real sequence number, not an Output
    # count. Multiple deliveries may honestly show the same number.
    composition_version_number: int | None = None
    # 质检裁决 (期 3): verify 节点的 {status, checks, attempt, checked_at};
    # None = 未质检（旧行 / 无 verify 的图）。
    quality: dict | None = None
    publishing: dict = Field(default_factory=dict)
    # Display aspect from the video-spec, then its explicit payload declaration.
    aspect: str | None = None
    # Integrity hash of the immutable render input.
    spec_hash: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> Any:
        # The null-as-string plan token reads as absent — one predicate
        # (is_null_token) shared with the proposal boundary's scrub.
        return None if is_null_token(value) else value

    @field_validator("payload", mode="before")
    @classmethod
    def _validate_payload(cls, value: Any, info: ValidationInfo) -> Any:
        output_type = info.data.get("type")
        if output_type is None or not isinstance(value, dict):
            return value
        model = OUTPUT_PAYLOAD_SCHEMAS.get(output_type)
        if model is None:
            return value
        return model.model_validate(value).model_dump(mode="json")

    @model_validator(mode="after")
    def _resolve_file_urls(self) -> OutputResponse:
        """Resolve stored object keys in files/publishing to public URLs."""
        from app.providers.storage import resolve_stored_url

        for key in ("video", "image"):
            if self.files.get(key):
                self.files[key] = resolve_stored_url(self.files[key])
        if self.publishing.get("cover_image_url"):
            self.publishing["cover_image_url"] = resolve_stored_url(
                self.publishing["cover_image_url"]
            )
        return self

    @model_validator(mode="after")
    def _derive_aspect(self) -> OutputResponse:
        """Single server-side aspect derivation (产物展示统一 P1): the
        video-spec declares ``render_spec.aspect``; an explicit
        ``payload["aspect"]`` is the fallback; ``"original"``
        and empty values normalize to None (unknown frame — surfaces
        fall back to their default tier or the shared probe)."""
        declared = self.payload.get("aspect") if isinstance(self.payload, dict) else None
        candidates = (
                    getattr(self.render_spec, "aspect", None)
            if self.render_spec is not None
            else None,
            declared,
        )
        self.aspect = next(
            (
                a
                for a in candidates
                if isinstance(a, str) and a and a != "original"
            ),
            None,
        )
        return self


class ChatOutputEntry(BaseModel):
    """One persisted delivery reference in a Chat's shared Output browser."""

    output_id: UUID
    # Null = the exact historical reference no longer resolves. Keeping its
    # seat makes the viewer honest instead of silently substituting a newer Output.
    output: OutputResponse | None = None


class OutputPosterResponse(BaseModel):
    output_id: UUID
    poster_url: str


class ExtractedPersonaMemory(BaseModel):
    """模型提取的人设信息，直接对应 Persona 数据库字段。name 是提炼出的人设标签，如“务实的 AI 推广者”。自动创建时用作 Persona.name，不以文件名命名。手动重新生成时保留用户自己选的名称。"""

    name: str = ""
    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str = ""
    emotional_tone: str = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None






class AssetTranscriptCue(BaseModel):
    """One display-face cue row of an asset's transcript (ADR-113 §1 — cues
    are a read-time derivation of ``meta.words`` via the ONE grouping law,
    never persisted): timeline anchor + raw-joined text + the preformatted
    ``m:ss–m:ss`` label (the client never formats time)."""

    model_config = ConfigDict(extra="forbid")

    start: float
    end: float
    text: str
    label: str


class AssetTranscriptResponse(BaseModel):
    """``GET /projects/{id}/assets/{asset_id}/transcript`` — the asset's
    content layer (ADR-113 §1, the ONE seat):

    - ``text`` = the SOURCE layer (ASR/extraction/paste yield), always.
    - ``edited_text`` = the user's edit overlay (``assets.edited_transcript``;
      C4 — the overlay never reverse-computes a timecode). NULL = source
      shown as-is. The card displays ``edited_text ?? text``.
    - ``cues`` = the timeline face, derived at read time; NULL when the
      asset has no word timestamps (paste/extraction yields carry no time
      axis — the honest plain-text face).
    - ``truncated`` = words beyond the grouping cap exist (the card renders
      the honest marker, never a silent window).
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    edited_text: str | None
    cues: list[AssetTranscriptCue] | None
    truncated: bool


class AssetTranscriptPutRequest(BaseModel):
    """``PUT /projects/{id}/assets/{asset_id}/transcript`` — the card's
    in-place direct edit writing the OVERLAY only (``edited_transcript``);
    ``text`` null = clear the overlay (the source layer shows again). No
    run, no credits — the edit is not executable work."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None


class FeedbackScope(StrEnum):
    """Feedback scope."""

    HOOK = "hook"
    FULL_SCRIPT = "full_script"
    TONE = "tone"
    TRANSLATION = "translation"


class FeedbackReason(StrEnum):
    """Feedback reason."""

    HOOK_NOT_CATCHY = "hook_not_catchy"
    NOT_LIKE_PERSONA = "not_like_persona"
    TOO_COMPLEX = "too_complex"
    TOO_SIMPLE = "too_simple"
    FACTUALLY_INACCURATE = "factually_inaccurate"
    DIFFERENT_EXPRESSION = "different_expression"
    OTHER = "other"




class RunResponse(BaseModel):
    """Workflow run response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: WorkflowStatus
    progress: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    context: dict | None = None
    # Aggregated step metering (sum of workflow_steps.cost); None until metered.
    cost: dict | None = None
    # RunPlan steps, ordered by seq; empty for runs predating RunPlan.
    steps: list[StepResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class ProjectAssetStatus(BaseModel):
    """Lightweight per-asset processing status for the results page.

    Lets the results page render the transcribing/parsing phase of the
    loading state while the generation run waits for assets to settle.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: AssetType
    processing_status: AssetStatus
    processing_error: str | None = None


class GraphNodeResponse(BaseModel):
    """One source-asset or ordinary manual Canvas node."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: Literal["text", "table", "image", "video", "audio"]
    state: Literal["draft", "done"]
    spec: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)
    asset: AssetResponse | None = None
    created_at: datetime
    updated_at: datetime | None = None


class GraphEdgeResponse(BaseModel):
    """One typed flow of the persistent graph (ADR-057 port law)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_node: UUID
    from_port: str | None = None
    to_node: UUID
    to_port: str | None = None
    edge_type: str


class LifecycleStamp(BaseModel):
    """The server-named lifecycle projection (ADR-087 §2, Phase 1) — one
    truth, many readers. The four CONFIRMATION_READY conjuncts are
    independent fields (门禁三: never one boolean); ``state`` is the
    presentation rollup, ``blockers`` the first-class reason channel
    (U1: FAILED ≠ generic not-ready)."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["preparing", "plan_ready", "confirmation_ready", "running"]
    material_ready: bool
    plan_ready: bool
    confirmation_scope_ready: bool
    charge_semantics_ready: bool
    no_active_conflicting_run: bool
    confirmation_ready: bool
    blockers: list[str] = Field(default_factory=list)
    charge: dict = Field(default_factory=dict)


class ProjectGraphResponse(BaseModel):
    """The project graph's one read frame — nodes + edges + joined display
    rows, everything the canvas renders, in one fetch."""

    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)
    lifecycle: LifecycleStamp | None = None


class ProjectResultsResponse(BaseModel):
    """Aggregated results for the project detail/results page."""

    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    prompt: str | None = None
    latest_run: RunResponse | None = None
    assets: list[ProjectAssetStatus] = Field(default_factory=list)
    pending_brief: PendingPlan | None = None
    lifecycle: LifecycleStamp | None = None


# ---------------------------------------------------------------------------
# Music library (DB-backed AI-generated pieces; see docs/MUSIC_ARCHITECTURE.md).
# Audio bytes stay on disk under assets/music/{id}.<ext>; these schemas cover
# the metadata API surface only.
# ---------------------------------------------------------------------------


class MusicResponse(BaseModel):
    """A music library piece (metadata + stream URL; no audio bytes)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mood: str
    title: str
    ext: str
    url: str
    size_bytes: int
    duration_seconds: int | None = None
    prompt: str | None = None
    model: str | None = None
    license: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool
    created_at: datetime


class MusicGenerateRequest(BaseModel):
    """Request body for on-demand music generation from a prompt."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    mood: str | None = None
    title: str | None = None
    is_instrumental: bool = True


class MusicMetadataUpdate(BaseModel):
    """Editable metadata fields for a music piece (PUT)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    license: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Distribution — channels & publications (docs/DISTRIBUTION.md, ADR-030/031)
# ─────────────────────────────────────────────────────────────────────────────


class ChannelPlatform(StrEnum):
    """P1 platform scope (2026-07-23 定界): LinkedIn + TikTok only."""

    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"


class ChannelAccountStatus(StrEnum):
    """OAuth token lifecycle states (DISTRIBUTION.md §3.1)."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class PublicationState(StrEnum):
    """Publish-order state machine (DISTRIBUTION.md §3.3).

    ``draft`` / ``pending_review`` / ``approved`` are the P2 institutional path
    (ADR-027); the P1 personal flow is born ``scheduled`` (create = publish
    now) and never touches them.
    """

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChannelAccountResponse(BaseModel):
    """Public view of a connected channel — credentials never leave the server."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: ChannelPlatform
    platform_user_id: str
    display_name: str
    avatar_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    status: ChannelAccountStatus
    token_expires_at: datetime | None = None
    created_at: datetime | None = None


class PublicationResponse(BaseModel):
    """Publish-order view; ``payload`` is the frozen snapshot from creation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    output_id: UUID
    channel_account_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ai_disclosure: bool = False
    state: PublicationState
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    platform_post_url: str | None = None
    attempt_count: int = 0
    last_error: str | None = None
    created_at: datetime | None = None


class NotificationResponse(BaseModel):
    """One bell-panel row; ``payload`` shape depends on ``type``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int

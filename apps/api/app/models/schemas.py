"""Pydantic models for Repurposer API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)
import structlog

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
    kind: str  # heading / text / button / image / video / pinned
    text: str = ""
    x: float
    y: float
    w: float
    h: float
    covered: bool = False
    # Absolute CSS-page box of the visible element region. ``pixel_box`` is
    # the same region in the full-page image; the element crop starts at its
    # own (0, 0). Old captures carry neither enhancement.
    css_box: CaptureBox | None = None
    pixel_box: CaptureBox | None = None
    device_scale_factor: float = 1.0
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


class MessageRole(StrEnum):
    """Chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


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
    """One option on a structured question."""

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

    id: str
    label: str
    # 一问拍一体化 (2026-09-27, Claude-Card parity): the option's one-line
    # reason rides the card under the label — bare labels forced the
    # "which do you recommend?" follow-up tax. "" on legacy rows and
    # code-built options (asset_role) — 读容忍.
    description: str = Field(
        default="",
        description="One short line: why this option — the conclusion the user can judge, never your reasoning process.",
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


class AnswerPayload(BaseModel):
    """The typed ``answer`` payload on a message.

    ``bail`` is a first-class answer kind — a graceful exit, never a failure.
    ``start`` is the plan confirmation (the answer that starts the run)
    — a kind of its own, not a magic option id (C1).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["option", "freeform", "bail", "start"]
    option_id: str | None = None
    text: str | None = None
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


class StartAnswerRequest(BaseModel):
    """Confirm the docked plan and start the run (task_book questions).

    Replaces the phase-1 magic ``option_id="start"`` — the confirmation is a
    kind of its own, so the kind-specific field (the review panel's edited
    plan) is only valid here, never silently ignored on other kinds (C2).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["start"]
    # RETIRED: the film storyboard presents at the design beat (a plain
    # design_storyboard message); there is no review gate to waive. The
    # field stays so old clients keep passing it without a 422
    # (extra="forbid"); the value is accepted and IGNORED, never carried
    # into the run (the autonomy precedent below).
    skip_storyboard_review: bool = False
    # RETIRED (Phase 4 B7 / ADR-087 R9, D1): the autonomy tier is gone —
    # every run is an autonomous continuation. The field stays so old
    # clients keep passing it without a 422 (extra="forbid"); the value is
    # accepted and IGNORED, never carried into the run.
    autonomy: Literal["auto", "review"] | None = None
    # The review panel's edited plan (hand-edited slots marked explicit).
    # Wins over the stored pending brief, so panel edits reach the run;
    # None = use the stored pending brief.
    intent: InferredIntent | None = None


class BailAnswerRequest(BaseModel):
    """Bail — a graceful exit (back to draft / stop the parked run), never an error."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bail"]


# Request body for ``POST /chat/messages/{id}/answer`` — discriminated on
# ``kind`` so kind-specific fields can't ride along where they're ignored.
AnswerRequest = Annotated[
    OptionAnswerRequest
    | FreeformAnswerRequest
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
    focus_output: FocusRef | None = None
    workflow_run_id: UUID | None = None
    intent: dict | None = None
    question: dict | None = None
    answer: dict | None = None
    # 建议谱系交互块 (ADR-099 §4): non-blocking next-step options this
    # assistant row offered, provenance included — the OptionDock renders
    # them under the prose; a pick rides back as suggestion_ref.
    suggestions: list[SuggestionRecord] = Field(default_factory=list)
    # Structured presentation blocks (ADR-145 phase B): server-stamped
    # component references (video_storyboard cards); absent/[] on legacy
    # rows (读容忍).
    blocks: list[dict] = Field(default_factory=list)
    # 点选引用 (ADR-099 §4): a user row that IS a suggestion pick carries
    # its structured ref — the visible content stays the picked label.
    suggestion_ref: SuggestionRef | None = None
    # Transcript 数组位置 (ADR-108): per-conversation monotonic; the client
    # renders in seq order and never re-derives interleaving from clocks.
    seq: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


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
    the prompt templates (``app/prompts/chat/intent_router_system.j2``'s ask
    rule / ``chat_intent_system.j2``'s shape C) — those are the single
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
    # question — 认领 the request + why this ONE question decides quality.
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
    slot: Literal["topic", "audience", "tone", "asset_role"] | None = None
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


class WiringProposal(BaseModel):
    """Intent agent output, state E (ADR-057 K4): edit the persistent graph,
    then the deterministic scope classifier adjudicates the resulting paid
    execution scope (ADR-087 §4, D4) — an approved-scope continuation
    (e.g. ``edit_prompt(node)`` + ``run({node} ∪ downstream)`` on filled
    nodes) re-fills autonomously; a scope expansion / unproven op rolls the
    door's mutation back and docks a plan for explicit confirmation instead.
    ``ops`` speaks the graph_store wiring registry's vocabulary (add_node /
    connect / edit_prompt / delete_node / run); adjudication is
    ``apply_wiring_ops``'s (op shape / references / ports / cycles), never
    the schema boundary's — ops stay loose dicts here so the registry's own
    errors feed the repair round verbatim."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_null_name(cls, data: Any) -> Any:
        """读容忍 — same null seat as TaskListProposal.name."""
        if isinstance(data, dict) and data.get("name") is None:
            data = dict(data)
            data.pop("name", None)
        return data

    type: Literal["wiring"] = "wiring"
    ops: list[dict] = Field(default_factory=list)
    summary: str
    # LLM 建图时命名 (ADR-058): same seat as TaskListProposal.name — the
    # revision run's compact deliverable name, "" = unnamed.
    name: str = ""
    # Kept when EditGraphArgs is translated into this internal proposal so
    # the expansion dock reads the current message's production fact instead
    # of an out-of-scope variable. None remains the safe awaiting-production
    # default for code-assembled revision proposals.
    production_intent: bool | None = None


IntentProposal = Annotated[
    TaskListProposal | QuestionProposal | AnswerProposal | WiringProposal,
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
    (OutputResponse.language / compose_spec_prompt normalization)."""
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
    """``ask_user`` params, plan path — the ask_user machinery's one-question
    shape (QuestionProposal minus the prose, which is the content channel
    now).
    ``slot`` names the brief slot the question fills (plan-path only
    — post-run questions never backfill a brief). The envelope seats ride
    the same call so the turn's brief proposal and material promotion
    arrive with the call, exactly once."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(
            tolerate_null_keys(data, "options", "default_path", "slot", "material_text", "material_urls", "recommended_id", "pending_disposition")
        )

    question: str = Field(
        description="The ONE question, in the interface language — the bare question, no framing, no default-path tail (those live in your spoken message)."
    )
    options: list[Option] = Field(
        default_factory=list,
        description="3 concrete one-word values (2 only for a genuinely binary choice) sourced from the user's persona/context, translated into the interface language. Each carries its one-line reason (description). Empty only when no sensible options exist (a freeform ask). Freeform input always stays available alongside.",
    )
    allow_freeform: bool = True
    recommended_id: str | None = Field(
        default=None,
        description="The ONE option id you recommend (at most one) — your judgment rides the card, and your spoken message leans toward the same pick (one judgment, one voice). Null = no recommendation.",
    )
    default_path: str = Field(
        default="",
        description="One short clause: what you will do if the user skips. The skip must be safe.",
    )
    slot: Literal["topic", "audience", "tone", "asset_role"] | None = Field(
        default=None,
        description="The brief slot this question fills (the pre-run router's seat). 'asset_role' is NOT a brief slot: the 资产角色 disambiguation (ADR-078 判词④) — ask it when ≥2 videos are attached and which is the user's own material vs the reference exemplar is undecidable from the message. Its options are code-built from the videos at the dock seat (never write option ids yourself); the answer settles the source/exemplar pins by code.",
    )
    brief: Brief | None = Field(
        default=None,
        description="Brief updates this turn: only the slots you have a view on, each with its source (user-stated ONLY when the user's own words literally state the value). Slots you leave out keep their stored value.",
    )
    material_text: str | None = Field(
        default=None,
        description="Verbatim source text the user explicitly declared as their own material this turn ('this is my transcript: …'). Null otherwise — a bare request is never material.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="URLs the user's own message offers as MATERIAL to work from (a page they paste so you can make something of it — 'make a short film of https://…'). Copy each URL verbatim; the system captures the page into a project asset itself. A link shared only for discussion ('what do you think of this site?') is NOT material — leave it out. Null otherwise.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — the question settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
    )


class PresentPlanArgs(BaseModel):
    """``present_plan`` params, plan path — the draft call's payload (the
    plan docks for confirmation; it never starts a run by itself). The
    plan-introducing echo is your spoken message, never a param."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(
            tolerate_null_keys(
                data, "tasks", "specific_instruction", "caption_mode", "tasks_explicit", "name", "material_text", "material_urls", "pending_disposition", "production_intent"
            )
        )

    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="The proposed tool chain — one task per piece of work, in execution order (an English and a German post = two write_post tasks; whole-video bilingual subtitles = one translate_clip task).",
    )
    specific_instruction: str | None = Field(
        default=None,
        description="Free-form instruction distilled from the prompt.",
    )
    caption_mode: Literal["bilingual", "source_only", "target_only"] | None = Field(
        default=None,
        description="Caption mode for captioned-video runs (write_quotes / caption-bearing recipes). Set it only when the user's own words already name the mode; when omitted, the system derives the default and the plan card shows it as a visible fact the user can change with one sentence.",
    )
    tasks_explicit: bool = Field(
        default=False,
        description="True when the user explicitly named the work themselves; False when the chain is the default proposal.",
    )
    name: str = Field(
        default="",
        description="A compact noun phrase (2-6 words, interface language) naming the plan's deliverable — it titles the run's receipt. Name the work, never the tools.",
    )
    brief: Brief | None = Field(
        default=None,
        description="Brief updates this turn: only the slots you have a view on, each with its source (user-stated ONLY when the user's own words literally state the value).",
    )
    material_text: str | None = Field(
        default=None,
        description="Verbatim source text the user explicitly declared as their own material this turn. Null otherwise.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="URLs the user's own message offers as MATERIAL to work from (a page they paste so you can make something of it — 'make a short film of https://…'). Copy each URL verbatim; the system captures the page into a project asset itself. A link shared only for discussion ('what do you think of this site?') is NOT material — leave it out. Null otherwise.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — the question settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
    )
    production_intent: bool | None = Field(
        default=None,
        description=(
            "Does the user's message ask for this work to be MADE now? "
            "True only for an explicit production request or delegation "
            "('按这版制作' / 'go ahead' / '直接做，细节你决定'); false for a "
            "pure modification, a review-only ask ('先给我看方案'), or a "
            "discussion. The user's auto/ask settings only waive approval "
            "beats — they never turn a message without a production "
            "request into one: a plan docked without it waits for the "
            "user's word (the card keeps its start button). A film "
            "storyboard design/revision is the family exception: without "
            "current production intent it closes through answer after the "
            "full presentation, not through a production dock. Never omit "
            "this judgment."
        ),
    )


class DesignStoryboardArgs(BaseModel):
    """``design_storyboard`` params (both paths) — the film family's review
    beat (分镜不是开工, 分镜也不是方案 dock): a plain tool call that designs
    the storyboard and presents its markdown as an ordinary message; NO plan
    docks and NO run starts here. The params mirror the launch_film task's
    storyboard-relevant fields verbatim — the dock that follows the user's
    approval reuses THIS board only when the params match (the fingerprint's
    params half), so carry the same values through."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        # target_seconds / scene_count / group_chars are presence-sensitive:
        # an omitted key inherits on redraft, while an explicit null clears
        # the base constraint. Do not pass them through tolerate_null_keys.
        return tolerate_null_keys(
            data, "focus", "language", "voiceover", "subtitles", "music_mood", "aspect", "specific_instruction", "material_urls", "pending_disposition", "review_hold", "edits", "base_ref", "text", "verbatim"
        )

    @model_validator(mode="after")
    def _edits_branch_exclusive(self) -> "DesignStoryboardArgs":
        """The patch path's arg discipline: ``edits`` rides ONLY with
        ``base_ref`` (mandatory — the read-time reference), ``review_hold``
        and conversation-level ``pending_disposition`` (never a design
        parameter). Every design param (focus/language/voiceover/subtitles/
        music_mood/aspect) belongs to the BASE version + the ops themselves
        (set_music / set_voiceover), and open redraft feedback rides
        ``specific_instruction`` — mixing the two paths is never legal."""
        if self.edits:
            if not self.base_ref:
                raise ValueError(
                    "edits require base_ref — re-read the version you are "
                    "editing (get_output_spec on the film output, or the "
                    "design beat's own reference line) and echo its base_ref "
                    "verbatim"
                )
            mixed = [
                name
                for name in (
                    "focus", "language", "voiceover", "subtitles", "music_mood", "aspect",
                    "specific_instruction", "material_urls", "text", "verbatim",
                    "target_seconds", "scene_count", "group_chars",
                )
                if name in self.model_fields_set
            ]
            if mixed:
                raise ValueError(
                    f"edits never mix with {', '.join(mixed)} — a patch "
                    "changes the base version through the ops alone; open "
                    "feedback rides specific_instruction WITHOUT edits"
                )
        return self

    focus: str | None = Field(
        default=None,
        description="The agreed creative direction as the storyboard's emphasis steer (launch_film's focus, verbatim).",
    )
    language: str | None = Field(
        default=None,
        description="The film's spoken language when one was agreed or named (launch_film's language, verbatim). Null = the page's own.",
    )
    voiceover: bool | None = Field(
        default=None,
        description="Spoken narration (launch_film's voiceover, verbatim). A NEW film defaults OFF: pass true ONLY when the user explicitly asked for spoken narration — never on your own initiative; null/false = no spoken narration (no synthesis, no TTS cost). Subtitles and the music bed are independent: 'no voiceover' implies neither 'no subtitles' nor 'no music'. Revising an existing version inherits its pinned setting unless the user names a change.",
    )
    subtitles: bool | None = Field(
        default=None,
        description="Independent visible subtitle tracks (launch_film's subtitles, verbatim). A NEW film defaults ON, with or without voiceover; pass false only when the user asks for no subtitles. Revising an existing version inherits its pinned setting unless the user names a change. This is separate from spoken narration and from clip caption styles.",
    )
    music_mood: str | None = Field(
        default=None,
        description="Background-music mood for the bed (launch_film's music_mood, verbatim): on a first version, choose one library mood when the user has not named music; an explicit user choice or 'off' takes precedence. Later versions inherit the pinned choice unless the user asks for a change.",
    )
    aspect: Literal["16:9", "1:1", "9:16"] | None = Field(
        default=None,
        description="Canvas aspect when one was agreed (launch_film's aspect, verbatim). Null = 16:9.",
    )
    text: str | None = Field(
        default=None,
        description="The copy for a TEXT film (text planes on solid color — no webpage, no capture): the user's own words when they want them shown, else the copy you distilled or authored from their brief (set verbatim false then). Present = a text film; absent = a web film (the URL rides material_urls). Never both in one call.",
    )
    verbatim: bool | None = Field(
        default=None,
        description="Only with text: true = the text is the user's own copy AND they asked for it preserved word for word (the system rejects any rewrite/reorder/trim/dropped line); false = you distilled or authored it from their brief. Judge it from the user's stated direction — never from the mere fact that text was pasted. Null reads as true.",
    )
    target_seconds: float | None = Field(
        default=None,
        description="Only with text: the user's named total duration in seconds (e.g. 20 for '做一个20秒视频'). On a redraft, OMIT to inherit the base duration; explicit null CLEARS it so the system paces the copy naturally; a number overrides it. A named duration is honored even when FASTER than the natural reading pace — it is the user's explicit choice (the presentation notes the readability impact); only a duration over the 120s render frame cap rejects.",
    )
    scene_count: int | None = Field(
        default=None,
        description="Only with text: the user's named scene count (e.g. 6 for '改成6幕') — the segmentation lands on exactly this count. On a redraft, OMIT to inherit the base count; explicit null CLEARS it so the director picks; a number overrides it.",
    )
    group_chars: list[int] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Only with text: the user's named ON-SCREEN GROUP size as [min, max] characters per screen ('一次只展示3-5个字' → [3, 5]) — each screen shows ONE group of the copy, the previous group leaving as the next enters; the words stay byte-exact (a citation line splits into pieces, never rewrites). Count: a CJK character or latin letter is 1; punctuation and spaces count 0 (punctuation rides its group, never a screen of its own). On a redraft, OMIT to inherit the base grouping; explicit null CLEARS it so the director paces whole screens itself; a [min, max] value overrides it.",
    )

    @model_validator(mode="after")
    def _group_chars_ordered(self) -> "DesignStoryboardArgs":
        if self.group_chars is not None:
            lo, hi = self.group_chars
            if not (1 <= lo <= hi):
                raise ValueError(
                    "group_chars is [min, max] with 1 <= min <= max"
                )
        return self
    edits: list[FilmEditOp] | None = Field(
        default=None,
        description=(
            "PATCH TOP-LEVEL CONTRACT: with a non-empty edits array, base_ref is "
            "required; review_hold and pending_disposition are the only optional "
            "top-level companions. Omit focus, language, voiceover, subtitles, music_mood, "
            "aspect, specific_instruction, material_urls, text, verbatim, "
            "target_seconds, scene_count and group_chars entirely — none of them "
            "expresses a targeted patch. Change speech with a set_voiceover op "
            "and music with a set_music op inside edits; there is no aspect edit "
            "op. Minimal legal patch shape (echo the real base_ref from the "
            "current-version read): {\"base_ref\":\"<exact base_ref from the "
            "read>\",\"edits\":[{\"op\":\"set_voiceover\",\"enabled\":false},"
            "{\"op\":\"update_scene\",\"scene_id\":\"s2\",\"copy_slots\":"
            "{\"lines\":[\"A talk can become an article,\",\"and spark a wider "
            "discussion.\"]}}]}. Targeted edits to the version you just read or "
            "presented (the patch path — a new version, never a silent overwrite): "
            "set_subtitles (create/replace a scene's independent subtitle_track; "
            "track=null deletes it; works on ui and every other scene type, "
            "without voiceover; read current track before replacing it), "
            "update_scene (one scene's view/seconds/focuses/narration/copy slots), "
            "update_element (ONE element inside a composite scene, addressed by "
            "scene_id + element_id — a text element's lines/tone/timing, "
            "placement/window/fit/z, a video element's source range/play "
            "window/keep_audio; fields not applying to the element's kind reject; "
            "an absent field keeps its value, explicit null restores its default; "
            "the cited asset itself never swaps), reorder_scenes (the full id "
            "permutation), remove_scene, set_music (mood + retime keep_cut|recut; "
            "mood 'off' switches the bed off for good), set_voiceover (enabled "
            "false = no spoken narration; enabled true = re-open synthesis of "
            "the board's OWN existing narration lines — a board with zero "
            "narration lines rejects, author the lines first). The system "
            "applies them atomically against the base version; a stale or "
            "fabricated base_ref, an empty-effect batch, or a violated "
            "constraint rejects the WHOLE batch with the reason. Omit for a "
            "first draft or an open feedback redraft."
        ),
    )
    base_ref: str | None = Field(
        default=None,
        description="Mandatory with edits: the read-time reference of the version these edits were formed against, echoed VERBATIM from the read (get_output_spec's film branch or the design beat's own reference line). It proves the world did not move since you read it — a mismatch rejects safely and tells you to re-read.",
    )
    specific_instruction: str | None = Field(
        default=None,
        description="THIS beat's new storyboard feedback ('重点讲社交功能') — a redraft trigger that revises the CURRENT board (what the feedback does not name stays); omit it when designing the first board.",
    )
    review_hold: bool | None = Field(
        default=None,
        description="True when the user scoped this to review only ('只看分镜，先别制作') — the hold then persists across turns until they explicitly ask for production after seeing the board; false releases a standing hold when the user explicitly asks for production. Omit = a fresh draft holds for review by default; a re-presentation of the same board keeps the stored hold. A work's FIRST board is the exception: it must always be presented and approved afterward, so neither false nor an opening direct-production delegation skips that first review.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="The site's URL when no captured page exists in the project yet (the direction stage ran as a discussion, or the design beat came first) — copy it verbatim from the conversation; the system captures it BEFORE drafting so the board is grounded.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — the question settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
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
    """The explicit revision base (§2.2): which work, which version, and the
    content identity read at design time. Echoed verbatim from the version's
    own presentation line or a get_video_version read."""

    model_config = ConfigDict(extra="forbid")

    composition_id: UUID
    composition_version_id: UUID
    content_digest: str = Field(min_length=64, max_length=64)


class DesignVideoArgs(BaseModel):
    """``design_video`` params (both paths). A website promo (a URL's
    captured pages) instantiates the launch-film skill's template; a text
    input (``text``) designs a free motion-graphics piece; video assets or
    delivered Outputs used as material design a mixed real-recording piece.
    ``composition_id`` + ``specific_instruction`` redraft an existing work's
    direction into a new child version."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "motion_graphics", "program", "image"] = Field(
        default="auto",
        description="Use program for Agent-authored drawing-v1 motion, image for one MiniMax image-01 still background, motion_graphics for native text/shapes; auto preserves the material-based default.",
    )
    scene_count: int | None = Field(default=None, ge=1, le=6, description="MG: exact scene count when the user names it.")
    target_seconds: float | None = Field(default=None, gt=0, le=118, description="MG: exact total duration when named.")
    aspect: Literal["16:9", "9:16", "1:1"] | None = Field(default=None, description="MG canvas aspect when named; absent = 16:9.")
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$",
        description="MG exact canvas background when named, e.g. black=#000000, white=#FFFFFF.")
    material_asset_ids: list[UUID] | None = Field(default=None, max_length=12,
        description="Owned source assets explicitly @referenced, including from another Chat. Video assets make a mixed recording composition; captured webpages make a website walkthrough.")
    material_output_ids: list[UUID] | None = Field(default=None, max_length=12,
        description="Delivered video Outputs explicitly used AS MATERIAL for a NEW mixed composition. Never use this to continue editing the original work; that path is revise_video with its saved base_ref.")
    music: Literal["off"] | None = Field(default=None,
        description='"off" ONLY when the user explicitly asks for no background music; absent = the default bed law (persona skin, then the calm catalog default).')
    narration: str | None = Field(
        default=None,
        max_length=9000,
        description="MG only: exact spoken copy to pace across scenes. Supplying it explicitly enables narration; the voice is resolved and pinned by code, never synthesized during design.",
    )
    narration_enabled: bool | None = Field(
        default=None,
        description="MG only: true ONLY when the user explicitly asks for spoken narration; false explicitly turns it off. Null inherits a redraft's setting and defaults a fresh design to off.",
    )

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(
            data,
            "focus",
            "language",
            "material_urls",
            "material_output_ids",
            "text",
            "specific_instruction",
            "composition_id",
            "pending_disposition",
            "music",
            "mode",
            "narration",
            "narration_enabled",
        )

    focus: str | None = Field(
        default=None,
        description="The agreed creative direction / emphasis steer for this design, in the user's words.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="Website promo only: the site's URL(s), copied verbatim from the conversation, when the project has no captured page for the site yet — the system captures BEFORE drafting so the storyboard is grounded in the real page. Omit when the project's captured pages already cover the site.",
    )
    text: str | None = Field(
        default=None,
        description="Motion-graphics video only (no webpage): the exact on-screen copy — the user's own words, or the copy you distilled from their brief. Present = an MG video; absent = a website promo. Never both in one call.",
    )
    language: str | None = Field(
        default=None,
        description="The video's language when one was agreed or named. Null = the material's own.",
    )
    composition_id: UUID | None = Field(
        default=None,
        description="Redraft only: the composition to redesign (from its storyboard card or a get_video_version read). Omit for a new work.",
    )
    specific_instruction: str | None = Field(
        default=None,
        description="Explicit requirements for this design: colors, timing, layout or open direction. With composition_id it redesigns that work; a named-element edit uses revise_video.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )

    @model_validator(mode="after")
    def _shape(self) -> "DesignVideoArgs":
        if self.material_urls and (self.material_asset_ids or self.material_output_ids):
            raise ValueError("name captured asset/output ids or new URLs, not both in one design")
        if self.text and (self.material_urls or self.material_asset_ids or self.material_output_ids):
            raise ValueError("text and media materials never mix — use an MG video or a media composition")
        if self.narration_enabled is False and self.narration is not None:
            raise ValueError("narration text and narration_enabled=false conflict")
        if (self.narration is not None or self.narration_enabled is True) and not self.text:
            raise ValueError("the first narration consumer is an MG design with exact on-screen text")
        if self.composition_id is None and self.narration_enabled and not self.narration:
            raise ValueError("a fresh narrated design needs the exact spoken copy")
        if self.mode in {"program", "image"} and (
            self.narration is not None or self.narration_enabled is True
        ):
            raise ValueError("narration currently belongs to the MG design path")
        if self.mode == "program":
            if self.composition_id is not None:
                raise ValueError("revise an existing GeneratorObject with revise_video, not a redraft")
            if self.material_urls or self.material_asset_ids or self.material_output_ids:
                raise ValueError("the first drawing-v1 program consumer takes no media materials")
            if not self.specific_instruction:
                raise ValueError("a visual program needs the requested picture in specific_instruction")
        if self.mode == "image":
            if self.composition_id is not None:
                raise ValueError("revise an existing GeneratorObject with revise_video, not a redraft")
            if self.material_urls or self.material_asset_ids or self.material_output_ids:
                raise ValueError("the first image-v1 consumer takes no media materials")
            if not self.specific_instruction:
                raise ValueError("a generated image needs the requested picture in specific_instruction")
            if self.aspect not in (None, "16:9"):
                raise ValueError("the first image-v1 consumer supports a 16:9 background")
        if self.mode == "motion_graphics" and not self.text:
            raise ValueError("native motion graphics needs exact on-screen text")
        if len(self.material_asset_ids or []) + len(self.material_output_ids or []) > 12:
            raise ValueError("a design accepts at most 12 referenced media items")
        if self.composition_id is not None and not self.specific_instruction and not self.focus:
            raise ValueError(
                "a redraft needs the new direction: specific_instruction "
                "(open feedback) or focus"
            )
        return self


class ReviewVideoArgs(BaseModel):
    """Review one exact delivered Output against the user's stated requirements."""

    model_config = ConfigDict(extra="forbid")

    output_id: UUID = Field(
        description="Exact delivered video Output id from its card or @output mention; never the composition's latest Output by implication."
    )
    requirements: str = Field(
        min_length=1,
        max_length=4000,
        description="The relevant user requirements, copied faithfully from the current request and conversation; never a prewritten review conclusion.",
    )
    at_seconds: list[float] | None = Field(
        default=None,
        max_length=4,
        description="Specific actual Output times to inspect; when present these times define the sample, especially for rechecking an earlier finding."
    )
    refresh: bool = Field(
        default=False,
        description="True to decode and review again; false reuses this exact Output's saved report when one exists. A new Output always needs its own review."
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "at_seconds", "refresh", "pending_disposition")


class VideoEditUpdateText(BaseModel):
    """Replace one text clip's copy (and optionally its style knobs). The
    clip_id comes from the storyboard read; fields absent keep their values."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_text"]
    clip_id: str = Field(min_length=1)
    text: str | None = None
    font_size: int | None = Field(default=None, gt=0, le=400)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    background: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="Explicit null clears the chip background; absent keeps it.",
    )
    align: Literal["left", "center", "right"] | None = None
    weight: Literal[400, 500, 600, 700, 800] | None = None
    x: float | None = Field(default=None, description="Text box left edge in canvas pixels; absent keeps it.")
    y: float | None = Field(default=None, description="Text box top edge in canvas pixels; absent keeps it.")
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)


class VideoEditUpdateSpeech(BaseModel):
    """Revise one SpeechObject without moving its reviewed output window."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_speech"]
    clip_id: str = Field(min_length=1)
    text: str | None = Field(default=None, min_length=1, max_length=9000)
    voice_id: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    gain_db: float | None = Field(default=None, ge=-60, le=12)


class VideoEditSyncCaptions(BaseModel):
    """Explicitly replace captions linked to one SpeechClip with its current text."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["sync_captions"]
    clip_id: str = Field(min_length=1, description="The SpeechClip id from the storyboard read.")


class VideoEditAddText(BaseModel):
    """Add one text clip inside a named scene's window (a new title/caption
    beat). The system owns the layout for the chosen track role."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add_text"]
    scene_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    track: Literal["title", "caption"] = "caption"
    at_seconds: float | None = Field(
        default=None, ge=0, description="Start inside the scene; absent = the scene's start."
    )
    duration_seconds: float | None = Field(
        default=None, gt=0, description="How long it shows; absent = to the scene's end."
    )
    size: Literal["small", "medium", "large"] = "medium"
    align: Literal["left", "center", "right"] = "center"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class VideoEditRemoveClip(BaseModel):
    """Remove one exact clip and its transition links; other clips stay intact."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_clip"]
    clip_id: str = Field(min_length=1)


class VideoEditUpdateVideo(BaseModel):
    """Adjust one VideoObject or its source window without touching other layers."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_video"]
    clip_id: str = Field(min_length=1)
    snapshot_id: UUID | None = Field(default=None, description="Another snapshot ALREADY BOUND to this version; absent keeps the current source.")
    source_start_seconds: float | None = Field(default=None, ge=0)
    source_end_seconds: float | None = Field(default=None, gt=0)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    scale: float | None = Field(default=None, gt=0, le=10)
    fit: Literal["cover", "contain"] | None = None
    gain_db: float | None = Field(default=None, ge=-60, le=12)
    muted: bool | None = None


class VideoEditSplitClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["split_clip"]
    clip_id: str
    at_seconds: float = Field(gt=0, description="Absolute output time; linked media follows the split.")


class VideoEditTrimClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["trim_clip"]
    clip_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0, description="Keep this output subrange; no ripple of other clips.")


class VideoEditTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_transition"]
    from_clip_id: str
    to_clip_id: str
    duration_seconds: float = Field(gt=0)
    kind: Literal["crossfade"] = "crossfade"


class VideoEditRemoveTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_transition"]
    transition_id: str


class VideoEditSnapCut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["snap_cut"]
    from_clip_id: str
    to_clip_id: str
    music_clip_id: str
    tolerance_seconds: float = Field(
        default=0.2, gt=0, le=1,
        description="Maximum cut shift in seconds: greater than zero, at most 1; defaults to 0.2.",
    )


class VideoEditFocusWeb(BaseModel):
    """Recompute one webpage clip's camera from a frozen element id.

    The server owns all coordinates and keyframe numbers; a revision never
    asks the model to transcribe camera math.
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal["focus_web"]
    clip_id: str = Field(min_length=1)
    element_id: str = Field(min_length=1)


class VideoEditUpdateShape(BaseModel):
    """Adjust one native shape without turning its geometry into baked media."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_shape"]
    clip_id: str = Field(min_length=1)
    shape: Literal["rect", "ellipse", "path"] | None = None
    fill: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float | None = Field(default=None, ge=0, le=200)
    corner_radius: float | None = Field(default=None, ge=0, le=1000)
    path: str | None = Field(default=None, max_length=4096)
    opacity: float | None = Field(default=None, ge=0, le=1)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    scale: float | None = Field(default=None, gt=0, le=10)
    rotation: float | None = None


class VideoEditUpdateGenerator(BaseModel):
    """Rewrite a visual program or model-image request, or adjust external layout."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_generator"]
    clip_id: str = Field(min_length=1)
    code: str | None = Field(default=None, min_length=1, max_length=24000)
    prompt: str | None = Field(default=None, min_length=1, max_length=2000)
    parameters: dict[str, str | float | bool] | None = Field(default=None, max_length=24)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    scale: float | None = Field(default=None, gt=0, le=10)
    fit: Literal["cover", "contain"] | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)


class VideoEditKeyframe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_seconds: float = Field(ge=0, description="Clip-local time of this keyframe.")
    value: float | list[float] = Field(description="Scalar, or [x, y] for transform.position.")
    easing: Literal["linear", "hold", "ease_out"] = "linear"


class VideoEditUpdateAnimation(BaseModel):
    """Replace one existing animation's keyframes (the target object and
    animated property never move — a different property is a different
    animation). The animation_id comes from the storyboard read."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_animation"]
    animation_id: str = Field(min_length=1)
    keyframes: list[VideoEditKeyframe] = Field(min_length=1)


class VideoEditMoveScene(BaseModel):
    """Move one scene (and everything belonging to it) to a new start time."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["move_scene"]
    scene_id: str = Field(min_length=1)
    start_seconds: float = Field(ge=0)


class VideoEditRemoveScene(BaseModel):
    """Remove one scene and the content belonging to it."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_scene"]
    scene_id: str = Field(min_length=1)


class VideoEditBackground(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_background"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$", description="Exact canvas background, e.g. black=#000000.")


VideoEditOp = Annotated[
    VideoEditUpdateText
    | VideoEditUpdateSpeech
    | VideoEditSyncCaptions
    | VideoEditAddText
    | VideoEditRemoveClip
    | VideoEditUpdateVideo
    | VideoEditSplitClip
    | VideoEditTrimClip
    | VideoEditTransition
    | VideoEditRemoveTransition
    | VideoEditSnapCut
    | VideoEditFocusWeb
    | VideoEditUpdateShape
    | VideoEditUpdateGenerator
    | VideoEditUpdateAnimation
    | VideoEditMoveScene
    | VideoEditRemoveScene
    | VideoEditBackground,
    Field(discriminator="op"),
]


class ReviseVideoArgs(BaseModel):
    """``revise_video`` params (both paths): targeted edits against an
    explicitly-named base version. The system applies the batch atomically
    through the content write door and returns the computed change set plus
    the new version's canonical storyboard."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "visual_descriptions", "pending_disposition")

    base_ref: VideoVersionRef
    edits: list[VideoEditOp] = Field(min_length=1)
    visual_descriptions: list[dict[str, str]] | None = Field(
        default=None,
        description=(
            "For every scene whose VISUAL content your edits changed: the "
            "rewritten user-readable 'what the viewer sees' summary of the "
            "scene's CURRENT content ([{scene_id, text}]) — the edit clears "
            "the stale one; leave a scene out only when its picture did not "
            "change. Never describe elements that are not in the version."
        ),
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )


class GetVideoVersionParams(BaseModel):
    """``get_video_version`` params — the explicit version read (§2.2)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "version_id", "composition_id", "output_id", "present")

    version_id: UUID | None = Field(
        default=None, description="Read this exact version (from a storyboard card or a previous read)."
    )
    composition_id: UUID | None = Field(
        default=None, description="Read the CURRENT version of this work."
    )
    output_id: UUID | None = Field(
        default=None, description="Resolve an owned @output to the EXACT version it delivered, across Chats."
    )
    present: bool = Field(default=False, description="Show this saved version's canonical storyboard card again for review/recovery.")

    @model_validator(mode="after")
    def _one_address(self) -> "GetVideoVersionParams":
        if sum(v is not None for v in (self.version_id, self.composition_id, self.output_id)) != 1:
            raise ValueError("name exactly one of version_id / composition_id / output_id")
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
        description="The option row's text — user-voice, a complete short instruction they would plausibly type, interface language, ≤40 chars.",
    )
    description: str = Field(
        default="",
        description="One short line: why this option — the conclusion the user can judge, never your reasoning process.",
    )
    recommended: bool = Field(
        default=False,
        description="True on the ONE option you recommend (at most one across the list) — the same lean your speech's verdict named (one judgment, one voice).",
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
    """``start_run`` params, plan path — start the confirmed plan's run."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "skip_storyboard_review")

    # RETIRED: the film storyboard presents at the design beat (a plain
    # design_storyboard message), so no review gate remains to waive. The
    # field stays so cached tool calls keep validating (extra="forbid");
    # the value is accepted and IGNORED, never consulted.
    skip_storyboard_review: bool = False


class PlanAnswerArgs(BaseModel):
    """``answer`` params, plan path — a purely informational reply. The
    answer text itself is your spoken message; the envelope seats ride here."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return _drop_bad_brief(tolerate_null_keys(data, "material_text", "material_urls", "pending_disposition"))

    brief: Brief | None = Field(
        default=None,
        description="Brief updates this turn, if any (same rules as the other tools).",
    )
    material_text: str | None = Field(
        default=None,
        description="Verbatim source text the user explicitly declared as their own material this turn. Null otherwise.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="URLs the user's own message offers as MATERIAL to work from (a page they paste so you can make something of it — 'make a short film of https://…'). Copy each URL verbatim; the system captures the page into a project asset itself. A link shared only for discussion ('what do you think of this site?') is NOT material — leave it out. Null otherwise.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — the question settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
    )


class ProposeTasksArgs(BaseModel):
    """``propose_tasks`` params, chat path (TaskListProposal minus summary —
    the proposal's summary is your spoken message). Empty tasks = the legal
    ask-back read, but prefer ask_user when one question decides it."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "tasks", "name", "specific_instruction", "material_urls", "pending_disposition", "production_intent")

    tasks: list[TaskItem] = Field(
        default_factory=list,
        description="The proposed tool chain — one task per piece of work, in execution order.",
    )
    material_urls: list[str] | None = Field(
        default=None,
        description="URLs the user's own message offers as MATERIAL to work from (a page they paste so you can make something of it — 'make a short film of https://…'). Copy each URL verbatim; the system captures the page into a project asset itself. A link shared only for discussion is NOT material — leave it out. Null otherwise.",
    )
    specific_instruction: str | None = Field(
        default=None,
        description=(
            "A short distilled EXTRA instruction for the generator — only "
            "constraints or focus NOT already expressed by the task params; "
            "never restate the requested work itself. Omit when nothing "
            "extra remains."
        ),
    )
    name: str = Field(
        default="",
        description="A compact noun phrase (2-6 words, interface language) naming the run's deliverable. Name the work, never the tools.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
    )
    production_intent: bool | None = Field(
        default=None,
        description=(
            "Does the user's message ask for this work to be MADE now? "
            "True only for an explicit production request or delegation "
            "('按这版制作' / 'go ahead' / '直接做，细节你决定'); false for a "
            "pure modification, a review-only ask ('先给我看方案'), or a "
            "discussion. The user's auto/ask settings only waive approval "
            "beats — they never turn a message without a production "
            "request into one: a plan docked without it waits for the "
            "user's word (the card keeps its start button). A film "
            "storyboard design/revision is the family exception: without "
            "current production intent it closes through answer after the "
            "full presentation, not through a production dock. Never omit "
            "this judgment."
        ),
    )


class EditGraphArgs(BaseModel):
    """``edit_graph`` params, chat path (WiringProposal minus summary):
    revise the persistent graph — a revision inside the already-confirmed
    work re-fills the affected subgraph directly; one that adds new paid
    work docks for the user's confirmation instead, it does not run. ``ops``
    stays loose dicts — adjudication is ``apply_wiring_ops``'s (op shape /
    references / ports / cycles), whose own errors feed back as the
    rejection echo."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "ops", "name", "pending_disposition", "production_intent")

    ops: list[dict] = Field(
        default_factory=list,
        description="Wiring ops in the registry vocabulary: add_node / connect / edit_prompt / delete_node / run.",
    )
    name: str = Field(
        default="",
        description="A compact noun phrase (2-6 words, interface language) naming the revision run's deliverable.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="Pending-question settlement for this turn: 'answer' = the message ENGAGES the question (answers it, hands the choice back to you, or discusses its options) and it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )
    production_intent: bool | None = Field(
        default=None,
        description=(
            "Does the user's message ask for this work to be MADE now? "
            "True only for an explicit production request or delegation "
            "('按这版制作' / 'go ahead' / '直接做，细节你决定'); false for a "
            "pure modification, a review-only ask ('先给我看方案'), or a "
            "discussion. The user's auto/ask settings only waive approval "
            "beats — they never turn a message without a production "
            "request into one: a plan docked without it waits for the "
            "user's word (the card keeps its start button). Never omit "
            "this judgment."
        ),
    )


class ChatAskArgs(BaseModel):
    """``ask_user`` params, chat path — the same one-question shape as the
    plan path minus the brief slot (post-run questions never backfill a
    brief)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "options", "default_path", "recommended_id", "pending_disposition")

    question: str = Field(
        description="The ONE question, in the interface language — the bare question, no framing, no default-path tail."
    )
    options: list[Option] = Field(
        default_factory=list,
        description="3 concrete one-word values (2 only for a genuinely binary choice) sourced from the user's persona/context, translated into the interface language. Each carries its one-line reason (description). Empty only for a freeform ask.",
    )
    allow_freeform: bool = True
    recommended_id: str | None = Field(
        default=None,
        description="The ONE option id you recommend (at most one) — your judgment rides the card, and your spoken message leans toward the same pick (one judgment, one voice). Null = no recommendation.",
    )
    default_path: str = Field(
        default="",
        description="One short clause: what you will do if the user skips. The skip must be safe.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="When the context shows a pending question: 'answer' = this message ENGAGES it (answers it, hands the choice back to you, or discusses its options) — it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection (the question stays pending).",
    )


class ChatAnswerArgs(BaseModel):
    """``answer`` params, chat path (AnswerProposal minus text — the answer
    IS your spoken message). The pending-question disposition rides here."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "pending_disposition")

    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="Pending-question settlement for this turn: 'answer' = the message ENGAGES the question (answers it, hands the choice back to you, or discusses its options) and it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )


class RetryUploadArgs(BaseModel):
    """``retry_upload`` params: recover a finished render whose upload failed."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "output_id", "pending_disposition")

    output_id: UUID | None = Field(
        default=None,
        description="The @output pin's definite id. Omit it when the latest failed run has exactly one upload failure; the system resolves that output. Never invent an id.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="Pending-question settlement for this turn: 'answer' = the message ENGAGES it (answers it, hands the choice back to you, or discusses its options) and it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )


class ReviseOutputTarget(BaseModel):
    """``revise_output``'s pointing (iter-3 S3, E4): the user's OWN pointing
    words ride verbatim — ``plan_ref`` relays the ordinal / plan_id
    ("2", "plan 2", the id from get_pending_plan); ``output_id`` is the
    @output pin's definite id. One or the other; both empty = the target is
    unclear (ask, never guess)."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)
    # coerce_numbers_to_str (2026-09-23, prompt_gate probe G 实测): the
    # provider emits the ordinal as a bare NUMBER ('plan 2' → plan_ref: 2)
    # and never recovers from the strict-string rejection — the pointing
    # words are the user's, so the schema absorbs the dialect (顺形律).

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "plan_ref", "output_id")

    plan_ref: str | None = Field(
        default=None,
        description=(
            "The user's pointing words for the plan, verbatim — an ordinal "
            "('2', 'plan 2') or a plan_id. Relay, never resolve it yourself."
        ),
    )
    output_id: UUID | None = Field(
        default=None,
        description="The pinned output's id (an @output mention) — the definite reference.",
    )


class ReviseOutputArgs(BaseModel):
    """``revise_output`` params, chat path (iter-3 S3, ADR-089 §6 修订二分律):
    the CRAFT-level revision verb — the how inside the paid envelope
    ('plan 2 的字幕太长了', 'make the hook sharper'), never the what
    (a plan's deliverables change = revise_plan). The system routes the
    pointing to the confirmed scope's node set (R20), rewrites the affected
    programs with the instruction, and the scope classifier decides: inside
    the confirmed scope it reruns directly; new paid work re-docks as a
    mini decision package."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "target", "instruction", "pending_disposition")

    target: ReviseOutputTarget = Field(
        default_factory=ReviseOutputTarget,
        description="What the revision points at — plan_ref XOR output_id.",
    )
    instruction: str = Field(
        default="",
        description="The user's change ask, restated in one compact line (what changes about the work).",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="Pending-question settlement for this turn: 'answer' = the message ENGAGES the question (answers it, hands the choice back to you, or discusses its options) and it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )


class EditOutputParams(BaseModel):
    """``edit_output``'s product-semantics params (ADR-090, E2): one kind
    consumes exactly one key — the code pairs them (多给/缺给 = 域拒绝).
    NO timestamps, no ids, no op internals: the quote is the user's words,
    the seconds a plain count, the style a preset enum name."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    quote: str | None = Field(
        default=None,
        description="remove_range: the words to cut, quoted verbatim from the user or the captions.",
    )
    seconds: float | None = Field(
        default=None,
        description="set_trim: how many seconds to take OFF the clip's end (a positive count).",
    )
    style: str | None = Field(
        default=None,
        description="set_caption_style: a preset name from list_caption_styles (enum only, never free-form).",
    )
    title: str | None = Field(
        default=None,
        description="set_title: the new title text, verbatim.",
    )


# The precise edit's param→verb decode table (ADR-090 E2; edit_ops.KIND_PARAMS
# is the same law's forward direction — a pure test pins the bijection).
_EDIT_KIND_BY_PARAM = {
    "quote": "remove_range",
    "seconds": "set_trim",
    "style": "set_caption_style",
    "title": "set_title",
}


def edit_kind_for_params(params: "EditOutputParams") -> str | None:
    """The verb decode (ADR-090 E2, 顺形律 — probe H 实测 2026-09-24; Final
    Hardening B1: the ONLY kind source). Exactly one filled param determines
    the kind; zero or 2+ filled carries no verb → None → the pairing law's
    domain refusal rides the loop (never a guess). There is no ``kind``
    field: the verb is expressed purely through WHICH param is filled, so
    schema and production dispatch can never disagree."""
    filled = [
        k
        for k, v in params.model_dump(mode="python").items()
        if v is not None and str(v).strip() != ""
    ]
    if len(filled) == 1:
        return _EDIT_KIND_BY_PARAM.get(filled[0])
    return None


class EditOutputArgs(BaseModel):
    """``edit_output`` params, chat path (ADR-090 §1/§4): the PRECISE edit
    verb — a mechanically executable change to an already-produced clip
    ('delete this line' / '3 seconds shorter' / 'captions to karaoke' /
    'retitle to X'). The verb is carried by WHICH one param is filled
    (``edit_kind_for_params`` — the schema deliberately has no ``kind``
    field; the loop strips stray naming keys anyway); the system resolves
    the quote to seconds, journals the op, and re-renders. An open-ended
    craft ask goes to revise_output; when the change is not mechanically
    specifiable, ask — never guess."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "target", "params", "pending_disposition")

    target: ReviseOutputTarget = Field(
        default_factory=ReviseOutputTarget,
        description="What the edit points at — the @output pin (output_id) XOR the plan ordinal (plan_ref relayed verbatim).",
    )
    params: EditOutputParams = Field(default_factory=EditOutputParams)
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description="Pending-question settlement for this turn: 'answer' = the message ENGAGES the question (answers it, hands the choice back to you, or discusses its options) and it settles with the user's own words verbatim; 'skip' = an explicit decline; 'none' = a clearly unrelated interjection.",
    )


# ---- 触发回合 (T3, ADR-077 判词③) — the proactive turn's terminal --------
# (SuggestionItem lives beside the answer args above — two seats, one shape.)


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
        description="0-3 next-step options grounded in what you actually read — each a user-voice label (≤40 chars) with its one-line reason, the ONE you recommend marked. Never a generic checklist.",
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
    """One LLM-proposed task: a registry tool plus its params (CHAT_ARCH §3).

    The LLM proposes; ``compile_graph`` adjudicates existence, params and
    topology against ``app/tools/__init__.py`` — the LLM never writes node specs.
    """

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
    ``context.persona``; the brand block bakes into the clip-spec.
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


class SourceSpan(BaseModel):
    """A timeline span of one source asset (iter-2 ②, N-57): the writer's
    material narrows to this range instead of the whole talk.

    Compiler-set on plan-sourced chains (the exploration world resolved the
    Select's evidence range at the door); ``asset_id`` pins the asset
    deterministically (the compile knows the candidate set's asset), None
    = resolve to the project's timeline-carrying asset.
    """

    model_config = ConfigDict(extra="forbid")

    start: float
    end: float
    asset_id: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "SourceSpan":
        if not self.start < self.end:
            raise ValueError(f"source_span start ({self.start}) must be < end ({self.end})")
        return self


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
    # Film-family slots (launch_film): spoken narration / independent visible
    # subtitles / BGM mood / canvas aspect — None = plan default.
    voiceover: bool | None = None
    subtitles: bool | None = None
    music_mood: str | None = None
    aspect: str | None = None
    # Text-source films (ADR-138 §7.6): the copy + its role + the user's
    # named shape. None = a web-source film (the keys stay out).
    text: str | None = None
    verbatim: bool | None = None
    target_seconds: float | None = None
    scene_count: int | None = None
    group_chars: list[int] | None = None  # [min, max] 字 per screen
    # iter-2 ② (N-57): the writer's source narrowing — compiler-emitted on
    # plan-sourced chains, None on every existing path (the whole material).
    source_span: SourceSpan | None = None
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


_SLOT_TO_TOOL = {
    # Legacy outputs-grammar slot type → its producing tool (ADR-043 read
    # tolerance for stored pending_brief rows — never written).
    "clips": "select_clips",
    "post": "write_post",
    "quotes": "write_quotes",
    "carousel": "write_carousel",
    "article": "write_article",
}


def _legacy_slots_to_tasks(data: dict) -> list[dict]:
    """outputs-grammar plan → task list (ADR-043): each slot becomes its
    producing tool's task (slot fields sink to params — params models ignore
    stray keys at adjudication); the retired plan-level modifiers fan out
    into per-language transform tasks; a plan-level aspect rides the clips
    task. Read tolerance only — new writes are born as task lists."""
    tasks: list[dict] = []
    aspect = data.get("aspect")
    for slot in data.get("outputs") or []:
        if isinstance(slot, str):
            slot = {"type": slot}
        if not isinstance(slot, dict):
            continue
        tool = _SLOT_TO_TOOL.get(slot.get("type"))
        if tool is None:
            continue
        params = {
            k: slot[k]
            for k in ("count", "focus", "language", "tone_override")
            if slot.get(k) is not None
        }
        if tool == "select_clips" and aspect:
            params["aspect"] = aspect
        tasks.append({"tool": tool, "params": params})
    for lang in data.get("dub_languages") or []:
        # fork: the slots-era compile produced dub/translate as fork nodes
        # (derived rows, source untouched) — the upgrade keeps that shape.
        tasks.append(
            {"tool": "dub_clip", "params": {"target_language": lang, "fork": True}}
        )
    bilingual = bool(data.get("caption_bilingual"))
    for lang in data.get("caption_languages") or []:
        tasks.append(
            {
                "tool": "translate_clip",
                "params": {
                    "target_language": lang,
                    "bilingual": bilingual,
                    "fork": True,
                },
            }
        )
    return tasks


# ---------------------------------------------------------------------------
# brief（DIALOG_WORKFLOW §2.4, ADR-052 B2): the dialog engine's structured
# state. Five slots, each with provenance; the intent router proposes a full
# update every plan turn and code merges by source precedence (merge_brief —
# LLM proposes, code decides; user-stated is never reverse-overwritten).
# ---------------------------------------------------------------------------


class BriefSlotSource(StrEnum):
    """Provenance of one brief slot's value (merge precedence: stated > inferred > default)."""

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
    """The brief: five slots + code-owned bookkeeping.

    topic / audience / tone / constraints are the askable slots — the ask
    strategy (一轮一问决定槽) targets the one whose answer most decides
    quality. ``material_state`` is code-stamped at write time (assets with
    files → attached; pasted text material → pasted; else none) — the router
    READS it in the brief block for the root judgment, never proposes it.

    顺形律 (2026-09-11，ADR-064): ``constraints`` = 来源化条目的**数组**
    (``list[BriefSlot[str]]``)，不是对象包数组——实测（M3 十七次复跑 +
    tool-calling spike 六次）模型的第一直觉写法恒为对象数组，「对象包数组」
    形状曾造成 schema 两连败杀死整回合。schema 顺着模型的自然写法设计；
    读容忍只兜底存量/跑偏形状，不承担正典形状的分歧。

    ADR-071 ⑤ signpost (2026-09-11): the model-facing brief spec (which
    slots exist, emit-only-what-you-have-a-view-on, source precedence
    user-stated > inferred > default) lives in
    ``app/prompts/chat/intent_router_system.j2``'s brief rule — the schema
    never reaches the model (json_object response format, parse-side only).
    Edit the template first, then sync this mirror.
    """

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
    constraints: list[BriefSlot[str]] = Field(default_factory=list)
    material_state: BriefSlot[MaterialState] = Field(default_factory=BriefSlot)
    # Code-owned roll of the slots already asked once this plan phase (一轮
    # 一问决定槽， bounded: each slot asks at most once — the second rootless
    # call docks the draft-from-persona plan instead). merge_brief never
    # reads it from the LLM's proposal (禁 LLM 簿记); code stamps it when the
    # question docks.
    asked: list[str] = Field(default_factory=list)


class InferredIntent(BaseModel):
    """The intent router's payload: four actions + the proposed tool chain.

    ADR-043 (outputs → derive): the request layer carries NO output
    declarations — ``tasks`` is the only grammar (a registry tool + its
    params, the same shape the chat loop's task_list proposals use). Outputs
    are a derived projection of the compiled graph, never a request field.

    ADR-052 B2 (action set): ``draft`` drafts/refines the plan (it never
    generates — the retired ``generate`` name lied); ``ask`` asks ONE
    question through the dock's ask_user machinery (the shared
    QuestionProposal shape, 案 A 双实例); ``answer`` is a purely
    informational reply;
    ``start`` confirms the docked plan.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_legacy_shape(cls, data: Any) -> Any:
        """Upgrade stored legacy plans on read (never written): the pre-slot
        flat shape → slots, the slots/modifiers grammar → a task list; the
        retired keys (outputs / tone / the four plan-level modifiers) are
        stripped. Read tolerance for stored ``pending_brief`` rows only."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # An explicit ``tasks: null`` (the LLM's habit on start/answer
        # calls) reads as "no opinion" — dropping the key lets the field
        # default apply instead of failing validation.
        if data.get("tasks") is None:
            data.pop("tasks", None)
        # Same null tolerance for ``name`` (ADR-058 — the LLM writes null on
        # start/ask/answer calls; 打字机律牙①: a rejection costs the
        # funnel's repair round, which never streams).
        if data.get("name") is None:
            data.pop("name", None)
        # Same null tolerance for ``tasks_explicit`` (2026-09-09 实测: ask
        # calls habitually write null here — three repair rounds observed
        # in one day, each costing ~15s and diverging the stream from the
        # envelope; an ask has no tasks to be explicit about, so the False
        # default is the honest read).
        if data.get("tasks_explicit") is None:
            data.pop("tasks_explicit", None)
        # 2026-08-05 restructure leftover: legacy stored plans carry
        # plan-level ``language`` / ``language_explicit`` — strip on read.
        for retired in ("language", "language_explicit"):
            data.pop(retired, None)
        outputs = data.get("outputs")
        if isinstance(outputs, list) and any(isinstance(o, str) for o in outputs):
            # Pre-slot flat shape → slot dicts (the retired flat counts ride).
            flat_counts = {
                "clips": data.get("clip_count"),
                "quotes": data.get("quotes_count"),
                "carousel": data.get("carousel_count"),
            }
            data["outputs"] = [
                {"type": o, "count": flat_counts.get(o)} if isinstance(o, str) else o
                for o in outputs
            ]
        if "tasks" not in data and isinstance(data.get("outputs"), list):
            tasks = _legacy_slots_to_tasks(data)
            if tasks:
                data["tasks"] = tasks
                data["tasks_explicit"] = bool(data.get("outputs_explicit"))
        for retired in (
            "outputs",
            "tone",
            "dub_languages",
            "caption_languages",
            "caption_bilingual",
            "aspect",
            "outputs_explicit",
            "clip_count",
            "quotes_count",
            "carousel_count",
            "clip_count_explicit",
        ):
            data.pop(retired, None)
        # 校验分层律 (2026-09-11, ADR-064): the brief is ADVISORY
        # bookkeeping — after its own shape normalization it still fails to
        # parse, drop the field and let the turn live (the critical payload
        # — action / tasks / answer / ask / name, the things that drive a
        # paid run — stays strict above). Losing one brief update is
        # harmless: the next turn re-proposes, and the raw messages are
        # still there. The drop is logged, never silent.
        brief = data.get("brief")
        if brief is not None:
            try:
                Brief.model_validate(brief)
            except Exception:
                logger.warning(
                    "brief_dropped",
                    brief=json.dumps(brief, default=str)[:500],
                )
                data["brief"] = None
        return data

    action: Literal["ask", "draft", "answer", "start"] = Field(
        default="draft",
        description=(
            "Whether the user wants content drafted ('draft' — build/refine "
            "the plan), is asking a question about the tool's "
            "capabilities ('answer'), is confirming the proposed plan "
            "('start' — a prose 'looks good, go ahead' in the confirm "
            "phase, not a revision), or one missing answer most decides "
            "quality and you must ask first ('ask')."
        ),
    )
    ask: QuestionProposal | None = Field(
        default=None,
        description=(
            "The ONE question when action is 'ask' — the shared question "
            "shape (3 one-word options — 2 only for a genuinely binary "
            "choice — + freeform). Null for every other action."
        ),
    )
    answer: str | None = Field(
        default=None,
        description=(
            "The user-facing reply: the direct answer when action is "
            "'answer'; the plan-introducing echo prose when action is "
            "'draft'. Null for 'start' and 'ask'."
        ),
    )
    material_text: str | None = Field(
        default=None,
        description=(
            "Verbatim source text the user explicitly declared as their own "
            "material ('this is my transcript: …', '这是我的文字稿：…'). Null "
            "when the user did not declare pasted text as source material — "
            "a bare request is never material. Null for action='start'/'ask'."
        ),
    )
    tasks: list[TaskItem] = Field(
        default_factory=list,
        description=(
            "The proposed tool chain — one task per piece of work, in "
            "execution order (e.g. an English and a German post = two "
            "write_post tasks; whole-video bilingual subtitles = one "
            "translate_clip task). Empty for start/answer/ask calls."
        ),
    )
    specific_instruction: str | None = Field(
        default=None,
        description="Free-form instruction distilled from the prompt. Null for 'answer'/'start'/'ask'.",
    )
    # No consumers anywhere (verified 2026-09-11, ADR-071) — kept on the
    # schema for read tolerance (the model may still emit it); the prompts
    # no longer ask for it. Delete on the next schema-breaking batch.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tasks_explicit: bool = Field(
        default=False,
        description=(
            "True when the user explicitly named the work themselves. "
            "False when the chain is the default proposal."
        ),
    )
    # Caption mode for runs that produce captioned video (Phase 1, 2026-08-25):
    # quote-cards' write_quotes task asks the user via chat which caption mode
    # they want — bilingual is the canonical default (matches the recipe's
    # example prompt), source_only / target_only honour a single-language pick.
    # None = chat should dock the question; a value = the answer has been
    # recorded and lands in run.context.caption_mode at the run birthplace.
    caption_mode: Literal["bilingual", "source_only", "target_only"] | None = Field(
        default=None,
        description=(
            "Caption mode for captioned-video runs (write_quotes / future "
            "caption-bearing recipes). None = chat should ask the user. "
            "Bilingual = original + target language side-by-side; "
            "source_only = original language only; target_only = the run's "
            "target language only."
        ),
    )
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
    # resumes (the dock handshake, same pattern as the caption_mode_ prefix).
    # None on every question that is not a brief ask (caption mode, direction
    # interrupts, post-run shape C). ADR-078 判词④ adds ``asset_role``: the
    # 角色消歧 dock ask — its options are code-built (id = asset id) and its
    # answer settles the PendingPlan source/exemplar pins by code, never by
    # LLM re-interpretation. ``default_path`` is the schema tooth of
    # 提问策略 ③: what happens when the user skips — the framing prose
    # (``content``) carries it visibly; the field keeps it machine-readable
    # for the dock's × and the interjection reminder tail.
    slot: Literal["topic", "audience", "tone", "asset_role"] | None = None
    default_path: str = ""
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
    # task_book only, server-stamped: the dock echo's content carries the
    # film storyboard's code-rendered markdown. On refresh the row's content
    # replays as a flow message while the dock revives separately. Absent on
    # legacy / non-film rows (读容忍 — reads False).
    storyboard_echo: bool = False
    # task_book only, film chains (ADR-129): the draft token of the
    # storyboard version this dock presents. A newer design beat mints a new
    # token, and the start gate rejects this row's Start as stale (旧 Start
    # 失效, nothing deleted). Absent on non-film and pre-version rows
    # (读容忍: the gate then falls back to the fingerprint comparison).
    film_draft_token: str | None = None
    # The presented version stamped with the draft token. Start compares
    # both — token binds the draft identity, version makes the compared
    # revision explicit. Absent on legacy rows (读容忍).
    film_storyboard_version: int | None = None


class PendingPlan(BaseModel):
    """Unconfirmed plan persisted on ``projects.pending_brief``.

    Written by the chat plan path on draft-action turns (an
    answer-action turn never overwrites the stored plan), cleared once the
    run starts. Lets a user who left the plan-confirmation chat resume it
    exactly, from any device. Ask-action turns write a brief-only row
    (``intent=None``): the merged brief persists while the ONE question is
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
    # The docked film storyboard handoff (internal, never user-facing
    # structure): the RESOLVED FilmStoryboard dump whose code-rendered
    # markdown rode the dock echo — Start stamps it onto run.context so the
    # run consumes exactly the storyboard the user last saw (the node
    # revalidates against the current pages). ``film_storyboard_fingerprint``
    # is the dock seat's reuse key (launch_film params + the instruction —
    # a revision that moves either redrafts; anything else reuses). None on
    # non-film / pre-storyboard rows (读容忍).
    film_storyboard: dict | None = None
    film_storyboard_fingerprint: str | None = None
    # 版本化分镜状态 (ADR-129, film 旅程闭环 Batch 1): the presented board is
    # a VERSIONED draft — every field below is stamped by the design beat
    # (design_storyboard) and only READ by the dock / start / worker seats
    # (禁 dock 期重起草). All read-tolerant: None/absent on legacy rows.
    #
    # ``film_storyboard_version``: 1 on the first presented board, +1 per
    # redraft; a reuse (same fingerprint, no fresh feedback) keeps it.
    film_storyboard_version: int | None = None
    # The design params that produced the current version (focus / language /
    # voiceover / subtitles / music_mood / aspect as named — nulls preserved): the dock
    # seats rewrite the launch_film task's params from THIS, so the confirmed
    # chain carries exactly what the presented board was designed with.
    film_storyboard_params: dict | None = None
    # sha256 over the resolved board's canonical dump — the presented-draft
    # identity (呈现稿 digest = run context digest = render spec digest).
    film_storyboard_content_digest: str | None = None
    # The execution snapshot frozen at design time (ADR-130 §1): the pages
    # the board was grounded on, the resolved music grid (track id / bpm /
    # beats), the timing constants, and its own ``digest`` — LaunchFilm
    # consumes THIS, and drift against it fails honestly (never a silent
    # re-orchestration).
    film_storyboard_execution: dict | None = None
    # Provenance: the user message that authorized THIS version's design
    # (the direction yes / the revision request), and the assistant message
    # that presented its markdown.
    film_design_authorized_by: str | None = None
    film_presented_message_id: str | None = None
    # 「只看分镜」review hold (ADR-129): set by the design beat's
    # review_hold param, cleared only by an explicit production request (a
    # film proposal docking) — never by a new turn, a refresh, or an
    # unrelated Q&A. The start gate blocks while it stands.
    film_review_hold: bool = False
    # Per-version draft token: a fresh draft mints a new one; the dock
    # stamps it onto the task_book payload, and the start gate rejects a
    # Start whose stamped token is not the current draft's (旧 Start 失效 —
    # the row, its messages, assets and run history all stay).
    film_draft_token: str | None = None
    # In-flight draft marker (并发护栏): written by the design beat's BEGIN
    # in its own committed mini-transaction ({draft_id, base_version,
    # started_at, user_message_id}), before the long draft starts; a fresh
    # begin supersedes the old film confirmation (the token clears). While a
    # non-stale marker stands, Start fails closed and a second begin is
    # refused; the publish beat writes only if the marker still names ITS
    # draft; failure clears only its own marker; a marker older than the
    # design budget is stale.
    film_draft_inflight: dict | None = None
    # 未接受文字漂移 (7276ef13 定点收尾②复审): ``{baseline_sha256}`` = the
    # LAST PROVABLY-ACCEPTED copy's digest, set when a verbatim publish's
    # pinned text drifted from that baseline without user proof. Carried
    # forward by every later version until one of the three provable
    # releases (restore / user-pasted / the copy_drift dock's explicit
    # confirm — the start consumes the pending); the dock seats read it as
    # ``copy_drift`` (``film_text_drift_held`` — the world truth, never a
    # turn-local flag, so a rebuilt turn never loses the protection).
    film_text_drift: dict | None = None
    # Version envelope (the patch path's lineage — ADR-134 修订后 edit/
    # variant 不新增 hold): ``film_created_via`` = compose|patch|variant
    # (None on a legacy row); ``film_base_version`` = the version this one
    # was built from (None on a first draft); ``film_change_set`` = the
    # SYSTEM-computed diff for patch versions (never the op echo — None on
    # compose); ``film_kept_frames`` = the version's frozen cut (冻结时间轴
    # = 版本状态 — the base version's own established per-scene frames,
    # frozen at patch time by a keep_cut swap OR inherited by any
    # timeline-preserving edit; consumed fail-closed by the run whenever
    # present; None on a compose/recut/timeline-changing birth);
    # ``film_constraints_choice`` reserved for the constraint provenance
    # (四层约束的 source 记录, 写座在 validator 分层落地时). All
    # read-tolerant: absent/None on pre-envelope rows.
    film_base_version: int | None = None
    film_created_via: str | None = None
    film_change_set: dict | None = None
    film_kept_frames: list[int] | None = None
    # Video Project presentation receipt (ADR-145 phase B, §2.3): the
    # canonical storyboard presentation's proof — which composition version
    # was presented, its content + presentation digests, and the presenting
    # message (null until that row persists). Read-tolerant: absent on
    # pre-video rows; carried verbatim across PendingPlan rewrites by
    # editing/service.video_carry_state.
    video_presentation: dict | None = None
    # The frozen cut's other half (冻结场内切点 = 冻结时间轴同一继承律):
    # the reveal words' landing beats, one entry per scene (None per
    # non-reveal scene); consumed fail-closed by the run whenever the kept
    # cut covers a reveal scene. Read-tolerant: absent on pre-envelope
    # rows.
    film_kept_reveal_onsets: list[int | None] | None = None
    film_constraints_choice: dict | None = None

    @property
    def film_cut_frames(self) -> list[int] | None:
        """The revision-base read surface (与 resolve_film_revision_base 的
        命名空间同形): a live pending's own established cut = its frozen
        kept frames, else None."""
        return self.film_kept_frames

    @property
    def film_cut_reveal_onsets(self) -> list[int | None] | None:
        """The frozen cut's other half on the revision-base read surface
        (与命名空间同座): a live pending's frozen reveal onsets ride its
        kept cut — None when no cut is frozen."""
        if not isinstance(self.film_kept_frames, list):
            return None
        return self.film_kept_reveal_onsets

    @property
    def film_cut_state(self) -> str:
        """The cut's provenance on the revision-base read surface (与命名空
        间同座): a live pending never ran — ``"kept"`` when the version
        carries a frozen cut, else ``"draft"`` (its PRESENTED plan timeline
        is the trustworthy cut; never "unreadable" — that state belongs to
        an executed work whose spec went missing/corrupt)."""
        return "kept" if isinstance(self.film_kept_frames, list) else "draft"


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


class Segment(BaseModel):
    """A high-potential segment extracted from project source assets."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this segment")
    source_text: str = Field(description="Original text of the segment")
    start_marker: str = Field(description="Approximate start location in source")
    end_marker: str = Field(description="Approximate end location in source")
    start_seconds: float | None = Field(
        default=None,
        description="Exact start time in seconds (preferred over text markers)",
    )
    end_seconds: float | None = Field(
        default=None,
        description="Exact end time in seconds (preferred over text markers)",
    )
    summary: str = ""
    hook: str = ""
    recommendation_score: int = Field(default=50, ge=1, le=100)
    golden_quote: str = ""
    # Span-carrier bound: highlights stay ≤120s by the ClipPlan contract (the
    # LLM-facing schema); Segment also carries materialize_source's full-span
    # [0, source duration) segment (ADR-043), so the ceiling here is 4h.
    duration_seconds: int = Field(default=30, ge=5, le=14400)


class ClipPlan(BaseModel):
    """A complete clip plan produced by the clip agent.

    Combines segment selection and script writing into one structure so that a
    single multimodal call can produce everything needed for ``Clip`` creation
    and ``render_spec`` building. ``to_segment`` keeps the existing segment
    path unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this clip plan")
    source_text: str = Field(description="Original segment text from the talk")
    start_marker: str = Field(description="Approximate start location in source")
    end_marker: str = Field(description="Approximate end location in source")
    start_seconds: float | None = Field(
        default=None,
        description="Exact start time in seconds (preferred over text markers)",
    )
    end_seconds: float | None = Field(
        default=None,
        description="Exact end time in seconds (preferred over text markers)",
    )
    summary: str = ""
    hook: str = ""
    title: str = ""
    golden_quote: str = ""
    recommendation_score: int = Field(default=50, ge=1, le=100)
    # One-sentence justification of the score, shown to the user verbatim
    # (STRATEGY §2.1: a visible reason is what makes the score falsifiable).
    score_reason: str = ""
    duration_seconds: int = Field(default=30, ge=5, le=120)
    music_mood: str = "calm"
    # Music selection (see docs/MUSIC_ARCHITECTURE.md §8.3): the Clip Agent picks
    # one piece per clip. ``music_id`` is the Music row's UUID (string) — or, as a
    # robust fallback, a mood key (calm/uplifting/corporate) the orchestrator
    # resolves server-side. ``music_enabled``/``music_gain_db`` are per-clip
    # overrides; when ``music_id`` is unset the persona skin default is used.
    music_id: str | None = None
    music_enabled: bool = True
    music_gain_db: float = -18.0
    visual_notes: str = ""
    title_options: list[str] = Field(default_factory=list)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    topic: str = ""
    # When false, the renderer skips burned-in captions (e.g., source video
    # already has hard-coded subtitles). ASR is still performed so the transcript
    # and SRT export remain available. ``None`` means the agent did not decide,
    # so the persona skin default applies.
    caption_enabled: bool | None = None

    def to_segment(self) -> Segment:
        return Segment(
            id=self.id,
            source_text=self.source_text,
            start_marker=self.start_marker,
            end_marker=self.end_marker,
            start_seconds=self.start_seconds,
            end_seconds=self.end_seconds,
            summary=self.summary,
            hook=self.hook,
            recommendation_score=self.recommendation_score,
            golden_quote=self.golden_quote,
            duration_seconds=self.duration_seconds,
        )


class ClipPlans(BaseModel):
    """Clip agent output: analysis + a list of ready-to-render clip plans."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_arguments: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    clips: list[ClipPlan] = Field(default_factory=list)


class ContentAnalysis(BaseModel):
    """Analysis result for project source assets."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_arguments: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    segments: list[Segment] = Field(default_factory=list)


class Post(BaseModel):
    """Generated social post."""

    model_config = ConfigDict(extra="forbid")

    content: str
    hashtags: list[str] = Field(default_factory=list)


class Quote(BaseModel):
    """Generated quote card (Phase 2, 2026-08-25, RECIPES §4.6.2).

    The writer LLM NEVER sets timestamps — the runner snaps them off
    ``understanding.quotable_lines[id]`` (Phase 2 line 7: pick by id, snap
    by code). ``quote_alt`` is filled either by the LLM (when it knows the
    target language) or by the runner via the translator agent
    (RECIPES §4.6.2 — alt = LLM-judged translation of the source quote,
    not the writer's free composition).
    """

    model_config = ConfigDict(extra="forbid")

    quote: str
    attribution: str
    # LLM picks by ordinal into understanding.quotable_lines; None when the
    # chain had no material (vague prompt → writer drafts from persona style
    # alone, the runner leaves timestamps null and Phase 3's image source
    # fallback carries the card without source video).
    quotable_line_id: int | None = None
    # Code-set timestamps snapped off the picked quotable line — the renderer
    # (Phase 3) reads these to slice the source video and pick the cover frame.
    source_start: float | None = None
    source_end: float | None = None
    # Midpoint of [source_start, source_end] rounded to 0.1s (the
    # frame-grabber's quantize step). Null when the line has no timecode.
    frame_at: float | None = None
    # Source-language quote (verbatim from the material when
    # quotable_line_id is set; otherwise the writer's persona-style draft).
    # Phase 3 reads this as the main caption line.
    quote_source: str | None = None
    # The opposite-language translation; populated when caption_mode is
    # "bilingual". Source/target are decided by ``caption_mode`` on the run
    # (REVIEWED FOR PHASE 2: NEVER auto-inferred from output language).
    quote_alt: str | None = None


class Quotes(BaseModel):
    """Quote-card chain response (RECIPES §4.6.2 chain variant, 2026-08-25).

    Phase 2 / 3 default: ``quotes`` was a single-element list — "1 quote = 1
    video card". The chain variant replaces that with a CORE-IDEAL-CHAIN:
    the writer picks a core idea, then judges how many sentences are
    needed to fully express it (N = 3..7, dynamic — depends on the topic's
    complexity), and selects N verbatim ``quotable_line_id``s in sequence.
    The materializer renders all N as a vertical stack of caption strips
    on a 9:16 canvas, with an optional speaker frame on top
    (``needs_speaker_frame``).

    The schema tolerates ``quotes=[]`` for the no-material path (writer
    drafts from persona style alone). ``core_idea`` is always filled when
    the writer had material to anchor on; ``needs_speaker_frame`` defaults
    to False (text-only stack, image #34 style — the safer default; the
    writer opts in to a speaker face when the topic reads as visual
    anchor worthy, image #35 style).
    """

    model_config = ConfigDict(extra="forbid")

    # 2026-08-25 chain variant: the writer's verdict on the talk's central
    # idea. Lands on the Quotes output payload and rides to the renderer via
    # _materialize_quote_card_outputs (currently display-only — the chain
    # strips show the sentences themselves, the idea is upstream reasoning).
    core_idea: str | None = None
    # Optional speaker frame at the top of the cascade (image #35 Charlie
    # Munger style); off = pure caption strips (image #34 style). Writer
    # judges — no LLM-only path can derive this from text alone, the
    # persona/topic feel carries it.
    needs_speaker_frame: bool = False
    quotes: list[Quote] = Field(default_factory=list)


class QuoteFrame(BaseModel):
    """Frame-card image payload (quote-cards §2.2, 2026-08-28).

    A quote_frame is an IMAGE product (PNG on ``files.image``), never a
    render job — the frame card (one chain entry: curated frame + single
    caption block) and the chain composite (N strips, forms A/B) share
    the type; ``source_ref.quote_chain`` distinguishes the composite and
    ``source_ref.parents`` names its frame-card parents. ``aspect`` feeds
    OutputResponse._derive_aspect for canvas node sizing.
    """

    model_config = ConfigDict(extra="forbid")

    quote: str = ""
    attribution: str = ""
    aspect: str | None = None


class CarouselSlide(BaseModel):
    """One slide of a social carousel (a swipeable narrative)."""

    model_config = ConfigDict(extra="forbid")

    title: str  # short heading
    body: str = ""  # 1-3 short lines; may be empty on a pure-title cover/CTA


class CarouselResponse(BaseModel):
    """A carousel = ordered slides (cover/hook -> points -> CTA)."""

    model_config = ConfigDict(extra="forbid")

    slides: list[CarouselSlide] = Field(default_factory=list)


class Article(BaseModel):
    """Generated article / blog post."""

    model_config = ConfigDict(extra="forbid")

    title: str
    content: str


class DerivativeType(StrEnum):
    """Derivative content types."""

    POST = "post"
    QUOTES = "quotes"
    CAROUSEL = "carousel"
    ARTICLE = "article"


DerivativeContent = Post | Quotes | CarouselResponse | Article


def validate_derivative_content(
    derivative_type: DerivativeType,
    content: dict,
) -> dict:
    """Validate and normalize derivative content against its type schema.

    Returns a plain dict so it can be stored in the JSON column, but raises
    ``ValueError`` if the shape does not match the declared type.
    """
    mapping: dict[DerivativeType, type[BaseModel]] = {
        DerivativeType.POST: Post,
        DerivativeType.QUOTES: Quotes,
        DerivativeType.CAROUSEL: CarouselResponse,
        DerivativeType.ARTICLE: Article,
    }
    model = mapping.get(derivative_type)
    if model is None:
        return content
    return model.model_validate(content).model_dump(mode="json")


class RenderStatus(StrEnum):
    """Vertical-clip render job statuses (NULL on a Clip = render not requested)."""

    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# clip-spec: the renderer-agnostic contract for the vertical-clip editor.
# See docs/VIDEO_EDITOR.md §4. Describes WHAT to render, never HOW — contains no
# Remotion/React/FFmpeg concepts, so the renderer behind it stays swappable.
# ---------------------------------------------------------------------------


class ImageShot(BaseModel):
    """One planned shot of a stills clip (期 2 剪辑师契约段, ADR-016 兼容扩展).

    Renderer-agnostic WHAT: which image holds, for how long, with what
    motion. When ``ClipSource.image_shots`` is non-empty it replaces the
    renderer's even-split fallback — an absent/empty list renders exactly
    like a pre-期 2 spec (backward compatible).
    """

    model_config = ConfigDict(extra="forbid")

    image_url: str  # storage-seam URL (same seam as image_urls)
    dwell_s: float = Field(gt=0)
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "none"
    # Ken Burns endpoint scale (craft band 1.05–1.20; pan reuses it as the
    # travel magnitude). 1.0 with a motion kind is meaningless but legal.
    motion_rate: float = Field(default=1.0, ge=1.0, le=1.5)


class ClipSource(BaseModel):
    """Source backing a clip: an on-camera video, or a "stills" audiogram."""

    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    kind: Literal["video", "stills"] = "video"
    # browser-playable URL via storage.stream_url() (storage seam).
    # video: the video file. stills: the optional speech audio ("" when none).
    url: str = ""
    # stills only: ordered backing images (0 -> solid bg, 1 -> full-frame,
    # N -> even hard-cut slideshow across the duration).
    image_urls: list[str] = Field(default_factory=list)
    # stills only, 期 2: the editor's planned shots. Empty = the legacy even
    # split over ``image_urls`` (both stay in the spec — shots reference the
    # same URLs; the empty-fallback keeps old specs rendering identically).
    image_shots: list[ImageShot] = Field(default_factory=list)
    fps: int = 30
    duration: float | None = None  # source length (seconds) — trim slider bound


class ClipSegment(BaseModel):
    """A kept span of a source. ``hidden=True`` is a non-destructive delete.

    Widened (2026-08-17, ADR-044 操作集闭包): every segment carries a stable
    ``id`` — the anchor-addressable entity identity — minted at birth and on
    split (old persisted specs gain ids on the first validating read; the op
    that persists them backfills the row). ``asset_id`` / ``url`` stay None
    for the homogeneous default (the spec's own ``source``); a hetero
    main-track splice (切 op) carries its donor's asset id + storage-seam
    ``url`` resolved at write. ``provenance`` marks a generated segment
    (None = real).

    ``transition`` is the ENTRY-edge dissolve into this segment (枚举可、画廊
    不可, ADR-016 L3 修订): ``none`` hard cut, ``fade`` through black,
    ``dip`` white flash. Cap: at most 3 non-none transitions per clip —
    enforced where the op is registered, not here.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    asset_id: UUID | None = None
    url: str | None = None
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    hidden: bool = False
    provenance: Literal["real", "generated"] | None = None
    transition: Literal["none", "fade", "dip"] = "none"


class ClipAnchor(BaseModel):
    """Where a layer pins — the storage truth (存法 C: 锚是真相, ADR-044).

    Three forms (绝对时间永不入库 — lane positions are a compile artifact):
    - ``segment``: 段锚 — ``segment_id`` + ``offset_seconds`` into that
      segment's kept span (source-clock offset).
    - ``edge``: 边锚 — ``head``/``tail`` of the kept-video portion +
      ``offset_seconds`` (tail resolves to video_end − offset). The brand
      intro/outro blocks are edge-anchored by construction.
    - ``ratio``: 比例锚 — ``ratio`` ∈ [0,1] of the kept-video duration.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["segment", "edge", "ratio"]
    segment_id: str | None = None
    edge: Literal["head", "tail"] | None = None
    ratio: float | None = Field(default=None, ge=0, le=1)
    offset_seconds: float = 0.0

    @model_validator(mode="after")
    def _coherent(self) -> "ClipAnchor":
        if self.kind == "segment" and not self.segment_id:
            raise ValueError("segment anchor requires segment_id")
        if self.kind == "edge" and self.edge is None:
            raise ValueError("edge anchor requires edge")
        if self.kind == "ratio" and self.ratio is None:
            raise ValueError("ratio anchor requires ratio")
        return self


class ClipRect(BaseModel):
    """Normalized rectangle of the composition (CSS ∩ libass expressible)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class LayerMedia(BaseModel):
    """A layer's content: one branch by media type (video/image/text)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video", "image", "text"]
    url: str | None = None  # video/image: storage-seam URL
    text: str | None = None  # text: the callout content


class ClipLayer(BaseModel):
    """An overlay item on the layer track (ADR-044; "overlay" 词禁用于视频层,
    NAMING §2).

    Position = ``anchor`` (storage truth) + ``duration_seconds``; the output
    timeline window is projected at the bake seam, never persisted.
    ``provenance`` is REQUIRED — every layer item declares its ADR-026 class
    at write. ``source_ref`` carries the entity reference the LLM proposed
    from (never an absolute timecode).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    kind: Literal["broll", "text_callout", "pip", "motion_graphic"]
    anchor: ClipAnchor
    duration_seconds: float = Field(gt=0)
    rect: ClipRect
    z: int = 0
    source_ref: dict | None = None
    media: LayerMedia | None = None
    provenance: Literal["real", "generated"]


class ClipCrop(BaseModel):
    """9:16/1:1 reframe as a normalized center + scale (applied via transform)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    scale: float = Field(default=1.0, gt=0.0)


class CropKeyframe(BaseModel):
    """One framing decision on the SOURCE timeline (ADR-045 D5): from source
    second ``t``, hold this normalized center + scale. The crop data track is
    a sparse list of these — a keyframe is a decision ("switch to A here"),
    never per-frame data. Anti-dizzy parameters (dwell / deadzone / slew) are
    write-side constraints of the tool, never serialized; the renderer eases
    into each keyframe over a fixed ~8-frame smoothstep (a render constant).
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    t: float = Field(ge=0.0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0)


class CaptionCue(BaseModel):
    """One caption cue (word/line) from ASR word-level timestamps; text editable."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    lang: str = "en"
    # 期 2 强调隔离: the editor marked this word as emphasized — its line
    # takes the pop-in entrance regardless of the preset's default entrance.
    emphasis: bool = False


class Point(BaseModel):
    """Normalized center point in [0,1] (CSS translate / libass \\pos)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ClipTitle(BaseModel):
    """Optional title/hook card overlay."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    enabled: bool = False
    size: int | None = None  # composition px; None -> renderer default
    position: Point | None = None  # normalized center; None -> default (top)


class ClipMusic(BaseModel):
    """Optional background music."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # The Music row's UUID (string). Accepts a legacy ``track_id`` key on input so
    # existing render_spec JSON (pre-rename) still deserializes, but the init
    # param and serialized field are both ``music_id`` (see docs/MUSIC_ARCHITECTURE.md).
    music_id: str | None = Field(
        default=None, validation_alias=AliasChoices("music_id", "track_id")
    )
    url: str | None = None  # resolved track URL (storage seam); None = no track
    enabled: bool = False
    gain_db: float = -18.0


class GenerationContext(BaseModel):
    """Shared context passed to every content generation agent.

    Assembled once per generation run from the resolved persona (style +
    brand skin), tone settings, project metadata, and user instruction.
    """

    model_config = ConfigDict(extra="forbid")

    persona: PersonaContext | None = None
    event_name: str | None = None
    tone_settings: ToneSettings | None = None
    target_language: str = "en"
    instruction: str | None = None
    # The persona skin block's default music piece (Music.id as string); the
    # Clip Agent uses this as the default unless a clip's content suggests
    # otherwise.
    brand_music_id: str | None = None
    # 2026-08-25 Phase 2: caption mode for caption-bearing runs
    # (write_quotes when the chain produces a captioned video card).
    # Three values: "bilingual" (source + target), "source_only", or
    # "target_only". None = no caption-mode decision yet (legacy / no
    # caption work). Threaded from run.context.caption_mode by the
    # derivative dispatch.
    caption_mode: Literal["bilingual", "source_only", "target_only"] | None = None
    # 2026-08-28 P2 (quote-cards §2.3): the run's resolved language pair.
    # ``source_language`` = the ASR-detected language of the source
    # material (asset.meta["language"], project.language fallback);
    # ``quote_alt_language`` = the derived SECOND caption language for
    # bilingual mode (derive_quote_alt_language — user-named target →
    # project/UI locale → run target, first that ≠ source; None when no
    # distinct alt exists, in which case bilingual is meaningless and the
    # gate stamps source_only). Threaded by DerivativeWriterNode.run so
    # the quotes enrich step never re-derives.
    source_language: str | None = None
    quote_alt_language: str | None = None


# ---------------------------------------------------------------------------
# Understand/Plan two-step (RunPlan Phase 2): the retired single-pass ContentPlan is
# replaced by a material-scoped understanding (reusable via asset hash) and a
# request-scoped storyboard (re-planned every run). docs/tasks/director-two-step.md
# ---------------------------------------------------------------------------


class KeyArgument(BaseModel):
    """One key argument of the talk, with its transcript location."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable id within the understanding (a1, a2, …)")
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


# ---------------------------------------------------------------------------
# Beat map (产物质量线期 1, docs/tasks/output-quality-line.md §2.2): the
# understanding's SEMANTIC halves. The acoustic/visual halves live on
# asset.meta["prosody"] / asset.meta["visual_anchors"] — separate fields by
# design (预合并 = 自信地错且不可溯源; the channels' disagreement is the
# editor's arbitration signal). ``start``/``end``/``asset_id`` are NEVER LLM
# output: the LLM writes verbatim text anchors (and may copy coarse cue
# seconds into ``approx_start``); code snaps them onto the ASR word axis
# (word-level timestamps are the deterministic foundation, never overwritten).
# ---------------------------------------------------------------------------


class TopicBoundary(BaseModel):
    """One topic segment of the talk (semantic segmentation)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable id within the understanding (t1, t2, …)")
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
    """A semantic climax span — the semantic half of the climax channel."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""  # the verbatim climax sentence(s)
    why: str = ""
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None


class EmphasisWord(BaseModel):
    """A word the LLM judges semantically emphasized (semantic half).

    The weight here is the LLM's; the acoustic F0/energy z-scores stay on
    asset.meta["prosody"]["words"] — never merged.
    """

    model_config = ConfigDict(extra="forbid")

    word: str
    weight: float = 0.5
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None


class QuotableLine(BaseModel):
    """A verbatim quotable line with a code-checked self-containment flag."""

    model_config = ConfigDict(extra="forbid")

    text: str  # verbatim from the material
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None
    # Code-set, never the LLM's: False when the line opens with a dangling
    # pronoun / connective (it, this, but, 这/但/而且…) or trails off mid-thought.
    self_contained: bool = True


class NarrativeRoleHint(BaseModel):
    """The global-arc role of a span (setup/payoff/example/transition)."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["setup", "payoff", "example", "transition"]
    note: str = ""
    marker: str = ""  # verbatim first words of the span (snapping anchor)
    approx_start: float | None = None
    asset_id: str = ""
    start: float | None = None
    end: float | None = None


class VisualAnchor(BaseModel):
    """The LLM's semantic half of a visual anchor for one image asset.

    The deterministic half (faces / subject box / safe area) lives on the
    asset's meta["visual_anchors"]; this row joins them by ``asset_id``.
    """

    model_config = ConfigDict(extra="forbid")

    # The image's ordinal in the media list the LLM saw ("image 2" → 2);
    # code-resolved to the asset id at persist time ("" = unresolved).
    ref: str = ""
    asset_id: str = ""
    label: str = ""  # what / whom the image shows
    # Ids of key_arguments this image visually backs.
    argument_ids: list[str] = Field(default_factory=list)


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


# ---------------------------------------------------------------------------
# Research brief (ADR-052 B4, DIALOG_WORKFLOW §2.6): the bounded loop node's
# artifact — web grounding gathered by the researcher agent's search/fetch
# iterations, stamped into the research step's spec and appended to
# consuming writers' asset texts. Machine channel only (step spec): it never
# enters the dialog engine's brief — same word, different object.
# ---------------------------------------------------------------------------


class ResearchSource(BaseModel):
    """One web source the brief actually used."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    url: str = ""


class ResearchBrief(BaseModel):
    """The research loop's closing artifact.

    ``caveat`` carries the honest-degradation note (iteration-cap synthesis,
    search trail ran dry, research unavailable) — a caveated brief is a
    COMPLETE step, never a failed one: research is best-effort enrichment,
    the run continues either way.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    key_facts: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    caveat: str | None = None


class ResearchVerdict(BaseModel):
    """The researcher agent's per-iteration verdict (bounded loop, ADR-052
    B4): pick the ONE next action — run a new search, open one result URL,
    or close with the final brief. The agent chooses actions; the node's
    code owns the tool set and the iteration count (禁开放自治)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["search", "fetch", "brief"]
    query: str | None = None  # search
    url: str | None = None  # fetch
    brief: ResearchBrief | None = None  # brief


# ---------------------------------------------------------------------------
# Beat plan (产物质量线期 2, docs/tasks/output-quality-line.md §2.3): the
# stills editor's per-shot timeline decisions — the timeline-creation layer
# between storyboard (WHAT) and clip-spec (怎么渲). Same 铁律 as the beat
# map: the LLM writes verbatim markers (+ optional coarse seconds); code
# snaps them onto the word axis and chains the ends (zero-gap sequence,
# cuts always on word boundaries — dwell IS the word-span duration, so
# captions, cuts, and dwells can never drift apart).
# ---------------------------------------------------------------------------


class StillBeat(BaseModel):
    """One shot decision of a stills beat plan (节拍方案的一拍)."""

    model_config = ConfigDict(extra="forbid")

    # The backing visual, exactly as listed in the prompt ("image 2" → the
    # second backing visual); code resolves it to asset_id + image_url.
    image_ref: str
    asset_id: str = ""  # "" for slide pages (no asset) or unresolved
    image_url: str = ""
    # The beat's narration anchor: the verbatim opening words of its span.
    # Ends are code-chained by TILING (each beat ends exactly at the next
    # beat's first word — shots play back-to-back on the render timeline, so
    # dwells, cuts, and captions share the one word clock); the last beat
    # ends at the clip span's end.
    marker: str = ""
    approx_start: float | None = None
    start: float | None = None
    end: float | None = None
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "none"
    # Ken Burns endpoint scale within the craft band (1.05–1.20); the
    # compiler clamps into the band.
    motion_rate: float = 1.0
    # 强调隔离: hold (the dwell itself lengthens — no extra mechanics),
    # punch_in (compiles to zoom_in ≥1.15), caption_pop (the span's caption
    # cues get emphasis=true → pop-in entrance).
    emphasis: Literal["none", "hold", "punch_in", "caption_pop"] = "none"
    # 结构呼吸: a deliberate reset shot (wider/slower/quieter).
    reset: bool = False
    note: str = ""  # one-line why (judge-facing evidence)


class BeatPlan(BaseModel):
    """节拍方案: the stills editor's output — one clip's shot timeline."""

    model_config = ConfigDict(extra="forbid")

    arc: str = ""  # the one-line global arc (two-stage: from the outline pass)
    beats: list[StillBeat] = Field(default_factory=list)


class BeatSection(BaseModel):
    """大纲段的一节 (>15 拍两段式): role + assigned visuals + span anchor."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["hook", "build", "reset", "payoff"]
    image_refs: list[str] = Field(default_factory=list)
    marker: str = ""  # verbatim opening words of the section
    approx_start: float | None = None
    note: str = ""
    start: float | None = None  # code-resolved / chained
    end: float | None = None


class BeatOutline(BaseModel):
    """大纲段产出: global arc + resource assignment before per-beat work."""

    model_config = ConfigDict(extra="forbid")

    arc: str = ""
    sections: list[BeatSection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verify judge (产物质量线期 3, §2.7 judge rubric 纪律): the LLM half of the
# verify loop — subjective items only (金句上下文可读性). Evidence-citation-
# first (context_read BEFORE the verdict field), no abstract scores, temp 0
# (declared on the agent), provenance-blind (the prompt never sees ids/round).
# Verdicts ride the ledger as cls="judge" — advisory until the human
# calibration set lands (judge 漂移无地面真值不可检测).
# ---------------------------------------------------------------------------


class QuoteJudgment(BaseModel):
    """One quote's context-readability judgment (evidence before verdict)."""

    model_config = ConfigDict(extra="forbid")

    quote: str = ""  # echoed verbatim — the evidence anchor
    context_read: str = ""  # what the source excerpt around it establishes
    standalone: bool = True  # reads in context AND stands alone on a card
    issue: str = ""  # when not standalone: what's missing / awkward


class QuoteReadability(BaseModel):
    """The judge's verdict over one quotes output."""

    model_config = ConfigDict(extra="forbid")

    judgments: list[QuoteJudgment] = Field(default_factory=list)


class StoryboardSlot(BaseModel):
    """槽位: one output's WHAT (angle/arguments/language/format). HOW is the executor's."""

    model_config = ConfigDict(extra="forbid")

    slot: str = Field(description="clips | post | quotes | carousel | article")
    focus: str = ""
    # Ids referencing the understanding's key arguments; unknown ids are
    # dropped by code before coverage is computed.
    argument_ids: list[str] = Field(default_factory=list)
    quote_candidates: list[str] = Field(default_factory=list)
    cta: str | None = None
    tone_override: str | None = None
    count: int | None = None


class CoverageReport(BaseModel):
    """覆盖报告: argument → slot accountability. Code-derived, never LLM output."""

    model_config = ConfigDict(extra="forbid")

    assignments: dict[str, list[str]] = Field(default_factory=dict)
    unused_arguments: list[str] = Field(default_factory=list)
    collisions: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    """分镜表: plan step — request-scoped assignments (re-planned every run).

    The LLM proposes only ``slots``; ``coverage`` is computed by the runner
    from valid argument_ids before persisting.
    """

    model_config = ConfigDict(extra="forbid")

    slots: list[StoryboardSlot] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)


# ---------------------------------------------------------------------------
# RunPlan vocabulary (ADR-028/030): workflow_steps + unified outputs.
# Node kinds and output types have their living sources in NODE_KINDS /
# the outputs registry (N-35/N-32) — no parallel Literals here.
# ---------------------------------------------------------------------------

# "waiting" is a seat for HITL/suspend-resume (variant_pick gate, chat-loop-v1
# Task 4): a step parks in waiting with spec.suspend_payload until resumed.
StepStatus = Literal["pending", "running", "done", "failed", "skipped", "waiting"]

OutputProvenance = Literal["real", "generated"]


class ClipPayload(BaseModel):
    """Payload for ``outputs[type=clip]`` — the clip's creative fields.

    Timeline semantics live in ``source_ref``, the render pipeline in
    ``render_spec``/``render_status``, publishing metadata in ``publishing``
    (ADR-030 payload rules 2/3).
    """

    model_config = ConfigDict(extra="forbid")

    hook: str = ""
    title_options: list[str] = Field(default_factory=list)
    music_mood: str = "calm"
    duration: int = 30
    # The display-class stamp for "original"-aspect chains (2026-09-13
    # 用户拍板 — 产物卡跟源比例): at clip birth the source's real pixels name
    # the display class ("9:16" / "1:1" / "16:9"), so the canvas card shapes
    # itself to the material instead of the 16:9 default strip (黑边). The
    # RENDER contract is untouched — render_spec.aspect stays "original";
    # this feeds only OutputResponse._derive_aspect (same write-point
    # pattern as image products). None when dims are unknown or the chain
    # carries an explicit aspect (render_spec declares then).
    aspect: str | None = None


# ---------------------------------------------------------------------------
# film family (MG film skill — ADR-119): the LLM-authored storyboard is the
# orchestration-side contract; the render-side boundary (shape-only zod)
# lives in apps/render/src/film/schema.ts. Semantic grounding / content
# constraints are the grounding validator's seat (app/tools/film/storyboard.py)
# — ONE law, one seat: these models carry shape, never content bounds.
#
# Deterministic frame allocation: the LLM writes a bounded SECONDS intent per
# scene; integer frames are assigned by code (fixed fps, structural minimums,
# total = Σ scene frames). The renderer only sums integers.
# ---------------------------------------------------------------------------


class FilmFocus(BaseModel):
    """One camera beat of a ui scene (the screenshot walk). Two legal forms
    (ADR-121 B2): **element-named** — ``element`` ids the shot's captured
    inventory and the spec builder resolves x/y/zoom deterministically (the
    model never invents coordinates); or the **raw triple** ``x``/``y``/
    ``zoom`` (the pre-B2 form — read tolerance for stored storyboards, and
    the fallback when a shot lists no elements)."""

    model_config = ConfigDict(extra="forbid")

    at: float  # seconds from scene start
    element: str | None = None  # s<shot>e<j> from the page block's inventory
    x: float | None = None  # normalized [0,1] camera center — bounds are the validator's seat
    y: float | None = None
    zoom: float | None = None  # magnification (1 = full frame)


class SubtitleCue(BaseModel):
    """One subtitle, in seconds relative to its scene (independent of audio)."""

    model_config = ConfigDict(extra="forbid")
    at: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> SubtitleCue:
        if self.end <= self.at or not self.text.strip():
            raise ValueError("subtitle needs nonblank text and end > at")
        return self


class SubtitleStyle(BaseModel):
    """Shared subtitle style; geometry is relative to the canvas."""

    model_config = ConfigDict(extra="forbid")
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    background: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    font_size: float = Field(default=34, ge=12, le=120, allow_inf_nan=False,
                             description="Font size on the 1920-wide design canvas.")
    font_weight: Literal[400, 500, 600, 700, 800] = 600
    bottom: float = Field(default=0.04, ge=0, le=0.8, allow_inf_nan=False)
    width: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    enter: Literal["none", "fade", "rise"] = "fade"
    exit: Literal["none", "fade"] = "fade"
    fade_seconds: float = Field(default=0.2, gt=0, le=2, allow_inf_nan=False)


class SubtitleTrack(BaseModel):
    """An independent subtitle track; ordered, nonoverlapping cues."""

    model_config = ConfigDict(extra="forbid")
    cues: list[SubtitleCue] = Field(min_length=1)
    style: SubtitleStyle = Field(default_factory=SubtitleStyle)

    @model_validator(mode="after")
    def nonoverlapping(self) -> SubtitleTrack:
        if any(b.at < a.end for a, b in zip(self.cues, self.cues[1:])):
            raise ValueError("subtitle cues must be ordered and nonoverlapping")
        return self


class FilmSceneBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subtitle_track: SubtitleTrack | None = None


class FilmSceneWords(FilmSceneBase):
    model_config = ConfigDict(extra="forbid")

    type: Literal["words"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    dark: bool
    lines: list[str] = Field(min_length=1)
    # Text-plane vocabulary (ADR-138 §7.6 — closed enums, renderer-implemented):
    # ``motion`` = the camera move on the text plane (null = static);
    # ``enter`` = the text's entrance rhythm ("lines" = per-line stagger —
    # the pre-vocabulary default; "words" = word-by-word). Null reads as the
    # default and is EXCLUDED from the content digest, so legacy boards keep
    # their byte-identical digests (the scene_id law's twin).
    motion: Literal["static", "push", "pull"] | None = None
    enter: Literal["lines", "words"] | None = None
    # Precise entrance/motion timing (Batch B): scene-relative seconds,
    # quantized by the film's fixed fps at the render seat. ``enter_*``
    # parameterizes the selected entrance (word tokens or whole lines): the
    # first unit's start, adjacent-unit start interval, one unit's entrance
    # duration, and the hold endpoint. Null keeps the pre-parameterization
    # default; lines default to their legacy 8-frame stagger. An explicit
    # ``enter_hold_until`` is a HARD endpoint — the text leaves at that frame
    # (with exit_duration it fades out across the final stretch); null = hold
    # to the scene end.
    # ``motion_start``/``motion_end`` bound a push/pull move inside the scene.
    # Explicit zero stays zero — presence, not truthiness, carries intent.
    enter_start: float | None = Field(default=None, ge=0.0)
    enter_interval: float | None = Field(default=None, ge=0.0)
    enter_duration: float | None = Field(default=None, ge=0.0)
    enter_hold_until: float | None = Field(default=None, ge=0.0)
    motion_start: float | None = Field(default=None, ge=0.0)
    motion_end: float | None = Field(default=None, ge=0.0)
    # The text's OWN exit fade (seconds at the window's end — the hold
    # endpoint when set, else the scene's end): the words fade out over the
    # final N seconds of their window; null = no exit fade (the boundary's
    # own transition carries the leave). The background never fades with
    # the text. Explicit values quantize to frames like the enter timing.
    exit_duration: float | None = Field(default=None, gt=0.0)
    # The push/pull move's end scale (push: 1 → scale; pull: scale → 1);
    # null = the legacy 1.06. Subtle drifts live around 1.02–1.04. Requires
    # motion="push"|"pull".
    motion_scale: float | None = Field(default=None, gt=1.0, le=1.25)
    # Horizontal text alignment: null/"left" = the legacy left edge;
    # "center" centers every line (and the camera's zoom origin).
    align: Literal["left", "center"] | None = None
    # Font size tier: null/"medium" = the legacy 168px grid size;
    # "small"/"large" = 120/232. The line-wrap capacity scales with it, so
    # a larger tier never clips or drops copy.
    size: Literal["small", "medium", "large"] | None = None
    # How *emphasized* spans render: null/"chip" = the legacy inverted
    # chip; "color" = the theme's accent color as plain text (a colored
    # word, not a highlighted tile).
    accent_style: Literal["chip", "color"] | None = None
    # The entrance EFFECT (orthogonal to ``enter``'s organization — lines
    # vs words is WHO arrives together, this is HOW each token appears):
    # null/"rise" = the legacy fade+rise+blur entrance; "fade" = opacity
    # only; "slide" = deterministic translate-only entrance, no fade/blur.
    enter_style: Literal["rise", "fade", "slide"] | None = None
    narration: str | None = None
    # The scene's PRE-WRAP corpus (逐字律的场级锚点): ``lines`` above is the
    # layout RESULT of wrapping this text for the screen — a visual wrap is
    # not a paragraph break, so the version's pinned ``text`` re-derives
    # from these per-scene sources, never from the display lines. Kept
    # accent-free (emphasis is presentation, not corpus). Null = a legacy
    # board assembled before the anchor existed; excluded from the content
    # digest while null (the ``_LEGACY_ABSENT_SCENE_KEYS`` law's sibling).
    copy_text: str | None = None


class FilmSceneHero(FilmSceneBase):
    model_config = ConfigDict(extra="forbid")

    type: Literal["hero"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    word: str
    sub: str
    narration: str | None = None


class FilmSceneUi(FilmSceneBase):
    """The page walk: the LLM names the page by its index in the presented
    manifest list; the screenshot URL / display URL are baked BY CODE (the
    model never invents URLs). ``shot`` picks WHICH captured view of the page
    (0 = the fold; sections beyond it — ADR-121 B1). ``frame`` chooses the
    presentation: True = the browser-chrome card (the "this is a real product
    page" beat), False = full-bleed (the immersive push-in — the camera fills
    the canvas with the page itself)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ui"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    page: int  # 0-based index into the presented pages
    shot: int = 0  # 0-based index into the page's captured shots
    frame: bool = True  # browser chrome card vs full-bleed
    focuses: list[FilmFocus] = Field(min_length=1)
    narration: str | None = None


class FilmPlateCard(BaseModel):
    """One glass card: a big number/short mark over a small label. ``big`` is
    null for a phrase card (the label carries it, slightly larger)."""

    model_config = ConfigDict(extra="forbid")

    big: str | None = None
    label: str


class FilmScenePlate(FilmSceneBase):
    """The numbers beat: 2-4 glass cards over a calm procedural backdrop —
    the film's "proof by specs" moment. Only legal when the page actually
    carries numbers or very short labels (the grounding validator enforces
    it). ``backdrop`` names a code-rendered scenery variant (a closed enum —
    never an image URL, never a free prompt)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["plate"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    title: str
    cards: list[FilmPlateCard] = Field(min_length=2, max_length=4)
    backdrop: Literal["aurora", "dunes", "mist", "tide"] = "mist"
    narration: str | None = None


class FilmSceneDivider(FilmSceneBase):
    """Section break with a rolling word list. The ordinal index ("01") is
    chrome — code assigns it, the model never writes it."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["divider"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    label: str
    roll: list[str] = Field(min_length=1)
    # Grounding memory for later compose revisions: the full cited pillar,
    # not the condensed display title in roll[-1]. Never emitted to film-spec.
    source_text: str | None = None
    narration: str | None = None


class FilmSceneReveal(FilmSceneBase):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reveal"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    lead: str
    word: str
    sub: str
    # The lead-in holds alone for the scene's FIRST HALF, then a one-beat
    # black pause, then the word lands on the music grid (the split reveal's
    # lead → beat → word arc); seconds-from-scene-start, code-assigned at
    # assembly. The default only covers pre-split persisted boards.
    lead_seconds: float = 1.5
    narration: str | None = None


class FilmSceneEnd(FilmSceneBase):
    """Closing brand card. The display URL is baked by code from the page's
    real URL; logo stays text-only in v1 (logo_url never LLM-written)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["end"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    name: str
    tagline: str
    narration: str | None = None


# ---------------------------------------------------------------------------
# Composite scene elements (ADR-140): a composite scene is a theme-colored
# background plus an ordered element list. Screen recordings, camera videos
# and plain uploads are all just VIDEO assets here; image assets ride the
# same structure; text is an independently controllable element that shares
# the words plane's ONE animation implementation (renderer-side TextPlane).
# Two time spaces, never mixed: ``source_start``/``source_end`` are SOURCE
# media seconds (video only); ``at``/``until``/``duration`` are scene-relative
# OUTPUT seconds; the enter/motion timing fields are ELEMENT-WINDOW-relative
# seconds (the element window is the text's own mini-scene).
# ---------------------------------------------------------------------------


class FilmElementRect(BaseModel):
    """A normalized placement box {x, y, w, h} ∈ [0,1] — the clip-spec
    layers' coordinate law. The default is the full canvas."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    w: float = Field(default=1.0, gt=0.0, le=1.0)
    h: float = Field(default=1.0, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _inside_canvas(self) -> "FilmElementRect":
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError(
                f"rect ({self.x:g},{self.y:g},{self.w:g},{self.h:g}) extends past the canvas"
            )
        return self


class FilmElementVideo(BaseModel):
    """A video asset playing one SOURCE range inside one OUTPUT window.

    ``asset`` is the asset id — code resolves the storage key (the model
    never invents URLs, the ui scene's law). The play window length is
    ``duration`` (null = the full source range); a window LONGER than the
    source range rejects — no speed change, no looping, no tail freeze, no
    replay-from-zero. When the window ends the element LEAVES the screen.
    ``keep_audio`` (default false) is the original-sound switch: the source
    trim and the audio trim are the same cut (one startFrom/endAt pair), so
    original sound exists only inside the element's own window."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"]
    # Stable element identity (the scene_id law's twin): assigned at birth
    # or derived positionally on first patch; NEVER part of the content
    # digest.
    element_id: str | None = None
    asset: str  # the project asset's id (uuid string)
    source_start: float = Field(ge=0.0)
    source_end: float = Field(gt=0.0)
    at: float = Field(default=0.0, ge=0.0)  # scene-relative output start
    duration: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    fit: Literal["cover", "contain"] = "cover"
    keep_audio: bool = False
    z: int = 0

    @model_validator(mode="after")
    def _range_ordered(self) -> "FilmElementVideo":
        if self.source_end <= self.source_start:
            raise ValueError(
                f"source_end {self.source_end:g}s must stay after source_start "
                f"{self.source_start:g}s"
            )
        if self.duration is not None and self.duration > (
            self.source_end - self.source_start
        ) + 1e-9:
            raise ValueError(
                f"the play window {self.duration:g}s is longer than the source "
                f"range {self.source_end - self.source_start:g}s — the clip "
                "never loops, stretches, or freezes to fill time"
            )
        return self


class FilmElementImage(BaseModel):
    """An image asset placed in a rect for a scene-relative window
    (``until`` null = the scene's end)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"]
    element_id: str | None = None  # identity handle; never in the digest
    asset: str  # the project asset's id (uuid string)
    at: float = Field(default=0.0, ge=0.0)
    until: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    fit: Literal["cover", "contain"] = "cover"
    z: int = 0

    @model_validator(mode="after")
    def _window_ordered(self) -> "FilmElementImage":
        if self.until is not None and self.until <= self.at:
            raise ValueError(
                f"until {self.until:g}s must stay after at {self.at:g}s"
            )
        return self


class FilmElementText(BaseModel):
    """An independently controllable text block: content (``lines``), ink
    polarity (``tone`` — light/dark, the two-stop vocabulary, plus "accent"
    = the theme's accent color for the whole element; accent *chips* invert
    the same way), placement (``rect``), display window (``at`` /
    ``until``, null = scene end — the window's end is the leave; a set
    ``exit_duration`` fades the text out over the window's final seconds,
    the background never fades with it), and the words plane's
    entrance/motion vocabulary (``enter`` / ``motion`` + the timing fields,
    ELEMENT-WINDOW-relative seconds — ``enter_hold_until`` does not exist
    here, ``until`` plays that role). ``copy_text`` is the pre-wrap corpus
    anchor (the words scene's 逐字律 seat, per element)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"]
    element_id: str | None = None  # identity handle; never in the digest
    lines: list[str] = Field(min_length=1)
    tone: Literal["light", "dark", "accent"] = "light"
    at: float = Field(default=0.0, ge=0.0)
    until: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    enter: Literal["lines", "words"] | None = None
    motion: Literal["static", "push", "pull"] | None = None
    enter_start: float | None = Field(default=None, ge=0.0)
    enter_interval: float | None = Field(default=None, ge=0.0)
    enter_duration: float | None = Field(default=None, ge=0.0)
    motion_start: float | None = Field(default=None, ge=0.0)
    motion_end: float | None = Field(default=None, ge=0.0)
    # The words plane's style/exit knobs, element-scoped (the words scene's
    # field law verbatim): exit_duration = fade-out seconds at the window's
    # end; motion_scale = the push/pull end scale (null = 1.06); align =
    # horizontal centering; size = the font tier (element grid: 56/80/120);
    # accent_style = chip (legacy inverted tile) vs color (accent ink);
    # enter_style = rise (legacy fade+rise+blur), fade (opacity only), or
    # slide (translate only, no fade/blur).
    exit_duration: float | None = Field(default=None, gt=0.0)
    motion_scale: float | None = Field(default=None, gt=1.0, le=1.25)
    align: Literal["left", "center"] | None = None
    size: Literal["small", "medium", "large"] | None = None
    accent_style: Literal["chip", "color"] | None = None
    enter_style: Literal["rise", "fade", "slide"] | None = None
    copy_text: str | None = None
    z: int = 0

    @model_validator(mode="after")
    def _window_ordered(self) -> "FilmElementText":
        if self.until is not None and self.until <= self.at:
            raise ValueError(
                f"until {self.until:g}s must stay after at {self.at:g}s"
            )
        return self


FilmSceneElement = Annotated[
    FilmElementVideo | FilmElementImage | FilmElementText,
    Field(discriminator="kind"),
]


class FilmSceneComposite(FilmSceneBase):
    """The composition scene (ADR-140): a theme-colored background (``dark``
    polarity, the words scene's two-stop vocabulary) plus an ordered element
    list — video/image media elements and independent text elements composing
    one screen. "Video with a left title", "recording with bottom text" and
    "image with word-by-word copy" are CONFIGURATIONS of this one structure,
    never separate scene types with separate text implementations. At least
    one media element (pure full-screen text stays with the words scene).
    Elements overlap freely; ``z`` orders them (ties keep list order)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["composite"]
    # Stable scene identity (ADR: film edits) — assigned at birth or
    # derived positionally on first patch (读容忍: legacy boards carry none).
    # Identity handle only; NEVER part of the content digest.
    scene_id: str | None = None
    seconds: float
    dark: bool = False
    elements: list[FilmSceneElement] = Field(min_length=1)
    narration: str | None = None


FilmScene = Annotated[
    FilmSceneWords
    | FilmSceneHero
    | FilmSceneUi
    | FilmSceneDivider
    | FilmScenePlate
    | FilmSceneReveal
    | FilmSceneComposite
    | FilmSceneEnd,
    Field(discriminator="type"),
]


class FilmStoryboardTheme(BaseModel):
    """Optional monochrome pair + accent override (hex). Absent = the code
    default. ``accent`` colors *emphasized* spans when a scene asks for
    accent-color text (accent_style="color" / tone="accent"); absent = the
    default accent."""

    model_config = ConfigDict(extra="forbid")

    canvas: str
    ink: str
    accent: str | None = None


class FilmStoryboard(BaseModel):
    """The launch film's storyboard — the LLM's ONE artifact in the film
    chain (grounding-validated, frame-allocated by code, then baked into a
    film-spec). ``name`` is the two-source display-copy seat: LLM-chosen,
    null-read tolerant (打字机牙①).

    Per-scene ``narration`` (配音词) is SPOKEN copy — code synthesizes it and
    does not implicitly create a subtitle track; it
    is never grounding-checked verbatim (the director rephrases the page's
    facts into speech), and reads as no-voiceover when null
    (打字机牙① applies to every prose field)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    theme: FilmStoryboardTheme | None = None
    # The film's SPOKEN language, declared by the drafter (2026-10-15 语言钉
    # 参): the plan's pin when one rode the proposal, else the page's own
    # language (the product's voice — never the conversation's). Null =
    # undeclared (legacy rows, 读容忍); the node's output stamp then falls
    # to the run's legacy language chain.
    language: str | None = None
    scenes: list[FilmScene] = Field(min_length=1)

    @model_validator(mode="after")
    def subtitle_windows(self) -> FilmStoryboard:
        for scene in self.scenes:
            if scene.subtitle_track and scene.subtitle_track.cues[-1].end > scene.seconds:
                raise ValueError("subtitle cues must fit within their scene duration")
        return self


# ---------------------------------------------------------------------------
# Film edit ops (the patch path's contract) + the system-computed change_set.
# Application semantics live in app/tools/film/edits.py — the model authors
# ops, the SYSTEM applies them; these models only pin the wire shape.
# ---------------------------------------------------------------------------


class FilmViewRef(BaseModel):
    """``update_scene``'s view replacement (ui scenes only): which captured
    view the scene walks, and optionally the presentation (``frame`` None =
    keep the scene's current presentation)."""

    model_config = ConfigDict(extra="forbid")

    page: int
    shot: int = 0
    frame: bool | None = None


class FilmEditUpdateScene(BaseModel):
    """Field-level scene edit. Absent fields keep the current value;
    ``narration`` is presence-sensitive (an explicit null CLEARS the line —
    ``model_fields_set`` distinguishes, never the value). ``copy_slots`` addresses
    the scene type's prose slots (hero word/sub, words lines, divider
    label/roll, reveal lead/word/sub, plate title, end name/tagline);
    unknown keys for the scene type reject at apply time. ``motion`` /
    ``enter`` are the words plane's text vocabulary (static/push/pull camera
    settle; lines/word-by-word entrance) — words scenes only. The ``enter_*``
    timing fields parameterize that entrance in scene-relative
    seconds (start / adjacent-unit interval / one unit's entrance duration /
    hold endpoint); words mode animates tokens, lines mode animates whole lines. ``motion_start``/``motion_end`` bound a push/pull move.
    These timing fields are presence-sensitive: absent keeps the value, an
    explicit null restores the default, and explicit zero stays zero.
    ``dark`` is
    the words plane's background polarity (deep/light — a two-stop
    vocabulary, never an arbitrary color) — words scenes only."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_scene"]
    scene_id: str
    view: FilmViewRef | None = None
    seconds: float | None = None
    focuses: list[FilmFocus] | None = None
    narration: str | None = None
    copy_slots: dict[str, str | list[str]] | None = Field(
        default=None,
        description=(
            "Scene-type prose slots. A words scene uses ONLY 'lines', and its "
            "value is a JSON array of strings: copy_slots={\"lines\":[\"见阳光的人\",\"眼里全是温柔和笑意\"]}. "
            "Never put 'words' around it and never pass the lines as a string. "
            "When the user asks for complete sentences, the entries read in "
            "order must form complete grammatical sentences; split them only "
            "at semantic boundaries. Line breaks are layout, not a waiver of "
            "any per-line, line-count, scene-duration or timing bound. When "
            "the user asked to preserve the original copy, rewrap only with "
            "its wording and order intact — never truncate, drop or rewrite "
            "copy just to pass validation. To make whole lines enter "
            "sequentially, set enter='lines', enter_style='slide', "
            "enter_duration and enter_interval>=duration; clear stale word "
            "timing keys explicitly in the same op."
        ),
    )
    motion: Literal["static", "push", "pull"] | None = None
    enter: Literal["lines", "words"] | None = None
    dark: bool | None = None
    enter_start: float | None = Field(
        default=None,
        ge=0.0,
        description="Entrance start in scene-relative seconds (first token or line). Absent = keep; explicit null = restore the default (0); explicit 0 is a real value.",
    )
    enter_interval: float | None = Field(
        default=None,
        ge=0.0,
        description="Interval between adjacent token or line entrance starts, in seconds. Absent = keep; explicit null = restore the cadence default; explicit 0 means simultaneous starts. For strict sequential line entrances, use slide with interval >= duration.",
    )
    enter_duration: float | None = Field(
        default=None,
        ge=0.0,
        description="One token or line entrance duration, in seconds. Absent = keep; explicit null = restore the default entrance; explicit 0 means an instant appearance.",
    )
    enter_hold_until: float | None = Field(
        default=None,
        ge=0.0,
        description="The entrance hold endpoint, seconds after scene start: a set value is the leave moment — the text leaves at that frame (with exit_duration it fades out across the final stretch). Absent = keep; explicit null = hold to the scene end; a value beyond the scene window rejects with the concrete overflow.",
    )
    motion_start: float | None = Field(
        default=None,
        ge=0.0,
        description="Push/pull motion start, seconds after scene start. Absent = keep; explicit null = restore the full-scene default start.",
    )
    motion_end: float | None = Field(
        default=None,
        ge=0.0,
        description="Push/pull motion end, seconds after scene start. Absent = keep; explicit null = restore the full-scene default end. Must stay after motion_start and inside the scene window.",
    )
    exit_duration: float | None = Field(
        default=None,
        gt=0.0,
        description="Text fade-out seconds at the window's end (the hold endpoint when set, else the scene's end) — the words fade out; the background never fades with them. Absent = keep; explicit null = no exit fade (the scene boundary's own transition carries the leave).",
    )
    motion_scale: float | None = Field(
        default=None,
        gt=1.0,
        le=1.25,
        description="The push/pull move's end scale (null/legacy = 1.06; subtle drift lives around 1.02–1.04). Requires motion push/pull. Absent = keep; explicit null = restore 1.06.",
    )
    align: Literal["left", "center"] | None = Field(
        default=None,
        description="Horizontal text alignment on the words plane (center also centers the camera's zoom origin). Absent = keep; explicit null = restore left.",
    )
    size: Literal["small", "medium", "large"] | None = Field(
        default=None,
        description="Font size tier (medium = the legacy default). Absent = keep; explicit null = restore medium.",
    )
    accent_style: Literal["chip", "color"] | None = Field(
        default=None,
        description="How *emphasized* spans render: chip = the legacy inverted tile; color = the theme's accent color as plain text. Absent = keep; explicit null = restore chip.",
    )
    enter_style: Literal["rise", "fade", "slide"] | None = Field(
        default=None,
        description="The entrance EFFECT (orthogonal to enter's organization): rise = the legacy fade+rise+blur; fade = opacity only — no translate, no blur; slide = deterministic translate only — no opacity ramp, no blur, exact start/end frames. Absent = keep; explicit null = restore rise.",
    )


class FilmEditReorderScenes(BaseModel):
    """``order`` must be an exact permutation of the current scene ids."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["reorder_scenes"]
    order: list[str]


class FilmEditRemoveScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_scene"]
    scene_id: str


class FilmEditSetMusic(BaseModel):
    """``mood``: a library mood name — or ``"off"`` to switch the bed OFF
    (a real terminal state: later versions inherit it, the persona/default
    never re-opens it). ``retime``: keep_cut = swap/remove the track,
    frames untouched (the honest presentation: cuts do NOT ride the new
    beat grid); recut = re-snap beat boundaries and re-check every
    narration window (execution seats, R4). Switching OFF with recut
    re-establishes the timeline on NO grid (a music-less cut)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_music"]
    mood: str
    retime: Literal["keep_cut", "recut"] = "keep_cut"


class FilmEditSetVoiceover(BaseModel):
    """Both directions ride this op. ``enabled=false`` = the pure
    subtraction (the lines stay in the board, unsynthesized).
    ``enabled=true`` re-opens synthesis of the version's OWN existing
    narration lines — zero redesign, never a director call. A board
    carrying NO narration lines rejects with a content-gap refusal
    (``voiceover_needs_narration``): author the lines first
    (``update_scene`` … ``narration=…``), then re-issue — the refusal names
    a writing gap, never a synthesis/voice problem."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_voiceover"]
    enabled: bool


class FilmEditUpdateElement(BaseModel):
    """Field-level edit of ONE element inside a composite scene (ADR-140).

    Addressing is by stable identity — ``scene_id`` + ``element_id`` — never
    by array position. Presence semantics follow the timing fields' law:
    absent = keep the current value; an explicit null restores the field's
    DEFAULT (``at``→0, ``until``/``duration``→the window/range default,
    ``rect``→full canvas, ``fit``→cover, ``tone``→light, ``enter``/``motion``
    and the timing fields→absent default, ``keep_audio``→false, ``z``→0);
    an explicit zero stays zero. ``lines`` and ``source_start``/``source_end``
    have no default to restore — an explicit null on them is an error. Fields
    that do not apply to the element's kind reject ``field_not_applicable``
    (text knobs on a video element, source ranges on a text element, …).
    Changing the asset IDENTITY is not an edit — a different video is a
    different composition, never a silent swap."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update_element"]
    scene_id: str
    element_id: str
    # Text element content (lines are accent-marked copy; an edit re-anchors
    # the element's copy_text corpus and preserves still-corresponding
    # emphasis — the words scene's copy-edit law).
    lines: list[str] | None = Field(default=None, min_length=1)
    tone: Literal["light", "dark", "accent"] | None = None
    # Shared placement / window (scene-relative output seconds).
    at: float | None = Field(default=None, ge=0.0)
    until: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect | None = None
    z: int | None = None
    # Media fit (video + image).
    fit: Literal["cover", "contain"] | None = None
    # Video element source range / play window / original sound.
    source_start: float | None = Field(default=None, ge=0.0)
    source_end: float | None = Field(default=None, gt=0.0)
    duration: float | None = Field(default=None, gt=0.0)
    keep_audio: bool | None = None
    # Text element animation vocabulary (element-window-relative seconds).
    enter: Literal["lines", "words"] | None = None
    motion: Literal["static", "push", "pull"] | None = None
    enter_start: float | None = Field(default=None, ge=0.0)
    enter_interval: float | None = Field(default=None, ge=0.0)
    enter_duration: float | None = Field(default=None, ge=0.0)
    motion_start: float | None = Field(default=None, ge=0.0)
    motion_end: float | None = Field(default=None, ge=0.0)
    # Text element style/exit knobs (the words scene's update law,
    # element-scoped): exit_duration = fade-out seconds at the window's
    # end (the background never fades with the text); motion_scale = the
    # push/pull end scale (requires motion push/pull; null restores 1.06);
    # align = horizontal centering; size = the font tier (56/80/120);
    # accent_style = chip (inverted tile) vs color (accent-ink text);
    # enter_style = rise (fade+rise+blur), fade (opacity only), or slide
    # (translate only, no fade/blur).
    exit_duration: float | None = Field(default=None, gt=0.0)
    motion_scale: float | None = Field(default=None, gt=1.0, le=1.25)
    align: Literal["left", "center"] | None = None
    size: Literal["small", "medium", "large"] | None = None
    accent_style: Literal["chip", "color"] | None = None
    enter_style: Literal["rise", "fade", "slide"] | None = None


class FilmEditSetSubtitles(BaseModel):
    """Create or replace a scene's entire subtitle track; null deletes it.
    Read the current track first when modifying cues/style, preserve everything
    not requested. Times are scene-relative seconds. Works on ALL scene types,
    without narration, audio synthesis, or redesign. Batch one op per scene.
    """

    model_config = ConfigDict(extra="forbid")
    op: Literal["set_subtitles"]
    scene_id: str
    track: SubtitleTrack | None


FilmEditOp = Annotated[
    FilmEditSetSubtitles
    | FilmEditUpdateScene
    | FilmEditUpdateElement
    | FilmEditReorderScenes
    | FilmEditRemoveScene
    | FilmEditSetMusic
    | FilmEditSetVoiceover,
    Field(discriminator="op"),
]


class FilmChangeMoved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    from_index: int
    to_index: int


class FilmChangeEdited(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    fields: list[str]
    # Deterministic side-facts the field list cannot say (e.g. an emphasis
    # whose phrase survived a copy edit but lost its mark) — computed by the
    # diff, never authored. Read-tolerant default: older change sets carry
    # none.
    notes: list[str] = Field(default_factory=list)


class FilmChangeAdded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    scene_type: str


class FilmChangeRemoved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    scene_type: str


class FilmChangeRetimed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    seconds_before: float
    seconds_after: float


class FilmChangeMusic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mood_before: str | None
    mood_after: str
    retime: Literal["keep_cut", "recut"]


class FilmChangeSet(BaseModel):
    """The version-to-version diff — computed BY THE SYSTEM from the base
    and result boards (scene-digest comparison keyed by scene_id), never
    echoed from the requested ops. ``seconds`` deltas live in ``retimed``
    (never double-counted in ``edited``); ``warnings`` carries the
    validator's quality reminders (design-layer seat, empty from ops)."""

    model_config = ConfigDict(extra="forbid")

    moved: list[FilmChangeMoved] = []
    edited: list[FilmChangeEdited] = []
    added: list[FilmChangeAdded] = []
    removed: list[FilmChangeRemoved] = []
    retimed: list[FilmChangeRetimed] = []
    music: FilmChangeMusic | None = None
    voiceover: bool | None = None  # the new value when the op flipped it
    warnings: list[str] = []


class FilmProvenance(BaseModel):
    """交付物血缘 (ADR-129): the presented storyboard's content digest + the
    execution snapshot digest this film was built from — written by the
    birth node after re-proof, never copied blind. Absent on rows born
    before versioning."""

    model_config = ConfigDict(extra="forbid")

    storyboard_digest: str | None = None
    execution_digest: str | None = None


class FilmPayload(BaseModel):
    """Payload for ``outputs[type=film]`` — the launch film's creative facts.

    Timeline semantics: none (a film has no source span — its "source" is the
    captured page, carried in ``source_ref.pages``); the render pipeline rides
    ``render_spec``/``render_status`` exactly like clips (ADR-030 rules 2/3).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""  # the storyboard's LLM-chosen name (null read as "")
    duration: int = 0  # seconds — the allocated total (Σ frames / fps)
    scene_count: int = 0
    # The display-class stamp (same write-point law as ClipPayload.aspect):
    # v1 films are landscape-only, so the stamp is constant at birth.
    aspect: str | None = "16:9"
    provenance: FilmProvenance | None = None


class FilmSpecEnvelope(BaseModel):
    """film-spec read envelope for OutputResponse.render_spec.

    ADR-016 unchanged: the render-side zod schema (apps/render/src/film/
    schema.ts) is THE film contract — the API never re-validates film
    content. This envelope exists so a film output's render_spec survives
    serialization without impersonating ClipSpec (a clip dict fails the
    ``family`` literal, a film dict fails ClipSpec's required ``source`` —
    the union's two branches split deterministically).
    """

    model_config = ConfigDict(extra="allow")

    family: Literal["film"]


class VideoSpecEnvelope(BaseModel):
    """video-spec read envelope (ADR-145) — the third spec family's read side.

    Same posture as FilmSpecEnvelope: the contract lives in
    ``packages/video-spec`` (zod) and the API never re-validates content;
    the envelope exists so a video output's render_spec round-trips
    ``OutputResponse`` serialization without impersonating ClipSpec.
    """

    model_config = ConfigDict(extra="allow")

    family: Literal["video"]


class VideoPayload(BaseModel):
    """Payload for ``outputs[type=video]`` (ADR-145) — a Composition render.

    Timeline semantics ride the pinned CompositionVersion (the output's
    ``composition_id`` / ``composition_version_id`` columns);
    ``composition_digest`` completes the §2.2 three-fact pin. The render
    pipeline rides ``render_spec``/``render_status`` exactly like clips and
    films (ADR-030 rules 2/3).
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


class ClipDub(BaseModel):
    """Cloned-voice dubbed speech; when enabled, replaces the source's audio."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None  # resolved dub audio URL (storage seam)
    enabled: bool = False
    gain_db: float = 0.0


class IntroOutroCard(BaseModel):
    """Intro/outro brand card: text, image, or a short video."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "image", "video"] = "image"
    text: str | None = None  # kind == "text"
    media_url: str | None = None  # kind == "image" | "video" (storage-seam URL)
    # How long the card displays; None -> renderer default (2s).
    duration_seconds: float | None = Field(default=None, gt=0)


class ClipBrand(BaseModel):
    """Resolved brand values baked into the spec at generation time.

    Renderer-agnostic data (no DB ref): the API resolves the persona's
    ``brand`` skin block into these fields so the render service / preview
    never need DB access. ``None`` = renderer falls back to its default look.
    """

    model_config = ConfigDict(extra="forbid")

    caption_color: str | None = None  # hex; overrides the default white caption
    caption_size: int | None = None  # px; overrides the default caption size
    caption_font: str | None = None  # font key: lilita/inter/playfair/source-serif
    intro: IntroOutroCard | None = None  # opening card (None = no intro)
    outro: IntroOutroCard | None = None  # closing card (None = no outro)
    fill_mode: Literal["fill", "fit"] = "fill"  # video objectFit: cover / contain
    # Default from the persona skin block; Clip plan can override per clip.
    caption_enabled: bool = True


class ClipSpec(BaseModel):
    """Renderer-agnostic clip render contract (see docs/VIDEO_EDITOR.md §4)."""

    model_config = ConfigDict(extra="forbid")

    source: ClipSource
    # "original" (2026-08-17, 整条材料化跟源画幅): no fixed tier — the
    # renderer resolves the SOURCE's own dimensions at render time
    # (calculateMetadata). Only materialize_source writes it; excerpt clips
    # always carry a fixed tier.
    aspect: Literal["9:16", "1:1", "16:9", "original"] = "9:16"
    segments: list[ClipSegment] = Field(default_factory=list)
    crop: ClipCrop = Field(default_factory=ClipCrop)
    # Crop data track (ADR-045): sparse framing decisions on the source
    # timeline, sampled per frame by the renderer's sampleCrop. Empty/absent
    # = the static `crop` above (degenerate form, 语义不变).
    crop_track: list[CropKeyframe] | None = None
    caption_track: list[CaptionCue] = Field(default_factory=list)
    # 双语对照轨 (translation_track, 2026-08-14 双语字幕): the translated half
    # of a bilingual caption pair — UNIT-level cues (one per ~10 words, no
    # karaoke word timing), paired with caption_track's word-level ORIGINAL
    # lines by time overlap. Empty = single-language captions. Only
    # translate_clip with spec.bilingual writes it (fork/morph alike).
    translation_track: list[CaptionCue] = Field(default_factory=list)
    # Preset enum, NOT free styling — keeps preview=render parity and the
    # future hand-rolled-FFmpeg swap cheap (CSS ∩ libass subset). The preset
    # ids MIRROR the caption catalog in packages/clip/src/captions.ts, which
    # is the single source of truth for style BEHAVIOR; Python only validates
    # membership. Adding a style = one catalog line + this list.
    caption_style_preset: Literal[
        "clean-bottom", "karaoke-highlight", "fade-in", "pop-in", "slide-up", "stacking"
    ] = "clean-bottom"
    caption_position: Point | None = None  # normalized center; None -> default (bottom)
    caption_enabled: bool = True  # when false, caption_track is not burned into video
    title: ClipTitle = Field(default_factory=ClipTitle)
    music: ClipMusic = Field(default_factory=ClipMusic)
    dub: ClipDub | None = None  # cloned-voice dub; replaces source audio when enabled
    # Layer track (ADR-044): anchor-pinned overlay items (broll / text_callout /
    # pip / motion_graphic). Empty = no layers. No tool writes them yet —
    # insert_broll lands on the 08-19+ line.
    layers: list[ClipLayer] = Field(default_factory=list)
    brand: ClipBrand | None = None  # resolved brand values (None = default look)
    brand_ref: UUID | None = None
    target_language: str = "en"

    @model_validator(mode="after")
    def _unique_item_ids(self) -> "ClipSpec":
        """Anchor addressing is by item id — duplicates would silently
        misresolve (first-match). Enforced at the contract so every write
        path (ops applies round-trip through model_validate) inherits it."""
        seg_ids = [s.id for s in self.segments]
        if len(set(seg_ids)) != len(seg_ids):
            raise ValueError("segments: duplicate ids — anchor addressing requires uniqueness")
        layer_ids = [layer.id for layer in self.layers]
        if len(set(layer_ids)) != len(layer_ids):
            raise ValueError("layers: duplicate ids — anchor addressing requires uniqueness")
        return self

    @model_validator(mode="after")
    def _crop_track_ordered(self) -> "ClipSpec":
        """Crop keyframes ride strictly ascending source seconds — the
        sampler's hold-then-ease semantics need an unambiguous 'latest
        decision' per instant."""
        track = self.crop_track or []
        ts = [k.t for k in track]
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise ValueError("crop_track: keyframe t must be strictly ascending")
        return self


# ---------------------------------------------------------------------------
# Craft skeleton (ADR-078): the decompiler's product — video → clip-spec
# skeleton. An internal output row (INTERNAL_OUTPUT_TYPES member), asset-level
# + content-addressed + reusable (the understand row's reuse discipline). The
# fields layer by determinism: shots / rhythm / aspect / caption scan are
# deterministic detections (zero LLM — craft_scan.py imports no provider); the
# music mood / hook device / capability gaps are the LLM's judgment
# (CraftJudgment, the decompile agent's output schema); content slots stay
# EMPTY — the shot list is structure to fill, it carries timing never content.
# ---------------------------------------------------------------------------


class CraftShot(BaseModel):
    """One detected shot of the exemplar (a scene-cut span, source clock)."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class CraftRhythm(BaseModel):
    """Cut rhythm, measured off the shot list (deterministic)."""

    model_config = ConfigDict(extra="forbid")

    shot_count: int = Field(ge=0)
    cuts_per_minute: float = Field(ge=0)
    median_shot_seconds: float = Field(ge=0)
    # Coarse pace class off the median shot length (<2s fast / ≤4s steady /
    # else slow) — skeleton-internal vocabulary, never a clip-spec field.
    pace: Literal["fast", "steady", "slow"]


class CraftCaptionScan(BaseModel):
    """Burned-in caption findings — visual nearest-neighbor BEST-FIT over the
    contract enums (零 LLM): the preset id lives only inside the
    ClipSpec.caption_style_preset catalog, the color snaps to the craft_scan
    palette. ``present=False`` ⇒ every other field stays None (the remix
    keeps the skin's caption defaults)."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    # Mirrors ClipSpec.caption_style_preset's Literal (the drift gate: the
    # pure suite asserts the two sets stay equal).
    preset: Literal[
        "clean-bottom", "karaoke-highlight", "fade-in", "pop-in", "slide-up", "stacking"
    ] | None = None
    color: str | None = None  # hex, palette-snapped (never a raw sample)
    position: Point | None = None  # normalized center of the detected band


class CraftGap(BaseModel):
    """One observed device the remix cannot reproduce — 契约即能力边界
    (ADR-078 判词②): the honest「做不到 / 还不能」清单 entry, the 带理由纠偏
    substrate (JOURNEYS 旅程二 2b). ``unsupported`` = no seat in the contract
    (L3 line — never promised); ``not_yet`` = a contract seat whose writer
    skill hasn't landed (the layers track's family — a 需求池 candidate)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "motion_graphics",
        "multi_track",
        "transition_effects",
        "speed_ramp",
        "broll_overlay",
        "text_layers",
        "other",
    ]
    severity: Literal["unsupported", "not_yet"]
    detail: str | None = None


class CraftJudgment(BaseModel):
    """The decompile agent's output — ONLY the judgment fields (mood / hook
    device / gaps). 骨架确定性字段零 LLM 介入 is structural here: this schema
    has no aspect/shots/rhythm/caption seat, so the LLM cannot write them
    (the pure suite asserts the disjointness)."""

    model_config = ConfigDict(extra="forbid")

    # Judged from the keyframes (+ transcript when the case has speech) —
    # clamped by code to the assembled catalog's moods, never a free string
    # reaching a spec.
    music_mood: str | None = Field(
        default=None,
        description="The backing music's mood — pick from the provided catalog moods; null when the case carries no music bed.",
    )
    hook_device: str | None = Field(
        default=None,
        description="The opening hook device as a short noun phrase (e.g. 'cold-open question', 'title card', 'silent montage'); null when the opening is plain.",
    )
    gaps: list[CraftGap] = Field(
        default_factory=list,
        description="Effects/devices you OBSERVE that the listed contract cannot express (motion graphics, multi-track compositing, transition effects, speed ramps, b-roll overlays, animated text layers). Only what you actually see.",
    )


class CraftSkeleton(BaseModel):
    """The clip-spec-shaped craft skeleton (ADR-078 判词①) — one exemplar
    video's craft, reverse-compiled.

    内容槽位留空 by construction: ``shots`` is the structure to FILL (timing,
    never content — no text/url/title seats exist). Remix = 内容槽替换
    (判词③): the user's material fills the slots downstream; the style
    fields (captions / music mood / rhythm / aspect) ride as
    exemplar-derived params, code-mapped (LLM 永不写 spec, 判词⑤).
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    # Deterministic layer (craft_scan, zero LLM):
    aspect: Literal["9:16", "1:1", "16:9"]
    duration_seconds: float = Field(ge=0)
    shots: list[CraftShot] = Field(default_factory=list)
    rhythm: CraftRhythm
    captions: CraftCaptionScan
    # LLM layer (the decompile agent's judgment; None when the call degraded):
    music_mood: str | None = None
    hook_device: str | None = None
    gaps: list[CraftGap] = Field(default_factory=list)


# ADR-030 rule 1: payload is the default home and a schema registry guards the
# door. Write = model_dump(); read = parse back into the typed model (same
# pattern as render_spec/ClipSpec). The registry sits BELOW the craft classes
# (2026-09-16 boot fix): every value must be defined by this line — T5 ①'s
# forward reference to CraftSkeleton made the whole module unimportable.
OUTPUT_PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "clip": ClipPayload,
    "film": FilmPayload,
    "video": VideoPayload,
    "post": Post,
    "quotes": Quotes,
    "quote_frame": QuoteFrame,
    "carousel": CarouselResponse,
    "article": Article,
    "material_understanding": MaterialUnderstanding,
    "storyboard": Storyboard,
    "craft_skeleton": CraftSkeleton,
}


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


class ModelFact(BaseModel):
    """One model/provider fact about a product (ADR-051 H). ``modality`` is
    the UI's grouping key (copy / voice / captions / music — localized via
    the composer models panel's keys); ``model`` is the display name, DATA
    (a proper noun — locale-invariant)."""

    modality: str
    model: str


class TrackStackVideoBlock(BaseModel):
    """One kept segment of a clip product on the OUTPUT timeline, plus its
    SOURCE range and the source asset's id (the cross-highlight's data —
    ADR-113 §6; None when the spec carries no asset identity). ``src_label``
    / ``out_label`` are the preformatted ``m:ss–m:ss`` source/output ranges
    (the client never formats time)."""

    model_config = ConfigDict(extra="forbid")

    out_start: float
    out_end: float
    src_start: float
    src_end: float
    asset_id: str | None = None
    src_label: str = ""
    out_label: str = ""


class TrackStackTextBlock(BaseModel):
    """One caption sentence on the OUTPUT timeline (ADR-113 §4) — text +
    preformatted ``m:ss–m:ss`` label (the client never formats time)."""

    model_config = ConfigDict(extra="forbid")

    out_start: float
    out_end: float
    text: str
    label: str


class TrackStackRulerTick(BaseModel):
    """One scale tick on the NLE axis's ruler (ADR-115): ``label`` is
    preformatted (the origin reads bare "0"; the client never formats time).
    Every rendered tick is labeled — a major cramped by the named end leaves
    the scale, never rides unlabeled."""

    model_config = ConfigDict(extra="forbid")

    t: float
    label: str


class TrackStackResponse(BaseModel):
    """The deliverable card's track-stack inspection face (ADR-113 §4;
    ADR-115 NLE 轴): video lane (kept segments concatenated on the output
    clock) + text lane (caption sentences per segment, cut = hard break) +
    the ruler scale + modifier presence. Read-only — never an orchestration
    surface (L3). Derived at read time from ``render_spec``; None on
    non-clip products."""

    model_config = ConfigDict(extra="forbid")

    video_lane: list[TrackStackVideoBlock]
    text_lane: list[TrackStackTextBlock]
    ruler: list[TrackStackRulerTick] = []
    modifiers: dict[str, bool]


class OutputResponse(BaseModel):
    """Unified product row (ADR-030): clips and derivatives became types.

    ``payload`` is validated against ``OUTPUT_PAYLOAD_SCHEMAS`` at the API
    boundary; ``files``/``publishing`` URLs are resolved through the storage
    seam exactly like the retired ClipResponse did.
    """

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
    render_spec: ClipSpec | FilmSpecEnvelope | VideoSpecEnvelope | None = None
    render_status: RenderStatus | None = None
    render_error: str | None = None
    # Composition lineage (ADR-145): set on video-family outputs only.
    composition_id: UUID | None = None
    composition_version_id: UUID | None = None
    # The immutable content version's real sequence number, not an Output
    # count. Multiple deliveries may honestly show the same number.
    composition_version_number: int | None = None
    score: dict | None = None
    # 质检裁决 (期 3): verify 节点的 {status, checks, attempt, checked_at};
    # None = 未质检（旧行 / 无 verify 的图）。
    quality: dict | None = None
    publishing: dict = Field(default_factory=dict)
    # Display-layer aspect (产物展示统一 P1, 2026-08-27): server-side single
    # derivation — ``render_spec.aspect`` (clip family) → payload-declared
    # ``aspect`` (image products) → None; the ``"original"`` sentinel
    # normalizes to None (the frame follows the source, unknown here).
    aspect: str | None = None
    # Chain-integrity hash of render_spec (ADR-032) — the client's base_hash
    # for operation batches. None when there is no render_spec.
    spec_hash: str | None = None
    # Per-product spec prompt (ADR-051 F — hover prompt 框): the producing
    # step's slot/params composed into a prompt-style line in the run's
    # pinned ui_language. Stamped ONLY by the /results endpoint (the sole
    # place outputs and their producing steps meet); None elsewhere and for
    # carried rows whose step isn't in the payload.
    spec_prompt: str | None = None
    # Per-product model/provider facts (ADR-051 H — 详情面模型事实): the
    # producing step's kind projected to its real model usage (one provider
    # per modality today — a fact registry, never a selector / SKU shelf,
    # 禁令2). Stamped ONLY by /results alongside spec_prompt; None elsewhere
    # and for carried rows. Display-only — the node caption NEVER carries a
    # model name (prohibition #12); the lightbox info column is the surface.
    model_facts: list[ModelFact] | None = None
    # The track-stack inspection face (ADR-113 §4 — video lane + text lane
    # on the output timeline): derived at read time from render_spec by the
    # /graph + /results seats (transient stamp, never persisted); None for
    # non-clip products and everywhere else.
    track_stack: TrackStackResponse | None = None
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

        for key in ("video", "srt", "image"):
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
        clip family declares via ``render_spec.aspect``; image products
        declare ``payload["aspect"]`` at the write point; ``"original"``
        and empty values normalize to None (unknown frame — surfaces
        fall back to their default tier or the shared probe)."""
        declared = self.payload.get("aspect") if isinstance(self.payload, dict) else None
        candidates = (
            # film specs carry no aspect (the family is landscape-fixed) —
            # getattr, never attribute access: the envelope has no such field.
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


class CaptionTranslation(BaseModel):
    """LLM caption-translation result: translated lines, parallel to the input."""

    model_config = ConfigDict(extra="forbid")

    lines: list[str] = Field(default_factory=list)


class SpeakerFormGate(BaseModel):
    """M3 form-gate verdict for a video asset's frame grid (ADR-045 D4).

    ``scene`` classifies the setup (a two-person face-to-face ``interview``,
    a one-speaker ``presentation``/stage talk, or ``other``); low
    ``confidence`` sends the gate to its one confirmation grid (2 calls cap).
    The people count is NOT the LLM's job (ADR-106 聚合判定: local per-frame
    majority) — the grid verdict carries only the scene semantics the
    aggregate can't see.
    """

    model_config = ConfigDict(extra="forbid")

    scene: Literal["interview", "presentation", "other"]
    confidence: Literal["high", "low"] = "high"


class SpeakerArbitration(BaseModel):
    """M3 arbitration verdict for one ambiguous interview turn (ADR-045 D3):
    a short mid-turn video clip (audio included) → which side is speaking
    (screen ``left`` / ``right``), or ``unclear`` (caller falls back to the
    energy argmax).
    """

    model_config = ConfigDict(extra="forbid")

    speaker: Literal["left", "right", "unclear"]


class ExtractedPersonaMemory(BaseModel):
    """LLM persona-extraction result; maps directly to Persona DB columns.

    ``name`` is the LLM-synthesized persona label (e.g. "Pragmatic AI
    evangelist") — used as the Persona.name when the pipeline auto-creates a
    persona, so the row is never named after an uploaded file. Ignored on
    manual regenerate, where the user owns the name.
    """

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


class TranslateCaptionsRequest(BaseModel):
    """Re-translate a clip's caption track into ``target_language``."""

    target_language: str = Field(description="Target language code, e.g. en/fr/de/es/it")


class DubRequest(BaseModel):
    """Voice-clone dub a clip into ``target_language`` (the persona's own voice)."""

    target_language: str = Field(description="Target language code, e.g. en/fr/de/es/it")


class GenerateResponse(BaseModel):
    """Result of ``POST /projects/{id}/generate`` (202 Accepted) — typed so
    the contract can evolve under schema protection (B3: was a bare dict)."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: WorkflowStatus


class GraphReviseRequest(BaseModel):
    """The card-face prompt direct edit (ADR-058 — deterministic graph action,
    not a chat turn): rewrite ONE node's program with the user's verbatim
    words and re-fill it with its downstream. Ops are constructed by code —
    zero intent recognition (the node id is structurally exact), zero chat
    messages (the node's own state cycle is the whole feedback)."""

    model_config = ConfigDict(extra="forbid")

    node_id: UUID
    prompt: str = Field(min_length=1)


class GraphReviseResponse(BaseModel):
    """Result of ``POST /projects/{id}/graph/revise`` (202 Accepted)."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: WorkflowStatus


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


class GenerateRequest(BaseModel):
    """Generate content request."""

    # The confirmed task chain (ADR-043 — the plan path's only grammar).
    # Required for full-scope requests (422 otherwise — the plan is
    # built and confirmed via the chat plan path); None only on targeted
    # scopes (hook/clip/derivative/render re-run one node family off
    # target_id).
    tasks: list[TaskItem] | None = None
    tone_settings: ToneSettings | None = None
    target_language: str | None = Field(
        default=None,
        description=(
            "Spec-level language fallback, e.g. en/zh/fr/de/es/it. Language "
            "is a per-task param now — None derives from the first task that "
            "carries one (fallback en)."
        ),
    )
    instruction: str | None = Field(
        default=None,
        description="User steering prompt: what to focus on / produce.",
    )
    scope: Literal[
        "full", "hook", "clip", "post", "quotes", "derivative", "translation", "render"
    ] = Field(
        default="full",
        description="Scope of the generation: full project or targeted revision.",
    )
    target_id: UUID | None = Field(
        default=None,
        description="Clip or derivative ID when scope is not 'full'.",
    )
    operation: Literal[
        "regenerate", "shorten", "lengthen", "translate", "render"
    ] = Field(
        default="regenerate",
        description="Operation to apply when scope is targeted.",
    )
    # Retry-reference echo (ADR-087 §4 D2, Phase 4 B5): the client names
    # WHICH historical confirmed scope it means — these ride into the
    # TaskSpec verbatim so an exact retry's run.context equals the
    # original's. They are NEVER authorization proof (Rule 9): the
    # server-side gate proves chain equality against persisted run.context
    # rows; a client-invented combination simply matches nothing → 422
    # scope.unproven.
    persona_id: str | None = Field(
        default=None,
        description="The run-pinned persona of the chain being retried (echo of run.context).",
    )
    caption_mode: Literal["bilingual", "source_only", "target_only"] | None = Field(
        default=None,
        description="The caption mode of the chain being retried (echo of run.context).",
    )
    source_asset_id: str | None = Field(
        default=None,
        description="The source-role asset pin of the chain being retried (echo of run.context).",
    )
    exemplar_asset_id: str | None = Field(
        default=None,
        description="The exemplar-role asset pin of the chain being retried (echo of run.context).",
    )


class ExportRequest(BaseModel):
    """Export project content request."""

    formats: list[Literal["text", "images"]] = Field(
        default_factory=lambda: ["text"]
    )


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


class FeedbackRequest(BaseModel):
    """Feedback request."""

    scope: FeedbackScope
    reason: FeedbackReason
    detail: str | None = None


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
    """One node of the project's persistent graph (ADR-057 — the graph IS
    the product object; the canvas reads this frame directly, zero
    projection).

    ``spec`` is the node's program (prompt / params / estimate / role /
    fill_key — the node type's own shape, never interpreted at the API
    boundary); ``layout`` is the settled canvas frame (画布定居取景,
    append-only). ``estimate_credits`` folds the node's quotation to
    credits at read time (same serialization-layer rule as StepResponse).
    ``asset`` / ``outputs`` are the joined display rows: the asset node
    carries its asset row; a producer node carries its product rows
    (``spec.output_ids`` resolved, visibility-filtered, created_at
    ascending — the card's pager order)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # The family word (词表 v3, ADR-076 / C5b): medium five values +
    # server-internal birth words, mapped through _read_face for legacy rows.
    # Distinct from ``step.kind`` (the tool name, N-35).
    type: str
    state: str
    spec: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)
    estimate_credits: list[int] | None = None
    # Read-time Product Graph projection (I-PFA-02 / 合同 §7 C-1 约束❶):
    # the node's topological depth over the read-frame Product DAG, computed
    # by product_graph.product_ranks at read time. NOT persisted node state,
    # NOT an independent graph authority — never store it, never let it
    # outrank the DAG itself. None = the legacy compatibility state (a
    # B4-lite-gate survivor the predicate does not rank).
    rank: int | None = None
    asset: AssetResponse | None = None
    outputs: list[OutputResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class GraphEdgeResponse(BaseModel):
    """One typed flow of the persistent graph (ADR-057 port law)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_node: UUID
    from_port: str
    to_node: UUID
    to_port: str
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


class ProjectArtifactFacet(BaseModel):
    """One facet's summary on the deliverable card (ADR-097 §3 — the facet
    exits the default projection; its program/state stay inspectable here).
    ``surface="hidden_modifier"`` marks the lever surfaces (LEVER_TOOLS 兼容
    共存, 两层门不合并)."""

    node_id: UUID
    tool: str | None = None
    label: str | None = None
    state: str
    surface: str | None = None


class ProjectArtifactActivity(BaseModel):
    """The artifact's single activity owner (ADR-097 §4 — one aggregated
    activity state per artifact; member-level location only on failure)."""

    state: str
    failed_node_ids: list[UUID] = Field(default_factory=list)


class ProjectArtifact(BaseModel):
    """One product artifact's read-face block (ADR-097 Phase 1 — additive
    projection off the stamped canonical four fields; membership is a
    compile-time fact, never read-time inference). ``current_output_id`` =
    the live version's唯一归属 (one live output lands on at most one card);
    archived versions keep their historical ownership (ADR-091)."""

    artifact_key: str
    work_key: str
    name: str | None = None
    deliverable_node_id: UUID | None = None
    facet_node_ids: list[UUID] = Field(default_factory=list)
    facets: list[ProjectArtifactFacet] = Field(default_factory=list)
    companion_node_ids: list[UUID] = Field(default_factory=list)
    current_output_id: UUID | None = None
    archived_output_ids: list[UUID] = Field(default_factory=list)
    activity: ProjectArtifactActivity


class ProjectGraphResponse(BaseModel):
    """The project graph's one read frame — nodes + edges + joined display
    rows, everything the canvas renders, in one fetch."""

    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)
    lifecycle: LifecycleStamp | None = None
    # ADR-097 Phase 1 (additive): the artifact projection — one deliverable
    # one card, facets summarized, companions first-class. Unknown/legacy
    # nodes never appear here (passthrough on the default projection).
    artifacts: list[ProjectArtifact] = Field(default_factory=list)


class ProjectResultsResponse(BaseModel):
    """Aggregated results for the project detail/results page."""

    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    prompt: str | None = None
    outputs: list[OutputResponse] = Field(default_factory=list)
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

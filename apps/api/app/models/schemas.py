"""Pydantic models for Repurposer API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
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


class FocusRef(BaseModel):
    """The canvas product a turn is pointed at (ADR-041 D8 焦点注入).

    Rides the turn as one context line (an instruction naming no other target
    resolves to it) and persists on the user message ({id, label},
    denormalized like mentions) so the rebuilt history renders the gray
    focus prefix row after a refresh. Not a second intent entry: the mention
    registry stays the definite-reference channel.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str


class AskOption(BaseModel):
    """One option on a structured ask (choice kind)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str


class AskPayload(BaseModel):
    """The typed ``question`` payload on a message (ask primitive).

    The mechanism words live here — ``kind`` carries the *use* (task book
    confirmation, a choice, a cost quote later), never combined with the
    mechanism (NAMING: use × mechanism combos are banned). ``content`` on the
    message row keeps the question's human text.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["task_book", "choice", "confirm"]
    options: list[AskOption] = Field(default_factory=list)
    allow_freeform: bool = True
    # The stored cost-quote seat. Its supply is code, never the LLM: the
    # estimate fold (N-34) — wired in with the week-6 presentation (dock
    # total / chat unit price); NULL until then.
    estimate: str | None = None
    # task_book only: the needs_clarification reason KEYS (data, localized at
    # render — never baked into `content`, which is user-facing prose).
    reasons: list[str] = Field(default_factory=list)


class AnswerPayload(BaseModel):
    """The typed ``answer`` payload on a message.

    ``bail`` is a first-class answer kind — a graceful exit, never a failure.
    ``start`` is the task_book confirmation (the answer that starts the run)
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
    """Confirm the docked task book and start the run (task_book questions).

    Replaces the phase-1 magic ``option_id="start"`` — the confirmation is a
    kind of its own, so the kind-specific fields (autonomy tier, the review
    panel's edited task book) are only valid here, never silently ignored on
    other kinds (C2).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["start"]
    # Autonomy tier carried into the run (dock toggle, §2.7); None = auto.
    autonomy: Literal["auto", "review"] | None = None
    # The review panel's edited task book (hand-edited slots marked explicit).
    # Wins over the stored pending intent, so panel edits reach the run;
    # None = use the stored pending intent.
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


class ChatMessageResponse(BaseModel):
    """A single chat message returned by the API."""

    model_config = ConfigDict(from_attributes=True)

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
    created_at: datetime
    updated_at: datetime | None = None


class MessageListResponse(BaseModel):
    """List of chat messages in a session."""

    items: list[ChatMessageResponse]


class TaskListProposal(BaseModel):
    """Intent agent output, state A: run new tasks (→ compile_graph mode②).

    ``tasks=[]`` is the legal "ask back" state (CHAT_ARCH §7) — an ambiguous
    instruction gets a clarifying reply in ``summary``, not a run.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["task_list"] = "task_list"
    tasks: list[TaskItem] = Field(default_factory=list)
    summary: str


class EditOp(BaseModel):
    """One clip-spec-level edit operation (Operation Model vocabulary, §9).

    v1 only pins the boundary (edit ops → no run); the op set is finalized
    with the Operation Model, so the op key tolerates ``type`` and extra keys
    are stored verbatim.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    op: str = Field(default="", validation_alias=AliasChoices("op", "type"))
    target: str | None = None
    params: dict = Field(default_factory=dict)


class EditOpsProposal(BaseModel):
    """Intent agent output, state B: edit an existing output (→ Operation
    Model, v2 — v1 answers with the boundary text and creates no run)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["edit_ops"] = "edit_ops"
    target_output_id: UUID
    ops: list[EditOp] = Field(default_factory=list)
    summary: str


class AskProposal(BaseModel):
    """Intent agent output, state C: a structured ask (→ QuestionDock).

    N-18 (overturning N-14): the structured-ask payload is orthogonal to
    task_list / edit_ops, so the union gains a third state. The pre-N-18
    "tasks=[] ask back" migrates here as an ``options=[]`` + ``allow_freeform``
    ask. ``kind`` carries the *use* (NAMING N-19): choice is the chat loop's
    question; task_book is raised by the chat plan path, never by the
    agent; confirm is the reserved seat for the cost quote (v3).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["ask"] = "ask"
    question: str
    kind: Literal["choice", "task_book", "confirm"] = "choice"
    options: list[AskOption] = Field(default_factory=list)
    allow_freeform: bool = True


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
    TaskListProposal | EditOpsProposal | AskProposal | AnswerProposal,
    Field(discriminator="type"),
]
"""The four-state discriminated union the chat intent agent returns (§3, N-18 + N-21)."""


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


class AnswerResponse(BaseModel):
    """Result of ``POST /chat/messages/{id}/answer``.

    The answer endpoint doubles as the resume mechanism (NAMING: answer =
    resume): ``answered_question`` is the settled question (the QA archive
    row — same name as ``ChatResponse.answered_question``, same role), and
    ``follow_up`` is the assistant's continuation when the answer unblocks
    the conversation (choice kind — the pick rides into the next turn).
    """

    answered_question: ChatMessageResponse
    follow_up: ChatMessageResponse | None = None


class ChatRequest(BaseModel):
    """Send a message to the project's chat.

    The backend locates or creates the project conversation, builds the
    context, and dispatches any background work. Asset-scoped conversations
    are retired (ADR-041 D8 — 产物对话归 dock + 焦点注入): a product the user
    points at rides as ``focus_output`` (one context line), never as a
    separate conversation scope.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    message: str
    attachments: list[ChatAttachment] = Field(default_factory=list)
    mentions: list[ChatMention] = Field(default_factory=list)
    # The canvas's focused product (ADR-041 D8 焦点注入): the output the user
    # last pointed at. Carried per turn (one context line on the chat loop)
    # and persisted on the user message — the history's focus prefix row.
    focus_output: FocusRef | None = None
    # Plan-path transports (intent-surface-unification W3 — carry only, never
    # persisted on the message):
    # The review panel's current task book (the user may have hand-edited the
    # chain). Panel edits ARE task-list mutations (ADR-043) — the panel's
    # chain is shown to the PlanAgent as the presented plan and re-emitted
    # whole on every revision, so hand edits survive unless the message
    # revises them; None = the stored pending intent is presented, if any.
    prior_intent: "InferredIntent | None" = None
    # The composer's persona choice rides the first message; written into the
    # pending intent only when the plan path docks a task book (a later turn
    # omitting it never clobbers the stored choice).
    persona_id: UUID | None = None
    # The dock's autonomy tier (§2.7) — consumed only when this turn confirms
    # the task book by prose (PlanAgent verdict "start"): a typed "looks
    # good, start it" must not silently drop a review-tier choice.
    autonomy: Literal["auto", "review"] | None = None


class TaskItem(BaseModel):
    """One LLM-proposed task: a registry skill plus its params (CHAT_ARCH §3).

    The LLM proposes; ``compile_graph`` adjudicates existence, params and
    topology against ``app/skills/__init__.py`` — the LLM never writes node specs.
    """

    model_config = ConfigDict(extra="forbid")

    skill: str
    params: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Result of sending a chat message.

    ``answered_question`` is the pending question this turn settled via
    deterministic autoResume (option letter/number/label hit, or freeform)
    — the frontend archives it as a QA pair before the assistant's reply.
    """

    conversation_id: UUID
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    run_id: UUID | None = None
    answered_question: ChatMessageResponse | None = None


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
    sentence_style: str = ""
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] = "rational"
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
    """任务槽: one line of the task book — one requested output (request layer).

    N-20 layering: the IntentSlot says WHAT the user wants; the director's
    ``StoryboardSlot`` (派工层） says how the work is assigned. ``None`` fields
    mean "task-book default": count → the per-type default (clips 3 / quotes 3
    / carousel 6). Language is a per-slot property (2026-08-05 restructure —
    the book-level field is retired): ``None`` is legacy/read-tolerant and
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
        task books (pre-slot) deserialize through this; new writes never
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
        import app.skills  # noqa: F401
        from app.pipeline.graph import known_output_types

        if self.type not in known_output_types():
            raise ValueError(f"Unknown output type: {self.type}")
        return self


_SLOT_TO_SKILL = {
    # Legacy outputs-grammar slot type → its producing skill (ADR-043 read
    # tolerance for stored pending_intent rows — never written).
    "clips": "select_clips",
    "post": "write_post",
    "quotes": "write_quotes",
    "carousel": "write_carousel",
    "article": "write_article",
}


def _legacy_slots_to_tasks(data: dict) -> list[dict]:
    """outputs-grammar book → task list (ADR-043): each slot becomes its
    producing skill's task (slot fields sink to params — params models ignore
    stray keys at adjudication); the retired book-level modifiers fan out
    into per-language transform tasks; a book-level aspect rides the clips
    task. Read tolerance only — new writes are born as task lists."""
    tasks: list[dict] = []
    aspect = data.get("aspect")
    for slot in data.get("outputs") or []:
        if isinstance(slot, str):
            slot = {"type": slot}
        if not isinstance(slot, dict):
            continue
        skill = _SLOT_TO_SKILL.get(slot.get("type"))
        if skill is None:
            continue
        params = {
            k: slot[k]
            for k in ("count", "focus", "language", "tone_override")
            if slot.get(k) is not None
        }
        if skill == "select_clips" and aspect:
            params["aspect"] = aspect
        tasks.append({"skill": skill, "params": params})
    for lang in data.get("dub_languages") or []:
        # fork: the slots-era compile produced dub/translate as fork nodes
        # (derived rows, source untouched) — the upgrade keeps that shape.
        tasks.append(
            {"skill": "dub_clip", "params": {"target_language": lang, "fork": True}}
        )
    bilingual = bool(data.get("caption_bilingual"))
    for lang in data.get("caption_languages") or []:
        tasks.append(
            {
                "skill": "translate_clip",
                "params": {
                    "target_language": lang,
                    "bilingual": bilingual,
                    "fork": True,
                },
            }
        )
    return tasks


class InferredIntent(BaseModel):
    """The PlanAgent's verdict: three actions + the proposed skill chain.

    ADR-043 (outputs → derive): the request layer carries NO output
    declarations — ``tasks`` is the only grammar (a registry skill + its
    params, the same shape the chat loop's task_list proposals use). Outputs
    are a derived projection of the compiled graph, never a request field.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_legacy_shape(cls, data: Any) -> Any:
        """Upgrade stored legacy books on read (never written): the pre-slot
        flat shape → slots, the slots/modifiers grammar → a task list; the
        retired keys (outputs / tone / the four book-level modifiers) are
        stripped. Read tolerance for stored ``pending_intent`` rows only."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # An explicit ``tasks: null`` (the LLM's habit on start/answer
        # verdicts) reads as "no opinion" — dropping the key lets the field
        # default apply instead of failing validation.
        if data.get("tasks") is None:
            data.pop("tasks", None)
        # 2026-08-05 restructure leftover: legacy stored books carry
        # book-level ``language`` / ``language_explicit`` — strip on read.
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
        return data

    action: Literal["generate", "answer", "start"] = Field(
        default="generate",
        description=(
            "Whether the user wants to generate content, is asking a question "
            "about the tool's capabilities, or is confirming the proposed task "
            "book ('start' — a prose 'looks good, go ahead' in the confirm "
            "phase, not a revision)."
        ),
    )
    answer: str | None = Field(
        default=None,
        description="Direct answer text when action is 'answer'. Null for generate.",
    )
    material_text: str | None = Field(
        default=None,
        description=(
            "Verbatim source text the user explicitly declared as their own "
            "material ('this is my transcript: …', '这是我的文字稿：…'). Null "
            "when the user did not declare pasted text as source material — "
            "a bare request is never material."
        ),
    )
    tasks: list[TaskItem] = Field(
        default_factory=list,
        description=(
            "The proposed skill chain — one task per piece of work, in "
            "execution order (e.g. an English and a German post = two "
            "write_post tasks; whole-video bilingual subtitles = one "
            "translate_clip task). Empty for start/answer verdicts."
        ),
    )
    specific_instruction: str | None = Field(
        default=None,
        description="Free-form instruction distilled from the prompt.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tasks_explicit: bool = Field(
        default=False,
        description=(
            "True when the user explicitly named the work themselves. "
            "False when the chain is the default proposal."
        ),
    )


class PendingIntent(BaseModel):
    """Unconfirmed task book persisted on ``projects.pending_intent``.

    Written by the chat plan path on generate-action turns (an
    answer-action turn never overwrites the stored book), cleared once the
    run starts. Lets a user who left the plan-confirmation chat resume it
    exactly, from any device.
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
    intent: InferredIntent
    reasons: list[str] = Field(default_factory=list)
    persona_id: UUID | None = None
    # Derived preview (ADR-043): the dry-run-compiled graph's user-facing
    # projection — what this chain will produce — computed at dock time
    # (outputs are derived, never declared). Rows: {"type": "video"|"clips"|
    # "post"|"quotes"|"carousel"|"article", "variant": "subs"|"dub"|None,
    # "language"?, "count"?, "bilingual"?}. Empty on legacy rows.
    derived: list[dict] = Field(default_factory=list)


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
    processed_at: datetime | None = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stream_url(self) -> str | None:
        """Browser-playable URL for this asset, resolved through the storage seam."""
        from app.tools.storage import stream_url

        return stream_url(self.file_url)


class AssetUploadUrlRequest(BaseModel):
    """Request a presigned PUT URL for direct upload to object storage."""

    filename: str
    content_type: str = "application/octet-stream"


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
    """Generated quote card."""

    model_config = ConfigDict(extra="forbid")

    quote: str
    attribution: str


class Quotes(BaseModel):
    """Multiple quote cards response."""

    model_config = ConfigDict(extra="forbid")

    quotes: list[Quote] = Field(default_factory=list)


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
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    asset_id: UUID | None = None
    url: str | None = None
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    hidden: bool = False
    provenance: Literal["real", "generated"] | None = None


class ClipCrop(BaseModel):
    """9:16/1:1 reframe as a normalized center + scale (applied via transform)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    scale: float = Field(default=1.0, gt=0.0)


class CaptionCue(BaseModel):
    """One caption cue (word/line) from ASR word-level timestamps; text editable."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    lang: str = "en"


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


# ---------------------------------------------------------------------------
# Director two-step (RunPlan Phase 2): the retired single-pass ContentPlan is
# replaced by a material-scoped understanding (reusable via asset hash) and a
# request-scoped storyboard (re-planned every run). docs/tasks/director-two-step.md
# ---------------------------------------------------------------------------


class KeyArgument(BaseModel):
    """One key argument of the talk, with its transcript location."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable id within the understanding (a1, a2, …)")
    text: str
    # Display alternates (checkpoint options render in the UI language,
    # never the material's): faithful English / Simplified-Chinese
    # renderings of the same argument. Empty on legacy cached payloads —
    # the display layer falls back to ``text``.
    text_en: str = ""
    text_zh: str = ""
    # Free-text location marker — the director never sees word-level
    # timestamps, so an honest text marker instead of fake seconds.
    position: str = ""


class MaterialUnderstanding(BaseModel):
    """素材理解: director step 1 — what the material says (material-scoped).

    Pure: built from source texts/media only — never persona, tone,
    instruction, or target language — so it stays reusable across runs,
    languages, and task books (asset-hash invalidation).
    """

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_thesis: str
    key_arguments: list[KeyArgument] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    # Verbatim sentences from the material, in the source language.
    quote_candidates: list[str] = Field(default_factory=list)


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
    """分镜表: director step 2 — request-scoped assignments (re-planned every run).

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


# ADR-030 rule 1: payload is the default home and a schema registry guards the
# door. Write = model_dump(); read = parse back into the typed model (same
# pattern as render_spec/ClipSpec).
OUTPUT_PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "clip": ClipPayload,
    "post": Post,
    "quotes": Quotes,
    "carousel": CarouselResponse,
    "article": Article,
    "material_understanding": MaterialUnderstanding,
    "storyboard": Storyboard,
}

# Internal types are node artifacts, not user-facing products. Every read path
# must exclude them via ``services.outputs.visible_outputs`` — never hand-roll a
# type filter (results/library/export, and future MCP/gallery surfaces).
# ``content_plan`` stays listed so pre-Phase-2 rows remain hidden.
INTERNAL_OUTPUT_TYPES: frozenset[str] = frozenset(
    {"content_plan", "material_understanding", "storyboard"}
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
    brand: ClipBrand | None = None  # resolved brand values (None = default look)
    brand_ref: UUID | None = None
    target_language: str = "en"


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
    # Output row ids this node produced — the RunCard collects these on run
    # completion to inline the product cards (chat-loop-v2).
    output_refs: list[UUID] = Field(default_factory=list)
    # DAG edges: upstream step ids (the RunFlowGraph's edge table, ADR-036).
    inputs: list[UUID] = Field(default_factory=list)
    # Canvas 渲染单元 (ADR-041 D6 修订 2026-08-12) — the node class's
    # self-described artifact identity, lifted by the serializer: steps
    # sharing a ``canvas_key`` within one run merge into ONE canvas node
    # ("plan" = understand+checkpoint+plan); None folds into the 过程脊;
    # ``canvas_hidden`` never renders (render projects onto the product
    # card). View behavior only; the row set is always full.
    canvas_key: str | None = None
    canvas_hidden: bool = False
    # The canvas node's body copy (e.g. the checkpoint's full direction
    # answer) — None = the surface falls back to ``summary``.
    canvas_text: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


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
    language: str
    status: str
    provenance: str
    payload: dict
    files: dict = Field(default_factory=dict)
    source_ref: dict | None = None
    render_spec: ClipSpec | None = None
    render_status: RenderStatus | None = None
    render_error: str | None = None
    score: dict | None = None
    publishing: dict = Field(default_factory=dict)
    # Chain-integrity hash of render_spec (ADR-032) — the client's base_hash
    # for operation batches. None when there is no render_spec.
    spec_hash: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

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
        from app.tools.storage import resolve_stored_url

        for key in ("video", "srt", "image"):
            if self.files.get(key):
                self.files[key] = resolve_stored_url(self.files[key])
        if self.publishing.get("cover_image_url"):
            self.publishing["cover_image_url"] = resolve_stored_url(
                self.publishing["cover_image_url"]
            )
        return self


class CaptionTranslation(BaseModel):
    """LLM caption-translation result: translated lines, parallel to the input."""

    model_config = ConfigDict(extra="forbid")

    lines: list[str] = Field(default_factory=list)


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


class GenerateRequest(BaseModel):
    """Generate content request."""

    # The confirmed task chain (ADR-043 — the plan path's only grammar).
    # Required for full-scope requests (422 otherwise — the task book is
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
    autonomy: Literal["auto", "review"] | None = Field(
        default=None,
        description=(
            "Autonomy tier for this run (intent-ask-primitive §2.7): auto = "
            "no optional interruptions (default); review = full runs pause at "
            "the direction checkpoint (phase 4). Stored verbatim on run.context."
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


class ProjectResultsResponse(BaseModel):
    """Aggregated results for the project detail/results page."""

    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    prompt: str | None = None
    outputs: list[OutputResponse] = Field(default_factory=list)
    latest_run: RunResponse | None = None
    assets: list[ProjectAssetStatus] = Field(default_factory=list)
    pending_intent: PendingIntent | None = None


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

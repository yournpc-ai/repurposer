"""The bounded tool-loop harness form (ADR-077 判词② — 会话层工具 loop 化).

The chat intent surface's call shape: the model speaks prose on the content
channel (it streams — the typewriter law holds natively) and closes the turn
by calling ONE terminal tool — the action union's mechanical translation
(ask → ``ask_user``, draft → ``present_plan``, start → ``start_run``,
task_list → ``propose_tasks``, precise edit → ``edit_output``, wiring →
``edit_graph``; the answer states close with the ``answer`` tool or bare
prose). The loop exists for TWO reasons: a rejected tool call — schema-class
truncation (``LLMSchemaError`` at the client seam), params validation, or the
execution's own guardrails (出书门槛搬进执行内) — feeds structured feedback
back and the model iterates, bounded; and the NON-terminal read tools (T2b's
perception family, ``app/chat/perception/``) let the model look at the world
before it closes — read-before-write is the relative-revision/recommendation
journeys' functional premise (JOURNEYS 旅程三). 修复/错误反馈语义同构 across
the wire tiers (ADR-077 判词④ 法则).

Guardrails (三条军规):

- ``max_iterations`` 封顶 — declared per agent (the two Chat entrances use 20).
  The loop's worst case is a fold: cap × one call's cost, never open-ended
  (报价 = fold 的会话层形态 — chat turns aren't pre-quoted, the bound is
  what makes that safe).
- 终态工具一调即停 — a terminal tool's accepted call ends the turn. The
  perception family's tools are declared ``terminal=False``: an accepted
  read feeds its observation back on the wire (assistant tool_call +
  role:tool result — the standard continuation) and the loop iterates.
- 零副作用往返 — the loop itself writes nothing and never commits; the
  executions write through the three only doors (edit ops / wiring ops /
  ``create_run``), flush-only; the read tools hold no writes in the TURN'S
  transaction (只读纪律). Carve-out (ADR-124): a read tool's world-fact
  snapshot write-through (the page readings seat) rides an INDEPENDENT
  short session — the turn's transaction stays read-only.

打字机律 on the tool wire (the three teeth restated for the loop form,
T2b): prose = the content channel, streamed on iteration 0. A REJECTED
call's speech is replaced speech — it never enters the envelope, later
iterations run quiet, and the frontend paces the settled prose at the
envelope (paceSettledProse — the zero-delta path unchanged). An ACCEPTED
read iteration's speech is KEPT speech: it composes into the envelope as
the prefix (the executions dock/write the composed whole), and the
unstreamed tail paces out through the same typewriter under the same key
(never a blob, never an erase). Structure frames (``on_tool_call``
name-known / ``on_tool_ready`` args-complete) fire on every iteration —
they are phase information, not prose; a read call's name-known frame is
the inspecting family's seat (「正在查曲库…」— the copy key rides the
registry entry, the tool name never reaches the user face).

Tier law (ADR-077 判词④): this driver speaks Tier 1 (native tool_calls). A
client without ``supports_native_tools`` fails LOUD here — the Tier-0
action-JSON floor for the chat loop lands with the second provider (the
research node's loop is the proven form); a silent downgrade nobody tests
would be a lie.
"""

import json
import re
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

from app.agents.arguments import normalize_numeric_arguments, numeric_string_changes
from app.agents.base import AGENTS, jinja_env
from app.agents.candidate_correction import (
    CORRECTION_TOOL_NAME,
    CandidateCorrectionArgs,
    CandidateRecord,
    CandidateRejected,
    CandidateScope,
    CorrectionError,
    RestoredCandidate,
    apply_correction,
    correction_tool,
)
from app.agents.tool_progress import ToolProgress, bind_progress
from app.agents.working_drafts import (
    WorkingDraftRejected,
    WorkingDraftReviewed,
    WorkingDraftUpdated,
    candidate_progress_digest,
    merge_working_draft,
    tool_progress_digest,
    verify_working_draft,
    working_draft_diagnostic,
    working_draft_observation,
)
from app.metering import bind_model_prompt
from app.providers.llm import get_llm_client
from app.providers.llm.base import LLMClient, LLMError, LLMSchemaError
from app.providers.llm.trace import trace_argument_normalization

logger = structlog.get_logger()

# A hook that may be sync or async (the funnel's DeltaCallback convention).
_Hook = Callable[..., Awaitable[None] | None]


async def _emit(hook: _Hook | None, *args: Any) -> None:
    if hook is None:
        return
    result = hook(*args)
    if result is not None:
        await result


@dataclass(frozen=True)
class ToolPresentationVariant:
    matches: Callable[[BaseModel | None], bool]
    active_key: str
    done_key: str


@dataclass(frozen=True)
class ToolPresentation:
    kind: str
    active_key: str
    done_key: str | None = None
    defer_start: bool = False
    policy: str | None = None
    receipt_kind: str | None = None
    variants: tuple[ToolPresentationVariant, ...] = ()
    steps: tuple[tuple[str, str], ...] = ()


NATIVE_PRESENTATION = ToolPresentation(kind="native", active_key="")


@dataclass(frozen=True)
class ChatTool:
    """One tool the chat loop may call (注册表纪律同 TOOL_REGISTRY: name +
    params schema + execute — the execute lives with the turn runners, keyed
    by name; the declaration here is the model-facing contract).

    ``description`` is model-facing and stays terse (注册表条目扰动 =
    prompt 扰动). ``params_model`` compiles to the tool's JSON schema — its
    Field descriptions ARE the parameter documentation. None = a zero-arg
    call (``start_run``). ``terminal``: a terminal tool's accepted call ends
    the turn (终态工具一调即停); a non-terminal tool (the perception family's
    reads) returns a ``ToolObservation`` and the loop iterates.

    ``wire_view``: an optional deployment-gate hook applied at spec time —
    it rewrites the (description, parameters) pair the MODEL sees, so a
    capability slice keyed to a deployment flag never reaches the wire while
    the flag is off (the tool's execute branch refuses the same slice
    independently — declaration and enforcement gate together).
    """

    name: str
    description: str
    params_model: type[BaseModel] | None
    terminal: bool = True
    wire_view: Callable[[str, dict], tuple[str, dict]] | None = None
    # Explicit opt-in for sequential multi-call batches; content writes and
    # terminal actions remain standalone even when non-terminal on the wire.
    batchable: bool = False
    repairable: bool = False
    # ConversationContext-backed working drafts use the same identity and
    # recovery records for successful incremental writes and failed saves.
    draftable: bool = False
    # Evidence reads authenticate and retain the same draft without merging writes.
    draft_reader: bool = False
    presentation: ToolPresentation | None = None
    finish_batch: Callable[[list[tuple[BaseModel, "ToolObservation"]]], Awaitable["ToolObservation | None"]] | None = None


def tool_spec(tool: ChatTool) -> dict:
    """The tool's OpenAI-compatible wire spec (the client seam's payload
    shape — the same dict the 2026-09-11/12 spike verified)."""
    parameters = (
        tool.params_model.model_json_schema()
        if tool.params_model is not None
        else {"type": "object", "properties": {}}
    )
    description = tool.description
    if tool.wire_view is not None:
        description, parameters = tool.wire_view(description, parameters)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description,
            "parameters": parameters,
        },
    }


def _defs_refs(node: object) -> set[str]:
    """Every ``#/$defs/<name>`` reference reachable from a schema node."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                found.add(value.rsplit("/", 1)[-1])
            else:
                found |= _defs_refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= _defs_refs(value)
    return found


def prune_wire_parameters(parameters: dict, keys: set[str]) -> dict:
    """A deployment gate's schema pruning (the wire_view hooks' shared
    seat): drop the named properties (+ their ``required`` entries) from a
    deep copy, then garbage-collect orphan ``$defs`` so the gated slice's
    vocabulary (e.g. the edit op models) never leaks onto the wire."""
    import copy

    pruned = copy.deepcopy(parameters)
    properties = pruned.get("properties")
    if isinstance(properties, dict):
        for key in keys:
            properties.pop(key, None)
    required = pruned.get("required")
    if isinstance(required, list):
        pruned["required"] = [k for k in required if k not in keys]
    defs = pruned.get("$defs")
    if isinstance(defs, dict):
        body = {k: v for k, v in pruned.items() if k != "$defs"}
        needed = _defs_refs(body)
        frontier = list(needed)
        while frontier:
            name = frontier.pop()
            for ref in _defs_refs(defs.get(name)):
                if ref not in needed:
                    needed.add(ref)
                    frontier.append(ref)
        pruned["$defs"] = {k: v for k, v in defs.items() if k in needed}
        if not pruned["$defs"]:
            del pruned["$defs"]
    return pruned


# 言语账本 (T2b) 见 ``call_loop``; ADR-085 的 interim_prose 通道与其分家——
# interim_prose 散文永不入账本。
MAX_INTERIM_PROSES_PER_TURN = 4  # ADR-109 §2: 节奏护栏（防逐调用啰嗦），非资格限制


@dataclass
class LoopResult:
    """One turn's loop outcome.

    ``tool_name=None`` + ``exhausted=False`` + no ``ended_by`` /
    ``no_progress_tool`` = the bare final reply (the model spoke without
    calling a tool — read as the answer call, the read-tolerant floor).
    ``exhausted=True`` = the iteration cap was hit
    before a terminal answer; successful observations and rejection facts
    remain available to the caller for a truthful incomplete-work response.
    ``version_saved`` means a real CompositionVersion write succeeded;
    successful ``save=false`` working-draft updates never set it.
    ``calls`` = the tool sequence trace (the scenario suite's T4 assertion
    target).
    """

    prose: str
    tool_name: str | None
    params: BaseModel | None
    iterations: int
    calls: list[str] = field(default_factory=list)
    exhausted: bool = False
    version_saved: bool = False
    # Set when the loop ended on an execute's TerminalRefusal (below): the
    # refusing tool's name. The caller maps it to its honest close — the
    # loop itself never words user-facing meaning.
    ended_by: str | None = None
    # Structured world facts supplied by that refusal (for example the
    # standing video version and duration). Never model-facing prose.
    refusal_facts: dict[str, Any] | None = None
    # A caller-supplied rejection policy stopped a repeated, non-recovering
    # tool call before max_iterations. This is distinct from both an execute
    # TerminalRefusal and budget exhaustion so the chat layer can close with
    # the truthful preservation/failure semantics.
    no_progress_tool: str | None = None
    observations: list[tuple[str, bool]] = field(default_factory=list)
    rejections: list["ToolRejected"] = field(default_factory=list)


@dataclass
class TerminalRefusal:
    """An execute's deterministic TURN-ENDING refusal: the call is a
    REJECTION (the loop emits the ToolRejected fact with the real
    iteration + duration — speech retracts, the half-started activity
    cancels) AND the loop ends here, with no further model iteration.

    Seat law: only an entry that is STRUCTURALLY unrecoverable this turn
    (a latched design begin or a declared media-capability boundary) may end
    the loop this way; the rejection echo's "one more iteration" would be a
    lie for it. A refused call whose repair is possible keeps riding the plain
    feedback string. Optional ``facts`` carry world state for the caller's
    honest close, never a drafted reply."""

    reason: str
    facts: dict[str, Any] | None = None


def _loop_echo(feedback: str) -> str:
    """The loop's structured echo — the funnel repair echo's tool-form twin
    (``agents/base.py`` ``_repair_echo``): a retry without feedback is just
    rolling the dice twice (ADR-039 P3 — the one bounded repair, re-homed
    into the loop)."""
    return (
        f"\n\n上次工具调用被拒绝：{feedback}。请用有效参数调用合适的工具。"
    )


def _compose_speech(parts: list[str]) -> str:
    """The turn's ONE speech from its kept parts (言语账本): an accepted read
    iteration's prose + the terminal iteration's prose join on a blank line;
    a rejected call's prose never reaches here (replaced speech). Single-part
    turns (the T2a-pure form) come out as the part itself, stripped."""
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _unwrap_item_dialect(value: Any) -> Any:
    """The provider's array-wrap dialect (iter-2 live-gate evidence,
    2026-09-23 — probe D 5/12 runs): MiniMax's tool-args serialization
    intermittently wraps a LIST argument in a single-key object
    (``{"item": [...]}``), and occasionally wraps a single nested object the
    same way — at any depth (``plans.0.outputs``, a plans list element).
    The model cannot see or avoid the dialect, and every params rejection
    costs a loop iteration (probe D burned 8-iteration budgets on it).
    Unwrap recursively at the wire so validation judges the CONTENT. Safe
    because every tool params model is ``extra="forbid"`` and no field is
    legitimately named ``item`` (grepped) — a sole-"item"-key dict here is
    always the dialect, never payload. Same repair-economy law as the
    null/habit tolerances below."""
    if isinstance(value, dict):
        if set(value) == {"item"}:
            return _unwrap_item_dialect(value["item"])
        return {k: _unwrap_item_dialect(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap_item_dialect(v) for v in value]
    return value


@dataclass(frozen=True)
class ContextSnapshot:
    """Fresh caller-owned facts; keys identify fully included resources."""

    text: str
    keys: frozenset[str] = frozenset()
    images: tuple[Any, ...] = ()
    resources: tuple[tuple[str, dict[str, Any]], ...] = ()
    skill_method: str | None = None


@dataclass(frozen=True)
class RoundAssembly:
    """One caller-owned projection of the next provider request."""

    tools: list[ChatTool]
    system: str
    context: str | None = None
    media: tuple[Any, ...] = ()
    stage: str | None = None
    include_project_context: bool = True
    include_observation_media: bool = True
    observation_tools: frozenset[str] | None = None
    stream_prose: bool = True
    missing_tool_feedback: str | None = None
    opening_text: str | None = None
    caller_state: dict | None = None
    # Keep this form's opening invitation across consecutive argument repairs.
    invitation_tool: str | None = None
    enforce_offered_tools: bool = False
    # A caller may acknowledge a settled user action when the first tool response is silent.
    acknowledgment: str | None = None
    project_reply: Callable[[str], str] | None = None


@dataclass(frozen=True)
class ConversationHistory:
    """Caller-owned historical protocol pairs and their assembly evidence."""

    messages: tuple[dict, ...] = ()
    audit: dict = field(default_factory=dict)
    candidates: tuple[RestoredCandidate, ...] = ()


@dataclass(frozen=True)
class ToolObservation:
    """A NON-terminal tool's accepted result (T2b 感知族 — the read tools'
    return channel). The text is model-facing (compact lines, capped by the
    execute); the loop appends it to the wire as the role:tool message and
    iterates. A terminal tool's execute never returns this (skew = loud).

    ``ok`` (ADR-102 §5): False = the read's target is unreadable (the
    material failed processing) — the read's activity frame settles FAILED
    with the honest failed-form key, never the done mirror's lie.

    ``images`` (film 读取座, R3): compressed material screenshots the read
    attaches for the model's creative judgment — MediaInput-shaped
    (``type``/``data_url``/``caption``; typed loosely here because the
    kernel never imports the domain layer), each caption
    binding the image to its asset/scene references. They ride the SAME
    tool message as content parts (the loop's observation seat projects
    them); budget enforcement (count/size/over-budget honesty) is the
    EXECUTE's job — by the time an observation exists, its image set is
    already within budget (a breach would have been an explicit text error
    instead)."""

    text: str
    ok: bool = True
    images: tuple[Any, ...] = ()
    # Opaque internal evidence for the accepted-event consumer. The loop never
    # interprets it and never adds it to the model-facing observation wire.
    receipt: BaseModel | None = None
    # call: one model continuation; turn: this loop; project: canonical facts
    # may replace the observation only after the fresh snapshot includes its keys.
    context_lifetime: str = "turn"
    context_keys: tuple[str, ...] = ()
    project_text: str | None = None
    # Fold the protocol pair after its first delivered continuation without
    # changing its durable ConversationContext lifetime.
    fold_after_delivery: bool = False
    # Independent of within-loop folding: may this result survive this turn?
    persist: bool = True
    # Accepted domain evidence may supply one user-facing finding after acceptance.
    accepted_interim_prose: str | None = None
    # A caller-owned handoff settled the observation and can finish this turn.
    stop_after_observation: bool = False
    awaiting_authorization: bool = False
    # A version-scoped observation expires when the snapshot no longer has its key.
    valid_for_key: str | None = None


@dataclass(frozen=True)
class ToolExchange:
    """An actual completed call/result; persistence belongs to the caller."""

    call_id: str
    tool_name: str
    arguments: dict
    observation: ToolObservation
    base_keys: frozenset[str] = frozenset()
    executed_arguments: dict | None = None
    iteration: int = 0
    call_index: int = 0
    # Actual correction calls retain their own wire identity; these fields
    # attribute validation, supersession and execution to the original tool.
    target_tool: str | None = None
    candidate: dict | None = None


def observation_wire_content(observation: ToolObservation) -> str | list[dict]:
    """The role:tool message's content (ONE wire seat — both chat paths ride
    this same loop). Plain text when the read carries no images (the
    historical shape, byte-identical); with images, the standard content
    parts: the observation text first, then per image its ``image_url``
    part followed by its caption text part (the agents/base.py media
    pairing law), so the model can bind each screenshot to its asset/scene
    references. The MiniMax client passes messages verbatim — the parts
    survive to the wire; the provider's acceptance of tool-role image
    parts is the R3 spike's question (the synthetic-user fallback is the
    designed answer if it refuses)."""
    if not observation.images:
        return observation.text
    parts: list[dict] = [{"type": "text", "text": observation.text}]
    for image in observation.images:
        part_key = f"{image.type}_url"
        parts.append({"type": part_key, part_key: {"url": image.data_url}})
        if image.caption:
            parts.append({"type": "text", "text": image.caption})
    return parts


# --- Internal loop events (ADR-087 §3 Phase 2, U1 裁定 2026-09-19) ---
#
# The loop's instrumentation channel: typed facts about WHAT HAPPENED in the
# kernel, nothing else. The frozen boundary (用户拍板): the loop never
# references Activity vocabulary, never constructs a user-facing activity,
# never touches Presentation — translating "what happened" into "what the
# user is told" is entirely the Activity Projection's job
# (``app/chat/activity.py`` is the channel's only consumer). Typed union,
# never a grab-bag dict: a new event kind is a new dataclass here.


@dataclass(frozen=True)
class ToolRejected:
    """A call was REJECTED at the moment it happened (拒绝当时) — schema
    truncation / unknown tool / params validation / execute guardrail.
    ``tool_name`` is None when the name never became reliably known (a
    truncation can sever the stream before/within the arguments).

    The forensic fields (rejection 取证批): ``iteration`` is the loop's
    0-based iteration index of the rejected attempt; ``detail`` is the
    rejection reason verbatim (truncated — the validation error / the
    guardrail feedback), None when the kind already carries the whole fact
    (unknown_tool's reason IS the name); ``duration_ms`` is the rejected
    attempt's own wall time (iteration start → the rejection, monotonic).
    All plain loop facts, not Activity vocabulary — the frozen boundary
    holds."""

    kind: str  # schema_truncation | unknown_tool | params_validation | execute_guardrail
    tool_name: str | None
    iteration: int
    detail: str | None
    duration_ms: int
    # Content-only fingerprint (target + arguments + base keys), excluding the
    # random candidate id so a fresh call cannot fake progress merely by renaming itself.
    candidate_digest: str | None = None


@dataclass(frozen=True)
class TerminalAccepted:
    """A TERMINAL call's execute returned accept (the stop) — the work the
    call commits to (dock / run birth / edit application) has completed."""

    tool_name: str


@dataclass(frozen=True)
class ReadAccepted:
    """A NON-terminal read's execute returned its observation — the read is
    done; the loop now enters the quiet decision iteration. Pairs with the
    call's name-known moment. ``ok`` mirrors the observation's landed flag
    (False → the frame settles FAILED, never the done mirror)."""

    tool_name: str
    ok: bool = True
    awaiting_authorization: bool = False
    # Opaque sideband from ToolObservation; not part of the model wire.
    receipt: BaseModel | None = None


@dataclass(frozen=True)
class ReadExecuting:
    """An accepted NON-terminal read's execute is ABOUT TO run — the work's
    START stamp (ADR-108 数组位置律). The Activity projector re-anchors the
    read span's honest duration here (execute entry): name_known is a
    mid-generation liveness beat, and a duration anchored there would make
    the persisted row's ``at``/``duration_ms`` measure LLM generation time
    instead of the real read work. Emitted after the interim_prose seat and
    before ``execute`` — sequential same-process stamps, never a clock
    race.

    ``params`` carries the call's VALIDATED params (None for a params-less
    tool) — the one fact the projection needs to tell a tool's VARIANTS
    apart at execute entry. name_known can never carry this bit: the name
    surfaces mid-stream while the arguments are still arriving, so a
    variant claimed there would be a guess. The kernel still reports WHAT
    HAPPENED only — the params→user-vocabulary translation is entirely the
    projector's, and activity frames never carry params (the wire
    whitelist is unchanged)."""

    tool_name: str
    params: BaseModel | None = None
    call_id: str = ""


@dataclass(frozen=True)
class LoopExhausted:
    """The iteration cap was hit with every call rejected — the caller
    degrades honestly. The projector's explicit-failure fact (an open repair
    span must not be swept to 'completed' by a cannot-do envelope)."""

    iterations: int


LoopEvent = ToolRejected | TerminalAccepted | ReadAccepted | ReadExecuting | ToolProgress | LoopExhausted

# A synchronous, caller-owned stop decision. The kernel supplies the real
# rejection and the preceding history; it never imports chat/Film policy.
RejectionStop = Callable[[ToolRejected, tuple[ToolRejected, ...]], bool]


# Execute signature: (tool name, validated params, the turn's composed speech
# so far) → None when a TERMINAL call is ACCEPTED (the stop), the structured
# feedback string when a call is REJECTED (the loop echoes it and iterates),
# or a ToolObservation when a NON-terminal read call is accepted (fed back,
# loop continues). The speech seat exists because the executions need it —
# the docked question row's content, the plan echo, the answer message all
# carry the turn's speech (ask 三分解剖 ① / 计划回声) — and that speech is
# the ACCUMULATED one: words spoken before a kept read are part of the reply.
# All side effects belong to the executor; the loop writes nothing.
LoopExecute = Callable[
    [str, BaseModel | None, str],
    Awaitable[str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftReviewed | WorkingDraftUpdated],
]


# A stage can start with a silent tool call. Announce the work once, before
# its activity row; only actual tool results can substantiate completion.
class ToolLoopAgent:
    """One chat-surface agent in the tool-loop form — a declared instance,
    not a subclass per agent (N-30 sibling to ``Agent``). Same declaration
    data (name / prompt / system / assemble / temperature / packs / client),
    minus the single-call contract (schema / postprocess / fallback), plus
    the tool set and the iteration cap. Registers into the shared ``AGENTS``
    roster so the startup self-check's pack resolution covers it."""

    def __init__(
        self,
        *,
        name: str,
        prompt: str,
        system: str,
        assemble: Callable[..., tuple[dict[str, Any], list]],
        tools: list[ChatTool],
        temperature: float = 0.3,
        max_iterations: int = 4,
        client: LLMClient | None = None,
        packs: list[str] | None = None,
        service_per_call: bool = False,
    ) -> None:
        if not tools:
            raise ValueError("a tool-loop agent declares its tool set")
        names = [t.name for t in tools]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate tool names in {name}: {names}")
        self.name = name
        self.prompt = prompt
        self.system = system
        self.assemble = assemble
        self.temperature = temperature
        self.tools = tools
        self.max_iterations = max_iterations
        self.client = client or get_llm_client()
        self.packs = packs or []
        self.service_per_call = service_per_call
        if name in AGENTS:
            raise RuntimeError(f"Duplicate agent declaration: {name}")
        AGENTS[name] = self

    async def call_loop(
        self,
        execute: LoopExecute,
        *,
        on_delta: _Hook | None = None,
        on_reasoning: _Hook | None = None,
        on_tool_call: _Hook | None = None,
        on_tool_ready: _Hook | None = None,
        on_repair: _Hook | None = None,
        on_interim_prose: _Hook | None = None,
        on_loop_event: _Hook | None = None,
        should_stop_rejection: RejectionStop | None = None,
        refresh_context: Callable[[], Awaitable[ContextSnapshot]] | None = None,
        restore_context: Callable[..., Awaitable[ConversationHistory]] | None = None,
        on_context_event: _Hook | None = None,
        candidate_scope: CandidateScope | None = None,
        tools: list[ChatTool] | None = None,
        round_assembler: Callable[..., RoundAssembly] | None = None,
        dialogue: list[dict] | None = None,
        speech_language_hint: str | None = None,
        system_prompt: str | None = None,
        **ctx: Any,
    ) -> LoopResult:
        """Run the bounded loop: assemble → render → [generate_with_tools →
        execute → feedback/observation] × at most ``max_iterations``.

        ``execute`` returns None to accept a TERMINAL call (the stop), a
        feedback string to reject (echoed, one more iteration), a
        ToolObservation to accept a NON-terminal read (the loop continues
        with the observation on the wire), or a TerminalRefusal to reject
        AND end the loop on the spot (an entry unrecoverable this turn —
        ``LoopResult.ended_by`` names the refusing tool). The hooks:

        - ``on_delta``: prose fragments — iteration 0 only (a rejected
          iteration's speech is replaced speech; later iterations run quiet
          and the envelope paces out — the repair-never-streams law).
        - ``on_reasoning``: reasoning fragments, a liveness signal only.
        - ``on_tool_call``: a call's name became known (the Activity
          projector's ``name_known`` seat + the explicit System Status
          clear, Phase 3 Batch B ③). Streaming path: the client fires it as
          the name arrives; quiet iterations: fired when the response lands.
        - ``on_tool_ready``: a call's arguments completed and validated,
          pre-execution (the question.preview seam — structure, not prose;
          fires on every iteration).
        - ``on_repair``: a rejection iteration begins (the funnel's reserved
          kwarg's loop seat — the repair ACTIVITY opens here via the
          projector's ToolRejected twin; the retired "repairing" System
          Status label rode this hook until Phase 3 Batch B ③).
          Fires ONLY when the previous iteration was a genuine rejection
          (schema truncation / unknown tool / params validation / execute
          guardrail) — an ACCEPTED read's continuation is not a repair and
          never wears the label (2026-09-17 交互完整性批 ②: the read-before-
          write journey used to light "reworking it…" right after a
          successful read — a lie about the world).
        - ``on_interim_prose``: a INTERIM_PROSE was delivered (ADR-109 言语座位
          通用化) — the prose riding ANY non-terminal call (before/after
          are the same seat: an after-report is the next iteration's prose
          meeting the same before-seat). Emitted BEFORE the call executes
          (发射座前移, ADR-104 发射时点修订): the call was accepted at
          params validation, and a waiting read (ADR-102) would otherwise
          hold the speech hostage for the whole wait. Quiet iterations
          never stream — the frontend paces the full text out under the
          typewriter law. InterimProse speech rides its own channel: it
          never enters ``speech_parts``, so the settled reply must stand
          alone. Chat delivers every call. For other agents the cap applies;
          beyond the cap the prose is dropped with a log (节奏护栏 — a
          breaching model loses the channel, it does not overflow it).
          None (the one-shot JSON path) keeps the ledger behavior — the
          prose composes into the envelope as before.
        - ``on_loop_event``: the typed internal-event channel (ADR-087 §3
          Phase 2, U1 裁定) — ``ToolRejected`` at the moment of every
          rejection, ``TerminalAccepted`` / ``ReadAccepted`` at the two
          accept points, ``LoopExhausted`` before the exhausted return.
          The loop emits WHAT HAPPENED and nothing else; user-facing
          meaning is the Activity Projection's job, never the kernel's.
          The iteration boundary has no separate event: its two causes
          (retry-after-rejection / continuation-after-read) already ride
          ``on_repair`` / ``ReadAccepted`` — an event without a consumer is
          a lie waiting to drift.
        - ``should_stop_rejection``: an optional synchronous, caller-owned
          policy receiving the current ``ToolRejected`` and prior rejection
          facts. It may stop a non-recovering retry before ``max_iterations``;
          the result then carries ``no_progress_tool`` (not ``exhausted`` and
          not ``ended_by``), emits no fake ``LoopExhausted``, and makes no
          further model call. The chat caller owns the user-facing close.
        - ``tools``: an optional per-call projection of the declared tool set.
          It changes this turn's wire and dispatch table without mutating the
          shared agent; the default remains the full declaration.
        - ``round_assembler``: an optional caller-owned projection rerun after
          context/draft restore and repair selection. It returns the final tools,
          System, dynamic facts and media policy; execution still validates the call.
        """
        capabilities = getattr(self.client, "capabilities", None)
        if capabilities is None or not capabilities.supports_native_tools:
            raise LLMError(
                f"{type(self.client).__name__} does not declare native tool "
                "support — the chat tool loop speaks Tier 1 (ADR-077 判词④); "
                "the Tier-0 action-JSON floor lands with the second provider."
            )
        template_kwargs, _media = self.assemble(**ctx)
        # The chat agents never carry media; their historical user-message
        # shape is the plain string (StreamingAgent 形态律 — the payload
        # shape is a behavioral surface, byte-preserved here).
        if self.packs:
            from app.agents.contexts import (
                pack_instructions,  # deferred: contexts pulls the chat/pipeline assembly layer
            )

            template_kwargs["packs"] = pack_instructions(self.packs)
        if self.prompt == "chat/user.j2":
            template_kwargs["mode"] = {
                "intent_router": "plan",
                "chat_intent": "conversation",
                "trigger_turn": "event",
                "trigger_delivery": "delivery",
            }[self.name]
        user_prompt = jinja_env.get_template(self.prompt).render(**template_kwargs)
        system_supplements = []
        if self.service_per_call:
            system_supplements.append(jinja_env.get_template("chat/_tool_service.j2").render())
        if speech_language_hint and re.fullmatch(r"[a-z]{2,3}", speech_language_hint):
            system_supplements.append(jinja_env.get_template("chat/_conversation_language.j2").render(
                language=speech_language_hint,
            ))
        active_tools = self.tools if tools is None else tools
        if not active_tools:
            raise ValueError("a tool-loop call declares its tool set")
        specs = [tool_spec(t) for t in active_tools]
        correction_declaration = correction_tool()
        declared_by_name = {t.name: t for t in [*active_tools, correction_declaration]}
        declared_parameter_schemas = {
            t.name: t.params_model.model_json_schema()
            for t in [*active_tools, correction_declaration]
            if t.params_model is not None
        }
        scope = candidate_scope or CandidateScope(
            owner_id=f"agent:{self.name}", conversation_id=f"loop:{self.name}"
        )
        effective_system = self.system if system_prompt is None else system_prompt
        base_messages: list[dict] = [
            {"role": "system", "content": effective_system},
            {"role": "user", "content": user_prompt},
        ]
        calls: list[str] = []
        # 言语账本 (T2b): an ACCEPTED read iteration's speech is kept speech —
        # it composes into the envelope's prefix (the terminal execution and
        # the LoopResult both carry the composed whole). A rejected call's
        # speech is replaced speech and never enters the parts.
        speech_parts: list[str] = []
        # InterimProse channel state (ADR-109 — 言语座位通用化): the seat is
        # UNIVERSAL — prose riding any non-terminal call interim_proses, no
        # registry eligibility (白名单退役: the model's speech instinct is
        # the judge; the harness's job is to provide the seat, not to
        # license it per tool). ``interim_proses_sent`` is the per-turn
        # anti-chatter cap (≤4 — a RHYTHM guardrail, never a license).
        # ``last_read_name`` rides for the hit-rate log (评审 2026-09-17).
        last_read_name: str | None = None
        interim_proses_sent = 0
        # Turn-summary observability (ADR-085 评审 2026-09-17 — 「不需要
        # dashboard，日志里能查就够」): ONE line per turn answers the
        # hit-rate questions — reads × interim_proses conversion (ADR-109:
        # the eligible axis retired with the whitelist).
        accepted_reads: list[str] = []
        observation_results: list[tuple[str, bool]] = []
        version_saved = False
        draft_finalized = False

        def _finish(result: LoopResult) -> LoopResult:
            result.observations = list(observation_results)
            result.version_saved = version_saved
            result.rejections = list(rejections)
            logger.info(
                "tool_loop_turn",
                agent=self.name,
                outcome=(
                    "exhausted"
                    if result.exhausted
                    else f"no_progress:{result.no_progress_tool}"
                    if result.no_progress_tool is not None
                    else result.tool_name or "bare_reply"
                ),
                iterations=result.iterations,
                reads=accepted_reads,
                interim_proses=interim_proses_sent,
            )
            return result
        # The wire continuation after an accepted read: the assistant tool_call
        # echo + the role:tool observation (the standard OpenAI form). The
        # tail survives later rejections, including the rejected call/result
        # pairs, so corrections have the full candidate and prior evidence.
        observation_tail: list[dict] = []
        observation_scopes: dict[str, tuple[str, tuple[str, ...]]] = {}
        project_image_observations: dict[str, ToolObservation] = {}
        delivered_observations: set[str] = set()
        fold_after_delivery: set[str] = set()
        observed_keys: dict[str, str] = {}
        # Repair-label truthfulness (交互完整性批 ②): set by the rejection
        # paths below, cleared at each iteration's top — on_repair marks a
        # rejection's retry, never an accepted read's continuation.
        prev_rejected = False
        pending_rejection_feedback: str | None = None
        invitation: str | None = None
        rejections: list[ToolRejected] = []
        rejected_candidates: list[dict] = []
        candidates: dict[str, CandidateRecord] = {}
        drafts: dict[str, CandidateRecord] = {}
        restored_live_ids: set[str] = set()
        restored_draft_ids: set[str] = set()
        retired_candidate_ids: set[str] = set()
        repair_candidate_id: str | None = None
        latest_draft_id: str | None = None
        execution_by_name: dict[str, ChatTool] = {}
        execution_parameter_schemas: dict[str, dict] = {}

        async def retire_failed_candidate(record: CandidateRecord, *, iteration: int, kind: str) -> None:
            """A terminal design failure is a durable inactive fact, not a
            candidate that a later turn may resurrect with an old digest."""
            nonlocal repair_candidate_id
            payload = record.diagnostic(kind=kind, correction_error=CorrectionError(
                "candidate_retired", "The design turn ended without saving this candidate; start from current project facts.",
            ))
            await _emit(on_context_event, ToolExchange(
                call_id=record.call_id, tool_name=record.tool_name, arguments={},
                observation=ToolObservation(json.dumps(payload, ensure_ascii=False), ok=False),
                base_keys=record.base_keys, iteration=iteration, call_index=0,
                target_tool=record.tool_name,
                candidate={"candidate_id": record.candidate_id,
                    "candidate_digest": record.candidate_digest,
                    "target_tool": record.tool_name, "base_keys": sorted(record.base_keys),
                    "active": False},
            ))
            retired_candidate_ids.add(record.candidate_id)
            candidates.pop(record.candidate_id, None)
            if repair_candidate_id == record.candidate_id:
                repair_candidate_id = None

        async def retire_working_draft(record: CandidateRecord, *, iteration: int, kind: str) -> None:
            nonlocal latest_draft_id
            payload = working_draft_diagnostic(record, kind=kind)
            payload["draft_retired"] = True
            await _emit(on_context_event, ToolExchange(
                call_id=record.call_id, tool_name=record.tool_name, arguments={},
                observation=ToolObservation(json.dumps(payload, ensure_ascii=False), ok=False),
                base_keys=record.base_keys, iteration=iteration, call_index=0,
                target_tool=record.tool_name,
                candidate={"candidate_id": record.candidate_id,
                    "candidate_digest": record.candidate_digest,
                    "target_tool": record.tool_name, "base_keys": sorted(record.base_keys),
                    "active": False},
            ))
            retired_candidate_ids.add(record.candidate_id)
            drafts.pop(record.candidate_id, None)
            if latest_draft_id == record.candidate_id:
                latest_draft_id = None

        async def _reject(
            event: ToolRejected, *, feedback: str, iteration: int
        ) -> LoopResult | None:
            """Project one rejection, then either retry with feedback or stop.

            The optional policy is caller-owned and synchronous. Returning a
            result here never invents speech: the already-emitted rejection
            retracts the failed iteration, and the chat finish seat writes
            the honest terminal response.
            """
            nonlocal prev_rejected, pending_rejection_feedback
            await _emit(on_loop_event, event)
            previous = tuple(rejections)
            rejections.append(event)
            if (
                event.tool_name is not None
                and should_stop_rejection is not None
                and should_stop_rejection(event, previous)
            ):
                failed_candidate = candidates.get(repair_candidate_id or "")
                if failed_candidate is not None:
                    await retire_failed_candidate(failed_candidate, iteration=iteration, kind="no_progress")
                logger.info(
                    "tool_loop_no_progress",
                    agent=self.name,
                    tool=event.tool_name,
                    iteration=iteration,
                    kind=event.kind,
                )
                return _finish(
                    LoopResult(
                        prose="",
                        tool_name=None,
                        params=None,
                        iterations=iteration + 1,
                        calls=calls,
                        no_progress_tool=event.tool_name,
                    )
                )
            # Keep the opening byte-stable for provider prefix caching. The
            # latest rejection remains visible as a trailing user message.
            pending_rejection_feedback = _loop_echo(feedback)
            prev_rejected = True
            return None

        assembled_result_count = 0
        for iteration in range(self.max_iterations):
            if iteration and prev_rejected and on_repair is not None:
                await _emit(on_repair)
            prev_rejected = False
            # rejection 取证批: the rejected attempt's own wall time rides
            # its ToolRejected fact (iteration start → the rejection).
            iteration_started = time.monotonic()
            streaming = on_delta is not None and iteration == 0
            snapshot = await refresh_context() if refresh_context is not None else None
            if snapshot is not None and not isinstance(snapshot, ContextSnapshot):
                raise TypeError("refresh_context must return ContextSnapshot")
            omitted = {
                call_id for call_id, (lifetime, keys) in observation_scopes.items()
                # Every result must reach the model in one complete assistant/
                # tool protocol pair before any lifetime can retire it. A fresh
                # project snapshot may already contain the just-written resource
                # on the very next iteration; folding at that point would hide
                # the successful call itself and make the model repeat the work.
                if call_id in delivered_observations
                and (
                    lifetime == "call" or call_id in fold_after_delivery
                    or (lifetime == "project" and keys and snapshot is not None
                        and set(keys).issubset(snapshot.keys))
                )
            }
            if snapshot is not None:
                omitted.update(call_id for call_id, key in observed_keys.items() if key not in snapshot.keys)
            replacements = {
                call_id: observation_wire_content(
                    replace(observation, text=observation.project_text, images=())
                )
                for call_id, observation in project_image_observations.items()
                if call_id in omitted and observation.context_lifetime == "project"
            }
            omitted -= replacements.keys()
            # Remove whole protocol pairs, never orphan assistant/tool messages.
            tail = []
            for message in observation_tail:
                if message.get("tool_call_id") in replacements:
                    tail.append({**message, "content": replacements[message["tool_call_id"]]})
                    continue
                if message.get("tool_call_id") in omitted:
                    continue
                if message.get("tool_calls"):
                    retained = [c for c in message["tool_calls"] if c["id"] not in omitted]
                    if retained:
                        tail.append({**message, "tool_calls": retained})
                else:
                    tail.append(message)
            feedback = (
                [{"role": "user", "content": pending_rejection_feedback}]
                if pending_rejection_feedback is not None else []
            )
            # Rejection feedback is a ONE-ROUND control message. Assembling it
            # consumes it; later rounds retain only durable observations and
            # any newly rejected call's own feedback.
            pending_rejection_feedback = None
            shared = [{"role": "user", "content": observation_wire_content(ToolObservation(snapshot.text, images=snapshot.images))}] if snapshot and (snapshot.text or snapshot.images) else []
            history = await restore_context(snapshot, [*base_messages, *(dialogue or []), *tail, *feedback, *shared]) if restore_context is not None else ConversationHistory()
            current_restored_ids: set[str] = set()
            current_draft_ids: set[str] = set()
            for restored in history.candidates:
                target = declared_by_name.get(restored.tool_name)
                is_draft = target is not None and target.draftable
                if (
                    restored.candidate_id in retired_candidate_ids
                    or target is None or not (target.repairable or target.draftable)
                    or (restored.base_keys and (snapshot is None or not restored.base_keys.issubset(snapshot.keys)))
                ):
                    continue
                try:
                    restored_record = CandidateRecord.restore(
                        restored, schema=declared_parameter_schemas[restored.tool_name], scope=scope
                    )
                except CorrectionError as exc:
                    history.audit.setdefault("candidate_rejections", []).append({
                        "candidate_id": restored.candidate_id, "reason": str(exc),
                    })
                    continue
                if is_draft:
                    if restored_record.candidate_id not in drafts:
                        drafts[restored_record.candidate_id] = restored_record
                    current_draft_ids.add(restored_record.candidate_id)
                else:
                    candidates[restored_record.candidate_id] = restored_record
                    current_restored_ids.add(restored_record.candidate_id)
            for stale_id in restored_live_ids - current_restored_ids:
                if stale_id != repair_candidate_id:
                    candidates.pop(stale_id, None)
            for stale_id in restored_draft_ids - current_draft_ids:
                if stale_id != latest_draft_id:
                    drafts.pop(stale_id, None)
            restored_live_ids = current_restored_ids
            restored_draft_ids = current_draft_ids
            active_repair = candidates.get(repair_candidate_id or "")
            restricted_tools = (
                [correction_declaration]
                if active_repair is not None
                else [*active_tools, correction_declaration]
                if candidates
                else active_tools
            )
            if round_assembler is not None:
                has_new_result = len(observation_results) > assembled_result_count
                new_result_ok = has_new_result and observation_results[-1][1]
                assembled = round_assembler(
                    tools=restricted_tools,
                    drafts=tuple(drafts.values()),
                    snapshot=snapshot,
                    active_repair=active_repair,
                    iteration=iteration,
                    interim_prose_count=interim_proses_sent,
                    new_result=bool(new_result_ok),
                    new_result_tool=observation_results[-1][0] if new_result_ok else None,
                    version_saved=version_saved,
                    draft_finalized=draft_finalized,
                )
                assembled_result_count = len(observation_results)
            else:
                assembled = RoundAssembly(tools=restricted_tools, system=effective_system)
            round_tools = assembled.tools
            effective_system = assembled.system
            wire_system = "\n".join([effective_system, *system_supplements])
            base_messages[0] = {"role": "system", "content": wire_system}
            if not assembled.include_project_context:
                shared = []
            if assembled.context:
                shared = [*shared, {"role": "user", "content": observation_wire_content(
                    ToolObservation(assembled.context, images=assembled.media)
                )}]
            if assembled.observation_tools is not None:
                retained_call_ids = {
                    message.get("tool_call_id") for message in tail
                    if message.get("role") == "tool" and (
                        message.get("name") in assembled.observation_tools
                        or message.get("tool_call_id") not in delivered_observations
                    )
                }
                filtered_tail = []
                for message in tail:
                    if message.get("role") == "tool":
                        if message.get("tool_call_id") in retained_call_ids:
                            filtered_tail.append(message)
                    elif message.get("tool_calls"):
                        retained_calls = [
                            call for call in message["tool_calls"] if call.get("id") in retained_call_ids
                        ]
                        if retained_calls:
                            filtered_tail.append({**message, "tool_calls": retained_calls})
                tail = filtered_tail
            if not assembled.include_observation_media:
                def without_media(message: dict) -> dict:
                    content = message.get("content")
                    if not isinstance(content, list):
                        return message
                    return {**message, "content": [
                        part for part in content
                        if not isinstance(part, dict) or part.get("type") == "text"
                    ]}

                history_messages = [without_media(message) for message in history.messages]
                tail = [without_media(message) for message in tail]
            else:
                history_messages = list(history.messages)
            opening = base_messages[1:]
            if assembled.opening_text is not None:
                history_messages = []
                opening = [{"role": "user", "content": assembled.opening_text}]
            by_name = {
                **{t.name: t for t in active_tools},
                **execution_by_name,
                **{t.name: t for t in [*round_tools, correction_declaration]},
            }
            parameter_schemas = {
                **{
                    t.name: t.params_model.model_json_schema()
                    for t in active_tools if t.params_model is not None
                },
                **execution_parameter_schemas,
                **{
                    t.name: t.params_model.model_json_schema()
                    for t in [*round_tools, correction_declaration]
                    if t.params_model is not None
                },
            }
            execution_by_name = by_name
            execution_parameter_schemas = parameter_schemas
            if assembled.enforce_offered_tools:
                by_name = {tool.name: tool for tool in round_tools}
            round_specs = specs if round_tools == active_tools else [tool_spec(t) for t in round_tools]
            # Keep refreshed evidence outside the stable history/observation prefix.
            if dialogue is not None:
                # On this provider, application-supplied evidence (including images)
                # uses user-role content parts. Name the source separately from the human.
                opening = [{**message, "name": "application_context"} for message in opening]
                shared = [{**message, "name": "project_evidence"} for message in shared]
                feedback = [{**message, "name": "tool_feedback"} for message in feedback]
            round_dialogue = dialogue
            if assembled.project_reply and dialogue is not None:
                round_dialogue = next(([m] for m in reversed(dialogue) if m["role"] == "user"), [])
            opening_index = 1 + len(history_messages)
            if dialogue is not None and self.name in {"trigger_turn", "trigger_delivery"}:
                dialogue_start = opening_index
                opening_index += len(round_dialogue)
                observation_start = opening_index + len(opening)
                feedback_start = observation_start + len(tail)
                project_start = feedback_start + len(feedback)
                messages = [base_messages[0], *history_messages, *round_dialogue, *opening,
                            *tail, *feedback, *shared]
            elif dialogue is None:
                messages = [base_messages[0], *history_messages, *opening, *tail, *feedback, *shared]
                dialogue_start = opening_index + len(opening)
                observation_start = dialogue_start
                feedback_start = observation_start + len(tail)
                project_start = feedback_start + len(feedback)
            else:
                # The transcript includes the current input, even when it was a dock pick.
                # Keep server evidence apart from speech and preserve live tool protocol pairs.
                if assembled.opening_text is not None:
                    opening = []
                project_start = opening_index + len(opening)
                dialogue_start = project_start + len(shared)
                observation_start = dialogue_start + len(round_dialogue)
                feedback_start = observation_start + len(tail)
                messages = [base_messages[0], *history_messages, *opening, *shared,
                            *round_dialogue, *tail, *feedback]
            assembly = {
                "agent": self.name, "iteration": iteration, "max_iterations": self.max_iterations,
                "system_sources": [
                    source for prompt in (effective_system, *system_supplements)
                    for source in getattr(prompt, "sources", [])
                ],
                "user_sources": getattr(user_prompt, "sources", []),
                "template_variables": sorted(template_kwargs),
                "declared_packs": self.packs,
                "pack_text": template_kwargs.get("packs"),
                "conversation_context": history.audit,
                "rejections": [{"iteration": r.iteration, "tool_name": r.tool_name,
                                "kind": r.kind, "detail": r.detail} for r in rejections],
                "accepted_reads": list(accepted_reads),
                "omitted_observation_ids": sorted(omitted),
                "summarized_observation_ids": sorted(replacements),
                "repair_tool": active_repair.tool_name if active_repair is not None else None,
                "repair_candidate": ({"candidate_id": active_repair.candidate_id,
                    "candidate_digest": active_repair.candidate_digest,
                    "target_tool": active_repair.tool_name} if active_repair is not None else None),
                "available_candidate_ids": sorted(candidates),
                "available_draft_ids": sorted(drafts),
                "retained_observation_ids": [m["tool_call_id"] for m in tail if m.get("tool_call_id")],
                "rejected_candidates": list(rejected_candidates),
                "candidate_retained": (
                    all(any(c.get("id") == candidate["call_id"]
                            for m in messages for c in m.get("tool_calls", []))
                        for candidate in rejected_candidates)
                    if rejected_candidates else None
                ),
                "message_sections": {"system": [0], "conversation_history": list(range(1, 1 + len(history_messages))),
                                     "opening_and_feedback": list(range(opening_index, opening_index + len(opening))),
                                     "observations": list(range(observation_start, feedback_start)),
                                     "loop_feedback": list(range(feedback_start, feedback_start + len(feedback))),
                                     "project_context": list(range(project_start, project_start + len(shared))),
                                     "dialogue": list(range(dialogue_start, dialogue_start + len(round_dialogue or [])))},
            }
            try:
                with bind_model_prompt(assembly):
                    if streaming:
                        result = await self.client.generate_stream_with_tools(
                            messages=messages,
                            tools=round_specs,
                            temperature=self.temperature,
                            thinking=False,
                            on_delta=on_delta if assembled.stream_prose else None,
                            on_reasoning=on_reasoning,
                            on_tool_call=None if self.service_per_call else on_tool_call,
                        )
                    else:
                        result = await self.client.generate_with_tools(
                            messages=messages,
                            tools=round_specs,
                            temperature=self.temperature,
                            thinking=False,
                        )
                        for tool_call in (() if self.service_per_call else result.tool_calls):
                            await _emit(on_tool_call, tool_call.name)
            except LLMSchemaError as e:
                # The truncation signature (finish_reason=tool_calls but
                # arguments hit EOF) — schema class: absorbed into the loop
                # with the reason as feedback, never a blind re-roll.
                logger.info(
                    "tool_loop_rejection",
                    agent=self.name,
                    iteration=iteration,
                    kind="schema_truncation",
                    detail=str(e)[:200],
                )
                # The name may never have become reliably known (the stream
                # can sever inside the arguments) — None is the honest fact.
                stopped = await _reject(
                    ToolRejected(
                        kind="schema_truncation",
                        tool_name=None,
                        iteration=iteration,
                        detail=str(e)[:200],
                        duration_ms=int((time.monotonic() - iteration_started) * 1000),
                    ),
                    feedback=str(e),
                    iteration=iteration,
                )
                if stopped is not None:
                    return stopped
                continue
            # Misplaced speech (an args-level "prose" habit key) reads as
            # speech when the content channel stayed empty (读容忍, below).
            prose = result.content
            if assembled.project_reply:
                prose = assembled.project_reply(prose)
                if any(not by_name[c.name].terminal for c in result.tool_calls if c.name in by_name):
                    prose = ""  # The Activity owns pre-execution speech for editor operations.
            if (
                len(result.tool_calls) == 1
                and result.tool_calls[0].name == assembled.invitation_tool
            ):
                if invitation is None and prose.strip():
                    invitation = prose.strip()
            else:
                invitation = None
            delivered_observations.update(observation_scopes)
            if not result.tool_calls:
                if not prose.strip():
                    # 空裸回复护栏 (2026-10-06, live 取证 96a86172 起 — the
                    # empty-prose guardrails' third sibling, after answer
                    # and ask_user): an empty, tool-less response is a
                    # malformed turn, never a bare reply — fed back and
                    # retried within the iteration budget, so a provider
                    # flake gets a repair round instead of lying down as
                    # the cannot-do floor. Exhaustion on repeats still
                    # degrades honestly.
                    logger.info(
                        "tool_loop_rejection",
                        agent=self.name,
                        iteration=iteration,
                        kind="empty_bare_reply",
                    )
                    stopped = await _reject(
                        ToolRejected(
                            kind="empty_bare_reply",
                            tool_name=None,
                            iteration=iteration,
                            detail=None,
                            duration_ms=int((time.monotonic() - iteration_started) * 1000),
                        ),
                        feedback=(
                            "上次回复为空，既没有正文也没有调用工具。请在正文中作答，或只调用一个工具。"
                        ),
                        iteration=iteration,
                    )
                    if stopped is not None:
                        return stopped
                    continue
                required_feedback = assembled.missing_tool_feedback
                editor_can_finish = assembled.project_reply is not None and bool(observation_scopes)
                if self.service_per_call and not required_feedback and not editor_can_finish:
                    required_feedback = "在助手消息正文中回答，并调用合适的终结工具。"
                if required_feedback:
                    stopped = await _reject(
                        ToolRejected(
                            kind="execute_guardrail",
                            tool_name="answer",
                            iteration=iteration,
                            detail=required_feedback[:200],
                            duration_ms=int((time.monotonic() - iteration_started) * 1000),
                        ),
                        feedback=required_feedback,
                        iteration=iteration,
                    )
                    if stopped is not None:
                        return stopped
                    continue
                # Bare final reply — the read-tolerant answer call unless the
                # caller still requires a terminal decision (any kept
                # read-iteration speech composes in front of it).
                return _finish(
                    LoopResult(
                        prose=_compose_speech([*speech_parts, prose]),
                        tool_name=None,
                        params=None,
                        iterations=iteration + 1,
                        calls=calls,
                    )
                )
            batched = len(result.tool_calls) > 1
            response_prose = prose
            prose_handled = False
            wire_calls = [
                {"id": call.id or f"call_{iteration}_{index}", "type": "function",
                 "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
                for index, call in enumerate(result.tool_calls)
            ]
            assistant_message = result.assistant_message or {"role": "assistant", "content": prose or ""}
            # Keep the provider's arguments and optional reasoning for the next
            # model request. Use the same fallback id as the tool result if needed.
            original_calls = assistant_message.get("tool_calls") or wire_calls
            assistant_message = {"role": "assistant", **assistant_message, "tool_calls": [
                {**original, "id": wire["id"]} for original, wire in zip(original_calls, wire_calls, strict=True)
            ]}
            if batched:
                observation_tail.append(assistant_message)

            async def remember(call, call_id, observation, executed_arguments=None, *,
                               candidate_record: CandidateRecord | None = None,
                               candidate_active: bool = True,
                               target_tool: str | None = None):
                if observation.context_lifetime not in {"call", "turn", "project"}:
                    raise ValueError("unknown observation context lifetime")
                fold_keys = observation.context_keys if not observation.images or observation.project_text is not None else ()
                if observation.images and observation.project_text is not None:
                    project_image_observations[call_id] = observation
                if observation.valid_for_key:
                    observed_keys[call_id] = observation.valid_for_key
                if observation.fold_after_delivery:
                    fold_after_delivery.add(call_id)
                observation_scopes[call_id] = (observation.context_lifetime, fold_keys)
                if not batched:
                    observation_tail.append(assistant_message)
                observation_tail.append({"role": "tool", "tool_call_id": call_id, "name": call.name,
                                         "content": observation_wire_content(observation)})
                await _emit(on_context_event, ToolExchange(
                    call_id=call_id, tool_name=call.name, arguments=call.arguments,
                    observation=observation, base_keys=snapshot.keys if snapshot else frozenset(),
                    executed_arguments=executed_arguments, iteration=iteration, call_index=call_index,
                    target_tool=target_tool,
                    candidate=({"candidate_id": candidate_record.candidate_id,
                        "candidate_digest": candidate_record.candidate_digest,
                        "target_tool": candidate_record.tool_name,
                        "base_keys": sorted(candidate_record.base_keys),
                        "active": candidate_active}
                        if candidate_record is not None else None),
                ))

            async def reject_candidate(call, call_id, record: CandidateRecord, *,
                                       include_candidate: bool, detail: str,
                                       kind: str = "params_validation",
                                       event_kind: str = "params_validation",
                                       correction_error: CorrectionError | None = None):
                nonlocal repair_candidate_id
                candidates[record.candidate_id] = record
                repair_candidate_id = record.candidate_id
                rejected_candidates.append({
                    "iteration": iteration, "call_id": call_id,
                    "tool_name": record.tool_name, "candidate_id": record.candidate_id,
                    "candidate_digest": record.candidate_digest,
                    "arguments": deepcopy(record.arguments), "errors": record.errors,
                })
                payload = record.diagnostic(
                    include_candidate=include_candidate, kind=kind,
                    correction_error=correction_error,
                )
                encoded = json.dumps(payload, ensure_ascii=False)
                await remember(
                    call, call_id, ToolObservation(encoded, ok=False),
                    executed_arguments=record.arguments, candidate_record=record,
                    target_tool=record.tool_name,
                )
                return await _reject(
                    ToolRejected(event_kind, record.tool_name, iteration, detail[:200], 0),
                    feedback=(
                        f"保留的 {record.tool_name} 候选尚未执行。请使用 {CORRECTION_TOOL_NAME}，传入 candidate_id={record.candidate_id} 及工具结果中的当前摘要，按诊断修正。不要重复准备资源。"
                    ),
                    iteration=iteration,
                )

            async def reject_working_draft(call, call_id, record: CandidateRecord, *,
                                           detail: str,
                                           kind: str = "content_validation",
                                           event_kind: str = "execute_guardrail",
                                           correction_error: CorrectionError | None = None):
                nonlocal latest_draft_id
                drafts[record.candidate_id] = record
                latest_draft_id = record.candidate_id
                rejected_candidates.append({
                    "iteration": iteration, "call_id": call_id,
                    "tool_name": record.tool_name, "candidate_id": record.candidate_id,
                    "candidate_digest": record.candidate_digest,
                    "arguments": deepcopy(record.arguments), "errors": record.errors,
                })
                payload = working_draft_diagnostic(record, kind=kind)
                if correction_error is not None:
                    payload["draft_error"] = {"code": correction_error.code, "message": str(correction_error)}
                await remember(
                    call, call_id, ToolObservation(
                        json.dumps(payload, ensure_ascii=False), ok=False, fold_after_delivery=True,
                    ),
                    executed_arguments=record.arguments, candidate_record=record,
                    candidate_active=True, target_tool=record.tool_name,
                )
                return await _reject(
                    ToolRejected(
                        event_kind, record.tool_name, iteration, detail[:200], 0,
                        candidate_digest=candidate_progress_digest(record),
                    ),
                    feedback="工作草稿未保存。最新标识和错误见工具结果。",
                    iteration=iteration,
                )

            unsafe = [call for call in result.tool_calls if call.name in by_name
                      and (by_name[call.name].terminal or not by_name[call.name].batchable)]
            group = by_name.get(result.tool_calls[0].name)
            finish_batch = group.finish_batch if group and all(call.name == group.name for call in result.tool_calls) else None
            batch_observations = []
            invalid_service = self.service_per_call and batched and not finish_batch
            if invalid_service or (batched and unsafe):
                # Reject BEFORE any work: no first write, silent drops or forked starts.
                feedback = "本批未执行。内容写入和终结操作必须单独提交，只有声明为可批量执行的读取或资源准备可以合并。"
                if invalid_service:
                    feedback = "未执行本批工具。请一次调用一个工具。"
                calls.extend(call.name for call in result.tool_calls)
                for call_index, call in enumerate(result.tool_calls):
                    await remember(call, wire_calls[call_index]["id"], ToolObservation(feedback, ok=False))
                correction_call = next((c for c in result.tool_calls if c.name == CORRECTION_TOOL_NAME), None)
                correction_candidate = candidates.get(str(correction_call.arguments.get("candidate_id") or "")) if correction_call is not None else None
                rejection_owner = (
                    active_repair.tool_name if active_repair is not None and correction_call is not None
                    else correction_candidate.tool_name if correction_candidate is not None
                    else result.tool_calls[0].name
                )
                stopped = await _reject(ToolRejected(kind="execute_guardrail", tool_name=rejection_owner,
                    iteration=iteration, detail=feedback, duration_ms=0), feedback=feedback, iteration=iteration)
                if stopped is not None:
                    return stopped
                continue

            if active_repair is not None and any(call.name != CORRECTION_TOOL_NAME for call in result.tool_calls):
                feedback = (
                    f"本次回复中的调用均未执行。当前只可使用 {CORRECTION_TOOL_NAME}。请参照保留候选的诊断和 target_parameters_schema，选择 patch 或显式 replace，不得编造查询参数结构的工具。"
                )
                for call_index, call in enumerate(result.tool_calls):
                    calls.append(call.name)
                    await remember(call, wire_calls[call_index]["id"], ToolObservation(feedback, ok=False),
                                   candidate_record=active_repair, target_tool=active_repair.tool_name)
                stopped = await _reject(ToolRejected("execute_guardrail", active_repair.tool_name,
                    iteration, feedback, 0), feedback=feedback, iteration=iteration)
                if stopped is not None:
                    return stopped
                continue

            for call_index, call in enumerate(result.tool_calls):
                call_id = call.id or f"call_{iteration}_{call_index}"
                prose = response_prose if not prose_handled else ""
                calls.append(call.name)
                tool = by_name.get(call.name)
                if tool is None:
                    if not batched:
                        await remember(call, call_id, ToolObservation(f"Unknown tool {call.name!r}; not executed.", ok=False))
                    logger.info(
                        "tool_loop_rejection",
                        agent=self.name,
                        iteration=iteration,
                        kind="unknown_tool",
                        tool=call.name,
                    )
                    if batched:
                        await remember(call, call_id, ToolObservation(f"Unknown tool {call.name!r}; not executed.", ok=False))
                        continue
                    stopped = await _reject(
                        ToolRejected(
                            kind="unknown_tool",
                            tool_name=call.name,
                            iteration=iteration,
                            detail=None,
                            duration_ms=int((time.monotonic() - iteration_started) * 1000),
                        ),
                        feedback=(
                            f"未知工具 {call.name!r}。请从以下工具中选一个："
                            + ", ".join(t.name for t in (round_tools if assembled.enforce_offered_tools else active_tools))
                        ),
                        iteration=iteration,
                    )
                    if stopped is not None:
                        return stopped
                    continue
                # 读容忍 at the loop boundary (打字机律牙①'s loop form): the
                # retired wire habits drop silently — "type"/"kind" naming keys
                # (the tool's name already carries both), a "prose" speech key
                # (speech belongs to the content channel — misplaced speech
                # still reads as speech when the channel stayed empty).
                raw = dict(call.arguments)
                raw.pop("type", None)
                raw.pop("kind", None)
                habit_prose = raw.pop("prose", None) or ""
                if not prose_handled and not prose.strip() and isinstance(habit_prose, str):
                    prose = habit_prose
                is_correction = call.name == CORRECTION_TOOL_NAME
                is_draft_merge = False
                is_draft_update = False
                if not is_correction:
                    raw = _unwrap_item_dialect(raw)
                dispatch_name = call.name
                dispatch_tool = tool
                candidate_record = active_repair if is_correction else None
                correction_merge = None
                if tool.params_model is not None and not is_correction:
                    raw, changes = normalize_numeric_arguments(raw, parameter_schemas[call.name])
                    trace_argument_normalization(model_call_id=assembly.get("model_call_id"), tool_call_id=call_id, agent=self.name, iteration=iteration, changes=changes)
                params: BaseModel | None = None
                if is_correction:
                    try:
                        correction_params = CandidateCorrectionArgs.model_validate(raw)
                        request = correction_params.root
                        candidate_record = candidate_record or candidates.get(request.candidate_id)
                        if candidate_record is None:
                            raise CorrectionError("unknown_candidate", "candidate_id does not name a current retained candidate in this owner/conversation.")
                        if candidate_record.base_keys and (
                            snapshot is None or not candidate_record.base_keys.issubset(snapshot.keys)
                        ):
                            stale = CorrectionError(
                                "stale_base", "The candidate's source/version facts are no longer current; it was retired without execution. Re-read current facts and create a new candidate.",
                            )
                            stopped = await reject_candidate(call, call_id, candidate_record,
                                include_candidate=False, detail=str(stale), correction_error=stale)
                            if stopped is None:
                                await retire_failed_candidate(candidate_record, iteration=iteration, kind="stale_base")
                                continue
                            return stopped
                        correction_merge = apply_correction(candidate_record, request)
                        raw = correction_merge.arguments
                        dispatch_name = candidate_record.tool_name
                        dispatch_tool = by_name[dispatch_name]
                    except ValidationError as e:
                        detail = str(e)
                        correction_error = CorrectionError("invalid_correction", detail)
                        if candidate_record is not None:
                            stopped = await reject_candidate(call, call_id, candidate_record,
                                include_candidate=False, detail=detail, correction_error=correction_error)
                        else:
                            feedback = json.dumps({"ok": False, "execution": "not executed", "saved": False,
                                "correction_error": {"code": correction_error.code, "message": detail}}, ensure_ascii=False)
                            await remember(call, call_id, ToolObservation(feedback, ok=False))
                            stopped = await _reject(ToolRejected("params_validation", active_repair.tool_name if active_repair else call.name,
                                iteration, detail[:200], 0), feedback=detail, iteration=iteration)
                        if stopped is not None:
                            return stopped
                        continue
                    except CorrectionError as e:
                        if candidate_record is None:
                            feedback = json.dumps({"ok": False, "execution": "not executed", "saved": False,
                                "correction_error": {"code": e.code, "message": str(e)}}, ensure_ascii=False)
                            await remember(call, call_id, ToolObservation(feedback, ok=False))
                            stopped = await _reject(ToolRejected("params_validation", call.name, iteration, str(e)[:200], 0),
                                feedback=str(e), iteration=iteration)
                        else:
                            stopped = await reject_candidate(call, call_id, candidate_record,
                                include_candidate=False, detail=str(e), correction_error=e)
                        if stopped is not None:
                            return stopped
                        continue
                    raw, changes = normalize_numeric_arguments(raw, parameter_schemas[dispatch_name])
                    trace_argument_normalization(model_call_id=assembly.get("model_call_id"), tool_call_id=call_id,
                        agent=self.name, iteration=iteration, changes=changes)
                    try:
                        params = dispatch_tool.params_model.model_validate(raw) if dispatch_tool.params_model is not None else None
                        trace_argument_normalization(model_call_id=assembly.get("model_call_id"), tool_call_id=call_id, agent=self.name, iteration=iteration, changes=numeric_string_changes(raw, params.model_dump(mode="json") if params is not None else {}))
                    except ValidationError as e:
                        errors = json.loads(e.json(include_input=False, include_url=False))
                        candidate_record = candidate_record.updated(raw, errors, call_id=call_id)
                        stopped = await reject_candidate(call, call_id, candidate_record,
                            include_candidate=not correction_merge.complete_arguments_in_call,
                            detail=str(e))
                        if stopped is not None:
                            return stopped
                        continue
                elif tool.params_model is not None:
                    try:
                        params = tool.params_model.model_validate(raw)
                        trace_argument_normalization(model_call_id=assembly.get("model_call_id"), tool_call_id=call_id, agent=self.name, iteration=iteration, changes=numeric_string_changes(raw, params.model_dump(mode="json")))
                    except ValidationError as e:
                        errors = json.loads(e.json(include_input=False, include_url=False))
                        draft_validation_record = None
                        if tool.draftable and isinstance(raw.get("draft_ref"), dict):
                            try:
                                reference = raw["draft_ref"]
                                draft_id = reference.get("draft_id")
                                if not isinstance(draft_id, str):
                                    raise CorrectionError("invalid_draft", "draft_id must be a string")
                                draft_record = drafts.get(draft_id)
                                if draft_record is None:
                                    raise CorrectionError("unknown_draft", "draft_id does not name a current retained Composition draft")
                                verify_working_draft(draft_record, reference)
                                draft_validation_record = draft_record.updated(
                                    draft_record.arguments, errors, call_id=call_id,
                                )
                            except (ValidationError, CorrectionError):
                                # An unauthenticated reference cannot borrow a
                                # retained draft's identity for its diagnostic.
                                pass
                        if draft_validation_record is not None:
                            stopped = await reject_working_draft(
                                call, call_id, draft_validation_record,
                                detail=str(e), kind="params_validation",
                                event_kind="params_validation",
                            )
                        elif tool.repairable:
                            candidate_record = CandidateRecord.create(
                                tool_name=call.name, arguments=raw, errors=errors,
                                schema=parameter_schemas[call.name], scope=scope,
                                base_keys=snapshot.keys if snapshot else frozenset(), call_id=call_id,
                            )
                            logger.info("tool_loop_rejection", agent=self.name, iteration=iteration,
                                kind="params_validation", tool=call.name, detail=str(e)[:200])
                            stopped = await reject_candidate(call, call_id, candidate_record,
                                include_candidate=False, detail=str(e))
                        else:
                            rejected_candidates.append({
                                "iteration": iteration, "call_id": call_id,
                                "tool_name": call.name, "arguments": raw, "errors": errors,
                            })
                            logger.info("tool_loop_rejection", agent=self.name, iteration=iteration,
                                kind="params_validation", tool=call.name, detail=str(e)[:200])
                            await remember(call, call_id, ToolObservation(json.dumps({
                                "ok": False, "execution": "not executed", "saved": False,
                                "kind": "params_validation", "errors": errors, "candidate": raw,
                                "repair": "Return valid arguments for this tool.",
                            }, ensure_ascii=False), ok=False, fold_after_delivery=tool.draftable))
                            stopped = await _reject(ToolRejected("params_validation", call.name, iteration,
                                str(e)[:200], int((time.monotonic() - iteration_started) * 1000)),
                                feedback=str(e), iteration=iteration) if not batched else None
                        if stopped is not None:
                            return stopped
                        continue
                if not is_correction and params is not None and getattr(params, "draft_ref", None) is not None:
                    reference = params.draft_ref
                    candidate_record = drafts.get(reference.draft_id)
                    try:
                        if candidate_record is None:
                            raise CorrectionError("unknown_draft", "draft_id does not name a current retained Composition draft in this owner/conversation")
                        verify_working_draft(candidate_record, reference)
                        if candidate_record.base_keys and (
                            snapshot is None or not candidate_record.base_keys.issubset(snapshot.keys)
                        ):
                            raise CorrectionError("stale_base", "The draft's source/version facts are no longer current; re-read current facts and start a new design")
                        bind_working_draft = getattr(params, "bind_working_draft", None)
                        if bind_working_draft is None:
                            raise CorrectionError("invalid_draft", "the target tool cannot accept working draft state")
                        if tool.draft_reader:
                            bind_working_draft(candidate_record.arguments)
                        else:
                            merged = merge_working_draft(candidate_record, params)
                            dispatch_name = candidate_record.tool_name
                            dispatch_tool = by_name[dispatch_name]
                            bind_working_draft(merged)
                            is_draft_merge = True
                    except (CorrectionError, ValidationError) as exc:
                        correction_error = exc if isinstance(exc, CorrectionError) else CorrectionError("invalid_revision", str(exc))
                        if candidate_record is not None:
                            stopped = await reject_working_draft(
                                call, call_id, candidate_record,
                                detail=str(exc), kind="params_validation",
                                event_kind="params_validation", correction_error=correction_error,
                            )
                        else:
                            feedback = json.dumps({"ok": False, "execution": "not executed", "saved": False,
                                "draft_error": {"code": correction_error.code, "message": str(correction_error)}}, ensure_ascii=False)
                            await remember(call, call_id, ToolObservation(feedback, ok=False))
                            stopped = await _reject(ToolRejected("params_validation", call.name, iteration,
                                str(exc)[:200], 0), feedback=str(exc), iteration=iteration)
                        if stopped is not None:
                            return stopped
                        if isinstance(correction_error, CorrectionError) and correction_error.code == "stale_base" and candidate_record is not None:
                            await retire_working_draft(candidate_record, iteration=iteration, kind="stale_base")
                        continue
                tool = dispatch_tool
                if is_correction:
                    assert candidate_record is not None and correction_merge is not None
                # Read speech lands before execution. Terminal speech belongs to its
                # answer/card. With no delivery hook, the ledger keeps both.
                prose_handled = True
                if (assembled.acknowledgment and not tool.terminal and not prose.strip()
                        and not interim_proses_sent and not speech_parts):
                    prose = assembled.acknowledgment
                # Draft judgments speak only from their accepted observation.
                if (
                    not tool.terminal and not self.service_per_call
                    and tool.draft_reader and getattr(params, "judgment", None) is not None
                ):
                    prose = ""
                interim_prose_route = (
                    not tool.terminal
                    and bool(prose.strip())
                    and on_interim_prose is not None
                )
                if interim_prose_route and (self.service_per_call or interim_proses_sent < MAX_INTERIM_PROSES_PER_TURN):
                    await _emit(on_interim_prose, prose.strip())
                    interim_proses_sent += 1
                    logger.info(
                        "tool_loop_interim_prose",
                        agent=self.name,
                        iteration=iteration,
                        predecessor=last_read_name,
                    )
                elif interim_prose_route:
                    logger.info(
                        "tool_loop_interim_prose_capped",
                        agent=self.name,
                        iteration=iteration,
                    )
                elif not tool.terminal:
                    speech_parts.append(prose)
                if self.service_per_call:
                    await _emit(on_tool_call, dispatch_name)
                await _emit(on_tool_ready, dispatch_name, params)
                # The composed speech: a TERMINAL call gets the ledger + this
                # iteration's prose (it never entered the ledger — the guard
                # above); a read gets the LEDGER AS IS — its prose either just
                # entered it (non-routed) or left the ledger for the interim_prose
                # channel (routed: emitted = the interim_prose owns the words;
                # capped = dropped, never merged back). Re-adding ``prose``
                # here would double the non-routed read's speech and leak
                # interim_prose words back into the ledger (regression caught by
                # test_read_observation_continues_the_loop_and_keeps_speech).
                speech = _compose_speech(
                    speech_parts if not tool.terminal else [*speech_parts, invitation or prose]
                )
                if not tool.terminal:
                    # The read's work-START stamp (ADR-108 数组位置律): the
                    # projector re-anchors the span's honest duration at
                    # execute entry — after the interim_prose seat above, so the
                    # waiter row is appended (and persisted) BEFORE the
                    # activity row's birth: 服务员话 → 读活动 → 读后回复 is
                    # array order, never a clock race.
                    await _emit(on_loop_event, ReadExecuting(tool_name=dispatch_name, params=params, call_id=call_id))
                with bind_progress(call_id, on_loop_event):
                    outcome = await execute(dispatch_name, params, speech)
                if isinstance(outcome, WorkingDraftReviewed):
                    if not tool.draft_reader or candidate_record is None:
                        raise RuntimeError(f"{dispatch_name} returned draft evidence without draft_reader=True")
                    candidate_record = candidate_record.updated(outcome.arguments, [], call_id=call_id)
                    drafts[candidate_record.candidate_id] = candidate_record
                    latest_draft_id = candidate_record.candidate_id
                    observation = outcome.observation
                    payload = json.loads(observation.text)
                    payload["draft_ref"] = working_draft_observation(candidate_record)["draft_ref"]
                    payload["review"] = working_draft_observation(candidate_record)["review"]
                    outcome = replace(observation, text=json.dumps(payload, ensure_ascii=False))
                    is_draft_update = True
                if isinstance(outcome, WorkingDraftUpdated):
                    if not tool.draftable:
                        raise RuntimeError(f"{dispatch_name} returned a working draft without draftable=True")
                    if candidate_record is None:
                        candidate_record = CandidateRecord.create(
                            tool_name=dispatch_name, arguments=outcome.arguments, errors=[],
                            schema=parameter_schemas[dispatch_name], scope=scope,
                            base_keys=snapshot.keys if snapshot else frozenset(), call_id=call_id,
                        )
                    else:
                        candidate_record = candidate_record.updated(outcome.arguments, [], call_id=call_id)
                    drafts[candidate_record.candidate_id] = candidate_record
                    latest_draft_id = candidate_record.candidate_id
                    receipt = working_draft_observation(candidate_record)
                    outcome = ToolObservation(
                        json.dumps(receipt, ensure_ascii=False),
                        ok=True,
                        fold_after_delivery=True,
                    )
                    is_draft_update = True
                    is_draft_merge = False
                if isinstance(outcome, WorkingDraftRejected):
                    if not tool.draftable:
                        raise RuntimeError(f"{dispatch_name} returned a working draft without draftable=True")
                    arguments = outcome.arguments
                    if candidate_record is None:
                        candidate_record = CandidateRecord.create(
                            tool_name=dispatch_name, arguments=arguments, errors=outcome.errors,
                            schema=parameter_schemas[dispatch_name], scope=scope,
                            base_keys=snapshot.keys if snapshot else frozenset(), call_id=call_id,
                        )
                    else:
                        candidate_record = candidate_record.updated(arguments, outcome.errors, call_id=call_id)
                    stopped = await reject_working_draft(
                        call, call_id, candidate_record,
                        detail=outcome.reason,
                    )
                    if stopped is not None:
                        return stopped
                    continue
                if isinstance(outcome, CandidateRejected):
                    if not tool.repairable:
                        raise RuntimeError(f"{dispatch_name} returned candidate validation without repairable=True")
                    if candidate_record is None:
                        candidate_record = CandidateRecord.create(
                            tool_name=dispatch_name, arguments=raw, errors=outcome.errors,
                            schema=parameter_schemas[dispatch_name], scope=scope,
                            base_keys=snapshot.keys if snapshot else frozenset(), call_id=call_id,
                        )
                    else:
                        candidate_record = candidate_record.updated(raw, outcome.errors, call_id=call_id)
                    stopped = await reject_candidate(
                        call, call_id, candidate_record,
                        include_candidate=is_correction and not correction_merge.complete_arguments_in_call,
                        detail=outcome.reason, kind="content_validation", event_kind="execute_guardrail",
                    )
                    if stopped is not None:
                        return stopped
                    continue
                if isinstance(outcome, ToolObservation):
                    if tool.terminal:
                        raise RuntimeError(
                            f"terminal tool {dispatch_name!r} returned a ToolObservation "
                            "— the declaration and the execute table skewed "
                            "(a terminal call ends the turn, never observes)"
                        )
                    if is_draft_merge and outcome.ok:
                        assert candidate_record is not None
                        retired_candidate_ids.add(candidate_record.candidate_id)
                        drafts.pop(candidate_record.candidate_id, None)
                        if latest_draft_id == candidate_record.candidate_id:
                            latest_draft_id = None
                        for stale_draft in list(drafts.values()):
                            await retire_working_draft(
                                stale_draft, iteration=iteration, kind="superseded"
                            )
                    elif outcome.ok and tool.draftable and not is_draft_update:
                        # A successful save supersedes retained working drafts;
                        # a save=false update remains the active draft itself.
                        for stale_draft in list(drafts.values()):
                            await retire_working_draft(
                                stale_draft, iteration=iteration, kind="superseded"
                            )
                    if is_correction:
                        retired_candidate_ids.add(candidate_record.candidate_id)
                        candidates.pop(candidate_record.candidate_id, None)
                        repair_candidate_id = None
                    # A working-draft observation is an accepted write step,
                    # not a saved version. Only the direct save observation
                    # carries this fact; tool.ok alone includes save=false.
                    if (
                        outcome.ok
                        and dispatch_name in {"design_video", "split_clip"}
                        and not is_draft_update
                    ):
                        version_saved = True
                        if dispatch_name == "design_video" and assembled.stage in {"draft_build", "draft_finalize"}:
                            draft_finalized = True
                    last_read_name = dispatch_name
                    accepted_reads.append(dispatch_name)
                    observation_results.append((dispatch_name, outcome.ok))
                    await remember(
                        call, call_id, outcome,
                        executed_arguments=(
                            candidate_record.arguments if (
                                candidate_record is not None
                                and (is_draft_update or (is_draft_merge and not outcome.ok))
                            )
                            else params.model_dump(mode="json") if params is not None else {}
                        ),
                        candidate_record=candidate_record if (is_correction or is_draft_merge or is_draft_update) else None,
                        candidate_active=is_draft_update or (is_draft_merge and not outcome.ok),
                        target_tool=dispatch_name if (is_correction or is_draft_merge or is_draft_update) else None,
                    )
                    await _emit(
                        on_loop_event,
                        ReadAccepted(
                            tool_name=dispatch_name,
                            ok=outcome.ok,
                            receipt=outcome.receipt,
                            awaiting_authorization=outcome.awaiting_authorization,
                        ),
                    )
                    if (
                        not self.service_per_call
                        and outcome.ok
                        and outcome.accepted_interim_prose
                        and on_interim_prose is not None
                        and interim_proses_sent < MAX_INTERIM_PROSES_PER_TURN
                    ):
                        await _emit(on_interim_prose, outcome.accepted_interim_prose)
                        interim_proses_sent += 1
                    if finish_batch and outcome.ok:
                        batch_observations.append((params, outcome))
                    if outcome.stop_after_observation:
                        return _finish(LoopResult(
                            prose=speech, tool_name=dispatch_name, params=params,
                            iterations=iteration + 1, calls=calls,
                        ))
                    continue
                if isinstance(outcome, TerminalRefusal):
                    if is_correction:
                        retired_candidate_ids.add(candidate_record.candidate_id)
                        candidates.pop(candidate_record.candidate_id, None)
                        repair_candidate_id = None
                    await remember(call, call_id, ToolObservation(outcome.reason, ok=False),
                                   (candidate_record.arguments if is_draft_merge and candidate_record is not None else params.model_dump(mode="json") if params is not None else {}),
                                   candidate_record=candidate_record if (is_correction or is_draft_merge) else None,
                                   candidate_active=is_draft_merge, target_tool=dispatch_name if (is_correction or is_draft_merge) else None)
                    # The deterministic turn-ending refusal: the REJECTION facts
                    # all ride the existing seat (ToolRejected — the speech
                    # retracts, the half-started activity cancels), then the
                    # loop ends instead of offering the echo's next iteration.
                    logger.info(
                        "tool_loop_rejection",
                        agent=self.name,
                        iteration=iteration,
                        kind="execute_terminal_refusal",
                        tool=dispatch_name,
                        detail=outcome.reason[:200],
                    )
                    await _emit(
                        on_loop_event,
                        ToolRejected(
                            kind="execute_guardrail",
                            tool_name=dispatch_name,
                            iteration=iteration,
                            detail=outcome.reason[:200],
                            duration_ms=int(
                                (time.monotonic() - iteration_started) * 1000
                            ),
                        ),
                    )
                    return _finish(
                        LoopResult(
                            prose="",
                            tool_name=None,
                            params=None,
                            iterations=iteration + 1,
                            calls=calls,
                            ended_by=dispatch_name,
                            refusal_facts=outcome.facts,
                        )
                    )
                if outcome is None:
                    if not tool.terminal:
                        raise RuntimeError(
                            f"read tool {dispatch_name!r} returned a terminal accept "
                            "— the declaration and the execute table skewed "
                            "(a read never ends the turn)"
                        )
                    if is_draft_merge:
                        assert candidate_record is not None
                        retired_candidate_ids.add(candidate_record.candidate_id)
                        drafts.pop(candidate_record.candidate_id, None)
                        latest_draft_id = None
                    if is_correction:
                        retired_candidate_ids.add(candidate_record.candidate_id)
                        candidates.pop(candidate_record.candidate_id, None)
                        repair_candidate_id = None
                    await _emit(on_loop_event, TerminalAccepted(tool_name=dispatch_name))
                    return _finish(
                        LoopResult(
                            prose=speech,
                            tool_name=dispatch_name,
                            params=params,
                            iterations=iteration + 1,
                            calls=calls,
                        )
                    )
                logger.info(
                    "tool_loop_rejection",
                    agent=self.name,
                    iteration=iteration,
                    kind="execute_guardrail",
                    tool=dispatch_name,
                    detail=outcome[:200],
                )
                if is_correction:
                    retired_candidate_ids.add(candidate_record.candidate_id)
                    candidates.pop(candidate_record.candidate_id, None)
                    repair_candidate_id = None
                if batched:
                    await remember(call, call_id, ToolObservation(outcome, ok=False))
                    await _emit(on_loop_event, ReadAccepted(tool_name=dispatch_name, ok=False))
                    continue
                await remember(call, call_id, ToolObservation(outcome, ok=False),
                    (candidate_record.arguments if is_draft_merge and candidate_record is not None else params.model_dump(mode="json") if params is not None else {}),
                    candidate_record=candidate_record if (is_correction or is_draft_merge) else None,
                    candidate_active=is_draft_merge, target_tool=dispatch_name if (is_correction or is_draft_merge) else None)
                rejection_digest = (
                    candidate_progress_digest(candidate_record)
                    if candidate_record is not None and (is_correction or is_draft_merge)
                    else tool_progress_digest(dispatch_name, call.arguments)
                    if dispatch_name in {"design_video", "split_clip"}
                    else None
                )
                stopped = await _reject(
                    ToolRejected(
                        kind="execute_guardrail",
                        tool_name=dispatch_name,
                        iteration=iteration,
                        detail=outcome[:200],
                        duration_ms=int((time.monotonic() - iteration_started) * 1000),
                        candidate_digest=rejection_digest,
                    ),
                    feedback=outcome,
                    iteration=iteration,
                )
                if stopped is not None:
                    return stopped
            if finish_batch and len(batch_observations) == len(result.tool_calls):
                settlement = await finish_batch(batch_observations)
                if settlement is not None:
                    if settlement.stop_after_observation:
                        return _finish(LoopResult(prose="", tool_name=group.name, params=params,
                                                  iterations=iteration + 1, calls=calls))
                    if not settlement.ok:
                        stopped = await _reject(
                            ToolRejected(kind="execute_guardrail", tool_name=group.name, iteration=iteration,
                                         detail=settlement.text[:200], duration_ms=0),
                            feedback=settlement.text, iteration=iteration,
                        )
                        if stopped is not None:
                            return stopped
        exhausted_candidate = candidates.get(repair_candidate_id or "")
        if exhausted_candidate is not None:
            await retire_failed_candidate(exhausted_candidate, iteration=self.max_iterations - 1, kind="exhausted")
        await _emit(on_loop_event, LoopExhausted(iterations=self.max_iterations))
        return _finish(
            LoopResult(
                prose="",
                tool_name=None,
                params=None,
                iterations=self.max_iterations,
                calls=calls,
                exhausted=True,
            )
        )

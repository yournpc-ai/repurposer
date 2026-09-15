"""The bounded tool-loop harness form (ADR-077 判词② — 会话层工具 loop 化).

The chat intent surface's call shape: the model speaks prose on the content
channel (it streams — the typewriter law holds natively) and closes the turn
by calling ONE terminal tool — the verdict union's mechanical translation
(ask → ``ask_user``, draft → ``present_plan``, start → ``start_run``,
task_list → ``propose_tasks``, edit_ops → ``apply_edit_ops``, wiring →
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

- ``max_iterations`` 封顶 — declared per agent (≤6 initial per the brief).
  The loop's worst case is a fold: cap × one call's cost, never open-ended
  (报价 = fold 的会话层形态 — chat turns aren't pre-quoted, the bound is
  what makes that safe).
- 终态工具一调即停 — a terminal tool's accepted call ends the turn. The
  perception family's tools are declared ``terminal=False``: an accepted
  read feeds its observation back on the wire (assistant tool_call +
  role:tool result — the standard continuation) and the loop iterates.
- 零副作用往返 — the loop itself writes nothing and never commits; the
  executions write through the three only doors (edit ops / wiring ops /
  ``create_run``), flush-only; the read tools carry no writes at all
  (只读纪律 — their implementations hold zero write functions).

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

from app.agents.base import AGENTS, jinja_env
from app.providers.llm.base import LLMError, LLMSchemaError
from app.providers.llm.minimax import MiniMaxClient, minimax_client

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
    """

    name: str
    description: str
    params_model: type[BaseModel] | None
    terminal: bool = True


def tool_spec(tool: ChatTool) -> dict:
    """The tool's OpenAI-compatible wire spec (the client seam's payload
    shape — the same dict the 2026-09-11/12 spike verified)."""
    parameters = (
        tool.params_model.model_json_schema()
        if tool.params_model is not None
        else {"type": "object", "properties": {}}
    )
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
        },
    }


@dataclass
class LoopResult:
    """One turn's loop outcome.

    ``tool_name=None`` + ``exhausted=False`` = the bare final reply (the
    model spoke without calling a tool — read as the answer verdict, the
    read-tolerant floor). ``exhausted=True`` = the iteration cap was hit
    with every call rejected — the caller degrades honestly (the cannot-do
    line or the code-composed topic question), never a fabricated success.
    ``calls`` = the tool sequence trace (the scenario suite's T4 assertion
    target).
    """

    prose: str
    tool_name: str | None
    params: BaseModel | None
    iterations: int
    calls: list[str] = field(default_factory=list)
    exhausted: bool = False


def _loop_echo(feedback: str) -> str:
    """The loop's structured echo — the funnel repair echo's tool-form twin
    (``agents/base.py`` ``_repair_echo``): a retry without feedback is just
    rolling the dice twice (ADR-039 P3 — the one bounded repair, re-homed
    into the loop)."""
    return (
        f"\n\nYour previous tool call was rejected: {feedback}. "
        "Speak to the user if the situation changed for them, then call the "
        "right tool with valid arguments."
    )


def _compose_speech(parts: list[str]) -> str:
    """The turn's ONE speech from its kept parts (言语账本): an accepted read
    iteration's prose + the terminal iteration's prose join on a blank line;
    a rejected call's prose never reaches here (replaced speech). Single-part
    turns (the T2a-pure form) come out as the part itself, stripped."""
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


@dataclass(frozen=True)
class ToolObservation:
    """A NON-terminal tool's accepted result (T2b 感知族 — the read tools'
    return channel). The text is model-facing (compact lines, capped by the
    execute); the loop appends it to the wire as the role:tool message and
    iterates. A terminal tool's execute never returns this (skew = loud)."""

    text: str


# Execute signature: (tool name, validated params, the turn's composed speech
# so far) → None when a TERMINAL call is ACCEPTED (the stop), the structured
# feedback string when a call is REJECTED (the loop echoes it and iterates),
# or a ToolObservation when a NON-terminal read call is accepted (fed back,
# loop continues). The speech seat exists because the executions need it —
# the docked question row's content, the plan echo, the answer message all
# carry the turn's speech (ask 三分解剖 ① / 任务书回声) — and that speech is
# the ACCUMULATED one: words spoken before a kept read are part of the reply.
# All side effects belong to the executor; the loop writes nothing.
LoopExecute = Callable[
    [str, BaseModel | None, str], Awaitable[str | None | ToolObservation]
]


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
        client: MiniMaxClient | None = None,
        packs: list[str] | None = None,
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
        self.client = client or minimax_client
        self.packs = packs or []
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
        **ctx: Any,
    ) -> LoopResult:
        """Run the bounded loop: assemble → render → [generate_with_tools →
        execute → feedback/observation] × at most ``max_iterations``.

        ``execute`` returns None to accept a TERMINAL call (the stop), a
        feedback string to reject (echoed, one more iteration), or a
        ToolObservation to accept a NON-terminal read (the loop continues
        with the observation on the wire). The hooks:

        - ``on_delta``: prose fragments — iteration 0 only (a rejected
          iteration's speech is replaced speech; later iterations run quiet
          and the envelope paces out — the repair-never-streams law).
        - ``on_reasoning``: reasoning fragments, a liveness signal only.
        - ``on_tool_call``: a call's name became known (the phase-frame
          seam — a read tool's name-known frame IS the inspecting family's
          「正在查曲库…」seat). Streaming path: the client fires it as the
          name arrives; quiet iterations: fired when the response lands.
        - ``on_tool_ready``: a call's arguments completed and validated,
          pre-execution (the question.preview seam — structure, not prose;
          fires on every iteration).
        - ``on_repair``: a rejection iteration begins (the funnel's reserved
          kwarg's loop seat — the thinking row's "repairing" label rides it).
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
            from app.agents.contexts import pack_instructions  # deferred: contexts pulls the chat/pipeline assembly layer

            template_kwargs["packs"] = pack_instructions(self.packs)
        user_prompt = jinja_env.get_template(self.prompt).render(**template_kwargs)
        specs = [tool_spec(t) for t in self.tools]
        by_name = {t.name: t for t in self.tools}
        base_messages: list[dict] = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": user_prompt},
        ]
        calls: list[str] = []
        # 言语账本 (T2b): an ACCEPTED read iteration's speech is kept speech —
        # it composes into the envelope's prefix (the terminal execution and
        # the LoopResult both carry the composed whole). A rejected call's
        # speech is replaced speech and never enters the parts.
        speech_parts: list[str] = []
        # The wire continuation after an accepted read: the assistant tool_call
        # echo + the role:tool observation (the standard OpenAI form). The
        # tail SURVIVES later rejections (they ride the user-message echo —
        # one rejection form only) so a retry never pays a second read.
        observation_tail: list[dict] = []
        for iteration in range(self.max_iterations):
            if iteration and on_repair is not None:
                await _emit(on_repair)
            streaming = on_delta is not None and iteration == 0
            messages = [*base_messages, *observation_tail]
            try:
                if streaming:
                    result = await self.client.generate_stream_with_tools(
                        messages=messages,
                        tools=specs,
                        temperature=self.temperature,
                        on_delta=on_delta,
                        on_reasoning=on_reasoning,
                        on_tool_call=on_tool_call,
                    )
                else:
                    result = await self.client.generate_with_tools(
                        messages=messages,
                        tools=specs,
                        temperature=self.temperature,
                    )
                    for tool_call in result.tool_calls:
                        await _emit(on_tool_call, tool_call.name)
            except LLMSchemaError as e:
                # The truncation signature (finish_reason=tool_calls but
                # arguments hit EOF) — schema class: absorbed into the loop
                # with the reason as feedback, never a blind re-roll.
                base_messages[1] = {
                    "role": "user",
                    "content": user_prompt + _loop_echo(str(e)),
                }
                continue
            # Misplaced speech (an args-level "prose" habit key) reads as
            # speech when the content channel stayed empty (读容忍, below).
            prose = result.content
            if not result.tool_calls:
                # Bare final reply — the read-tolerant answer verdict (any
                # kept read-iteration speech composes in front of it).
                return LoopResult(
                    prose=_compose_speech([*speech_parts, prose]),
                    tool_name=None,
                    params=None,
                    iterations=iteration + 1,
                    calls=calls,
                )
            call = result.tool_calls[0]
            if len(result.tool_calls) > 1:
                # The prompts say exactly one tool; extra calls never run
                # (parallel gate actions would fork the turn's writes).
                logger.warning(
                    "tool_loop_extra_calls",
                    agent=self.name,
                    extra_calls=[c.name for c in result.tool_calls[1:]],
                )
            calls.append(call.name)
            tool = by_name.get(call.name)
            if tool is None:
                base_messages[1] = {
                    "role": "user",
                    "content": user_prompt
                    + _loop_echo(
                        f"unknown tool {call.name!r} — call exactly one of: "
                        + ", ".join(t.name for t in self.tools)
                    ),
                }
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
            if not prose.strip() and isinstance(habit_prose, str):
                prose = habit_prose
            params: BaseModel | None = None
            if tool.params_model is not None:
                try:
                    params = tool.params_model.model_validate(raw)
                except ValidationError as e:
                    base_messages[1] = {
                        "role": "user",
                        "content": user_prompt + _loop_echo(str(e)),
                    }
                    continue
            await _emit(on_tool_ready, call.name, params)
            speech = _compose_speech([*speech_parts, prose])
            outcome = await execute(call.name, params, speech)
            if isinstance(outcome, ToolObservation):
                if tool.terminal:
                    raise RuntimeError(
                        f"terminal tool {call.name!r} returned a ToolObservation "
                        "— the declaration and the execute table skewed "
                        "(a terminal call ends the turn, never observes)"
                    )
                # A read accepted (T2b 感知族): the iteration's speech is KEPT
                # (it may have streamed — erasing it would glitch; the
                # envelope's prefix composes it), and the observation rides
                # the wire's standard continuation so the next iteration
                # reads what it asked for. Read executions never reject on
                # content — a miss is an honest empty observation — but a
                # feedback string stays legal and iterates like any rejection.
                speech_parts.append(prose)
                call_id = call.id or f"call_{iteration}"
                observation_tail.append(
                    {
                        "role": "assistant",
                        "content": prose or "",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(
                                        call.arguments, ensure_ascii=False
                                    ),
                                },
                            }
                        ],
                    }
                )
                observation_tail.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": call.name,
                        "content": outcome.text,
                    }
                )
                continue
            if outcome is None:
                if not tool.terminal:
                    raise RuntimeError(
                        f"read tool {call.name!r} returned a terminal accept "
                        "— the declaration and the execute table skewed "
                        "(a read never ends the turn)"
                    )
                return LoopResult(
                    prose=speech,
                    tool_name=call.name,
                    params=params,
                    iterations=iteration + 1,
                    calls=calls,
                )
            base_messages[1] = {
                "role": "user",
                "content": user_prompt + _loop_echo(outcome),
            }
        return LoopResult(
            prose="",
            tool_name=None,
            params=None,
            iterations=self.max_iterations,
            calls=calls,
            exhausted=True,
        )

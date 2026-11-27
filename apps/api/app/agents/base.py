"""The single Agent class — every LLM decision unit is a declared instance (N-30).

A declaration is data, not a subclass: ``name`` / ``prompt`` (jinja template,
versioned with the code) / ``schema`` (output contract) / ``system`` /
``temperature`` / ``assemble`` (+ optional ``postprocess`` /
``media_text_fallback`` / ``fallback`` / ``packs``). The call funnel: assemble → render →
``client.generate`` (schema enforced at the Model boundary) → one bounded
repair round on schema rejection → postprocess.

Repair carries feedback, never a blind re-roll (ADR-039 P3): a schema
rejection (``LLMSchemaError``) comes back once with the structured echo
appended to the same user message; a second rejection is the call's failure.
The same echo carries adjudication feedback from the caller (the chat loop's
registry/compile rejections) via the reserved ``repair_feedback`` kwarg.
Transport hiccups stay on the client layer's tenacity — a transport concern,
never repaired here.

Fallbacks are declared, never silent: ``media_text_fallback`` (multimodal →
text-only degradation) and ``fallback`` (last-resort result builder — the
intent router's never-a-white-screen default plan is the precedent) are
visible at the declaration; everything else raises.

Purity is signature-enforced (ADR-039): an agent's inputs are its assemble
function's parameter list — ``understand``'s assemble has no persona
parameter, so injecting one is a type error, not a prompt warning.

The one sanctioned subclass is ``StreamingAgent`` (N-30) — the chat intent
agents' streaming form (N-26).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
import asyncio
import contextvars
import hashlib
import time
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:  # the loop form's sibling declaration (no runtime import — tool_loop imports THIS module)
    from app.agents.tool_loop import ToolLoopAgent

import structlog
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from pydantic import BaseModel

from app.providers.llm import get_llm_client
from app.providers.llm.base import LLMClient, LLMError, LLMSchemaError
from app.agents.errors import AgentBudgetError, AgentOutputError, AgentStopError
from app.providers.llm.trace import trace_argument_normalization
from app.metering import bind_model_prompt, current_model_prompt
from app.agents.arguments import normalize_numeric_arguments, resolve_error_path, numeric_string_changes
from app.models.schemas import MediaInput

logger = structlog.get_logger()

OutT = TypeVar("OutT", bound=BaseModel)

# Provenance is diagnostic metadata attached to a str; it never changes the
# rendered wire text. Track executed includes, including cached templates,
# rather than guessing dependencies by scanning an entire prompt directory.
_prompt_sources: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "prompt_sources", default=None,
)


class RenderedPrompt(str):
    def __new__(cls, value: str, sources: list[dict]):
        result = super().__new__(cls, value)
        result.sources = sources
        return result


def _record_prompt_source(env, name):
    sources = _prompt_sources.get()
    if sources is None or not name or env.loader is None:
        return
    source, filename, _ = env.loader.get_source(env, name)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if not any(item["template"] == name and item["sha256"] == digest for item in sources):
        sources.append({"template": name, "path": filename, "sha256": digest,
                        "text": source, "chars": len(source)})


class PromptTemplate(Template):
    def render(self, *args, **kwargs):
        sources: list[dict] = []
        token = _prompt_sources.set(sources)
        try:
            _record_prompt_source(self.environment, self.name)
            return RenderedPrompt(super().render(*args, **kwargs), sources)
        finally:
            _prompt_sources.reset(token)


class PromptEnvironment(Environment):
    template_class = PromptTemplate

    def get_template(self, name, parent=None, globals=None):
        template = super().get_template(name, parent, globals)
        _record_prompt_source(self, template.name)
        return template

    def select_template(self, names, parent=None, globals=None):
        template = super().select_template(names, parent, globals)
        _record_prompt_source(self, template.name)
        return template


# The one jinja environment (previously rebuilt in five agent modules).
# auto_reload=True: prompt iteration is this project's core activity, and
# uvicorn --reload watches only *.py — without this, a .j2 edit silently
# keeps serving the compiled template until the process restarts. Cost is
# one stat() per render, nothing next to an LLM call.
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
jinja_env = PromptEnvironment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    auto_reload=True,
)

# Maximum characters to send per text to stay well within the model window.
MAX_CHARS_PER_TEXT = 150_000

# The roster dict (N-30): every declared instance self-registers on
# construction — shared crew (``agents/registry.py``) and tool-private
# declarations (``tools/<pkg>/agents.py``) alike, so ``AGENTS`` enumerates
# the whole crew once the registry door (``app/tools/__init__.py``) has
# imported every package. The startup self-check walks node→agent references
# against it (ADR-039 P2). Two declaration forms register here: ``Agent``
# (the single-call funnel) and ``agents/tool_loop.py``'s ``ToolLoopAgent``
# (the chat surface's bounded tool loop, ADR-077 判词②) — the self-check's
# pack resolution reads only ``name``/``packs``, shared by both.
AGENTS: dict[str, "Agent | ToolLoopAgent"] = {}

# assemble() returns (template kwargs, multimodal inputs).
AssembleResult = tuple[dict[str, Any], list[MediaInput]]

# Delta callbacks for the streaming form (N-26): raw response fragments /
# reasoning fragments, sync or async.
DeltaCallback = Callable[[str], Awaitable[None] | None]

# Repair-round visibility (2026-09-11 服务感): the funnel's one structural
# event — "the first proposal was schema-rejected, the repair round is
# running" — surfaced so the caller can say so (the chat layer labels the
# thinking row) instead of letting the repair window read as frozen
# thinking. Reserved funnel kwarg ``on_repair``: popped before assemble,
# exactly like ``repair_feedback`` — it never reaches the assemble inputs.
RepairCallback = Callable[[], Awaitable[None] | None]


def trim_texts(texts: list[str]) -> list[str]:
    """Return non-empty texts trimmed to a safe length."""
    return [t[:MAX_CHARS_PER_TEXT] for t in texts if t and t.strip()]


def _user_message(user_prompt: str, media: list[MediaInput]) -> dict[str, Any]:
    """Build a user message mixing text prompt and media content parts."""
    content: list[dict[str, Any]] = []
    for item in media:
        part_key = f"{item.type}_url"
        content.append({"type": part_key, part_key: {"url": item.data_url}})
        if item.caption:
            content.append({"type": "text", "text": item.caption})
    content.append({"type": "text", "text": user_prompt})
    return {"role": "user", "content": content}


def _repair_echo(feedback: str) -> str:
    """The repair round's structured echo: the rejection rides the same user
    message, so the model SEES what it broke — a retry without feedback is
    just rolling the dice twice (blind retries are retired, ADR-039 P3)."""
    return (
        f"\n\n上次提案被拒绝：{feedback}。请修正并返回有效提案。"
    )


def preserve_valid_candidate(previous: Any, current: Any, errors: list[dict], *, schema: dict | None = None) -> Any:
    """Apply a schema correction only where the previous candidate was invalid.

    Discriminator names in Pydantic locations aren't JSON keys. Resolve each
    error against the original input before comparing paths. No defaults or
    authored values are invented, and array shape changes remain possible at
    an invalid subtree. This candidate is still validated in full afterwards.
    """
    from copy import deepcopy

    invalid = [resolve_error_path(previous, error.get("loc", ()), schema) for error in errors]

    def related(path):
        return any(path[:len(bad)] == bad or bad[:len(path)] == path for bad in invalid)

    def merge(old, new, path=()):
        if not related(path):
            return deepcopy(old)
        if isinstance(old, dict) and isinstance(new, dict):
            result = deepcopy(new)
            for key, value in old.items():
                child = (*path, key)
                if key in new:
                    result[key] = merge(value, new[key], child)
                elif not related(child):
                    result[key] = deepcopy(value)
            return result
        if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
            if candidate_structure_changed(old, new):
                return deepcopy(new)
            return [merge(a, b, (*path, index)) for index, (a, b) in enumerate(zip(old, new))]
        return deepcopy(new)

    return merge(previous, current)


def candidate_structure_changed(previous: Any, current: Any) -> bool:
    """Array size/order/identity changes require a complete replacement candidate."""
    if isinstance(previous, dict) and isinstance(current, dict):
        return any(candidate_structure_changed(previous[k], current[k]) for k in previous.keys() & current.keys())
    if isinstance(previous, list) and isinstance(current, list):
        if len(previous) != len(current):
            return True
        identities = {"op", "scene_id", "track_id", "clip_id", "object_id", "animation_id", "snapshot_id", "kind", "at", "id"}
        for a, b in zip(previous, current):
            if isinstance(a, dict) and isinstance(b, dict) and any(a[k] != b[k] for k in identities & a.keys() & b.keys()):
                return True
            if candidate_structure_changed(a, b):
                return True
    return False


class Agent(Generic[OutT]):
    """One LLM decision unit, declared (N-30). See module docstring."""

    def __init__(
        self,
        *,
        name: str,
        prompt: str,
        schema: type[OutT],
        system: str,
        assemble: Callable[..., AssembleResult],
        temperature: float = 0.3,
        postprocess: Callable[[OutT, dict[str, Any]], OutT] | None = None,
        media_text_fallback: bool = False,
        fallback: Callable[..., OutT] | None = None,
        client: LLMClient | None = None,
        packs: list[str] | None = None,
        timeout_s: float | None = None,
        stream: bool = False,
        read_tools: list[Any] | None = None,
        max_read_iterations: int = 16,
    ) -> None:
        self.name = name
        self.prompt = prompt
        self.schema = schema
        self.system = system
        self.assemble = assemble
        self.temperature = temperature
        self.postprocess = postprocess
        # Declared fallback (ADR-039: silent degradation is the exception, and
        # it is visible at the declaration): when a multimodal call fails for
        # any reason, retry once with the text-only prompt.
        self.media_text_fallback = media_text_fallback
        # Declared last-resort result builder (same discipline): called with
        # the assemble ctx when the funnel exhausted its repair round with a
        # LLMError — the fallback fires AFTER the repair round, never
        # instead of it, and its result returns as-is (postprocess does NOT
        # run on it: a fallback builds a final-shaped result). None = raise
        # (the default).
        self.fallback = fallback
        # Declared skill packs (N-42 指令包): assembly-time prompt injection,
        # never runtime discovery — the assembler weaves the bodies verbatim.
        self.packs = packs or []
        # Declared per-request timeout override (rides the request call, not
        # the pool — music_generation 180s 同律): for agents whose payload is
        # known to run past the pool's 120s default. None = inherit.
        self.timeout_s = timeout_s
        # Declared streaming transport (2026-10-16, streaming transport): the
        # call rides ``generate_stream`` with NO delta consumer — reasoning
        # chunks keep the read timeout honest (a slow-but-alive generation
        # never false-fires it), ``llm_first_chunk`` gives liveness in
        # seconds, and a consumer-less retry is always lawful (nothing was
        # ever emitted downstream). The non-stream form's all-or-nothing
        # semantics (zero bytes until the whole generation lands) made a
        # provider-slow day indistinguishable from a hang, and tenacity then
        # burned the腹稿 on every read timeout (309340c6/6c2103ee 取证).
        self.stream = stream
        # Optional Director-only read tools. They are activated by a reserved
        # per-call executor, never registered as Chat tools or DAG capabilities.
        self.read_tools = read_tools or []
        self.max_read_iterations = max_read_iterations
        self.client = client or get_llm_client()
        if name in AGENTS:
            raise RuntimeError(f"Duplicate agent declaration: {name}")
        AGENTS[name] = self

    async def call(self, **ctx: Any) -> OutT:
        """Run the funnel: assemble → render → generate (one bounded repair
        round on schema rejection) → postprocess.

        ``repair_feedback`` is a reserved funnel kwarg (it never reaches
        ``assemble``): adjudication feedback from the caller — e.g. the chat
        loop's registry/compile rejection — rides the same structured echo
        as the schema-repair round. ``on_repair`` is the second reserved
        kwarg: a callback fired once when the repair round starts (repair
        visibility, 2026-09-11).
        """
        return await self._funnel(ctx)

    async def _funnel(
        self,
        ctx: dict[str, Any],
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
    ) -> OutT:
        repair_feedback = ctx.pop("repair_feedback", None)
        on_repair: RepairCallback | None = ctx.pop("on_repair", None)
        read_executor = ctx.pop("read_executor", None)
        context_snapshot = ctx.pop("context_snapshot", None)
        template_kwargs, media = self.assemble(**ctx)
        if self.packs:
            from app.agents.contexts import pack_instructions  # deferred: contexts pulls the chat/pipeline assembly layer

            template_kwargs["packs"] = pack_instructions(self.packs)
        user_prompt = jinja_env.get_template(self.prompt).render(**template_kwargs)
        user_sources = getattr(user_prompt, "sources", [])
        if context_snapshot is not None:
            user_prompt += "\n\n" + context_snapshot.text
        if repair_feedback is not None:
            user_prompt += _repair_echo(str(repair_feedback))
        t0 = time.monotonic()
        logger.info(
            "agent_call_started",
            agent=self.name,
            media_count=len(media),
            prompt_chars=len(user_prompt),
        )
        try:
            with bind_model_prompt({
                "agent": self.name,
                "system_sources": getattr(self.system, "sources", []),
                "user_sources": user_sources,
                "template_variables": sorted(template_kwargs),
                "declared_packs": self.packs,
                "pack_text": template_kwargs.get("packs"),
            }):
                result = await self._attempt(
                    user_prompt, media, on_delta, on_reasoning, on_repair,
                    read_executor=read_executor,
                )
        except AgentStopError:
            raise
        except LLMError:
            if self.fallback is None:
                raise
            logger.warning("agent_declared_fallback", agent=self.name)
            return self.fallback(**ctx)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "agent_call_failed",
                agent=self.name,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
            raise LLMError(f"{self.name} failed: {e}") from e
        if self.postprocess is not None:
            result = self.postprocess(result, ctx)
        logger.info(
            "agent_call_completed",
            agent=self.name,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        return result

    async def _attempt(
        self,
        user_prompt: str,
        media: list[MediaInput],
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        on_repair: RepairCallback | None = None,
        read_executor: Any = None,
    ) -> OutT:
        """One pass through the Model boundary, plus the ONE bounded repair
        round: a schema rejection comes back with the structured echo
        appended to the same user message. The repair round never streams —
        two interleaved delta streams for one bubble is a worse failure than
        a text swap at the envelope (N-26). ``on_repair`` fires once as the
        round starts — the caller's visibility hook, never a retry trigger.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system},
            self._user_message(user_prompt, media),
        ]
        try:
            return await self._generate(
                messages, user_prompt, media, on_delta, on_reasoning,
                read_executor=read_executor,
            )
        except LLMSchemaError as first_error:
            logger.warning(
                "agent_schema_repair",
                agent=self.name,
                error=str(first_error),
            )
            if on_repair is not None:
                notified = on_repair()
                if notified is not None:
                    await notified
            repair_prompt = user_prompt + _repair_echo(str(first_error))
            repair_messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.system},
                self._user_message(repair_prompt, media),
            ]
            return await self._generate(
                repair_messages, repair_prompt, media,
                read_executor=read_executor,
            )

    @staticmethod
    def _user_message(user_prompt: str, media: list[MediaInput]) -> dict[str, Any]:
        """The user message's payload shape — a per-form declaration point:
        the base funnel mixes media content parts; the streaming form (chat
        intent, never multimodal) keeps its historical plain-string shape."""
        return _user_message(user_prompt, media)

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        user_prompt: str,
        media: list[MediaInput],
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        read_executor: Any = None,
    ) -> OutT:
        """Call the Model boundary; declared media→text fallback when present.

        Media inputs (video/image/slide data URLs) are brittle: providers may
        reject them due to size, format, or transient issues, and the resulting
        exceptions are not always easy to classify. When media inputs are
        present AND the declaration allows it, fall back to the text-only
        prompt so generation can still succeed from transcripts/extracted
        text. A schema rejection is the carve-out: it routes to the repair
        round with the media still attached (media-derived fields must never
        be blind-labeled on a text-only retry). Failures without media inputs
        are re-raised immediately. The fallback retry never streams (same
        interleaved-deltas reason as the repair round).
        """
        try:
            if read_executor is not None:
                if not self.read_tools:
                    raise LLMError(f"{self.name} does not declare Director read tools")
                return await self._generate_with_read_tools(
                    messages, read_executor,
                )
            if on_delta is not None:
                return await self.client.generate_stream(
                    messages=messages,
                    response_model=self.schema,
                    temperature=self.temperature,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                )
            if self.stream:
                # Declared streaming transport, no delta consumer (see the
                # declaration): liveness + honest read timeouts, the same
                # validated return as ``generate``.
                return await self.client.generate_stream(
                    messages=messages,
                    response_model=self.schema,
                    temperature=self.temperature,
                    timeout_s=self.timeout_s,
                )
            return await self.client.generate(
                messages=messages,
                response_model=self.schema,
                temperature=self.temperature,
                timeout_s=self.timeout_s,
            )
        except LLMSchemaError:
            # A schema rejection is NOT media brittleness — it belongs to the
            # repair round (with the media still attached, so media-derived
            # fields never get blind-labeled on a text-only retry).
            raise
        except Exception as first_error:  # noqa: BLE001
            if read_executor is not None:
                raise
            if not media or not self.media_text_fallback:
                raise
            logger.warning(
                "multimodal_failed_falling_back_to_text",
                agent=self.name,
                error=str(first_error),
                error_type=type(first_error).__name__,
                media_count=len(media),
            )
            text_only_messages: list[dict[str, Any]] = [
                messages[0],
                {"role": "user", "content": user_prompt},
            ]
            return await self.client.generate(
                messages=text_only_messages,
                response_model=self.schema,
                temperature=self.temperature,
            )

    async def _generate_with_read_tools(
        self,
        messages: list[dict[str, Any]],
        read_executor: Any,
    ) -> OutT:
        """One typed Director answer behind bounded, non-terminal package reads.

        The first ``submit_direction`` carries the ordinary Agent schema;
        a correction exposes only rejected top-level fields and merges them
        into the retained candidate before full validation. Read observations stay inside this private
        harness; no prose, Chat activity, external tool declaration or second
        user-facing intent channel is created. The caller owns one read budget
        across this loop and any outer schema/grounding repair.
        """
        import json
        from copy import deepcopy
        from pydantic import ConfigDict, ValidationError, create_model
        from pydantic_core import PydanticUndefined
        from app.agents.tool_loop import (
            ChatTool,
            ToolObservation,
            observation_wire_content,
            tool_spec,
            _unwrap_item_dialect,
        )

        submit = ChatTool(
            name="submit_direction",
            description=(
                "读取本作品所需的包内证据后，提交完整设计。参数须为符合类型要求的完整设计结果。"
            ),
            params_model=self.schema,
        )
        declarations = [*self.read_tools, submit]
        specs = [tool_spec(tool) for tool in declarations]
        by_name = {tool.name: tool for tool in declarations}
        tail: list[dict[str, Any]] = []
        feedback: str | None = None
        force_submit = False
        submission_rejections = 0
        previous_candidate = None
        candidate_errors: list[dict] = []

        for iteration in range(self.max_read_iterations):
            wire = [*messages, *tail]
            if feedback:
                wire.append({
                    "role": "user",
                    "content": (
                        "上一步设计被拒绝：" + feedback
                        + ("。现在调用 submit_direction，不再检索包内资料。" if force_submit
                           else "。继续进行有效的包内读取，或调用 submit_direction。")
                    ),
                })
            feedback = None
            can_read = getattr(read_executor, "can_read", lambda: True)
            available = [submit] if force_submit or not can_read() else declarations
            read_tool_names = getattr(read_executor, "read_tool_names", None)
            if read_tool_names is not None and not force_submit and can_read():
                allowed_reads = read_tool_names()
                available = [
                    tool for tool in available
                    if tool.name == submit.name or tool.name in allowed_reads
                ]
            correction_fields = None
            if previous_candidate is not None and candidate_errors:
                # Keep the correction small: the server already holds all
                # valid fields, including complete scenes and source identities.
                roots = {error['loc'][0] for error in candidate_errors if error.get('loc')}
                if any(not error.get('loc') for error in candidate_errors):
                    roots = set(self.schema.model_fields)
                fields = {}
                for name in self.schema.model_fields:
                    if name not in roots:
                        continue
                    info = deepcopy(self.schema.model_fields[name])
                    info.default = PydanticUndefined
                    info.default_factory = None
                    fields[name] = (info.annotation, info)
                correction = create_model(
                    self.schema.__name__ + 'Correction',
                    __config__=ConfigDict(extra='forbid'), **fields,
                )
                correction_fields = set(fields)
                available = [ChatTool(
                    name=submit.name,
                    description="只返回被拒绝的字段。服务端保留其他字段，合并后会校验完整设计。",
                    params_model=correction,
                )]
            available_names = {tool.name for tool in available}
            specs = [tool_spec(tool) for tool in available]
            charge_generation = getattr(read_executor, "charge_generation", None)
            if charge_generation is not None:
                await charge_generation()
            try:
                # A model call owns the Agent's declared timeout. Package-reader
                # session age is unrelated to model execution or browser waits.
                async with asyncio.timeout(self.timeout_s):
                    result = await self.client.generate_stream_with_tools(
                        messages=wire,
                        tools=specs,
                        temperature=self.temperature,
                        thinking=False,
                    )
            except TimeoutError as exc:
                raise AgentBudgetError(f"{self.name} model call timed out") from exc
            if not result.tool_calls:
                try:
                    raw = json.loads(result.content)
                    raw, changes = normalize_numeric_arguments(raw, self.schema.model_json_schema())
                    trace_argument_normalization(model_call_id=(current_model_prompt() or {}).get("model_call_id"), tool_call_id=None, agent=self.name, iteration=iteration, changes=changes)
                    if previous_candidate is not None:
                        if isinstance(raw, dict) and correction_fields is not None:
                            raw = {key: value for key, value in raw.items() if key in correction_fields}
                        raw = preserve_valid_candidate(previous_candidate, raw, candidate_errors, schema=self.schema.model_json_schema())
                    candidate = self.schema.model_validate(raw)
                    trace_argument_normalization(model_call_id=(current_model_prompt() or {}).get("model_call_id"), tool_call_id=None, agent=self.name, iteration=iteration, changes=numeric_string_changes(raw, candidate.model_dump(mode="json")))
                    return candidate
                except (ValidationError, ValueError) as exc:
                    if isinstance(exc, ValidationError):
                        previous_candidate = raw
                        candidate_errors = exc.errors(include_input=False, include_url=False)
                    submission_rejections += 1
                    if submission_rejections >= 2:
                        raise AgentOutputError(f"{self.name} output invalid after one correction: {exc}") from exc
                    feedback = str(exc)
                    force_submit = True
                    continue
            # Every returned call gets a matching result. Reads are sequential:
            # each remains subject to the same owner, text, media and wall limits.
            # A submission must stand alone, after all required evidence is read.
            call_results: list[dict[str, Any]] = []
            calls_wire: list[dict[str, Any]] = []
            for index, call in enumerate(result.tool_calls):
                call_id = call.id or f"director_read_{iteration}_{index}"
                calls_wire.append({
                    "id": call_id, "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                })
                tool = by_name.get(call.name)
                observation = None
                if tool is None or call.name not in available_names:
                    observation = ToolObservation("当前阶段不可用此工具，请提交完整设计。", ok=False)
                else:
                    tool_schema = tool.params_model.model_json_schema() if tool.params_model is not None else None
                    raw = _unwrap_item_dialect(dict(call.arguments), tool_schema)
                    for key in ("type", "kind", "prose"):
                        raw.pop(key, None)
                    if tool_schema is not None:
                        raw, changes = normalize_numeric_arguments(raw, tool_schema)
                        trace_argument_normalization(model_call_id=(current_model_prompt() or {}).get("model_call_id"), tool_call_id=call_id, agent=self.name, iteration=iteration, changes=changes)
                    if call.name == submit.name and previous_candidate is not None:
                        if correction_fields is not None:
                            raw = {key: value for key, value in raw.items() if key in correction_fields}
                        raw = preserve_valid_candidate(previous_candidate, raw, candidate_errors, schema=self.schema.model_json_schema())
                    if call.name == submit.name:
                        if len(result.tool_calls) != 1:
                            observation = ToolObservation("请先读取结果，再单独提交设计。本次未接受任何设计。", ok=False)
                        else:
                            try:
                                candidate = self.schema.model_validate(raw)
                                trace_argument_normalization(model_call_id=(current_model_prompt() or {}).get("model_call_id"), tool_call_id=call_id, agent=self.name, iteration=iteration, changes=numeric_string_changes(raw, candidate.model_dump(mode="json")))
                                return candidate
                            except ValidationError as exc:
                                submission_rejections += 1
                                logger.warning("director_submission_rejected", agent=self.name,
                                               attempt=submission_rejections,
                                               errors=exc.errors(include_input=False, include_url=False))
                                if submission_rejections >= 2:
                                    raise AgentOutputError(f"{self.name} output invalid after one correction: {exc}") from exc
                                previous_candidate = raw
                                candidate_errors = exc.errors(include_input=False, include_url=False)
                                force_submit = True
                                feedback = json.dumps(exc.errors(include_input=False, include_url=False), ensure_ascii=False, default=str) + "。立即修正并重新提交纠错工具声明的字段。服务端保留全部有效字段，未被判为无效的场景无需重发，不要重新开始查阅包内资料。"
                                observation = ToolObservation(feedback, ok=False)
                    else:
                        try:
                            params = tool.params_model.model_validate(raw) if tool.params_model is not None else None
                        except ValidationError as exc:
                            observation = ToolObservation(str(exc), ok=False)
                        else:
                            try:
                                observation = await read_executor(call.name, params)
                            except AgentBudgetError as exc:
                                # Preserve all call IDs, including remaining batch items.
                                # The next generation has only the submit tool available.
                                force_submit = True
                                observation = ToolObservation(str(exc) + "。请使用已有证据并调用 submit_direction。", ok=False)
                            if not isinstance(observation, ToolObservation):
                                raise RuntimeError("a Director read must return ToolObservation")
                call_results.append({
                    "role": "tool", "tool_call_id": call_id, "name": call.name,
                    "content": observation_wire_content(observation),
                })
            tail.append({"role": "assistant", "content": result.content or "", "tool_calls": calls_wire})
            tail.extend(call_results)
        raise AgentOutputError(
            f"{self.name} exhausted its {self.max_read_iterations}-iteration "
            "Director read loop without a valid direction"
        )


class StreamingAgent(Agent[OutT]):
    """The one sanctioned Agent subclass (N-30): a streaming single-call form
    (N-26, ``generate_stream`` + a caller-side prose extractor). Same funnel
    as ``call`` — the first attempt simply streams its raw fragments. (The
    chat intent agents LEFT this form for the tool loop, ADR-077 判词②
    2026-09-14 — prose is the content channel there, no extractor.)"""

    @staticmethod
    def _user_message(user_prompt: str, media: list[MediaInput]) -> dict[str, Any]:
        """Plain-string user content — the chat intent agents' historical
        payload shape (they never carry media; a parts list reads differently
        to the provider and flipped S3's start call, 2026-08-10)."""
        return {"role": "user", "content": user_prompt}

    async def call_stream(
        self,
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        **ctx: Any,
    ) -> OutT:
        """The streaming twin of ``call``: identical result, but raw
        response fragments flow through ``on_delta`` while the JSON
        generates. ``on_reasoning`` receives reasoning fragments (a liveness
        signal only — never shown to the user, never parsed)."""
        return await self._funnel(ctx, on_delta, on_reasoning)

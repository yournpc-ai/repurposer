"""The single Agent class — every LLM decision unit is a declared instance (N-30).

A declaration is data, not a subclass: ``name`` / ``prompt`` (jinja template,
versioned with the code) / ``schema`` (output contract) / ``system`` /
``temperature`` / ``assemble`` (+ optional ``postprocess`` /
``media_text_fallback`` / ``fallback``). The call funnel: assemble → render →
``client.generate`` (schema enforced at the Model boundary) → one bounded
repair round on schema rejection → postprocess.

Repair carries feedback, never a blind re-roll (ADR-039 P3): a schema
rejection (``MiniMaxSchemaError``) comes back once with the structured echo
appended to the same user message; a second rejection is the call's failure.
The same echo carries adjudication feedback from the caller (the chat loop's
registry/compile rejections) via the reserved ``repair_feedback`` kwarg.
Transport hiccups stay on the client layer's tenacity — a transport concern,
never repaired here.

Fallbacks are declared, never silent: ``media_text_fallback`` (multimodal →
text-only degradation) and ``fallback`` (last-resort result builder — the
plan agent's never-a-white-screen default task book is the precedent) are
visible at the declaration; everything else raises.

Purity is signature-enforced (ADR-039): an agent's inputs are its assemble
function's parameter list — ``director_understand``'s assemble has no persona
parameter, so injecting one is a type error, not a prompt warning.

The one sanctioned subclass is ``StreamingAgent`` (N-30) — the chat intent
agents' streaming form (N-26).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from app.clients.minimax import MiniMaxClient, MiniMaxError, MiniMaxSchemaError, minimax_client
from app.models.schemas import MediaInput, Storyboard

logger = structlog.get_logger()

OutT = TypeVar("OutT", bound=BaseModel)

# The one jinja environment (previously rebuilt in five agent modules).
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
)

# Maximum characters to send per text to stay well within the model window.
MAX_CHARS_PER_TEXT = 150_000

# The roster dict (N-30): every declared instance self-registers on
# construction — shared crew (``agents/registry.py``) and skill-private
# declarations (``skills/<pkg>/agents.py``) alike, so ``AGENTS`` enumerates
# the whole crew once the registry door (``app/skills/__init__.py``) has
# imported every package. The startup self-check walks node→agent references
# against it (ADR-039 P2).
AGENTS: dict[str, "Agent"] = {}

# assemble() returns (template kwargs, multimodal inputs).
AssembleResult = tuple[dict[str, Any], list[MediaInput]]

# Delta callbacks for the streaming form (N-26): raw response fragments /
# reasoning fragments, sync or async.
DeltaCallback = Callable[[str], Awaitable[None] | None]


def trim_texts(texts: list[str]) -> list[str]:
    """Return non-empty texts trimmed to a safe length."""
    return [t[:MAX_CHARS_PER_TEXT] for t in texts if t and t.strip()]


def find_slot(storyboard: Storyboard, slot: str) -> dict:
    """Return the matching StoryboardSlot as a dict, or an empty fallback."""
    for s in storyboard.slots:
        if s.slot == slot:
            return s.model_dump()
    return {}


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
        f"\n\nYour previous proposal was rejected: {feedback}. "
        "Fix it and return a valid proposal."
    )


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
        client: MiniMaxClient | None = None,
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
        # MiniMaxError — the fallback fires AFTER the repair round, never
        # instead of it, and its result returns as-is (postprocess does NOT
        # run on it: a fallback builds a final-shaped result). None = raise
        # (the default).
        self.fallback = fallback
        self.client = client or minimax_client
        if name in AGENTS:
            raise RuntimeError(f"Duplicate agent declaration: {name}")
        AGENTS[name] = self

    async def call(self, **ctx: Any) -> OutT:
        """Run the funnel: assemble → render → generate (one bounded repair
        round on schema rejection) → postprocess.

        ``repair_feedback`` is a reserved funnel kwarg (it never reaches
        ``assemble``): adjudication feedback from the caller — e.g. the chat
        loop's registry/compile rejection — rides the same structured echo
        as the schema-repair round.
        """
        return await self._funnel(ctx)

    async def _funnel(
        self,
        ctx: dict[str, Any],
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
    ) -> OutT:
        repair_feedback = ctx.pop("repair_feedback", None)
        template_kwargs, media = self.assemble(**ctx)
        user_prompt = jinja_env.get_template(self.prompt).render(**template_kwargs)
        if repair_feedback is not None:
            user_prompt += _repair_echo(str(repair_feedback))
        logger.info("agent_call_started", agent=self.name, media_count=len(media))
        try:
            result = await self._attempt(user_prompt, media, on_delta, on_reasoning)
        except MiniMaxError:
            if self.fallback is None:
                raise
            logger.warning("agent_declared_fallback", agent=self.name)
            return self.fallback(**ctx)
        except Exception as e:  # noqa: BLE001
            logger.error("agent_call_failed", agent=self.name, error=str(e))
            raise MiniMaxError(f"{self.name} failed: {e}") from e
        if self.postprocess is not None:
            result = self.postprocess(result, ctx)
        logger.info("agent_call_completed", agent=self.name)
        return result

    async def _attempt(
        self,
        user_prompt: str,
        media: list[MediaInput],
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
    ) -> OutT:
        """One pass through the Model boundary, plus the ONE bounded repair
        round: a schema rejection comes back with the structured echo
        appended to the same user message. The repair round never streams —
        two interleaved delta streams for one bubble is a worse failure than
        a text swap at the envelope (N-26)."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system},
            self._user_message(user_prompt, media),
        ]
        try:
            return await self._generate(messages, user_prompt, media, on_delta, on_reasoning)
        except MiniMaxSchemaError as first_error:
            logger.warning(
                "agent_schema_repair",
                agent=self.name,
                error=str(first_error),
            )
            repair_prompt = user_prompt + _repair_echo(str(first_error))
            repair_messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.system},
                self._user_message(repair_prompt, media),
            ]
            return await self._generate(repair_messages, repair_prompt, media)

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
    ) -> OutT:
        """Call the Model boundary; declared media→text fallback when present.

        Media inputs (video/image/slide data URLs) are brittle: providers may
        reject them due to size, format, or transient issues, and the resulting
        exceptions are not always easy to classify. When media inputs are
        present AND the declaration allows it, fall back to the text-only
        prompt so generation can still succeed from transcripts/extracted
        text. Failures without media inputs are re-raised immediately. The
        fallback retry never streams (same interleaved-deltas reason as the
        repair round).
        """
        try:
            if on_delta is not None:
                return await self.client.generate_stream(
                    messages=messages,
                    response_model=self.schema,
                    temperature=self.temperature,
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                )
            return await self.client.generate(
                messages=messages,
                response_model=self.schema,
                temperature=self.temperature,
            )
        except Exception as first_error:  # noqa: BLE001
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


class StreamingAgent(Agent[OutT]):
    """The one sanctioned Agent subclass (N-30): the chat intent agents'
    streaming form (N-26, ``generate_stream`` + the service-side
    ProseDeltaExtractor single funnel). Same funnel as ``call`` — the first
    attempt simply streams its raw fragments for the prose preview channel.
    """

    @staticmethod
    def _user_message(user_prompt: str, media: list[MediaInput]) -> dict[str, Any]:
        """Plain-string user content — the chat intent agents' historical
        payload shape (they never carry media; a parts list reads differently
        to the provider and flipped S3's start verdict, 2026-08-10)."""
        return {"role": "user", "content": user_prompt}

    async def call_stream(
        self,
        on_delta: DeltaCallback | None = None,
        on_reasoning: DeltaCallback | None = None,
        **ctx: Any,
    ) -> OutT:
        """The streaming twin of ``call``: identical verdict, but raw
        response fragments flow through ``on_delta`` while the JSON
        generates. ``on_reasoning`` receives reasoning fragments (a liveness
        signal only — never shown to the user, never parsed)."""
        return await self._funnel(ctx, on_delta, on_reasoning)

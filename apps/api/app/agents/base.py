"""The single Agent class — every LLM decision unit is a declared instance (N-30).

A declaration is data, not a subclass: ``name`` / ``prompt`` (jinja template,
versioned with the code) / ``schema`` (output contract) / ``system`` /
``temperature`` / ``assemble`` (+ optional ``postprocess`` /
``media_text_fallback``). The call funnel: assemble → render →
``client.generate`` (schema enforced at the Model boundary) → postprocess.

Purity is signature-enforced (ADR-039): an agent's inputs are its assemble
function's parameter list — ``director_understand``'s assemble has no persona
parameter, so injecting one is a type error, not a prompt warning.

Structured one-round repair, declared fallbacks beyond the multimodal one, and
template-level metering attribution land in P3 (docs/tasks/arch-overhaul.md);
the streaming subclass (chat intent) is the only legal specialization.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from app.clients.minimax import MiniMaxClient, MiniMaxError, minimax_client
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
# construction — shared crew (``agents/roster.py``) and skill-private
# declarations (``skills/<pkg>/agents.py``) alike, so ``AGENTS`` enumerates
# the whole crew once the registry door (``app/skills/__init__.py``) has
# imported every package. The startup self-check walks node→agent references
# against it (ADR-039 P2).
AGENTS: dict[str, "Agent"] = {}

# assemble() returns (template kwargs, multimodal inputs).
AssembleResult = tuple[dict[str, Any], list[MediaInput]]


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
        self.client = client or minimax_client
        if name in AGENTS:
            raise RuntimeError(f"Duplicate agent declaration: {name}")
        AGENTS[name] = self

    async def call(self, **ctx: Any) -> OutT:
        """Run the funnel: assemble → render → generate → postprocess."""
        template_kwargs, media = self.assemble(**ctx)
        user_prompt = jinja_env.get_template(self.prompt).render(**template_kwargs)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system},
            _user_message(user_prompt, media),
        ]
        logger.info("agent_call_started", agent=self.name, media_count=len(media))
        try:
            result = await self._generate(messages, user_prompt, media)
        except MiniMaxError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error("agent_call_failed", agent=self.name, error=str(e))
            raise MiniMaxError(f"{self.name} failed: {e}") from e
        if self.postprocess is not None:
            result = self.postprocess(result, ctx)
        logger.info("agent_call_completed", agent=self.name)
        return result

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        user_prompt: str,
        media: list[MediaInput],
    ) -> OutT:
        """Call the Model boundary; declared media→text fallback when present.

        Media inputs (video/image/slide data URLs) are brittle: providers may
        reject them due to size, format, or transient issues, and the resulting
        exceptions are not always easy to classify. When media inputs are
        present AND the declaration allows it, fall back to the text-only
        prompt so generation can still succeed from transcripts/extracted
        text. Failures without media inputs are re-raised immediately.
        """
        try:
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

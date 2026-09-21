"""Harness-side context assembly (ADR-039 P3, AGENT_ARCH §5.3).

One home for the deterministic prompt-context assembly every agent call
stands on — the services orchestrate, they never assemble:

- ``generation_context`` — the GenerationContext every generation node
  builds from the run's plan (moved from ``pipeline/step_context.py``,
  which keeps the mechanical media/digest helpers).
- ``output_one_liner`` — a visible output's one-line label.
- ``pack_instructions`` — weave an agent declaration's skill packs.

The chat loop's intent context is the Agent Interface's OWN assembly and
lives in ``app.chat.context.build_context`` (ADR-087 §6 Phase 5 ownership
ruling — each layer assembles its own context; the harness no longer reads
the conversation store or the outputs read face on chat's behalf).

Digest doctrine (ADR-077 判词②, T2b 感知族): the fixed digest stops at
IDENTITY level — what exists (assets / outputs / the graph / the latest
run's one-line marker), so the agent knows what it may point at and which
read tool answers the detail. Anything a read tool reads is never
pre-injected: per-step run progress lives behind ``get_run_status``, an
output's spec behind ``get_output_spec``, an asset's detail behind
``get_asset``, the material understanding behind ``get_understanding``
(the understanding-summary fixed injection — the interim B1 form — retired
before ever landing; the tool IS the read).
"""

from typing import Any

from app.models.schemas import (
    GenerationContext,
    ToneSettings,
)
from app.models.tables import (
    Persona,
    Project,
    WorkflowRun,
)
from app.platform.project_context import persona_context_from_row
from app.skills import SKILL_REGISTRY


def pack_instructions(packs: list[str]) -> str:
    """Weave an agent declaration's skill packs into one instructions block
    (N-42 指令包: assembly-time injection — the model never decides when a
    pack loads). Unknown names raise KeyError at weave time; the startup
    self-check resolves every declared pack first, so this never fires
    mid-run. Bodies join on a blank line so stacked packs (persona-level
    loaders, later batch) keep their markdown sections separated; a single
    pack renders byte-identical to its bare body."""
    return "\n".join(SKILL_REGISTRY[name].body for name in packs)


def generation_context(
    run: WorkflowRun,
    project: Project,
    persona: Persona | None,
    *,
    brand_music_id: str | None = None,
) -> GenerationContext:
    """Assemble the GenerationContext from the run's plan (context)."""
    ctx = run.context or {}
    tone_raw = ctx.get("tone_settings")
    return GenerationContext(
        persona=persona_context_from_row(persona),
        event_name=project.event_name,
        tone_settings=ToneSettings.model_validate(tone_raw) if tone_raw else None,
        target_language=ctx.get("target_language", "en"),
        instruction=ctx.get("instruction"),
        brand_music_id=brand_music_id,
    )


def output_one_liner(output: Any) -> str:
    """A one-line label for a visible output (type + first creative line)."""
    payload = output.payload or {}
    for key in ("hook", "title", "body"):
        text = payload.get(key)
        if text:
            return str(text).split("\n", 1)[0][:80]
    return ""

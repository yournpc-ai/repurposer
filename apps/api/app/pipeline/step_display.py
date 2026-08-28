"""Step display face (ADR-039 P1 split): stage hints, spec fields, and the
quantified summary lines the stepper reads.

All writers use their own session with ``jsonb_set`` — never the runner
session: that session stays open across LLM calls, and holding a row lock on
``workflow_steps`` (from a flushed spec update) deadlocks the metering
session. Direct ``node.spec`` assignment from a runner is a race for the same
reason (execute_step's post-runner commit would flush the stale in-memory
dict and clobber fields written meanwhile).

The mirror discipline (D9, 2026-08-28): a runner must NEVER dirty the
Session-2-loaded node (ORM attribute assignment) — the next autoflush locks
the row for the rest of the run and the runner's own display writers below
deadlock against their own session (the verify-bounce feedback-pop did
exactly this until it moved to ``_pop_spec_field``). Session-2 writes to the
step row belong to execute_step's final settle only.
"""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import array as pg_array

from app.models.database import AsyncSessionLocal
from app.models.schemas import IntentSlot
from app.models.tables import WorkflowStep

logger = structlog.get_logger()


async def _set_stage(node_id: UUID, stage: str) -> None:
    """Write the stepper's display-stage hint in its own session."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec, pg_array(["stage"]), func.to_jsonb(stage), True
                )
            )
        )
        await s.commit()


async def _set_spec_field(node_id: UUID, key: str, value: Any) -> None:
    """Write one spec field in its own session — same jsonb_set discipline as
    ``_set_stage``."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec, pg_array([key]), func.to_jsonb(value), True
                )
            )
        )
        await s.commit()


async def _pop_spec_field(node_id: UUID, key: str) -> None:
    """Remove one spec key in its own session (atomic jsonb ``-`` subtraction).

    Built for the verify-bounce feedback-pop at runner start (D9, 2026-08-28):
    that pop MUST NOT go through ORM assignment — dirtying the Session-2 node
    makes the next autoflush lock the row for the rest of the run, and the
    runner's own display writers then deadlock against their own session."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(spec=WorkflowStep.spec.op("-")(key))
        )
        await s.commit()


async def _set_summary(node_id: UUID, summary: str) -> None:
    """Write the quantified one-liner (spec.summary) — same independent-session
    jsonb_set discipline as ``_set_stage`` (never Python read-modify-write)."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec, pg_array(["summary"]), func.to_jsonb(summary), True
                )
            )
        )
        await s.commit()


async def _fill_summary(
    node_id: UUID, kind: str, *, tag: str | None = None, ui_language: str = "en", **params: object
) -> None:
    """Fill spec.summary from the registry's summary_templates for ``kind``.

    Templates fill numbers, never LLM-polished prose (CHAT_ARCH §8). ``tag``
    appends the slot's distinguishing label (language/focus) so same-kind
    sibling steps stay distinguishable after completion. ``kind`` IS the
    tool name (N-35) — the registry key directly. ``ui_language`` is the
    run's pinned UI locale (NOT the material's); unknown locales fall back
    to the English template.

    Plural helper: every int param ``n`` auto-injects ``{n}_s`` ("" when the
    value is 1, else "s") so English templates inflect — ``clip{n_s}`` reads
    "1 clip" / "3 clips". zh templates leave the keys unused (no inflection)."""
    from app.tools import TOOL_REGISTRY  # deferred: import cycle

    entry = TOOL_REGISTRY.get(kind)
    templates = entry.summary_templates if entry is not None else {}
    template = templates.get(ui_language) or templates.get("en")
    if not template:
        return
    for name, value in list(params.items()):
        if isinstance(value, int) and not isinstance(value, bool):
            params[f"{name}_s"] = "" if value == 1 else "s"
    try:
        line = template.format(**params)
    except KeyError:
        logger.warning("summary_template_params_missing", kind=kind, params=list(params))
        return
    if tag:
        line = f"{line} · {tag}"
    await _set_summary(node_id, line)


def ui_lang_of(run: Any, project: Any) -> str:
    """The display locale for a run's step lines: the run's pinned UI
    locale, falling back to the project language (display_language chain —
    never the material's language alone)."""
    from app.ui_locale import display_language

    return display_language(
        run.context if isinstance(run.context, dict) else None,
        getattr(project, "language", None),
    )


def slot_tag(slot: IntentSlot | None) -> str | None:
    """A slot's distinguishing tag (language/focus) for step summaries.

    Shared by the orchestrator (creation-time preset label) and the runners
    (done-time quantified line) so a sibling step reads the same tag in both
    states. ``None`` when the slot carries nothing distinguishing."""
    if slot is None:
        return None
    parts = []
    if slot.language:
        parts.append(slot.language.upper())
    if slot.focus:
        parts.append(slot.focus[:40])
    return " · ".join(parts) if parts else None


def _node_slot(node: WorkflowStep, ctx: dict, slot_type: str) -> IntentSlot | None:
    """The executor node's own task slot.

    Compiled nodes carry it in spec (``spec.slot`` — the chain's compile-time
    projection); the context fallback is read tolerance for pre-ADR-043 runs
    (their slots lived on run.context.outputs), then None = all task-book
    defaults."""
    raw = (node.spec or {}).get("slot")
    if isinstance(raw, dict):
        return IntentSlot.model_validate(raw)
    for item in ctx.get("outputs") or []:
        slot = IntentSlot.model_validate(item)
        if slot.type == slot_type:
            return slot
    return None

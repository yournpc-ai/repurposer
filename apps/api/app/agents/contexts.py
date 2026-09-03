"""Harness-side context assembly (ADR-039 P3, AGENT_ARCH §5.3).

One home for the deterministic prompt-context assembly every agent call
stands on — the services orchestrate, they never assemble:

- ``_generation_context`` — the GenerationContext every generation node
  builds from the run's task book (moved from ``pipeline/step_context.py``,
  which keeps the mechanical media/digest helpers).
- ``_build_context`` — the chat loop's intent context: project summary
  (assets / visible outputs / latest run + the per-step status section),
  the recent rounds, the pending-question line, and the mention injection
  (moved from ``chat/service.py``).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    ChatMention,
    GenerationContext,
    ToneSettings,
)
from app.models.tables import (
    Asset,
    Message,
    Persona,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.outputs import list_visible_outputs
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


def _generation_context(
    run: WorkflowRun,
    project: Project,
    persona: Persona | None,
    *,
    brand_music_id: str | None = None,
) -> GenerationContext:
    """Assemble the GenerationContext from the run's task book (context)."""
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


def _output_one_liner(output: Any) -> str:
    """A one-line label for a visible output (type + first creative line)."""
    payload = output.payload or {}
    for key in ("hook", "title", "body"):
        text = payload.get(key)
        if text:
            return str(text).split("\n", 1)[0][:80]
    return ""


_RUN_STEP_PROGRESS_LIMIT = 12


def _format_step_progress(steps: list[WorkflowStep]) -> list[str]:
    """One quantified line per step of a run (G-2): ``kind: status —
    summary``. A waiting interrupt's line reads as "waiting for you" on its
    own; a slot label preset at materialization ("Post · DE") rides the
    summary the same way. Capped — when a run outgrows the budget the tail
    (current + upcoming work) is what a progress question is about."""
    rows = []
    for step in steps:
        row = f"- {step.kind}: {step.status}"
        summary = (step.spec or {}).get("summary")
        if summary:
            row += f" — {summary}"
        rows.append(row)
    if len(rows) > _RUN_STEP_PROGRESS_LIMIT:
        omitted = len(rows) - _RUN_STEP_PROGRESS_LIMIT
        rows = [f"- … ({omitted} earlier steps omitted)"] + rows[
            -_RUN_STEP_PROGRESS_LIMIT:
        ]
    return rows


async def _build_context(
    db: AsyncSession,
    project: Project,
    recent: list[Message],
    mentions: list[ChatMention],
    pending: Message | None,
    focus_output_id: UUID | None = None,
) -> dict[str, Any]:
    """Assemble the intent context deterministically (CHAT_ARCH §6, v1 scope):
    project summary (assets / visible outputs / latest run) + the last 3
    rounds + the mention list. Not a chat-history dump. ``pending`` (the
    conversation's still-open question, if any) is queried by the caller —
    this module assembles, it never queries the chat store's question
    lifecycle. ``focus_output_id`` is the canvas's pointed-at product
    (ADR-041 D8 焦点注入) — one context line, never a conversation scope."""
    lines = [
        f"Project: {project.title} (id={project.id}, language={project.language})",
    ]

    assets = list(
        (
            await db.execute(
                select(Asset)
                .where(Asset.project_id == project.id)
                .order_by(Asset.created_at)  # stable list order across turns
            )
        )
        .scalars()
        .all()
    )
    if assets:
        lines.append("Assets:")
        for a in assets:
            # The ASR-detected language rides the line — transform language
            # decisions (translate/dub target ≠ source language) stand on it.
            lang = (a.meta or {}).get("language")
            lines.append(
                f"- {a.type} id={a.id} status={a.processing_status}"
                + (f" language={lang}" if lang else "")
            )

    outputs = await list_visible_outputs(db, project.id)
    if outputs:
        lines.append("Current outputs:")
        for o in outputs:
            one_liner = _output_one_liner(o)
            lines.append(f"- {o.type} id={o.id}" + (f": {one_liner}" if one_liner else ""))

    latest_run = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is not None:
        lines.append(f"Latest run: status={latest_run.status} id={latest_run.id}")
        steps = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == latest_run.id)
                    .order_by(WorkflowStep.seq)
                )
            )
            .scalars()
            .all()
        )
        progress = _format_step_progress(steps)
        if progress:
            # Node-level progress (G-2): "how far along / how much longer"
            # gets answered from real step states, not guessed.
            lines.append("Latest run steps:")
            lines.extend(progress)

    if focus_output_id is not None:
        # 焦点注入 (ADR-041 D8): the canvas's pointed-at product joins as ONE
        # line — the default target for instructions naming no other output.
        # A stale id (the output left the visible set) drops silently.
        focused = next(
            (o for o in outputs if str(o.id) == str(focus_output_id)), None
        )
        if focused is not None:
            one_liner = _output_one_liner(focused)
            lines.append(
                f"Current focus output: {focused.type} id={focused.id}"
                + (f": {one_liner}" if one_liner else "")
            )

    if recent:
        lines.append("Recent rounds:")
        for m in recent:
            attached = [
                a.get("name") for a in (m.attachments or []) if a.get("name")
            ]
            if not m.content and not attached:
                continue
            line = f"- {m.role}: {m.content[:200]}"
            if attached:
                # An attachment-only user turn (files staged in the input
                # group, sent with no text) must still be visible to the
                # agent — the files themselves appear in the Assets block.
                line += f" [attached: {', '.join(attached)}]"
            qreasons = (m.question or {}).get("reasons") or []
            if qreasons:
                # Task-book needs-check keys are data for the agent (its
                # vocabulary) — they live on the payload, never in prose.
                line += f" (needs check: {', '.join(qreasons)})"
            if m.question and m.answer:
                # Answered questions collapse into the flow — the answer is
                # the user's decision and must be visible to the agent (a
                # bare "a" only makes sense next to the question it picked).
                answer = m.answer or {}
                reply = (
                    answer.get("text")
                    or answer.get("option_id")
                    or answer.get("kind")
                )
                line += f" (the user answered: {reply})"
            lines.append(line)

    if pending is not None:
        # A still-open question (e.g. pick-only, no freeform): the agent must
        # not re-ask it nor ignore it — the next message may be its answer.
        lines.append(
            f"Pending question awaiting the user's answer: {pending.content}"
        )
        options = (pending.question or {}).get("options") or []
        if options:
            lines.append(
                "Options: "
                + "; ".join(
                    f"{o.get('id')}) {o.get('label')}" for o in options
                )
            )

    if mentions:
        lines.append("Mentions (definite references):")
        for m in mentions:
            lines.append(f"- {m.type} id={m.id} label={m.label}")

    return {"text": "\n".join(lines)}

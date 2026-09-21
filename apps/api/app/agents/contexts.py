"""Harness-side context assembly (ADR-039 P3, AGENT_ARCH §5.3).

One home for the deterministic prompt-context assembly every agent call
stands on — the services orchestrate, they never assemble:

- ``generation_context`` — the GenerationContext every generation node
  builds from the run's plan (moved from ``pipeline/step_context.py``,
  which keeps the mechanical media/digest helpers).
- ``_build_context`` — the chat loop's intent context: project summary
  (assets / visible outputs / latest run), the recent rounds, the
  pending-question line, and the mention injection (moved from
  ``chat/service.py``).

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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    ChatMention,
    GenerationContext,
    ToneSettings,
)
from app.models.tables import (
    Asset,
    GraphEdge,
    GraphNode,
    Message,
    Persona,
    Project,
    WorkflowRun,
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


_GRAPH_CONTEXT_LIMIT = 16


async def _build_context(
    db: AsyncSession,
    project: Project,
    recent: list[Message],
    mentions: list[ChatMention],
    pending: Message | None,
) -> dict[str, Any]:
    """Assemble the intent context deterministically (CHAT_ARCH §6, v1 scope):
    project summary (assets / visible outputs / latest run) + the last 3
    rounds + the mention list. Not a chat-history dump. ``pending`` (the
    conversation's still-open question, if any) is queried by the caller —
    this module assembles, it never queries the chat store's question
    lifecycle. Pointing at a product is an @mention (ADR-058 — the canvas
    focus mechanism retired into the mentions registry); the mention block
    below carries the definite id."""
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
            one_liner = output_one_liner(o)
            lines.append(f"- {o.type} id={o.id}" + (f": {one_liner}" if one_liner else ""))

    # The persistent graph (ADR-057 — the wiring revision's target table):
    # the agent points at a node by its row id; the node's own program line
    # (prompt / params) and state ride so the agent can compose the NEW
    # program from the CURRENT one (never invent it). Capped — a grown
    # graph's older islands stop mattering to a revision ask.
    graph_nodes = list(
        (
            await db.execute(
                select(GraphNode)
                .where(GraphNode.project_id == project.id)
                .order_by(GraphNode.created_at)
            )
        )
        .scalars()
        .all()
    )
    if graph_nodes:
        graph_edges = list(
            (
                await db.execute(
                    select(GraphEdge).where(GraphEdge.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        children: dict[str, list[str]] = {}
        for e in graph_edges:
            children.setdefault(str(e.from_node), []).append(str(e.to_node))
        lines.append("Graph (the persistent canvas — wiring ops edit THIS):")
        for n in graph_nodes[:_GRAPH_CONTEXT_LIMIT]:
            spec = n.spec or {}
            label = spec.get("summary") or n.type
            row = f"- {n.type} id={n.id} state={n.state} — {label}"
            prompt = spec.get("prompt")
            if prompt:
                row += f" | program: {str(prompt)[:140]}"
            output_ids = spec.get("output_ids") or []
            if output_ids:
                row += f" | products: {len(output_ids)}"
            downstream = children.get(str(n.id)) or []
            if downstream:
                row += f" | downstream: {', '.join(downstream)}"
            lines.append(row)
        if len(graph_nodes) > _GRAPH_CONTEXT_LIMIT:
            lines.append(f"- … ({len(graph_nodes) - _GRAPH_CONTEXT_LIMIT} older nodes omitted)")

    latest_run = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is not None:
        # One-line marker only (the digest doctrine, module header): the
        # per-step progress detail retired behind the get_run_status read
        # tool — the agent knows a run exists and reads the detail on demand.
        lines.append(f"Latest run: status={latest_run.status} id={latest_run.id}")

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
                # Plan needs-check keys are data for the agent (its
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
        # The BARE question is the precise referent here (ask 三分解剖 ②);
        # the framing prose that content may carry is noise for this block.
        bare = (pending.question or {}).get("question") or pending.content
        lines.append(
            f"Pending question awaiting the user's answer: {bare}"
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
            line = f"- {m.type} id={m.id} label={m.label}"
            if m.quote:
                # 段落级指认 (2026-09-11 — 选区引用): the pinned passage rides
                # the mention line verbatim (capped — the card selection is
                # user truth, the context budget is not).
                line += f' — the user pinned this exact passage: "{m.quote[:500]}"'
            lines.append(line)

    return {"text": "\n".join(lines)}

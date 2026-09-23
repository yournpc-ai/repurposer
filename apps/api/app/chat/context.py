"""Chat intent-context assembly (CHAT_ARCH §6; ADR-087 §6 Phase 5 ownership).

The chat loop's deterministic intent context: project summary (assets /
visible outputs / latest run), the recent rounds, the pending-question
line, and the mention injection. This is the Agent Interface's OWN assembly
— moved from ``app.agents.contexts`` (the harness layer), whose home is the
GenerationContext: each layer assembles its own context, and the harness no
longer reads the conversation store (``Message``) or the outputs read face
on chat's behalf. Digest doctrine unchanged (ADR-077 判词② — identity
level only; anything a read tool reads is never pre-injected).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contexts import output_one_liner
from app.models.schemas import ChatMention
from app.models.tables import (
    Asset,
    GraphEdge,
    GraphNode,
    Message,
    Project,
    WorkflowRun,
)
from app.pipeline.exploration_store import (
    journey_summary_line,
    read_journey_summaries,
)
from app.pipeline.outputs import list_visible_outputs

_GRAPH_CONTEXT_LIMIT = 16
_PAST_JOURNEYS_CAP = 3


async def build_context(
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
            # iter-3 S2: exploration rows carry no `summary` — their
            # identity lives in title (content_plan) / topic (candidate_set)
            # / exploration_kind; execution rows keep the summary law
            # untouched.
            if n.type == "exploration":
                label = (
                    spec.get("title")
                    or spec.get("topic")
                    or spec.get("exploration_kind")
                    or n.type
                )
            else:
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

    # iter-3 S6 (E5, Memory 窄切 ②): the project's recent journeys ride as
    # ONE bounded identity-level block (goal + counts + the newest plan's
    # output facts) — the agent can answer "what have we done before" and
    # ground a "same as last time" reference WITHOUT a read tool; the full
    # artifact fields stay behind get_artifact (digest doctrine — anything
    # a read tool reads is never pre-injected in full).
    past_journeys = await read_journey_summaries(db, project.id, cap=_PAST_JOURNEYS_CAP)
    if past_journeys:
        lines.append("Past journeys (newest first):")
        for summary in past_journeys:
            lines.append(f"- {journey_summary_line(summary)}")

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

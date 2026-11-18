"""Chat intent-context assembly (CHAT_ARCH §6; ADR-087 §6 Phase 5 ownership).

The chat loop's deterministic intent context: project summary (assets /
visible outputs / latest run), the recent rounds, the pending-question
line, and the mention injection. This is the Agent Interface's OWN assembly
— moved from ``app.agents.contexts`` (the harness layer), whose home is the
GenerationContext: each layer assembles its own context, and the harness no
longer reads the conversation store (``Message``) or the outputs read face
on chat's behalf. Shared resource content is assembled separately by
``tools.project_context`` for every model request; this module owns the
conversation, workflow and pending-question framing.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contexts import output_one_liner
from app.chat.canvas_visibility import environment_line
from app.models.schemas import ChatMention
from app.models.tables import (
    GraphEdge,
    GraphNode,
    Message,
    Project,
    WorkflowRun,
)
from app.pipeline.outputs import list_visible_outputs
from app.platform.conversation_context import is_pending_plan


def conversation_messages(rows: list[Message]) -> list[dict]:
    """Project the durable chat into native roles, including dock submissions."""
    linked = {
        str((row.intent or {}).get("answered_question_id"))
        for row in rows if row.role == "user"
    }
    dialogue = []
    pending_answers = []

    def emit_due(before):
        while pending_answers and (before is None or pending_answers[0][0] <= before):
            _, reply = pending_answers.pop(0)
            dialogue.append({"role": "user", "content": reply})

    for row in rows:
        if row.created_at:
            emit_due(row.created_at)
        if row.role not in {"assistant", "user"}:
            continue
        question = row.question or {}
        lines = [row.content] if row.content else []
        attached = [a["name"] for a in row.attachments or [] if a.get("name")]
        if attached:
            lines.append("[attached: " + ", ".join(attached) + "]")
        title = question.get("question")
        if title and title != row.content:
            lines.append(title)
        items = question.get("items") or []
        for item in items or [question]:
            if items and item.get("question"):
                lines.append(item["question"])
            for option in item.get("options") or []:
                label = option.get("label")
                if label:
                    lines.append(label + (" — " + option["description"] if option.get("description") else ""))
        if lines:
            dialogue.append({"role": row.role, "content": "\n".join(lines)})

        answer = row.answer or {}
        if not answer or str(row.id) in linked or answer.get("text") == "superseded":
            continue
        fields = {item.get("slot"): item for item in items}
        replies = []
        for pick in answer.get("answers") or []:
            item = fields.get(pick.get("slot"), {})
            value = pick.get("text") or next(
                (opt["label"] for opt in item.get("options", []) if opt["id"] == pick.get("option_id")),
                pick.get("option_id", ""),
            )
            replies.append(f"{item.get('question') or pick['slot']} {value}")
        reply = "\n".join(replies) or answer.get("text") or answer.get("option_id") or answer["kind"]
        if answer.get("answered_at"):
            pending_answers.append((datetime.fromisoformat(answer["answered_at"]), reply))
            pending_answers.sort(key=lambda entry: entry[0])
        else:
            dialogue.append({"role": "user", "content": reply})
    emit_due(None)
    return dialogue


_GRAPH_CONTEXT_LIMIT = 16
_PAST_JOURNEYS_CAP = 3


def _estimate_text_tokens(text: str) -> int:
    """Estimated prompt cost of one text blob: ~4 chars/token for latin
    scripts, ~1 token per CJK / kana / hangul / fullwidth char. The
    chars/4-only estimator reads a zh history ~4× cheaper than reality,
    so the budget's fold would fire far too late for the product's main
    language family — the wide-char count keeps the guardrail honest on
    both scripts (overestimating folds earlier, the safe side)."""
    wide = sum(
        1
        for ch in text
        if 0x2E80 <= ord(ch) <= 0x9FFF
        or 0xAC00 <= ord(ch) <= 0xD7AF
        or 0xFF00 <= ord(ch) <= 0xFFEF
    )
    return wide + (len(text) - wide) // 4


async def build_context(
    db: AsyncSession,
    project: Project,
    mentions: list[ChatMention],
    pending: Message | None,
    canvas_available: bool | None = None,
    confirmation: tuple[str, str] | None = None,
    skill=None,
    skill_ambiguity: list[str] | None = None,
    include_pending: bool = True,
) -> dict[str, Any]:
    """Assemble the intent context deterministically (CHAT_ARCH §6, v1 scope):
    project summary (assets / visible outputs / latest run) + the last 3
    rounds + the mention list. Not a chat-history dump. ``pending`` (the
    conversation's still-open question, if any) is queried by the caller —
    this module assembles, it never queries the chat store's question
    lifecycle. Pointing at a product is an @mention (ADR-058 — the canvas
    focus mechanism retired into the mentions registry); the mention block
    below carries the definite id.

    ``canvas_available``: the conversation-stamped client capability bit
    (ADR-118 §6 双键). The Environment line rides when the bit is known —
    canvas_visible = canvas_available ∧ world_live (world_live = hasRuns ∨
    pending-plan — 与客户端谓词同义单源, 互指 app/chat/canvas_visibility.py);
    unknown → the line is omitted. This is environment evidence only; no
    delivery-speech interface guidance is derived from it.

    ``confirmation`` (ADR-117 D1) = the user's two confirmation prefs
    (execution, credits) — rendered as one fact line the system template's
    mode-conditional close law reads."""
    lines = [
        f"Project: {project.title} (id={project.id}, default_language={project.language}; not the delivered content language)",
    ]
    from app.chat.video_turn_seats import video_context_lines
    lines.extend(await video_context_lines(
        db, project, mentions, skill=skill, skill_ambiguity=skill_ambiguity,
    ))
    if confirmation is not None:
        # The FACT seat — the mode-conditional LAW stays in the static
        # system template (一法一座; the static prompt's prefix cache
        # survives per-user settings).
        lines.append(
            "Confirmation settings: execution="
            f"{confirmation[0]}, spending={confirmation[1]}."
        )

    # Mutable resource content/status is refreshed for every model request
    # by tools.project_context; don't freeze a duplicate asset roster here.
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
    # graph's older islands stop mattering to a revision ask. Workspace 合同
    # v4.2 C1: legacy type="exploration" graph rows are read-filtered here
    # too (the family's home is exploration_rows now — the journey digest
    # block below is its context seat).
    graph_nodes = list(
        (
            await db.execute(
                select(GraphNode)
                .where(
                    GraphNode.project_id == project.id,
                )
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

    # 环境双键 (ADR-118 §6): the structured Environment fact rides directly
    # under the Project line — canvas_visible = canvas_available ∧ world_live
    # (world_live = hasRuns ∨ pending-plan — 与客户端谓词同义单源, 互指
    # app/chat/canvas_visibility.py); 能力位未知 → 行缺席 (未知恒闭).
    env = environment_line(
        canvas_available,
        world_live=latest_run is not None or is_pending_plan(pending),
    )
    if env:
        lines.insert(1, env)

    if pending is not None and include_pending:
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
            if m.region:
                region = m.region
                rect = region.sourceRect
                source = region.sourceSize
                normalized = region.normalizedRect
                line += (
                    " — the user pinned this exact video frame region: "
                    f"media_time_ms={region.mediaTimeMs}; "
                    f"source_px={source.width}x{source.height}; "
                    f"source_rect_px=x:{rect.x},y:{rect.y},width:{rect.width},height:{rect.height}; "
                    f"normalized_rect=x:{normalized.x:.6f},y:{normalized.y:.6f},"
                    f"width:{normalized.width:.6f},height:{normalized.height:.6f}"
                )
            lines.append(line)

    return {"text": "\n".join(lines)}

"""Chat intent-context assembly (CHAT_ARCH §6; ADR-087 §6 Phase 5 ownership).

The chat loop's deterministic intent context: project summary (assets /
visible outputs), the recent rounds, the pending-question
line, and the mention injection. This is the Agent Interface's OWN assembly
— moved from ``app.agents.contexts`` (the harness layer), whose home is the
GenerationContext: each layer assembles its own context, and the harness no
longer reads the conversation store (``Message``) or the outputs read face
on chat's behalf. Shared resource content is assembled separately by
``tools.project_context`` for every model request; this module owns the
conversation and pending-question framing.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contexts import output_one_liner
from app.models.schemas import ChatMention
from app.models.tables import (
    Message,
    Project,
)
from app.pipeline.outputs import list_visible_outputs


def conversation_messages(
    rows: list[Message],
    *,
    compact_summary: dict[str, Any] | None = None,
) -> list[dict]:
    """Project the durable chat into native roles, including dock submissions.

    When ``compact_summary`` carries ``compacted_through_seq``, messages at or
    before that sequence number are skipped (the summary rides in the round
    context block) while newer messages stay verbatim.
    """
    compacted_through_seq = 0
    if isinstance(compact_summary, dict) and compact_summary.get("summary"):
        try:
            compacted_through_seq = int(compact_summary.get("compacted_through_seq") or 0)
        except (TypeError, ValueError):
            compacted_through_seq = 0
    if compacted_through_seq > 0:
        rows = [row for row in rows if (row.seq or 0) > compacted_through_seq]
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
    confirmation: tuple[str, str] | None = None,
    skill=None,
    include_pending: bool = True,
) -> dict[str, Any]:
    """Assemble the intent context deterministically (CHAT_ARCH §6, v1 scope):
    project summary (assets / visible outputs) + the last 3
    rounds + the mention list. Not a chat-history dump. ``pending`` (the
    conversation's still-open question, if any) is queried by the caller —
    this module assembles, it never queries the chat store's question
    lifecycle. Pointing at a product is an @mention (ADR-058 — the canvas
    focus mechanism retired into the mentions registry); the mention block
    below carries the definite id.

    ``confirmation`` (ADR-117 D1) = the user's two confirmation prefs
    (execution, credits) — rendered as one fact line the system template's
    mode-conditional close law reads."""
    lines = [
        f"Project: {project.title} (id={project.id}, default_language={project.language}; not the delivered content language)",
    ]
    from app.chat.video_turn_seats import video_context_lines
    lines.extend(await video_context_lines(
        db, project, mentions, skill=skill,
    ))
    if confirmation is not None:
        # The FACT seat — the mode-conditional LAW stays in the static
        # system template (一法一座; the static prompt's prefix cache
        # survives per-user settings).
        lines.append(
            "确认设置：execution="
            f"{confirmation[0]}, spending={confirmation[1]}."
        )

    # Mutable resource content/status is refreshed for every model request
    # by tools.project_context; don't freeze a duplicate asset roster here.
    outputs = await list_visible_outputs(db, project.id)
    if outputs:
        lines.append("当前输出：")
        for o in outputs:
            one_liner = output_one_liner(o)
            lines.append(f"- {o.type} id={o.id}" + (f": {one_liner}" if one_liner else ""))

    if pending is not None and include_pending:
        # A still-open question (e.g. pick-only, no freeform): the agent must
        # not re-ask it nor ignore it — the next message may be its answer.
        # The BARE question is the precise referent here (ask 三分解剖 ②);
        # the framing prose that content may carry is noise for this block.
        bare = (pending.question or {}).get("question") or pending.content
        lines.append(
            f"待用户回答的问题：{bare}"
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
        lines.append("用户明确引用的对象：")
        for m in mentions:
            line = f"- {m.type} id={m.id} label={m.label}"
            if m.quote:
                # 段落级指认 (2026-09-11 — 选区引用): the pinned passage rides
                # the mention line verbatim (capped — the card selection is
                # user truth, the context budget is not).
                line += f' — 用户指定了这段原文："{m.quote[:500]}"'
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

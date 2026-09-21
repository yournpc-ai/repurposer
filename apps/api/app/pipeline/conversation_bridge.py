"""Conversation command bridge (ADR-087 §6 explicit protocol; MODULE_ARCH §4).

``conversations`` / ``messages`` are owned by the Agent Interface — pipeline
is read-only on them (§4). The conversation WRITE commands the pipeline's
runtime/transport legitimately needs (the interrupt machine's dock +
post-commit settle, the /generate path's prompt bookkeeping) therefore stay
implemented in ``app.chat.service`` and are reached ONLY through this
registered bridge: the composition root (``app.main`` / ``app.worker``)
wires the implementations at boot via ``app.chat.seams.wire_pipeline_seams``.

Unregistered = fail loudly: a silent no-op would strand the interrupt
machine (a parked run with no question row) or drop the /generate path's
bookkeeping. The trigger seam's fire-and-forget degrade doctrine does NOT
apply to synchronous writes.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import QuestionPayload
from app.models.tables import Message


@dataclass(frozen=True)
class ConversationBridge:
    """The Agent Interface's conversation write commands, registered once
    per process. Signatures mirror ``app.chat.service``'s publics exactly —
    call sites are drop-in."""

    dock_interrupt_question: Callable[
        [AsyncSession, UUID, UUID, UUID, str, QuestionPayload],
        Awaitable[tuple[Message, list[UUID]]],
    ]
    finalize_bailed_runs: Callable[[list[UUID]], Awaitable[None]]
    seed_project_prompt: Callable[
        [AsyncSession, UUID, UUID, str], Awaitable[Message | None]
    ]
    discard_unanswered_plan: Callable[[AsyncSession, UUID, UUID], Awaitable[None]]


_bridge: ConversationBridge | None = None


def register_conversation_bridge(bridge: ConversationBridge) -> None:
    """Wire the Agent Interface's conversation commands. Called once per
    process by the composition root; a later call replaces (probe/test
    seams)."""
    global _bridge
    _bridge = bridge


def _require() -> ConversationBridge:
    if _bridge is None:
        raise RuntimeError(
            "conversation bridge unregistered — the composition root "
            "(app.main / app.worker) wires app.chat.service's "
            "implementations via app.chat.seams.wire_pipeline_seams"
        )
    return _bridge


async def dock_interrupt_question(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    run_id: UUID,
    content: str,
    payload: QuestionPayload,
) -> tuple[Message, list[UUID]]:
    """Bridge delegate — the implementation lives in ``app.chat.service``."""
    return await _require().dock_interrupt_question(
        db, user_id, project_id, run_id, content, payload
    )


async def finalize_bailed_runs(run_ids: list[UUID]) -> None:
    """Bridge delegate — the implementation lives in ``app.chat.service``."""
    await _require().finalize_bailed_runs(run_ids)


async def seed_project_prompt(
    db: AsyncSession, user_id: UUID, project_id: UUID, prompt: str
) -> Message | None:
    """Bridge delegate — the implementation lives in ``app.chat.service``."""
    return await _require().seed_project_prompt(db, user_id, project_id, prompt)


async def discard_unanswered_plan(
    db: AsyncSession, user_id: UUID, project_id: UUID
) -> None:
    """Bridge delegate — the implementation lives in ``app.chat.service``."""
    await _require().discard_unanswered_plan(db, user_id, project_id)

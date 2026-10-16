"""Film dock 审查门 (ADR-120; hold/draft 解耦 2026-10-15 拍板; 统一迟延 +
硬闸 2026-10-16 拍板).

The dock-time half is ONE stamp: a docked chain holding launch_film ALWAYS
owes the storyboard review hold — on every confirmation regime, never keyed
on a draft's success, and the draft NEVER runs inside the turn (the LLM
draft is minutes; a turn never blocks on it — the block lands late through
the worker-side deferred seat and the flow carries a drafting placeholder
meanwhile).

The deferred seat (``maybe_dock_deferred_storyboard``) owns every draft:
fired from a web_page capture's terminal state (first-URL docks) and from
the chat turn's post-commit point (revision docks whose pages are already
captured). It drafts with a bounded retry, lands the block in the message
flow on success, and on terminal failure lands ONE honest row (the hold
stands — the plan never starts unreviewed).

The start side (法1后半 + 法3, 2026-10-16): a film chain's start is gated
on a storyboard block newer than the dock (``film_start_block``) — the ONLY
waiver is the user's explicit "skip the storyboard" (the start_run call's
``skip_storyboard_review``), never a plain "go" and never the system
deciding for them.
"""

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.service import _create_message, _prefers_zh, record_storyboard_block
from app.models.schemas import (
    STORYBOARD_BLOCK_TYPE,
    AssetStatus,
    AssetType,
    FilmStoryboard,
)
from app.models.tables import Asset, Message, Project
from app.pipeline.trigger_events import TRIGGER_STORYBOARD_READY, fire_trigger
from app.platform.conversation_context import (
    find_conversation,
    is_pending_plan,
    latest_pending_question,
)

logger = structlog.get_logger(__name__)

# One project drafts once at a time (the chat-turn fire and the capture
# fire can overlap); pg_try_advisory_xact_lock is the cross-process
# single-flight (the API and the worker are different processes, the DB is
# the shared seat). Loser no-ops: both fires observe the same world.
_DRAFT_LOCK_KEY = "film_storyboard_draft"

# 打回有界的唯一座位在候选层 (orchestrate_storyboard 的 1+MAX_REWRITES)——
# 外层整稿重试与内层叠加成乘法失控 (2×3=6 次重多模态调用，2026-10-15
# zymix 取证: 37 分钟全灭)，dock 层只跑一次，穷尽即落诚实行。
_DRAFT_ATTEMPTS = 1

STORYBOARD_DRAFT_FAILED_TYPE = "storyboard_draft_failed"


def stamp_film_hold(tasks: list, need):
    """The dock-time half, hold-only: a chain holding launch_film ALWAYS
    docks with the storyboard_review hold ( stamped into the docked
    question's payload by the caller's sync).

    The review hold NAMES ITSELF even when a billing clause (guardrail /
    prefs / unquotable) also fired: the dock's reason is one string, and for
    a film dock the storyboard review is the primary fact the user must act
    on — the billing facts still ride ``quote_high`` / ``unquotable`` and
    the estimate tail's hold/settle semantics unchanged. (The model never
    announces a work-start on a film dock, so the guardrail clause's
    correction wording has nothing to correct.)
    """
    from app.pipeline.lifecycle import ConfirmationNeed  # deferred: pipeline edge

    if not any(t.tool == "launch_film" for t in tasks):
        return need
    return ConfirmationNeed(True, "storyboard_review", need.quote_high, need.unquotable)


async def land_storyboard_block(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    storyboard: FilmStoryboard,
    hosts: list[str],
    film_params: dict,
    instruction: str | None,
    on_storyboard=None,
) -> Message:
    """The block lands in the MESSAGE FLOW right under its dock (never the
    confirm dock) — the deferred seat has no SSE turn, so the row is the
    truth and the client's watch-window poll is the live arrival channel.
    The language chip reads the plan's pin first, then the draft's own
    declaration (世界自证 — the reviewed language is the one the run
    speaks)."""
    block_message = await record_storyboard_block(
        db,
        conversation_id,
        storyboard=storyboard,
        pages=hosts,
        instruction=instruction,
        voiceover=film_params.get("voiceover") is not False,
        music_mood=film_params.get("music_mood"),
        aspect=film_params.get("aspect") or "16:9",
        language=film_params.get("language") or storyboard.language,
    )
    if on_storyboard is not None and isinstance(block_message.intent, dict):
        await on_storyboard({**block_message.intent, "message_id": str(block_message.id)})
    return block_message


async def _block_newer_than_dock(
    db: AsyncSession, conversation_id: UUID, dock_created_at
) -> Message | None:
    """The storyboard block row validating THIS dock (None = the review is
    still owed). The dock's question row re-births on every re-dock
    (sync_plan_question supersedes in place), so 'newer than the dock' is
    the exact owing predicate — an older dock's block never validates a
    revised plan."""
    return (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.created_at >= dock_created_at,
                Message.intent["type"].astext == STORYBOARD_BLOCK_TYPE,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def film_start_block(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    tasks: list[dict],
    dock_created_at,
) -> Message | None:
    """法1后半硬闸's world read: the block that licenses a film chain's
    start. ``tasks`` is the docked chain as dicts (the pending question's
    intent). Returns None when the chain holds no launch_film (the gate is
    inert) — callers combine with the waiver:
    ``block is None and has_film and not waiver → start held``."""
    if not any(t.get("tool") == "launch_film" for t in tasks):
        return None
    return await _block_newer_than_dock(db, conversation_id, dock_created_at)


_warm_tasks: set[asyncio.Task] = set()


def fire_deferred_storyboard_check(project_id: UUID) -> None:
    """Fire-and-forget the deferred seat from the CHAT side (the turn's
    post-commit point — a revision dock's pages are already captured, so no
    capture event will ever fire for it). Every gate inside is a world
    read: a stale fire is a silent no-op."""

    async def _run() -> None:
        try:
            await maybe_dock_deferred_storyboard(project_id)
        except Exception as e:  # noqa: BLE001 — best-effort, never a turn failure
            logger.warning(
                "deferred_storyboard_check_failed",
                project_id=str(project_id),
                error=str(e),
            )

    task = asyncio.create_task(_run())
    _warm_tasks.add(task)
    task.add_done_callback(_warm_tasks.discard)


async def maybe_dock_deferred_storyboard(project_id: UUID) -> None:
    """The deferred seat: draft and land the storyboard block for a pending
    film dock, once the capture set has drained (no PENDING/PROCESSING
    pages left, sub-page discovery included).

    Every gate is a world read, so a stale fire is a silent no-op: no
    pending film plan / the dock already settled (answered = the user beat
    the block to it — but with the hard gate that only happens via an
    explicit waiver) / a block already landed for THIS dock / captures
    still in flight. The bounded retry lives in the candidate loop
    (``orchestrate_storyboard``); terminal failure lands ONE honest row
    (法2 — the hold stands, the plan never starts unreviewed, the user may
    rephrase or explicitly waive). Own session + own commit (the worker's
    fire-and-forget law).
    """
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    async with AsyncSessionLocal() as db:
        locked = (
            await db.execute(
                text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"),
                {"k": f"{_DRAFT_LOCK_KEY}:{project_id}"},
            )
        ).scalar_one()
        if not locked:
            return
        project = await db.get(Project, project_id)
        if project is None:
            return
        pending = project.pending_brief if isinstance(project.pending_brief, dict) else None
        intent = (pending or {}).get("intent") or {}
        tasks = intent.get("tasks") or []
        film_task = next((t for t in tasks if t.get("tool") == "launch_film"), None)
        if film_task is None:
            return
        in_flight = (
            await db.execute(
                select(func.count(Asset.id)).where(
                    Asset.project_id == project_id,
                    Asset.type == AssetType.WEB_PAGE,
                    Asset.processing_status.in_(
                        (AssetStatus.PENDING, AssetStatus.PROCESSING)
                    ),
                )
            )
        ).scalar_one()
        if in_flight:
            return
        conversation = await find_conversation(db, project.user_id, project_id)
        if conversation is None:
            return
        conversation_id = UUID(str(conversation.id))
        question = await latest_pending_question(db, conversation_id)
        if not is_pending_plan(question):
            return
        assert question is not None  # is_pending_plan guarantees the row
        if await _block_newer_than_dock(db, conversation_id, question.created_at) is not None:
            return
        film_params = dict(film_task.get("params") or {})
        from app.tools.film.storyboard import draft_film_storyboard  # deferred: tool seam

        drafted = None
        for attempt in range(1, _DRAFT_ATTEMPTS + 1):
            drafted = await draft_film_storyboard(
                db,
                project,
                instruction=(pending or {}).get("prompt"),
                focus=film_params.get("focus"),
                language=film_params.get("language"),
            )
            if drafted is not None:
                break
            logger.info(
                "storyboard_draft_retry" if attempt < _DRAFT_ATTEMPTS else "storyboard_draft_exhausted",
                project_id=str(project_id),
                attempt=attempt,
            )
        if drafted is None:
            await _land_draft_failure_row(
                db,
                conversation_id=conversation_id,
                prompt=(pending or {}).get("prompt"),
            )
            await db.commit()
            return
        storyboard, draft_pages = drafted
        await land_storyboard_block(
            db,
            conversation_id=conversation_id,
            storyboard=storyboard,
            hosts=[p.host for p in draft_pages],
            film_params=film_params,
            instruction=(pending or {}).get("prompt"),
        )
        await db.commit()
        # 就绪拍 (ADR-120 补言语): the block landed truthfully on its own;
        # the trigger turn speaks one beat over it. ref = THIS dock's
        # question id — a re-docked plan re-births the row, licensing one
        # fresh speech per revision. Fire-and-forget: no subscriber = the
        # card still lands, silence never fails the seat.
        fire_trigger(
            project_id, TRIGGER_STORYBOARD_READY, str(question.id)
        )


async def _land_draft_failure_row(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    prompt: str | None,
) -> None:
    """法2 的穷举诚实行: every draft attempt failed its own validation —
    the hold stands (the plan never starts unreviewed), so the flow must
    SAY it. Code-composed (no LLM turn exists here — the honest-line
    doctrine), in the plan's own language, and it names the two lawful
    moves: rephrase, or explicitly waive the review (法3's escape). The
    intent marker lets the client fold the drafting placeholder."""
    if _prefers_zh(prompt or ""):
        content = (
            "分镜稿起了几版都没通过我校验，这版方案我暂不开工。你可以换个说法"
            "让我再试（比如调整时长或侧重点）；如果不需要看分镜，直接说"
            "「不用看分镜，直接做」也可以。"
        )
    else:
        content = (
            "I drafted the storyboard a few times and none passed my own "
            "checks, so I won't start this plan yet. Rephrase the ask "
            "(duration, angle) and I'll try again — or, if you don't need "
            "to review the storyboard, just say so and I'll start directly."
        )
    await _create_message(
        db,
        conversation_id,
        "assistant",
        content,
        intent={"type": STORYBOARD_DRAFT_FAILED_TYPE},
    )

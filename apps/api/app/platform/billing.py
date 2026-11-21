"""Wallet and ledger writers for native media generation, export and payments.

Job submission reserves the authorized amount. Its terminal transaction releases
that reservation and captures the actual charge under job-specific idempotency
keys. Unresolved external work retains its reservation for reconciliation.
"""

from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime
from uuid import UUID
from typing import Literal
import math

import structlog
from sqlalchemy import String, case, exists, func, literal, select, tuple_, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import CreditTransaction, Wallet
from app.platform.configs import get_config
from app.providers.llm import price_text_tokens
from app.providers.llm.minimax import price_tokens, price_units

logger = structlog.get_logger()


class CreditsInsufficientError(ValueError):
    """Insufficient user credits at reservation time, with the balance and required amount."""

    def __init__(self, *, balance: int, required: int) -> None:
        super().__init__(f"credits.insufficient: balance {balance}, required {required}")
        self.balance = balance
        self.required = required


# ---- USD ↔ credits (the single conversion seam) ----------------------------


def estimate_usd_range(fold: dict) -> tuple[float, float]:
    """Money value (USD) of a folded estimate (``fold_estimates`` output) —
    [low, high]. Token ranges price per side; mechanical units are exact and
    join both. Reads PRICING through the client's price fns (禁第二份价目)."""
    units = fold.get("units") or {}
    units_usd = price_units(units) if units else 0.0
    prompt_low, prompt_high = (int(v) for v in fold["prompt_tokens"])
    completion_low, completion_high = (int(v) for v in fold["completion_tokens"])
    return (
        price_text_tokens(prompt_low, completion_low) + units_usd,
        price_text_tokens(prompt_high, completion_high) + units_usd,
    )


def estimate_rate_credits(fold: dict, seconds: float, ratio: int) -> tuple[int, int]:
    """Per-second RATE form of a folded estimate (BILLING §7 估价贴的用量计价
    变体): the duration-scaled share ÷ the declared source seconds, ceiled so
    the rate never under-promises — with the one-shot units (voice clone,
    billed once per voice) split out. A fixed [low, high] total anchored on
    the typical source misleads both ways for per-character-priced work
    (TTS): the 15-second test reads 6000 and bails, the hour-long upload
    reads it and under-budgets. Returns ``(per_second_credits,
    one_shot_credits)``; ``(0, 0)`` = unquotable rate."""
    _usd_low, usd_high = estimate_usd_range(fold)
    if usd_high <= 0 or seconds <= 0:
        return 0, 0
    one_shot_usd = price_units(
        {"voice_clones": (fold.get("units") or {}).get("voice_clones", 0.0)}
    )
    rate = math.ceil((usd_high - one_shot_usd) / seconds * ratio)
    one_shot = math.ceil(one_shot_usd * ratio)
    return max(rate, 0), one_shot


def cost_usd(cost: dict | None) -> float:
    """Money value (USD) of a step's persisted cost ledger. Media units'
    money already lives in ``fixed_cost`` (record_media_usage) — pricing the
    units again would double-count."""
    if not cost:
        return 0.0
    if cost.get("token_cost_usd") is not None:
        token_cost = float(cost["token_cost_usd"])
    elif cost.get("provider") == "deepseek" or str(cost.get("model") or "").startswith("deepseek-"):
        token_cost = price_text_tokens(
            int(cost.get("prompt_tokens") or 0),
            int(cost.get("completion_tokens") or 0),
            provider=cost.get("provider"),
            model=cost.get("model"),
        )
    else:
        # Rows without provider identity are legacy MiniMax ledgers.
        token_cost = price_tokens(
            int(cost.get("prompt_tokens") or 0),
            int(cost.get("completion_tokens") or 0),
        )
    return token_cost + float(cost.get("fixed_cost") or 0.0)


async def credits_for_cost(db: AsyncSession, usd: float) -> int:
    """USD → credits at the single consumption ratio (``credits.per_cost_usd``).

    The ONLY conversion point — the estimate fold and captures read the same
    value here, so one config edit moves every price display and every charge
    together (调参不动历史账: written rows stay as they were).
    """
    if usd <= 0:
        return 0
    return credits_at_ratio(usd, await get_config(db, "credits.per_cost_usd"))


def credits_at_ratio(usd: float, ratio: int) -> int:
    """Pure USD → credits at a caller-fetched ratio — the serialization
    layer's form (one ``get_config`` read per response, then every step
    derives with zero further I/O). Same rounding as ``credits_for_cost`` —
    the two stay the single conversion point's two sleeves."""
    if usd <= 0:
        return 0
    return int(
        (Decimal(str(usd)) * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


# ---- wallet verbs ------------------------------------------------------------


async def get_or_create_wallet(db: AsyncSession, user_id: UUID) -> Wallet:
    """Return the user's wallet, lazy-opening it on first login.

    Opening grants the signup credits (``wallet.signup_grant`` config) as the
    wallet's first ledger row (``kind=grant, ref={"source": "signup"}``).
    Idempotent by construction: the wallet PK and the
    ``user:{id}:signup_grant`` idempotency key are the dedupe backstop — a
    concurrent double-open fails one side on the UNIQUE constraint instead of
    double-granting (get_or_create_user's posture).
    """
    wallet = await db.get(Wallet, user_id)
    if wallet is not None:
        return wallet
    grant = await get_config(db, "wallet.signup_grant")
    wallet = Wallet(user_id=user_id, balance=grant)
    db.add(wallet)
    db.add(
        CreditTransaction(
            user_id=user_id,
            kind="grant",
            amount=grant,
            balance_after=grant,
            ref={"source": "signup"},
            idempotency_key=f"user:{user_id}:signup_grant",
            note="Signup grant",
        )
    )
    await db.flush()
    logger.info("wallet_opened", user_id=str(user_id), grant=grant)
    return wallet


async def balance(db: AsyncSession, user_id: UUID) -> int:
    """Current credit balance (opens the wallet lazily if absent)."""
    wallet = await get_or_create_wallet(db, user_id)
    return int(wallet.balance)


async def _list_outgoing_events(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: tuple[datetime, UUID] | None,
) -> tuple[list[CreditTransaction], tuple[datetime, UUID] | None, int]:
    """Paginate SEMANTIC spend events, not their raw hold/capture/release rows.

    A Job with at least one capture is one event, ordered by its latest ledger
    row; a negative non-run entry is one event. The page selects ten event keys
    first, then fetches every raw row for those runs so each fold is complete.
    """
    job_id = func.coalesce(CreditTransaction.ref["export_id"].astext, CreditTransaction.ref["media_job_id"].astext)
    job_scoped = (
        CreditTransaction.kind.in_(["hold", "capture", "release"])
        & job_id.is_not(None)
        & (job_id != "")
    )
    capture_total = func.sum(
        case((CreditTransaction.kind == "capture", CreditTransaction.amount), else_=0)
    )
    job_events = (
        select(
            job_id.label("event_key"),
            func.max(CreditTransaction.created_at).label("created_at"),
            # UUID is only a deterministic tie-breaker, not a chronological
            # value; text gives the union one portable cursor column type.
            func.max(CreditTransaction.id.cast(String)).label("cursor_id"),
            literal(True).label("job_scoped"),
        )
        .where(CreditTransaction.user_id == user_id, job_scoped)
        .group_by(job_id)
        .having(capture_total != 0)
    )
    single_events = select(
        CreditTransaction.id.cast(String).label("event_key"),
        CreditTransaction.created_at.label("created_at"),
        CreditTransaction.id.cast(String).label("cursor_id"),
        literal(False).label("job_scoped"),
    ).where(
        CreditTransaction.user_id == user_id,
        ~job_scoped,
        CreditTransaction.amount < 0,
        CreditTransaction.kind.notin_(["purchase", "grant", "refund"]),
    )
    events = union_all(job_events, single_events).subquery()
    total = int(
        await db.scalar(select(func.count()).select_from(events)) or 0
    )

    stmt = select(events)
    if cursor is not None:
        stmt = stmt.where(
            tuple_(events.c.created_at, events.c.cursor_id)
            < (cursor[0], str(cursor[1]))
        )
    stmt = stmt.order_by(events.c.created_at.desc(), events.c.cursor_id.desc()).limit(
        limit + 1
    )
    event_rows = list((await db.execute(stmt)).all())
    has_more = len(event_rows) > limit
    page = event_rows[:limit]
    if not page:
        return [], None, total

    job_ids = [row.event_key for row in page if row.job_scoped]
    single_ids = [UUID(row.event_key) for row in page if not row.job_scoped]
    raw_stmt = (
        select(CreditTransaction)
        .where(
            CreditTransaction.user_id == user_id,
            (job_scoped & job_id.in_(job_ids)) | CreditTransaction.id.in_(single_ids),
        )
        .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
    )
    rows = list((await db.execute(raw_stmt)).scalars().all())
    last = page[-1]
    nxt = (last.created_at, UUID(last.cursor_id)) if has_more else None
    return rows, nxt, total


async def list_transactions(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: tuple[datetime, UUID] | None = None,
    direction: Literal["in", "out"] | None = None,
) -> tuple[list[CreditTransaction], tuple[datetime, UUID] | None, int | None]:
    """Read the caller's ledger, newest first — the ``/wallet/transactions``
    projection (BILLING §7, the billing center's read-only predecessor).

    ``direction=out`` delegates to semantic-event pagination, returning complete
    run folds and an exact event total. ``direction=in`` filters raw incoming
    entries before keyset pagination; each is one semantic event. Unfiltered
    reads keep the original raw-ledger keyset and do not calculate a total.
    """
    if direction == "out":
        return await _list_outgoing_events(
            db, user_id, limit=limit, cursor=cursor
        )

    stmt = select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    if direction == "in":
        job_id = func.coalesce(CreditTransaction.ref["export_id"].astext, CreditTransaction.ref["media_job_id"].astext)
        job_scoped = (
            CreditTransaction.kind.in_(["hold", "capture", "release"])
            & job_id.is_not(None)
            & (job_id != "")
        )
        stmt = stmt.where(
            ~job_scoped
            & (
                CreditTransaction.kind.in_(["purchase", "grant", "refund"])
                | (CreditTransaction.amount >= 0)
            )
        )
    total = (
        int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        if direction == "in"
        else None
    )
    if cursor is not None:
        stmt = stmt.where(
            tuple_(CreditTransaction.created_at, CreditTransaction.id) < cursor
        )
    stmt = stmt.order_by(
        CreditTransaction.created_at.desc(), CreditTransaction.id.desc()
    ).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    if len(rows) <= limit:
        return rows, None, total
    page = rows[:limit]
    last = page[-1]
    return page, (last.created_at, last.id), total


async def held(db: AsyncSession, user_id: UUID) -> int:
    """Outstanding reservations from the same wallet ledger used for settlement."""
    amount = await db.scalar(select(func.sum(CreditTransaction.amount)).where(
        CreditTransaction.user_id == user_id,
        CreditTransaction.kind.in_(("hold", "release")),
    ))
    return -int(amount or 0)


async def check_hold(db: AsyncSession, *, user_id: UUID, required: int) -> Wallet:
    """Read-only sufficiency probe for a required hold.

    Raises CreditsInsufficientError when the balance can't cover it — a
    negative balance therefore fails every hold, including a free (0) one
    (BILLING §5: gate at the start, never mid-flight). The reservation writer re-checks
    atomically inside its UPDATE; this probe exists so the birthplace rejects
    before mutating anything, and for future UI previews.
    """
    wallet = await get_or_create_wallet(db, user_id)
    if wallet.balance < required:
        raise CreditsInsufficientError(balance=int(wallet.balance), required=required)
    return wallet


async def purchase_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    order_id: UUID,
    provider_event_id: str,
    amount: int,
) -> CreditTransaction:
    """Grant a paid order's credits through the ledger's exactly-once gate.

    The payment adapter locks its order before calling here; this event-level
    key handles webhook replays while the order lock separates different
    events for the same purchase. Writers flush, callers commit (PAYMENTS §4).
    """
    if amount <= 0:
        raise ValueError("purchase amount must be positive")
    await get_or_create_wallet(db, user_id)
    return await _mutate(
        db,
        user_id=user_id,
        kind="purchase",
        amount=amount,
        ref={"payment_order_id": str(order_id), "payment_event": provider_event_id},
        idem=f"stripe:{provider_event_id}:purchase",
        note="Credit package purchase",
    )


async def _mutate(
    db: AsyncSession,
    *,
    user_id: UUID,
    kind: str,
    amount: int,
    ref: dict,
    idem: str,
    note: str | None,
    require_balance: int | None = None,
) -> CreditTransaction:
    """One ledger movement = gated wallet UPDATE + append-only ledger row.

    The NOT-EXISTS gate on the idempotency key lives INSIDE the wallet UPDATE
    (evaluated against the row the update locks), so a duplicate call no-ops
    structurally — the UNIQUE constraint is the dedupe mechanism, never
    check-then-write code. ``version`` bumps on every movement (the optimistic
    lock bookkeeping of MODULE_ARCH §4).
    """
    conditions = [
        Wallet.user_id == user_id,
        ~exists().where(CreditTransaction.idempotency_key == idem),
    ]
    if require_balance is not None:
        conditions.append(Wallet.balance >= require_balance)
    new_balance = (
        await db.execute(
            update(Wallet)
            .where(*conditions)
            .values(balance=Wallet.balance + amount, version=Wallet.version + 1)
            .returning(Wallet.balance)
            .execution_options(synchronize_session=False)
        )
    ).scalar_one_or_none()
    if new_balance is None:
        # No movement: the gate rejected (duplicate — return the row that
        # already did this) or the balance floor failed (hold only).
        existing = await _txn_by_idem(db, idem)
        if existing is not None:
            return existing
        if require_balance is None:
            raise RuntimeError(
                f"ledger gate rejected {kind} {idem} but no such row exists"
            )
        wallet = await get_or_create_wallet(db, user_id)
        raise CreditsInsufficientError(
            balance=int(wallet.balance), required=require_balance
        )
    inserted_id = (
        await db.execute(
            pg_insert(CreditTransaction)
            .values(
                user_id=user_id,
                kind=kind,
                amount=amount,
                balance_after=new_balance,
                ref=ref,
                idempotency_key=idem,
                note=note,
            )
            # Belt and braces under the gate: a pathological same-key race can
            # never turn into an IntegrityError poisoning the caller's commit
            # alongside the business result in this transaction.
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(CreditTransaction.id)
        )
    ).scalar_one_or_none()
    if inserted_id is None:
        logger.warning("ledger_insert_conflict_after_mutation", idem=idem, kind=kind)
    txn = await _txn_by_idem(db, idem)
    if txn is None:  # can't happen: we just inserted, or the gate proved it exists
        raise RuntimeError(f"ledger row missing after mutation: {idem}")
    return txn


async def _txn_by_idem(db: AsyncSession, idem: str) -> CreditTransaction | None:
    """Fetch a ledger row by its idempotency key (the post-gate read — never
    a write-deciding check)."""
    return (
        await db.execute(
            select(CreditTransaction).where(CreditTransaction.idempotency_key == idem)
        )
    ).scalar_one_or_none()


def settled_job_amounts(job, result, *, export):
    """Expected signed ledger totals for a receipt that proves settlement."""
    if job.status not in {"succeeded", "failed", "cancelled"}:
        return None
    succeeded = job.status == "succeeded"
    if result.get("status") != ("available" if succeeded else job.status):
        return None
    charged = result.get("charged_credits")
    reserved = job.authorized_credits
    if (result.get("reserved_credits") != 0 or type(charged) is not int
            or not 0 <= charged <= reserved or (not succeeded and charged != 0)
            or (export and succeeded and charged != reserved)):
        return None
    return {"hold": -reserved, "release": reserved, "capture": -charged}


async def hold_export(db, *, user_id, export_id, credits):
    await check_hold(db, user_id=user_id, required=credits)
    if credits:
        await _mutate(db, user_id=user_id, kind="hold", amount=-credits,
                      ref={"export_id": str(export_id)}, idem=f"export:{export_id}:hold",
                      note="Video export reservation", require_balance=credits)


async def settle_export(db, *, user_id, export_id, reserved, charged):
    """Called under the export row lock in its terminal transaction."""
    if not 0 <= charged <= reserved:
        raise ValueError("Export charge exceeds its reservation")
    if reserved:
        await _mutate(db, user_id=user_id, kind="release", amount=reserved,
                      ref={"export_id": str(export_id)}, idem=f"export:{export_id}:release",
                      note="Video export reservation released")
    if charged:
        await _mutate(db, user_id=user_id, kind="capture", amount=-charged,
                      ref={"export_id": str(export_id)}, idem=f"export:{export_id}:capture",
                      note="Verified MP4 export")

async def hold_media(db, *, user_id, job_id, credits):
    await check_hold(db, user_id=user_id, required=credits)
    if credits:
        await _mutate(db, user_id=user_id, kind="hold", amount=-credits,
                      ref={"media_job_id": str(job_id)}, idem=f"media:{job_id}:hold",
                      note="Media generation reservation", require_balance=credits)


async def settle_media(db, *, user_id, job_id, reserved, charged):
    if not 0 <= charged <= reserved:
        raise ValueError("Media charge exceeds its reservation")
    ref = {"media_job_id": str(job_id)}
    if reserved:
        await _mutate(db, user_id=user_id, kind="release", amount=reserved, ref=ref,
                      idem=f"media:{job_id}:release", note="Media generation reservation released")
    if charged:
        await _mutate(db, user_id=user_id, kind="capture", amount=-charged, ref=ref,
                      idem=f"media:{job_id}:capture", note="Generated media")

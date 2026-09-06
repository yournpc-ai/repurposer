"""Wallet service — the credits wallet and ledger writers (ADR-055).

User-side currency layer of the credits system (docs/BILLING.md): ``metering``
accounts the provider side in USD (``workflow_steps.cost``); this module
accounts the user side in credits. One fold, two consumers — USD never
reaches the UI.

Charge cycle (BILLING §3): ``hold_run`` pre-charges the high-end fold at run
birth → ``capture_step`` settles each successful step's actual at the
metering merge point (same session, same commit — ADR-050) → ``release_run``
returns the un-captured remainder at the run's terminal state. Failed/skipped
steps never write a capture row (失败不扣费); NULL-estimate steps hold 0 but
capture their actual — the balance may go negative (BILLING §5, by design).
``purchase`` arrives with the W11 payment adapter; the ledger needs no change
for it.

Write discipline (create_notification precedent): writers flush, callers
commit — a ledger row must commit atomically with the event that caused it
(the signup here; the step's metering merge point for capture). Every ledger
row carries an ``idempotency_key`` and every mutation is gated on that key's
absence INSIDE the same UPDATE statement: dedupe is the UNIQUE constraint,
never check-then-write code, and a duplicate call never poisons the caller's
transaction with an IntegrityError.
"""

from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import exists, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import CreditTransaction, Wallet, WorkflowStep
from app.platform.configs import get_config
from app.providers.llm.minimax import price_tokens, price_units

logger = structlog.get_logger()


class CreditsInsufficientError(ValueError):
    """User-level shortfall at the hold gate (birthplace 422).

    Carries the structured 422 payload (BILLING §7): ``{code:
    "credits.insufficient", balance, required}``. A ValueError so create_run's
    handlers degrade gracefully; every user-facing path converts it to the
    typed 422 (typed endpoints raise it directly; the chat dispatch's
    ``_create_run_from_tasks`` is the single conversion funnel there) and the
    dock renders its grey row. Strictly the USER-level "积分不足" — never
    conflated with a provider 402.
    """

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
        price_tokens(prompt_low, completion_low) + units_usd,
        price_tokens(prompt_high, completion_high) + units_usd,
    )


def cost_usd(cost: dict | None) -> float:
    """Money value (USD) of a step's persisted cost ledger. Media units'
    money already lives in ``fixed_cost`` (record_media_usage) — pricing the
    units again would double-count."""
    if not cost:
        return 0.0
    return price_tokens(
        int(cost.get("prompt_tokens") or 0),
        int(cost.get("completion_tokens") or 0),
    ) + float(cost.get("fixed_cost") or 0.0)


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


async def list_transactions(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: tuple[datetime, UUID] | None = None,
) -> tuple[list[CreditTransaction], tuple[datetime, UUID] | None]:
    """Read the caller's ledger, newest first — the ``/wallet/transactions``
    projection (BILLING §7, the W11 billing center's read-only前身).

    Keyset pagination on (created_at, id) DESC: the ledger is append-only,
    so a keyset cursor is stable under concurrent appends where OFFSET would
    drift. Returns (rows, next_cursor) — next_cursor None on the last page.
    """
    stmt = select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    if cursor is not None:
        stmt = stmt.where(
            tuple_(CreditTransaction.created_at, CreditTransaction.id) < cursor
        )
    stmt = stmt.order_by(
        CreditTransaction.created_at.desc(), CreditTransaction.id.desc()
    ).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    last = page[-1]
    return page, (last.created_at, last.id)


async def held(db: AsyncSession, user_id: UUID) -> int:
    """Currently frozen credits — Σ over runs with a hold but no release of
    max(0, hold − Σcaptures): a settled run holds nothing; an over-captured
    (NULL-estimate) run contributes 0, its excess is the negative-balance
    charge, not something still frozen.

    Aggregates in Python, not SQL: the group key is a JSONB extraction, and
    grouping by a parameterised JSONB expression trips Postgres's
    SELECT/GROUP-BY identity rule (same text, different bind positions =
    mismatch → "column ref must appear in GROUP BY"). The per-user ledger is
    small; a plain filtered scan is cheap and honest.
    """
    rows = (
        await db.execute(
            select(CreditTransaction.kind, CreditTransaction.amount,
                   CreditTransaction.ref).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.kind.in_(["hold", "capture", "release"]),
            )
        )
    ).all()
    per_run: dict[str, dict[str, int]] = {}
    for kind, amount, ref in rows:
        run_id = (ref or {}).get("run_id")
        if not run_id:
            continue
        sums = per_run.setdefault(str(run_id), {})
        sums[kind] = sums.get(kind, 0) + int(amount)
    return sum(
        max(0, abs(sums.get("hold", 0)) - abs(sums.get("capture", 0)))
        for sums in per_run.values()
        if "release" not in sums
    )


async def check_hold(db: AsyncSession, *, user_id: UUID, required: int) -> Wallet:
    """Read-only sufficiency probe for a required hold.

    Raises CreditsInsufficientError when the balance can't cover it — a
    negative balance therefore fails every hold, including a free (0) one
    (BILLING §5: gate at the start, never mid-flight). ``hold_run`` re-checks
    atomically inside its UPDATE; this probe exists so the birthplace rejects
    before mutating anything, and for future UI previews.
    """
    wallet = await get_or_create_wallet(db, user_id)
    if wallet.balance < required:
        raise CreditsInsufficientError(balance=int(wallet.balance), required=required)
    return wallet


async def hold_run(
    db: AsyncSession, *, user_id: UUID, run_id: UUID, amount: int
) -> CreditTransaction | None:
    """Pre-charge the high-end estimate fold at run birth (idem
    ``run:{id}:hold``). Amount 0 → no row (nothing moved). The sufficiency
    check re-fires inside the UPDATE (``balance >= amount``), so a concurrent
    hold that drained the wallet between ``check_hold`` and here turns into
    the same CreditsInsufficientError, never a silent overdraw."""
    if amount <= 0:
        return None
    return await _mutate(
        db,
        user_id=user_id,
        kind="hold",
        amount=-amount,
        ref={"run_id": str(run_id)},
        idem=f"run:{run_id}:hold",
        note="Run estimate hold",
        require_balance=amount,
    )


async def capture_step(
    db: AsyncSession, *, user_id: UUID, node: WorkflowStep
) -> CreditTransaction | None:
    """Settle one successful step's actual (called at the metering merge
    point, same write). Amount = credits(node.cost total) − credits already
    captured for this step:

    - the common case writes one row at idem ``step:{id}:capture`` holding
      the step's full accumulated cost — transient retries included (成功收
      全量, BILLING §3);
    - a QualityBounce re-run reaches the success branch a second time with
      the SAME step-level key already taken; its row lands at
      ``step:{id}:capture:{attempt}`` carrying only the delta beyond what
      was captured, so the ledger still reconciles with workflow_steps.cost
      (× the ratio) instead of silently eating the re-run.

    Failed/skipped steps never reach here (失败不扣费); a step with nothing
    metered (cost NULL) or a credit amount that rounds to 0 writes no row —
    the ledger records money movement, and zero is not movement.
    """
    usd_total = cost_usd(node.cost)
    if usd_total <= 0:
        return None
    total_credits = await credits_for_cost(db, usd_total)
    prior = await _capture_sum_for_step(db, user_id=user_id, step_id=node.id)
    amount = total_credits - prior
    if amount <= 0:
        return None
    idem = (
        f"step:{node.id}:capture"
        if prior == 0
        else f"step:{node.id}:capture:{node.attempt or 0}"
    )
    return await _mutate(
        db,
        user_id=user_id,
        kind="capture",
        amount=-amount,
        ref={"run_id": str(node.run_id), "step_id": str(node.id)},
        idem=idem,
        note=f"Step {node.kind} capture",
    )


async def release_run(
    db: AsyncSession, *, user_id: UUID, run_id: UUID
) -> CreditTransaction | None:
    """Return the un-captured remainder of a run's hold at its terminal state
    (idem ``run:{id}:release``): remainder = hold − Σcaptures, clamped at 0 —
    NULL-estimate steps may capture past the hold, and that excess is the
    user's real charge (negative-balance semantics), never a negative
    release. Remainder 0 → no row."""
    held, captured = await _run_hold_capture_sums(db, user_id=user_id, run_id=run_id)
    remainder = max(0, held - captured)
    if remainder == 0:
        return None
    return await _mutate(
        db,
        user_id=user_id,
        kind="release",
        amount=remainder,
        ref={"run_id": str(run_id)},
        idem=f"run:{run_id}:release",
        note="Run hold release",
    )


# ---- internals ----------------------------------------------------------------


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
            # (execute_step's success write rides this session).
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


async def _capture_sum_for_step(db: AsyncSession, *, user_id: UUID, step_id: UUID) -> int:
    """Credits already captured for a step (bounce-delta bookkeeping)."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.kind == "capture",
                CreditTransaction.ref["step_id"].as_string() == str(step_id),
            )
        )
    ).scalar_one()
    return abs(int(total))


async def _run_hold_capture_sums(
    db: AsyncSession, *, user_id: UUID, run_id: UUID
) -> tuple[int, int]:
    """(held, captured) credit totals for a run — release's settlement base."""
    rows = await db.execute(
        select(
            CreditTransaction.kind,
            func.coalesce(func.sum(CreditTransaction.amount), 0),
        )
        .where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.kind.in_(["hold", "capture"]),
            CreditTransaction.ref["run_id"].as_string() == str(run_id),
        )
        .group_by(CreditTransaction.kind)
    )
    sums = {kind: int(total) for kind, total in rows}
    return abs(sums.get("hold", 0)), abs(sums.get("capture", 0))

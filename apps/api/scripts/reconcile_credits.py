"""reconcile_credits.py — 积分台账对账尺（验收口径 7 的实证工具，BILLING §2）。

BILLING §2 承诺「对账一条查出漂移」的工具版：四类检查，任一失败打印
漂移明细、退出码非零。金额与余额全部以台账行 + 表行重算，与
``wallets.balance`` 物化缓存对拍——缓存说谎时，这里捉出来。

  1. 钱包链完整（per wallet）：Σ amount == balance，且最新
     (created_at, id) 行的 balance_after == balance。
  2. run 结算恒等（per 有 hold 行的 run）：终态 run 必有 release 且
     amount == max(0, hold − Σcaptures)；非终态 run 无 release（在途不
     提前结清）；有 capture/release 却无 hold = 异常。被删 run 视为终态；
     其未结 hold 记 known-open（孤儿回收机制立项中，BILLING §8），不计漂移。
  3. 失败不扣费：failed/skipped 步骤零 capture（ref.step_id 命中 0 条）。
  4. step × 比例对账：done 且 cost 非空的步骤，Σ|capture 行| ==
     credits_at_ratio(cost_usd(cost), 当前比例)。

第 4 类的已知边界（设计语义，非 bug）：capture 按 capture 时刻的比例
结算，调参后历史 capture 与「按当前比例重算」不再相等（BILLING §4
调参不动历史账）。``--since`` 一刀切两个语义：capture 行在其后创建 +
run 在其后出生——调参演示后核新行用它，划掉 billing go-live 前的考古
行也用它（验收 = ``--since`` 到今日起）。换算只经
``app.platform.billing`` 的三个件（cost_usd / credits_at_ratio /
get_config），本脚本禁第二份价目与换算。

Usage (from apps/api/):
    uv run python scripts/reconcile_credits.py
    uv run python scripts/reconcile_credits.py --user <uuid>
    uv run python scripts/reconcile_credits.py --since 2026-09-11T09:00:00+00:00
"""

import argparse
import asyncio
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import WorkflowStatus  # noqa: E402
from app.models.tables import (  # noqa: E402
    CreditTransaction,
    Project,
    Wallet,
    WorkflowRun,
    WorkflowStep,
)
from app.platform.billing import (  # noqa: E402
    cost_usd,
    credits_at_ratio,
)
from app.platform.configs import get_config  # noqa: E402

problems: list[str] = []
checked = {"wallets": 0, "runs": 0, "dead_runs": 0, "open_dead_holds": 0, "steps": 0}


def fail(msg: str) -> None:
    problems.append(msg)
    print(f"  ✘ {msg}")


def by_run(rows: list[CreditTransaction]) -> dict[str, list[CreditTransaction]]:
    per_run: dict[str, list[CreditTransaction]] = defaultdict(list)
    for row in rows:
        run_id = (row.ref or {}).get("run_id")
        if run_id:
            per_run[str(run_id)].append(row)
    return per_run


def check_wallet_chains(wallets: list[Wallet], txns: list[CreditTransaction]) -> None:
    """Check 1 — Σ amount == balance, latest balance_after == balance."""
    per_user: dict[uuid.UUID, list[CreditTransaction]] = defaultdict(list)
    for row in txns:
        per_user[row.user_id].append(row)  # rows arrive (created_at, id) ordered
    for wallet in wallets:
        checked["wallets"] += 1
        rows = per_user.get(wallet.user_id, [])
        total = sum(int(r.amount) for r in rows)
        if total != int(wallet.balance):
            fail(
                f"wallet {wallet.user_id}: Σ amount {total} != balance "
                f"{int(wallet.balance)}"
            )
        if rows:
            last = rows[-1]
            if int(last.balance_after) != int(wallet.balance):
                fail(
                    f"wallet {wallet.user_id}: latest balance_after "
                    f"{int(last.balance_after)} ({last.idempotency_key}) != "
                    f"balance {int(wallet.balance)}"
                )
            for prev, cur in zip(rows, rows[1:]):
                if int(prev.balance_after) + int(cur.amount) != int(cur.balance_after):
                    fail(
                        f"wallet {wallet.user_id}: chain break at "
                        f"{cur.idempotency_key} — {int(prev.balance_after)} + "
                        f"{int(cur.amount)} != {int(cur.balance_after)}"
                    )
    wallet_users = {w.user_id for w in wallets}
    for uid in per_user:
        if uid not in wallet_users:
            fail(f"ledger rows exist for {uid} but the wallet row is missing")


async def check_run_settlement(db, txns: list[CreditTransaction]) -> None:
    """Check 2 — per-run hold/capture/release settlement identity."""
    terminal = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
    for run_id, rows in by_run(txns).items():
        holds = [r for r in rows if r.kind == "hold"]
        captures = [r for r in rows if r.kind == "capture"]
        releases = [r for r in rows if r.kind == "release"]
        if not holds:
            if captures or releases:
                fail(
                    f"run {run_id}: capture/release rows without a hold "
                    f"({len(captures)} capture / {len(releases)} release)"
                )
            continue
        checked["runs"] += 1
        hold = sum(int(r.amount) for r in holds)  # signed: negative
        if len(holds) > 1:
            fail(f"run {run_id}: {len(holds)} hold rows (idem key should dedupe)")
        for r in holds:
            if int(r.amount) >= 0:
                fail(f"run {run_id}: hold amount {int(r.amount)} not negative")
        captured = sum(-int(r.amount) for r in captures)
        expected_release = max(0, -hold - captured)
        run = await db.get(WorkflowRun, uuid.UUID(run_id))
        if run is None:
            # The ledger is append-only and outlives run rows (project
            # deletion cascades runs; money history stays). A dead run is
            # terminal-by-deletion: its hold must still have settled.
            checked["dead_runs"] += 1
        label = "deleted" if run is None else run.status.value
        if run is None or run.status in terminal:
            if expected_release > 0 and not releases:
                if run is None:
                    # 豁免：被删 run 的未结 hold 归孤儿回收机制管辖
                    # （project 删除即解冻 / reaper，BILLING §8 立项项）
                    # ——记 known-open 不记漂移；活 run 未结 hold 仍硬判。
                    checked["open_dead_holds"] += 1
                    print(
                        f"  ○ run {run_id} (deleted): unsettled hold "
                        f"{expected_release} credits — orphan-hold recovery pending"
                    )
                else:
                    fail(
                        f"run {run_id} ({label}): terminal with an "
                        f"un-settled hold (expected release {expected_release})"
                    )
            if expected_release == 0 and releases:
                fail(
                    f"run {run_id} ({label}): release row despite a "
                    f"fully-captured hold (amount {int(releases[0].amount)})"
                )
            for r in releases:
                if int(r.amount) <= 0:
                    fail(f"run {run_id}: release amount {int(r.amount)} not positive")
                if int(r.amount) != expected_release:
                    fail(
                        f"run {run_id}: release {int(r.amount)} != expected "
                        f"{expected_release} (hold {-hold}, captured {captured})"
                    )
        else:
            if releases:
                fail(
                    f"run {run_id} ({label}): release before the "
                    f"terminal state"
                )


async def check_failed_steps_zero_capture(db, txns: list[CreditTransaction]) -> None:
    """Check 3 — failed/skipped steps never charge (失败不扣费)."""
    capture_step_ids = {
        (r.ref or {}).get("step_id") for r in txns if r.kind == "capture"
    }
    steps = (
        (
            await db.execute(
                select(WorkflowStep).where(
                    WorkflowStep.status.in_(["failed", "skipped"])
                )
            )
        )
        .scalars()
        .all()
    )
    for step in steps:
        checked["steps"] += 1
        if str(step.id) in capture_step_ids:
            fail(
                f"step {step.id} ({step.kind}, {step.status}): a capture row "
                f"exists — failed/skipped steps must never charge"
            )


async def check_step_ratio(
    db,
    txns: list[CreditTransaction],
    ratio: int,
    since: datetime | None,
    user_filter: uuid.UUID | None,
) -> None:
    """Check 4 — done steps: Σ|captures| == credits(cost × current ratio).

    ``--since`` is the billing-era cut: only capture rows created after it AND
    steps on runs born after it join the identity. Two uses, one flag: scope
    out pre-ratio-change rows after a 调参 demo (BILLING §4 — history is
    expected to differ), and scope out pre-go-live archaeology (cost metering
    predates billing; those steps never owed captures).
    """
    captures_by_step: dict[str, list[CreditTransaction]] = defaultdict(list)
    for row in txns:
        if row.kind != "capture":
            continue
        if since is not None and row.created_at <= since:
            continue
        step_id = (row.ref or {}).get("step_id")
        if step_id:
            captures_by_step[str(step_id)].append(row)
    stmt = select(WorkflowStep).where(
        WorkflowStep.status == "done",
        WorkflowStep.cost.isnot(None),
    )
    if since is not None:
        # Billing-era cut: steps on runs born before it are archaeology —
        # cost metering predates billing, they never owed captures.
        stmt = stmt.where(
            WorkflowStep.run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.created_at > since)
            )
        )
    if user_filter is not None:
        # Steps carry no user_id — scope through run → project.
        stmt = stmt.where(
            WorkflowStep.run_id.in_(
                select(WorkflowRun.id).where(
                    WorkflowRun.project_id.in_(
                        select(Project.id).where(Project.user_id == user_filter)
                    )
                )
            )
        )
    steps = (await db.execute(stmt)).scalars().all()
    for step in steps:
        checked["steps"] += 1
        want = credits_at_ratio(cost_usd(step.cost), ratio)
        got = sum(-int(r.amount) for r in captures_by_step.get(str(step.id), []))
        if want == 0 and got == 0:
            continue  # cost rounds to zero credits: no capture row is correct
        if got != want:
            fail(
                f"step {step.id} ({step.kind}): Σ captures {got} != "
                f"credits(cost × ratio) {want}"
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", help="scope every check to one wallet (uuid)")
    parser.add_argument(
        "--since",
        help="ISO timestamp — billing-era cut for the step×ratio check: only "
        "captures after it and steps on runs born after it participate "
        "(调参后历史行属期望 / go-live 前考古, BILLING §4)",
    )
    args = parser.parse_args()
    user_filter = uuid.UUID(args.user) if args.user else None
    since = datetime.fromisoformat(args.since) if args.since else None
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)  # DB rows are tz-aware

    async with AsyncSessionLocal() as db:
        ratio = await get_config(db, "credits.per_cost_usd")
        wallets = (
            (
                await db.execute(
                    select(Wallet).where(Wallet.user_id == user_filter)
                    if user_filter
                    else select(Wallet)
                )
            )
            .scalars()
            .all()
        )
        stmt = select(CreditTransaction).order_by(
            CreditTransaction.created_at, CreditTransaction.id
        )
        if user_filter:
            stmt = stmt.where(CreditTransaction.user_id == user_filter)
        txns = list((await db.execute(stmt)).scalars().all())

        print(
            f"reconcile credits — {len(wallets)} wallet(s), "
            f"{len(txns)} ledger row(s), ratio {ratio}\n"
        )
        check_wallet_chains(wallets, txns)
        await check_run_settlement(db, txns)
        await check_failed_steps_zero_capture(db, txns)
        await check_step_ratio(db, txns, ratio, since, user_filter)

    print(
        f"checked: {checked['wallets']} wallet(s), {checked['runs']} held run(s) "
        f"({checked['dead_runs']} deleted, {checked['open_dead_holds']} orphan "
        f"hold(s) pending recovery), {checked['steps']} step(s)"
    )
    if problems:
        print(f"\n{len(problems)} DRIFT(S) — ledger and wallet disagree")
        return 1
    print("\nledger and wallet agree — no drift")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

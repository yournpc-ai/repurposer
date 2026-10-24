"""Audit legacy double-debits; append missing reservation releases with --apply.

Never rewrites captures/history. Defaults to read-only; --run-id narrows scope.
Run from apps/api: python scripts/repair_credit_reservations.py [--run-id UUID] [--apply]
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.models.database import AsyncSessionLocal
from app.models.schemas import WorkflowStatus
from app.models.tables import CreditTransaction, Wallet, WorkflowRun
from app.platform.billing import _mutate, _run_hold_release_sums


async def main(run_id: str | None, apply: bool):
    async with AsyncSessionLocal() as db:
        query = select(CreditTransaction).where(CreditTransaction.kind == "hold")
        if run_id:
            query = query.where(CreditTransaction.ref["run_id"].astext == str(UUID(run_id)))
        holds = list((await db.execute(query)).scalars())
        for hold in holds:
            rid = UUID(hold.ref["run_id"])
            # Same lock order as finalization: run then wallet.
            run = await db.get(WorkflowRun, rid, with_for_update=apply)
            if run and run.status not in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
                continue
            if apply:
                await db.execute(select(Wallet).where(Wallet.user_id == hold.user_id).with_for_update())
            reserved, released = await _run_hold_release_sums(db, user_id=hold.user_id, run_id=rid)
            missing = max(0, reserved - released)
            if missing:
                print(f"run={rid} reservation_release_due={missing} apply={apply}")
                if apply:
                    await _mutate(
                        db, user_id=hold.user_id, kind="release", amount=missing,
                        ref={"run_id": str(rid)},
                        idem=f"run:{rid}:reservation-repair:v1",
                        note="Correct duplicated reservation debit",
                    )
            if apply:
                await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.run_id, args.apply))

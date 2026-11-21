"""Check wallet chains and native Job receipts against posted ledger entries."""

import argparse
import asyncio
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import CreditTransaction, ExportJob, MediaJob, Message, Project, Wallet
from app.platform.billing import settled_job_amounts

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)
    print(message)


def check_wallet_chains(wallets: list[Wallet], txns: list[CreditTransaction]) -> None:
    """Check 1 — Σ amount == balance, latest balance_after == balance."""
    per_user: dict[uuid.UUID, list[CreditTransaction]] = defaultdict(list)
    for row in txns:
        per_user[row.user_id].append(row)  # rows arrive (created_at, id) ordered
    for wallet in wallets:
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


async def check_jobs(db, txns, user, since):
    checked = 0
    for model, field in ((MediaJob, "media_job_id"), (ExportJob, "export_id")):
        by_id = defaultdict(list)
        for txn in txns:
            ref = (txn.ref or {}).get(field)
            if ref:
                by_id[ref].append(txn)
        query = (select(model, Project.user_id, Message.intent)
                 .join(Project, Project.id == model.project_id)
                 .outerjoin(Message, Message.id == model.receipt_id))
        if user:
            query = query.where(Project.user_id == user)
        for job, owner, intent in await db.execute(query):
            rows = by_id.pop(str(job.id), [])
            if since and job.created_at < since:
                continue
            checked += 1
            if intent is None or any(row.user_id != owner for row in rows):
                fail(f"{field} {job.id}: missing receipt or foreign ledger entry")
            result = (intent or {}).get("media_result") or {}
            expected = settled_job_amounts(job, result, export=model is ExportJob)
            if expected is None:
                if (job.status not in {"running", "queued", "unknown"}
                        and result.get("status") != "fixed_audio_pending_recovery"):
                    fail(f"{field} {job.id}: invalid settlement receipt for {job.status}")
                expected = {"hold": -job.authorized_credits, "capture": 0, "release": 0}
            amounts = {kind: sum(row.amount for row in rows if row.kind == kind)
                       for kind in expected}
            if amounts != expected or len(rows) != sum(value != 0 for value in expected.values()):
                fail(f"{field} {job.id}: ledger {amounts}, expected {expected}")
        for identity, rows in by_id.items():
            if since and all(row.created_at < since for row in rows):
                continue
            if sum(row.amount for row in rows if row.kind in {"hold", "release"}):
                fail(f"{field} {identity}: outstanding reservation without an owned job")
    return checked


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=uuid.UUID)
    parser.add_argument("--since", type=datetime.fromisoformat, help="audit jobs created since ISO timestamp")
    args = parser.parse_args()
    since = args.since
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        wallets = select(Wallet)
        transactions = select(CreditTransaction).order_by(CreditTransaction.created_at, CreditTransaction.id)
        if args.user:
            wallets = wallets.where(Wallet.user_id == args.user)
            transactions = transactions.where(CreditTransaction.user_id == args.user)
        wallets = list(await db.scalars(wallets))
        rows = list(await db.scalars(transactions))
        check_wallet_chains(wallets, rows)
        count = await check_jobs(db, rows, args.user, since)
    print(f"{len(wallets)} wallets, {count} jobs, {len(rows)} ledger rows, {len(problems)} discrepancies")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

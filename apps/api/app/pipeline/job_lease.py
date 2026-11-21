"""Database-clock fencing for assets, media generation and formal exports."""

import asyncio

from sqlalchemy import func, update


def authority(table, job_id, token, *, running=None):
    return (
        table.id == job_id,
        table.status == "running" if running is None else running,
        table.claim_token == token,
        table.lease_until > func.clock_timestamp(),
    )


async def heartbeat(sessions, table, job_id, token, lease, *, running=None):
    while True:
        await asyncio.sleep(lease.total_seconds() / 3)
        async with sessions() as db:
            result = await db.execute(
                update(table)
                .where(*authority(table, job_id, token, running=running))
                .values(lease_until=func.clock_timestamp() + lease)
            )
            await db.commit()
            if not result.rowcount:
                return

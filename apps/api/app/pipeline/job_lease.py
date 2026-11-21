"""Database-clock fencing shared by media generation and formal exports."""

import asyncio

from sqlalchemy import func, update


def authority(table, job_id, token):
    return (
        table.id == job_id,
        table.status == "running",
        table.claim_token == token,
        table.lease_until > func.clock_timestamp(),
    )


async def heartbeat(sessions, table, job_id, token, lease):
    while True:
        await asyncio.sleep(lease.total_seconds() / 3)
        async with sessions() as db:
            result = await db.execute(
                update(table)
                .where(*authority(table, job_id, token))
                .values(lease_until=func.now() + lease)
            )
            await db.commit()
            if not result.rowcount:
                return

import asyncio

import asyncpg


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@localhost:5432/repurposer"
    )
    cols = await conn.fetch(
        """SELECT column_name FROM information_schema.columns
           WHERE table_name='credit_transactions'"""
    )
    print("cols:", [c["column_name"] for c in cols])
    rows = await conn.fetch(
        """SELECT * FROM credit_transactions
           WHERE CAST(run_id AS text) LIKE 'd94c3a91%'
           ORDER BY created_at"""
        if "run_id" in [c["column_name"] for c in cols]
        else """SELECT * FROM credit_transactions ORDER BY created_at DESC LIMIT 6"""
    )
    for r in rows:
        d = dict(r)
        print(
            d.get("created_at").strftime("%H:%M:%S"),
            {k: (str(v)[:60]) for k, v in d.items() if k != "created_at"},
        )
    await conn.close()


asyncio.run(main())

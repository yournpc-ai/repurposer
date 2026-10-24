#!/usr/bin/env python3
"""Catch the projects-row lock holder during a T3 turn replay.

Polls pg_locks every 150ms for GRANTED locks on the projects table and
dumps the holder's pid / state / query / xact age. One-off forensics for
the 2026-10-23 T3 LockNotAvailableError hunt.
"""
import time

import psycopg2

DSN = "postgresql://postgres:postgres@127.0.0.1:5432/repurposer"
PROJECT = "d85eacce-d5c1-4bc7-b2bf-0cfea2ec8290"

SQL = """
SELECT l.pid, l.mode, l.granted, a.state, a.backend_start, a.xact_start,
       now() - a.xact_start AS xact_age, LEFT(a.query, 300) AS query
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE l.relation = 'projects'::regclass
"""


def main() -> None:
    seen: dict[tuple, float] = {}
    end = time.time() + 180
    with psycopg2.connect(DSN) as conn:
        conn.autocommit = True
        while time.time() < end:
            with conn.cursor() as cur:
                cur.execute(SQL)
                rows = cur.fetchall()
            for r in rows:
                key = (r[0], r[1])
                if key not in seen:
                    seen[key] = time.time()
                    print(f"[{time.strftime('%H:%M:%S')}] NEW pid={r[0]} mode={r[1]} granted={r[2]}")
                    print(f"    state={r[3]} xact_start={r[5]} age={r[6]}")
                    print(f"    query={r[7]!r}", flush=True)
            time.sleep(0.15)
    print("poller done", flush=True)


if __name__ == "__main__":
    main()

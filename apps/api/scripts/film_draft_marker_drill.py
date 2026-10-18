"""Film draft in-flight marker — REAL-DB concurrency drill (并发护栏验收座).

The pure suites prove the predicates; only a real database proves the
protocol: two interleaved requests, a NOWAIT refusal, a failure clear that
survives the turn's rollback, a stale-marker supersede. Every scenario runs
against the configured DATABASE_URL with two independent sessions standing
in for two HTTP requests. A throwaway project row is created and deleted
around the drill; nothing else is touched.

Run: uv run python scripts/film_draft_marker_drill.py
"""

import asyncio
import sys
import time
from uuid import uuid4

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import Project, User
from app.tools.film.storyboard import (
    begin_film_draft,
    clear_film_draft_marker,
    film_draft_inflight_live,
    read_committed_film_marker,
)

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: object = None) -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  detail={detail!r}"))
    if not cond:
        FAILURES.append(label)


async def _marker(project_id) -> dict | None:
    return await read_committed_film_marker(project_id)


async def drill() -> None:
    async with AsyncSessionLocal() as db:
        user_id = (await db.execute(select(User.id).limit(1))).scalar_one_or_none()
    if user_id is None:
        print("SKIP: no user row in this database — seed one first.")
        return

    project_id = None
    try:
        async with AsyncSessionLocal() as db:
            project = Project(
                id=uuid4(),
                user_id=user_id,
                title="film-draft-marker-drill",
                # A standing old confirmation — begin must void it.
                pending_brief={"prompt": "drill", "film_draft_token": "old-tok"},
            )
            db.add(project)
            await db.commit()
            project_id = project.id

        async def _turn_session():
            """A fresh 'request' session + its own project object."""
            session = AsyncSessionLocal()
            proj = await session.get(Project, project_id)
            return session, proj

        # 1. begin commits the marker; a SECOND request's begin is refused
        #    (never queued, never an interleaved overwrite).
        s1, p1 = await _turn_session()
        try:
            draft_a = await begin_film_draft(s1, p1, base_version=1, user_message_id=None)
            check(draft_a is not None, "begin A lands")
            assert draft_a is not None
            marker = await _marker(project_id)
            check(
                isinstance(marker, dict) and marker.get("draft_id") == draft_a,
                "the marker is COMMITTED (visible to another transaction) right after begin",
                marker,
            )
            async with AsyncSessionLocal() as sc:
                pend = (
                    await sc.execute(
                        select(Project.pending_brief).where(Project.id == project_id)
                    )
                ).scalar_one_or_none()
            check(
                (pend or {}).get("film_draft_token") is None,
                "begin supersedes the old film confirmation (token cleared)",
                pend,
            )

            s2, p2 = await _turn_session()
            try:
                draft_b = await begin_film_draft(s2, p2, base_version=1, user_message_id=None)
                check(draft_b is None, "concurrent begin B is REFUSED while A is live")
                marker = await _marker(project_id)
                check(
                    (marker or {}).get("draft_id") == draft_a,
                    "the refused begin never overwrote A's marker",
                    marker,
                )
            finally:
                await s2.close()

            # 2. failure clear survives the turn's rollback: the committed
            #    marker is gone even though the turn session commits nothing.
            await clear_film_draft_marker(s1, p1, draft_id=draft_a)
            await s1.rollback()  # the failing turn rolls back
            check(
                await _marker(project_id) is None,
                "failure clear is committed INDEPENDENT of the turn's rollback",
                await _marker(project_id),
            )
            # rollback expires the ORM object — re-fetch before reuse
            # (expired attribute access raises MissingGreenlet).
            p1 = await s1.get(Project, project_id)
            assert p1 is not None

            # 3. after the clear, a retry begins immediately (no budget wait).
            draft_c = await begin_film_draft(s1, p1, base_version=1, user_message_id=None)
            check(draft_c is not None, "retry begins right after the clear")
            assert draft_c is not None

            # 4. clear only touches its OWN marker: a newer marker survives.
            newer = {
                "draft_id": "someone-else",
                "base_version": 2,
                "started_at": time.time(),
                "user_message_id": None,
            }
            async with AsyncSessionLocal() as s3:
                row = await s3.get(Project, project_id, with_for_update=True)
                pend = dict(row.pending_brief or {})
                pend["film_draft_inflight"] = newer
                row.pending_brief = pend
                await s3.commit()
            await clear_film_draft_marker(s1, p1, draft_id=draft_c)
            check(
                (await _marker(project_id) or {}).get("draft_id") == "someone-else",
                "clear never touches another draft's marker",
            )

            # 5. a STALE marker (older than the design budget) is superseded.
            stale = dict(newer, started_at=time.time() - 3600)
            async with AsyncSessionLocal() as s4:
                row = await s4.get(Project, project_id, with_for_update=True)
                pend = dict(row.pending_brief or {})
                pend["film_draft_inflight"] = stale
                row.pending_brief = pend
                await s4.commit()
            check(
                not film_draft_inflight_live(stale),
                "a marker older than the budget reads stale",
            )
            draft_d = await begin_film_draft(s1, p1, base_version=3, user_message_id=None)
            check(draft_d is not None, "a stale marker never blocks a fresh begin")

            # 6. publish conditional read: once the pending plan is consumed
            #    (a Start) the marker read proves the draft superseded.
            async with AsyncSessionLocal() as s5:
                row = await s5.get(Project, project_id, with_for_update=True)
                row.pending_brief = None  # what a successful Start writes
                await s5.commit()
            live = await _marker(project_id)
            check(
                not (isinstance(live, dict) and live.get("draft_id") == draft_d),
                "the publish check sees the pending plan consumed (draft discarded)",
            )
        finally:
            await s1.close()
    finally:
        if project_id is not None:
            async with AsyncSessionLocal() as db:
                row = await db.get(Project, project_id)
                if row is not None:
                    await db.delete(row)
                    await db.commit()


if __name__ == "__main__":
    asyncio.run(drill())
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURES")
        sys.exit(1)
    print("\nall drills passed")

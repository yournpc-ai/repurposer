"""World seats — canonical read points for project-scoped world facts.

consult-first 律: a fetch-capable tool consults its seat BEFORE touching
the network — a fact the project already holds is read from the store,
never re-fetched. Freshness policy lives WITH the seat, never in the
tools: snapshot semantics — a stored reading is a capture AS OF its
``fetched_at`` (the observation carries the stamp), and a re-fetch is an
explicit act (the user says the page changed), never an implicit TTL.

Write discipline: the chat read tools' write-through rides an INDEPENDENT
short session (``write_page_reading``) so the turn's transaction stays
read-only (the tool loop's 零副作用往返 law — the snapshot row is a world
memo, never domain state, and it never rides the turn's commit); the
pipeline's capture chain writes through its own ``process_asset`` session
via ``upsert_page_reading``.
"""

from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import PageReading

logger = structlog.get_logger()


def normalize_page_url(url: str) -> str:
    """The seat key's canonical form: scheme/host lowercased, fragment
    dropped, a bare trailing slash stripped — 'https://X.ai/en/' and
    'https://x.ai/en' are the same page. The query stays (it discriminates
    content)."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


async def page_reading_for_url(
    db: AsyncSession, project_id: UUID, url: str
) -> PageReading | None:
    """THE page-reading seat: the project's stored reading of this URL,
    None = never read. Tenant law: the project scopes the read (the loop's
    dispatch already guarantees a project-scoped turn)."""
    stmt = select(PageReading).where(
        PageReading.project_id == project_id,
        PageReading.url == normalize_page_url(url),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def upsert_page_reading(
    db: AsyncSession, project_id: UUID, url: str, text: str
) -> None:
    """The write seat's core (upsert — the latest snapshot replaces). The
    caller owns the session: the pipeline passes its process_asset session,
    the chat path goes through ``write_page_reading`` instead."""
    key = normalize_page_url(url)
    row = await db.get(PageReading, (project_id, key))
    if row is None:
        db.add(PageReading(project_id=project_id, url=key, text=text))
    else:
        row.text = text
        row.fetched_at = datetime.now(UTC)
    await db.flush()


async def write_page_reading(project_id: UUID, url: str, text: str) -> None:
    """The chat read tool's write-through path — its OWN short session, so
    the turn's transaction stays read-only. A failed memo write never
    breaks the read that produced it (best-effort: log and move on)."""
    try:
        async with AsyncSessionLocal() as db:
            await upsert_page_reading(db, project_id, url, text)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — the memo is best-effort
        logger.warning("page_reading_write_failed", url=url, error=str(exc))

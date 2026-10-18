"""Asset creation helpers for non-route callers.

The upload routes own the client-driven creation path; this module is the
seat for server-originated assets — chat-declared source text promoted to a
first-class transcript asset, and user-named URLs promoted to WEB_PAGE
assets (the capture half of the "URL → asset" recipe).
"""

import hashlib
import re
from urllib.parse import urlparse
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, now_utc
from app.providers.storage import get_upload_path, save

logger = structlog.get_logger()


def _material_title(text: str) -> str:
    """Derive a human title from the pasted text: first non-empty line,
    truncated. Never the fake "prompt.txt" of the retired composer shim."""
    first_line = next(
        (line.strip() for line in text.splitlines() if line.strip()), ""
    )
    return (first_line[:40] + "…") if len(first_line) > 40 else (first_line or "transcript")


def asset_text_content(asset: Asset) -> str:
    """The asset's text content — ONE seat (ADR-113 §1): ``transcript`` (ASR
    yield) before ``extracted_text`` (extraction/paste yield). Every reader
    (processing chain / prompt assembly / display derivation) funnels
    through here; the two opposite fallback orders that grew across the
    codebase are retired."""
    return (asset.transcript or asset.extracted_text) or ""


async def create_transcript_asset_from_text(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    text: str,
) -> Asset:
    """Persist user-declared material text as a TRANSCRIPT asset.

    The bytes land in object storage like any upload (the key passes the same
    project+user prefix check), and ``extracted_text`` is set directly with
    status COMPLETED — the text is already here, so there is nothing for the
    worker to extract. Flush-only: the caller commits with its turn.
    """
    key = await get_upload_path(project_id, user_id, "transcript.txt")
    payload = text.encode("utf-8")
    await save(key, payload, content_type="text/plain")
    asset = Asset(
        user_id=user_id,
        project_id=project_id,
        type=AssetType.TRANSCRIPT,
        file_url=key,
        title=_material_title(text),
        extracted_text=text,
        processing_status=AssetStatus.COMPLETED,
        # Stamped at creation (this path bypasses the worker): the content-
        # addressing key the understanding digest builds on (期 1 前移).
        meta={"content_sha256": hashlib.sha256(payload).hexdigest()},
    )
    db.add(asset)
    # 上传即落图 (ADR-057 K2): the chat-declared transcript gets its asset
    # node in the same flush — the graph's asset family stays complete
    # regardless of which door the asset row came through.
    from app.pipeline.graph_fill import stamp_asset_node  # deferred: import cycle

    await stamp_asset_node(db, project_id, asset)
    await db.flush()
    return asset


def _url_title(url: str) -> str:
    """The birth title derived from the URL itself (host + path, truncated)
    — the page's own title lands in ``meta.research.title`` only after
    capture, and the birth title never retro-mutates (a stable label beats
    a stale card)."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path if parsed.path not in ("", "/") else ""
    base = host + path
    return (base[:60] + "…") if len(base) > 60 else (base or url[:60])


async def create_web_page_asset_from_url(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    url: str,
) -> Asset:
    """Persist a user-named URL as a WEB_PAGE asset (网页采集资产化).

    Same seat as :func:`create_transcript_asset_from_text` — but where the
    transcript's content is already in hand (born COMPLETED), capture is
    heavy (fetch + headless Chrome) and rides the queue: born PENDING with
    ``processing_requested_at`` stamped (the explicit URL IS the read
    request — 无休眠), so the worker's claim loop picks it up. No bytes
    exist at birth: ``file_url`` stays None; the screenshot lands in
    ``meta.screenshot_key`` at processing.

    The static SSRF gate runs at birth (CaptureBlocked propagates — an
    obviously-internal URL is refused at creation, not at processing); DNS
    and browser-level checks run in the capture chain.
    """
    from app.tools.research.capture import check_url_policy  # deferred: tool seam

    check_url_policy(url)
    asset = Asset(
        user_id=user_id,
        project_id=project_id,
        type=AssetType.WEB_PAGE,
        file_url=None,
        title=_url_title(url),
        processing_status=AssetStatus.PENDING,
        processing_requested_at=now_utc(),
        meta={"capture_url": url},
    )
    db.add(asset)
    # 上传即落图 (ADR-057 K2) — same flush, same wiring door as the
    # transcript promotion.
    from app.pipeline.graph_fill import stamp_asset_node  # deferred: import cycle

    await stamp_asset_node(db, project_id, asset)
    await db.flush()
    return asset


async def create_web_page_assets_from_urls(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    urls: list[str],
) -> list[Asset]:
    """Explicit multi-URL entry: N URLs → N assets through the singular
    seat (同一 processor 循环, 零新机制). Sub-page auto-discovery (ADR-121
    B4) births through this same seat too — from the processing chain
    (``asset_processing._spawn_discovered_pages``), never from chat."""
    return [
        await create_web_page_asset_from_url(db, project_id, user_id, url)
        for url in urls
    ]


async def create_web_page_assets_committed_from_urls(
    project_id: UUID,
    user_id: UUID,
    urls: list[str],
) -> list[UUID]:
    """Commit user-named URL assets in their OWN transaction and return the
    newborn ids (existing captures dedupe to no id).

    The dock-seat storyboard waits for the capture inside the same chat
    turn. A flush-only row is invisible to both the worker and the settle
    poll until the turn commits — waiting on it would deadlock the dock.
    This seat commits just the asset (+ its canvas node, through the
    singular creation seat) so the queue can claim it while the chat
    transaction stays open; the caller then re-reads the committed row
    through its own session.
    """
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    wanted = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not wanted:
        return []
    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.execute(
                    select(Asset).where(
                        Asset.project_id == project_id,
                        Asset.type == AssetType.WEB_PAGE,
                    )
                )
            )
            .scalars()
            .all()
        )
        known: dict[str, list[Asset]] = {}
        for a in rows:
            url = (a.meta or {}).get("capture_url")
            if url:
                known.setdefault(url, []).append(a)
        created: list[UUID] = []
        for url in wanted:
            siblings = known.pop(url, [])
            if any(a.processing_status != AssetStatus.FAILED for a in siblings):
                continue  # live or captured — the URL is genuinely known
            if siblings:
                # A FAILED capture is NOT "known": re-sending the link is the
                # documented recovery ("re-send the link to re-capture"), so
                # re-arm the dead row through the ONE reset seat (status +
                # counter + error move together — a status-only flip would
                # re-fail terminally on the next tick) instead of birthing a
                # duplicate row.
                from app.pipeline.jobs import reset_asset_processing

                for a in siblings:
                    reset_asset_processing(a)
                created.extend(UUID(str(a.id)) for a in siblings)
                continue
            asset = await create_web_page_asset_from_url(
                session, project_id, user_id, url
            )
            created.append(UUID(str(asset.id)))
        await session.commit()
    return created


# Direction-turn capture priming (2026-10-17 用户拍板): the website-film
# direction beat lawfully ends in a bare reply — NO tool seat runs, so the
# model's material_urls declaration may never happen and the capture would
# start cold at the design beat (the 2026-10-17 f5743045 incident: 151s of
# the design budget burned on waiting). The plan path IS the production
# planning phase, so a URL the user's own message carries there is the
# work's subject: birth its capture asset at turn assembly and the capture
# runs in the background through the direction conversation. The extraction
# is mechanical; the read tool's 「discussion link is not material」 law is
# untouched (it governs what get_web_page's READ implies, not what the plan
# path primes).
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"'】」)\]]+")
# Sentence punctuation that trails a pasted link is never part of it.
_URL_TRAILING_STRIP = "\"'<>)]}.,;:!?…。，、；：！？"


def urls_in_text(text: str) -> list[str]:
    """The message's URLs — order-kept, deduped, trailing punctuation
    stripped. Pure (the priming seat's one testable half)."""
    urls: list[str] = []
    for raw in _URL_IN_TEXT_RE.findall(text or ""):
        url = raw.rstrip(_URL_TRAILING_STRIP)
        if url and url not in urls:
            urls.append(url)
    return urls


async def prime_web_page_captures_from_text(
    project_id: UUID,
    user_id: UUID,
    text: str,
) -> list[UUID]:
    """Birth committed WEB_PAGE capture assets for the message's URLs (the
    direction-turn priming seat above). Idempotent per capture_url through
    the singular creation seat; best-effort per URL — a policy-blocked link
    logs and skips here (the point-of-use absorb speaks the refusal when
    the URL is actually used). Returns the newborn ids."""
    from app.tools.research.capture import CaptureBlocked  # deferred: tool seam

    created: list[UUID] = []
    for url in urls_in_text(text):
        try:
            created.extend(
                await create_web_page_assets_committed_from_urls(
                    project_id, user_id, [url]
                )
            )
        except CaptureBlocked as e:
            logger.info("web_capture_prime_blocked", url=url, error=str(e))
    return created

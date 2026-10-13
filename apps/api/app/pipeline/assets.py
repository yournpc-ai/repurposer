"""Asset creation helpers for non-route callers.

The upload routes own the client-driven creation path; this module is the
seat for server-originated assets — chat-declared source text promoted to a
first-class transcript asset, and user-named URLs promoted to WEB_PAGE
assets (the capture half of the "URL → asset" recipe).
"""

import hashlib
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, now_utc
from app.providers.storage import get_upload_path, save


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
    seat (同一 processor 循环, 零新机制). Auto-discovery (pulling links off
    a root page) is deliberately NOT here — 需求池."""
    return [
        await create_web_page_asset_from_url(db, project_id, user_id, url)
        for url in urls
    ]

"""Asset creation helpers for non-route callers.

The upload routes own the client-driven creation path; this module is the
seat for server-originated assets — today: chat-declared source text promoted
to a first-class transcript asset (the groundwork for the synthetic-talk
line, ``docs/tasks/synthetic-talk-video.md``: a transcript the pipeline can
pair with photos later).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset
from app.providers.storage import get_upload_path, save


def _material_title(text: str) -> str:
    """Derive a human title from the pasted text: first non-empty line,
    truncated. Never the fake "prompt.txt" of the retired composer shim."""
    first_line = next(
        (line.strip() for line in text.splitlines() if line.strip()), ""
    )
    return (first_line[:40] + "…") if len(first_line) > 40 else (first_line or "transcript")


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
    await save(key, text.encode("utf-8"), content_type="text/plain")
    asset = Asset(
        user_id=user_id,
        project_id=project_id,
        type=AssetType.TRANSCRIPT,
        file_url=key,
        title=_material_title(text),
        extracted_text=text,
        processing_status=AssetStatus.COMPLETED,
    )
    db.add(asset)
    await db.flush()
    return asset

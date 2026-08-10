"""Runner-side assembly and misc shared by node runners (ADR-039 P1 split).

Context assembly (``_generation_context``), multimodal input collection,
asset listing/digest, and the small shared vocabulary (``KNOWN_OUTPUTS``).
The harness-side assembly layer (``agents/contexts.py``) lands in P3 and may
absorb part of this module.
"""

import hashlib
import mimetypes
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import MAX_CHARS_PER_TEXT
from app.models.schemas import (
    AssetType,
    GenerationContext,
    MediaInput,
    ToneSettings,
)
from app.models.tables import Asset, Persona, Project, WorkflowRun
from app.platform.project_context import persona_context_from_row
from app.tools.storage import download_to_temp, file_to_data_url

KNOWN_OUTPUTS = ("clips", "post", "quotes", "article", "carousel")

# Media snippets above these thresholds are not sent directly to the multimodal
# model; we rely on ASR transcripts / extracted text instead. These limits are
# generous (10 min / 200 MB) because the agent layer now falls back to text-only
# automatically when a provider rejects or fails to process a media input, so
# the user still gets results from the transcript even for large files.
_MAX_DIRECT_VIDEO_SECONDS = 600  # 10 minutes
_MAX_DIRECT_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB


def _truncate(value: str | None, max_len: int) -> str | None:
    """Truncate a string to fit a SQL column, returning None for empty values."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


def _count_words(value: object) -> int:
    """Whitespace token count over every string in a payload (display-only)."""
    if isinstance(value, str):
        return len(value.split())
    if isinstance(value, dict):
        return sum(_count_words(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_words(v) for v in value)
    return 0


async def _list_assets(db: AsyncSession, project_id: UUID) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    return list(result.scalars().all())


def _generation_context(
    run: WorkflowRun,
    project: Project,
    persona: Persona | None,
    *,
    brand_music_id: str | None = None,
) -> GenerationContext:
    """Assemble the GenerationContext from the run's task book (context)."""
    ctx = run.context or {}
    tone_raw = ctx.get("tone_settings")
    return GenerationContext(
        persona=persona_context_from_row(persona),
        event_name=project.event_name,
        tone_settings=ToneSettings.model_validate(tone_raw) if tone_raw else None,
        target_language=ctx.get("target_language", "en"),
        instruction=ctx.get("instruction"),
        brand_music_id=brand_music_id,
    )


def _source_language(project: Project, assets: list[Asset]) -> str:
    """Language tag for the understanding row: the source material's language."""
    for asset in assets:
        lang = (asset.meta or {}).get("language")
        if lang:
            return str(lang)
    return project.language or "en"


def _asset_digest(asset_texts: list[str], assets: list[Asset]) -> str:
    """Content hash of the understanding's exact inputs.

    Texts are trimmed to the same window the prompt sees (a change beyond the
    trim window does not alter the LLM input, so it must not invalidate).
    Media identity = file_url (unique storage path per upload); ``words`` meta
    is not an understanding input and stays out of the hash.
    """
    h = hashlib.sha256()
    for text in asset_texts:
        if text and text.strip():
            h.update(text[:MAX_CHARS_PER_TEXT].encode("utf-8"))
            h.update(b"\x00")
    for asset in sorted(assets, key=lambda a: str(a.id)):
        descriptor = (
            f"{asset.id}|{asset.type}|{asset.file_url}|{len(asset.slide_pages or [])}"
        )
        h.update(descriptor.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _file_size_bytes(path: Path | None) -> int | None:
    """Return file size in bytes, or None if path is missing/unreadable."""
    if path is None or not path.is_file():
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


async def _media_input_for_image(file_url: str, caption: str | None = None):
    """Build a MediaInput for an image file URL, or None if unreadable."""
    path = await download_to_temp(file_url)
    if path is None:
        return None
    try:
        data_url = file_to_data_url(path)
        if data_url is None:
            return None
        from app.models.schemas import MediaInputType

        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "image/png"
        return MediaInput(
            type=MediaInputType.IMAGE,
            mime=mime,
            data_url=data_url,
            caption=caption,
        )
    finally:
        path.unlink(missing_ok=True)


async def _media_input_for_video(asset: Asset):
    """Build a MediaInput for a short video, or None if it exceeds safe limits."""
    if asset.type != AssetType.VIDEO or not asset.file_url:
        return None
    duration = asset.duration_seconds or 0
    if duration > _MAX_DIRECT_VIDEO_SECONDS:
        return None

    path = await download_to_temp(asset.file_url)
    if path is None:
        return None
    try:
        size = _file_size_bytes(path)
        if size is None or size > _MAX_DIRECT_VIDEO_BYTES:
            return None
        data_url = file_to_data_url(path)
        if data_url is None:
            return None
        from app.models.schemas import MediaInputType

        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "video/mp4"
        return MediaInput(
            type=MediaInputType.VIDEO,
            mime=mime,
            data_url=data_url,
            caption="A short video clip from the talk. Use it together with the transcript.",
        )
    finally:
        path.unlink(missing_ok=True)


async def collect_asset_media(assets: list[Asset]) -> list[MediaInput]:
    """Collect multimodal inputs from image/slide/video assets.

    Returns a list of MediaInput objects. AUDIO is intentionally omitted because
    MiniMax M3's audio input support is undocumented; speech stays on the ASR
    transcript path.
    """
    inputs: list[MediaInput] = []
    for asset in assets:
        if asset.type == AssetType.IMAGE and asset.file_url:
            item = await _media_input_for_image(str(asset.file_url))
            if item:
                inputs.append(item)
        elif asset.type == AssetType.SLIDES and asset.slide_pages:
            for idx, page_path in enumerate(asset.slide_pages, start=1):
                item = await _media_input_for_image(
                    str(page_path),
                    caption=f"Slide {idx} from the talk deck.",
                )
                if item:
                    inputs.append(item)
        elif asset.type == AssetType.VIDEO:
            item = await _media_input_for_video(asset)
            if item:
                inputs.append(item)
    return inputs

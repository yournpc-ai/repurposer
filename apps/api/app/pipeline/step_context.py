"""Runner-side mechanical helpers shared by node runners (ADR-039 P1 split).

Multimodal input collection, asset listing/digest, misc row helpers. Context
ASSEMBLY lives in the harness layer (``agents/contexts.py``:
``_generation_context`` there, the chat intent context there too); this
module keeps the media/digest mechanics. The output-type vocabulary lives on
the node classes (``pipeline/graph.py``, N-32).
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
    MediaInput,
)
from app.models.tables import Asset, Output, Persona, Project
from app.tools.storage import download_to_temp, file_to_data_url

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

    The ``understanding_v2`` salt invalidates pre-alternate payloads: the
    KeyArgument display renderings (text_en/text_zh, 2026-08-12) change the
    prompt's requested output, so a v1 cache row must regenerate once.
    """
    h = hashlib.sha256()
    h.update(b"understanding_v2\x00")
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


async def _estimate_facts(db: AsyncSession, project: Project) -> dict:
    """Compile-time quotation facts (P4, N-34), assembled once per create_run.

    Counts and lengths only — no media downloads, no payload reads beyond the
    clip rows' duration/caption text. Each node's ``estimate(ctx)`` picks what
    it needs; ``spec`` and ``input_kinds`` ride per node at the call site.
    """
    assets = await _list_assets(db, project.id)
    texts = [t for a in assets if (t := (a.extracted_text or a.transcript))]
    # Mirrors collect_asset_media's feed surface (no downloads): images with a
    # file, one item per slide page, videos within the direct-feed duration.
    media_count = sum(
        1
        for a in assets
        if (a.type == AssetType.IMAGE and a.file_url)
        or (
            a.type == AssetType.VIDEO
            and a.file_url
            and (a.duration_seconds or 0) <= _MAX_DIRECT_VIDEO_SECONDS
        )
    ) + sum(len(a.slide_pages or []) for a in assets if a.type == AssetType.SLIDES)

    persona = await db.get(Persona, project.persona_id) if project.persona_id else None
    # The dub chain reuses a bound voice_id; anything else pays one clone
    # (worst case — a cached sample.meta.voice_id would make the actual 0).
    voice_id = ((persona.voice or {}).get("voice_id")) if persona else None

    clip_rows = list(
        (
            await db.execute(
                select(Output).where(
                    Output.project_id == project.id,
                    Output.type == "clip",
                    Output.render_spec.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    clips: list[dict] = []
    output_seconds: dict[str, float] = {}
    for row in clip_rows:
        seconds = float((row.payload or {}).get("duration") or 30)
        caption_chars = sum(
            len(str(cue.get("text") or ""))
            for cue in ((row.render_spec or {}).get("caption_track") or [])
        )
        clips.append({"seconds": seconds, "caption_chars": caption_chars})
        output_seconds[str(row.id)] = seconds

    return {
        "text_chars": sum(len(t) for t in texts),
        "text_count": len(texts),
        "media_count": media_count,
        "persona_exists": persona is not None,
        "voice_clone_needed": not voice_id,
        "clips": clips,
        "output_seconds": output_seconds,
    }

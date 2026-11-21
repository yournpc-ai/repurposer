"""Multimodal source inputs and project asset facts for Chat and asset processing."""

import hashlib
import mimetypes
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    AssetType,
    MediaInput,
)
from app.models.tables import Asset, Project
from app.providers.storage import download_to_temp, file_to_data_url

# Media snippets above these thresholds are not sent directly to the multimodal
# model; we rely on ASR transcripts / extracted text instead. These limits are
# generous (10 min / 200 MB) because the agent layer now falls back to text-only
# automatically when a provider rejects or fails to process a media input, so
# the user still gets results from the transcript even for large files.
_MAX_DIRECT_VIDEO_SECONDS = 600  # 10 minutes
_MAX_DIRECT_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB


async def list_assets(db: AsyncSession, project_id: UUID) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.project_id == project_id))
    return list(result.scalars().all())


def _source_language(project: Project, assets: list[Asset]) -> str:
    """Language tag for the understanding row: the source material's language."""
    for asset in assets:
        lang = (asset.meta or {}).get("language")
        if lang:
            return str(lang)
    return project.language or "en"


def asset_digest(assets: list[Asset]) -> str:
    """Content-addressed digest of the understanding's material set (v3).

    Each asset contributes ``type|content_sha256`` (stamped by the first
    processor / at creation for pasted text), so the same bytes re-uploaded
    to another of the user's projects produce the same digest and reuse the
    existing understanding with zero LLM (期 1 素材理解前移). The derived
    texts are NOT hashed separately: they are deterministic functions of the
    same bytes, and hashing them would reintroduce upload-identity
    sensitivity through ASR nondeterminism. (Trade-off, accepted: an ASR
    model upgrade does not invalidate content-addressed rows — the salt
    bumps when the understand CONTRACT changes.)

    Assets without a content hash (legacy rows, failed processing) fall back
    to the per-upload ``id|file_url`` identity — same-project reuse only,
    never cross-project. Descriptors self-sort (content hashes are
    order-stable; asset ids are not).
    """
    h = hashlib.sha256()
    h.update(b"understanding_v3\x00")
    descriptors = []
    for asset in assets:
        content = (asset.meta or {}).get("content_sha256")
        identity = f"content:{content}" if content else f"upload:{asset.id}|{asset.file_url}"
        descriptors.append(f"{asset.type}|{identity}")
    for descriptor in sorted(descriptors):
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


async def media_input_for_image(
    file_url: str,
    caption: str | None = None,
    max_px: int | None = None,
):
    """Build a MediaInput for an image file URL / storage key, or None if
    unreadable. Public seam: any node whose agent sees imagery (slides, stills,
    web-page screenshots) builds its inputs here — one download + data-URL
    discipline, never re-rolled per caller.

    ``max_px`` (the read-tools' budget form, film 读取座): bound the LONG
    edge and re-encode as JPEG — a model reading a view for a creative
    judgment needs a legible thumbnail, not the full 1440px capture. None =
    the caller's bytes ride unchanged (the director's fold shots)."""
    path = await download_to_temp(file_url)
    if path is None:
        return None
    try:
        if max_px is not None:
            data_url = _resized_data_url(path, max_px)
            mime = "image/jpeg"
        else:
            data_url = file_to_data_url(path)
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
        if data_url is None:
            return None
        from app.models.schemas import MediaInputType

        return MediaInput(
            type=MediaInputType.IMAGE,
            mime=mime,
            data_url=data_url,
            caption=caption,
        )
    finally:
        path.unlink(missing_ok=True)


def _resized_data_url(path: Path, max_px: int) -> str | None:
    """Decode → long-edge-bound thumbnail → JPEG data URL (None when the
    bytes don't decode — the caller reports an unreadable view, never a
    silent drop)."""
    import base64
    import io

    try:
        from PIL import Image

        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_px, max_px), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
    except Exception:  # noqa: BLE001 — decode/encode failure = unreadable
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


async def media_input_for_video_source(
    file_url: str, *, duration_seconds: float, caption: str | None = None,
):
    """Build a bounded video observation for an Asset or frozen SourceSnapshot."""
    if duration_seconds > _MAX_DIRECT_VIDEO_SECONDS:
        return None

    path = await download_to_temp(file_url)
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
            caption=caption,
        )
    finally:
        path.unlink(missing_ok=True)


async def _media_input_for_video(asset: Asset):
    """Build a MediaInput for a short video, or None if it exceeds safe limits."""
    if asset.type != AssetType.VIDEO or not asset.file_url:
        return None
    return await media_input_for_video_source(
        str(asset.file_url),
        duration_seconds=asset.duration_seconds or 0,
        caption="A short video clip from the talk. Use it together with the transcript.",
    )


async def collect_asset_media(assets: list[Asset]) -> list[MediaInput]:
    """Collect multimodal inputs from image/slide/video assets.

    Returns a list of MediaInput objects. AUDIO is intentionally omitted because
    MiniMax M3's audio input support is undocumented; speech stays on the ASR
    transcript path.
    """
    inputs: list[MediaInput] = []
    for asset in assets:
        if asset.type == AssetType.IMAGE and asset.file_url:
            item = await media_input_for_image(str(asset.file_url))
            if item:
                inputs.append(item)
        elif asset.type == AssetType.SLIDES and asset.slide_pages:
            for idx, page_path in enumerate(asset.slide_pages, start=1):
                item = await media_input_for_image(
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

"""MiniMax music generation + on-disk persistence.

The native ``/v1/music_generation`` call (see ``clients/minimax.py``) returns a
short-lived audio URL. This service generates a piece, downloads the bytes
immediately, persists them under ``assets/music/{music_id}.{ext}``, and returns
the bytes + duration + provenance so ``services/music`` can create the DB row.

Bytes never live in the DB (ADR-011 local FS). The file path stored on the
``Music`` row is relative to ``settings.asset_dir``.
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
import structlog

from app.clients.minimax import MiniMaxError, minimax_client
from app.config import settings

logger = structlog.get_logger()

# Quality model for committed platform defaults; free model for ad-hoc user
# generation to control cost (see docs/MUSIC_ARCHITECTURE.md).
DEFAULTS_MODEL = "music-2.6"
USER_MODEL = "music-2.6-free"
AUDIO_EXT = "mp3"


@dataclass(frozen=True)
class GeneratedMusic:
    """A generated music piece ready to persist."""

    audio_bytes: bytes
    ext: str
    duration_seconds: int | None
    size_bytes: int
    model: str
    generation_id: str | None


async def generate_music(
    prompt: str,
    *,
    model: str = USER_MODEL,
    is_instrumental: bool = True,
) -> GeneratedMusic:
    """Generate a music piece via MiniMax and download the bytes.

    Raises ``MiniMaxError`` on any API/download failure.
    """
    result = await minimax_client.generate_music(
        prompt,
        model=model,
        is_instrumental=is_instrumental,
        output_format="url",
        audio_format=AUDIO_EXT,
    )
    if not result.audio_url:
        raise MiniMaxError("MiniMax music generation returned no audio URL")

    async with httpx.AsyncClient(timeout=120) as client:
        dl = await client.get(result.audio_url)
        dl.raise_for_status()
        audio_bytes = dl.content

    duration_seconds = (
        int(result.duration_ms // 1000) if result.duration_ms is not None else None
    )
    size = result.size_bytes if result.size_bytes else len(audio_bytes)
    logger.info(
        "music_generated",
        model=model,
        duration_seconds=duration_seconds,
        size_bytes=size,
        generation_id=result.generation_id,
    )
    return GeneratedMusic(
        audio_bytes=audio_bytes,
        ext=AUDIO_EXT,
        duration_seconds=duration_seconds,
        size_bytes=size,
        model=model,
        generation_id=result.generation_id,
    )


def music_file_path(music_id: UUID) -> str:
    """Return the stored file_path (relative to asset_dir) for a music piece."""
    return f"music/{music_id}.{AUDIO_EXT}"


def music_disk_path(music_id: UUID) -> Path:
    """Return the absolute on-disk path for a music piece's audio file."""
    return settings.asset_dir / music_file_path(music_id)


def persist_music(music_id: UUID, generated: GeneratedMusic) -> tuple[str, int]:
    """Write generated audio bytes to disk and return (relative file_path, size).

    Creates ``assets/music/`` if needed. ``file_path`` is relative to
    ``asset_dir`` so it can be stored on the ``Music`` row and served via the
    storage seam.
    """
    path = music_disk_path(music_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(generated.audio_bytes)
    return music_file_path(music_id), len(generated.audio_bytes)

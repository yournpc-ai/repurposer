"""Music object-storage mechanics (ADR-039 P1: pure mechanical, no provider).

The generated piece's bytes are persisted under ``music/{music_id}.{ext}`` in
object storage; the ``Music`` row's ``file_path`` is that object key. The
MiniMax generation call itself lives one layer up in ``pipeline/music.py``
(tools/ may not import the LLM client, N-29).

Bytes never live in the DB.
"""

from dataclasses import dataclass
from uuid import UUID

from app.tools.storage import exists, save

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


def music_file_path(music_id: UUID) -> str:
    """Return the object storage key for a music piece's audio file."""
    return f"music/{music_id}.{AUDIO_EXT}"


async def persist_music(music_id: UUID, generated: GeneratedMusic) -> tuple[str, int]:
    """Upload generated audio bytes to object storage.

    Returns (object_key, size). The key is ``music/{music_id}.{ext}``.
    """
    key = music_file_path(music_id)
    await save(key, generated.audio_bytes, content_type="audio/mpeg")
    return key, len(generated.audio_bytes)


async def music_disk_path(music_id: UUID) -> bool:
    """Return whether the music object exists in storage.

    Kept as an async compatibility shim for code that used ``music_disk_path``
    to check file existence.
    """
    return await exists(music_file_path(music_id))

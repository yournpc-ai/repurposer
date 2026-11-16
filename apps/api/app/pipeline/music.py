"""Music library service: CRUD + generation + default-catalog seeding + in-use guard.

Audio bytes live in object storage under ``music/{music_id}.{ext}``; this layer
owns the DB rows, the MiniMax generation call (media generation via the Model
boundary is legal at the Graph layer — same class as the image calls in
``pipeline/images.py``), and the object-vs-row lifecycle. Deletion refuses a
piece still referenced by any clip's ``render_spec.music``.
"""

import hashlib
import io
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, TypedDict
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import av
import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.llm.base import LLMError
from app.providers.llm.minimax import minimax_client
from app.metering import record_media_usage
from app.models.tables import Music, Output
from app.providers.storage import delete, exists, read, save

logger = structlog.get_logger()

# ---- object-storage mechanics ----------------------------------------------
# The generated piece's bytes are persisted under ``music/{music_id}.{ext}``
# in object storage; the ``Music`` row's ``file_path`` is that object key.
# Bytes never live in the DB. (通用件随消费方，N-42 批④：音乐库消费侧即本层。)

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


@dataclass(frozen=True)
class CuratedMusicAudio:
    """Validated local audio bytes for a curated catalog piece."""

    audio_bytes: bytes
    ext: str
    duration_seconds: int
    size_bytes: int
    content_sha256: str


def probe_music_duration_seconds(data: bytes) -> int:
    """Decode real audio and return its duration using the Music integer contract."""
    container = av.open(io.BytesIO(data), mode="r")
    try:
        if not container.streams.audio:
            raise ValueError("music source has no audio stream")
        stream = container.streams.audio[0]
        if stream.duration is not None and stream.time_base is not None:
            duration = Fraction(stream.duration) * Fraction(stream.time_base)
        elif container.duration is not None:
            duration = Fraction(container.duration, av.time_base)
        else:
            raise ValueError("music source has no decodable duration")
        if duration < 1:
            raise ValueError("music source is shorter than one second")
        try:
            next(container.decode(audio=0))
        except StopIteration as e:
            raise ValueError("music source decoded to zero audio frames") from e
        return int(duration)
    finally:
        container.close()


def music_file_path(music_id: UUID) -> str:
    """Return the object storage key for a music piece's audio file."""
    return f"music/{music_id}.{AUDIO_EXT}"


async def persist_music(
    music_id: UUID, generated: GeneratedMusic | CuratedMusicAudio
) -> tuple[str, int]:
    """Upload generated or curated audio bytes to object storage.

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

# Quality model for ad-hoc user generation; platform catalog pieces are imported
# from curated local objects and never generated implicitly at startup.
USER_MODEL = "music-2.6-free"


async def generate_music(
    prompt: str,
    *,
    model: str = USER_MODEL,
    is_instrumental: bool = True,
) -> GeneratedMusic:
    """Generate a music piece via MiniMax and download the bytes.

    The native ``/v1/music_generation`` call (see ``providers/llm/minimax.py``)
    returns a short-lived audio URL, so the bytes are downloaded immediately.

    Raises ``LLMError`` on any API/download failure.
    """
    result = await minimax_client.generate_music(
        prompt,
        model=model,
        is_instrumental=is_instrumental,
        output_format="url",
        audio_format=AUDIO_EXT,
    )
    if not result.audio_url:
        raise LLMError("MiniMax music generation returned no audio URL")
    await record_media_usage({"music_pieces": 1.0})

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


class MusicInUseError(Exception):
    """Raised when deleting a music piece still referenced by clips."""

    def __init__(self, music_id: UUID, count: int) -> None:
        self.music_id = music_id
        self.count = count
        super().__init__(f"Music {music_id} is referenced by {count} clip(s)")


class CuratedMusicEntry(TypedDict):
    """Code-declared provenance for one local, non-generated library piece."""

    mood: str
    title: str
    author: str
    style: str
    reference_bpm: int
    original_filename: str
    source_url: str
    license: str
    attribution: str
    provenance: str


# These license strings apply to the music recordings, not Shotcraft source
# code. They transcribe the supplied attribution metadata; they are not an
# independent legal verification or approval claim.
CURATED_MUSIC_CATALOG: list[CuratedMusicEntry] = [
    {
        "mood": "mixkit-tech-house",
        "title": "Tech House",
        "author": "Unresolved",
        "style": "Tech House",
        "reference_bpm": 124,
        "original_filename": "bgm-tech-house.mp3",
        "source_url": "",
        "license": "Mixkit Stock Music Free License; commercial use requires recheck",
        "attribution": "Tech House — bundled by Shotcraft; artist/source recheck required",
        "provenance": "Shotcraft assets/audio/ATTRIBUTION.md",
    },
    {
        "mood": "mixkit-cat-walk",
        "title": "Cat Walk",
        "author": "Arulo",
        "style": "House",
        "reference_bpm": 129,
        "original_filename": "cat-walk.mp3",
        "source_url": "https://assets.mixkit.co/music/371/371.mp3",
        "license": "Mixkit Stock Music Free License",
        "attribution": "Cat Walk — Arulo (Mixkit)",
        "provenance": "Shotcraft assets/audio/ATTRIBUTION.md",
    },
    {
        "mood": "mixkit-g-eazy-nba-type",
        "title": "G Eazy NBA type",
        "author": "Arulo",
        "style": "Hip Hop",
        "reference_bpm": 86,
        "original_filename": "g-eazy-nba-type.mp3",
        "source_url": "https://assets.mixkit.co/music/403/403.mp3",
        "license": "Mixkit Stock Music Free License",
        "attribution": "G Eazy NBA type — Arulo (Mixkit)",
        "provenance": "Shotcraft assets/audio/ATTRIBUTION.md",
    },
    {
        "mood": "mixkit-house-vibez",
        "title": "House Vibez",
        "author": "Lily J",
        "style": "House",
        "reference_bpm": 123,
        "original_filename": "house-vibez.mp3",
        "source_url": "https://assets.mixkit.co/music/745/745.mp3",
        "license": "Mixkit Stock Music Free License",
        "attribution": "House Vibez — Lily J (Mixkit)",
        "provenance": "Shotcraft assets/audio/ATTRIBUTION.md",
    },
    {
        "mood": "mixkit-tonight-hiphop",
        "title": "Tonight",
        "author": "Michael Ramir C.",
        "style": "Hip Hop",
        "reference_bpm": 103,
        "original_filename": "tonight-hiphop.mp3",
        "source_url": "https://assets.mixkit.co/music/841/841.mp3",
        "license": "Mixkit Stock Music Free License",
        "attribution": "Tonight — Michael Ramir C. (Mixkit)",
        "provenance": "Shotcraft assets/audio/ATTRIBUTION.md",
    },
]


def default_music_id(mood: str) -> UUID:
    """Deterministic UUID for a default-catalog piece (stable across runs)."""
    return uuid5(NAMESPACE_DNS, f"repurposer:music:{mood}")


async def list_music(db: AsyncSession, user_id: UUID | None = None) -> list[Music]:
    """List public music pieces plus the caller's own private pieces."""
    where_clause = Music.is_public.is_(True)
    if user_id is not None:
        where_clause = or_(where_clause, Music.generated_by_user_id == user_id)
    result = await db.execute(
        select(Music).where(where_clause).order_by(Music.created_at.desc())
    )
    return list(result.scalars().all())


async def get_music(db: AsyncSession, music_id: UUID) -> Music | None:
    """Get a music piece by id."""
    return await db.get(Music, music_id)


async def get_music_by_mood(db: AsyncSession, mood: str) -> Music | None:
    """Get a music piece by its unique mood natural key."""
    result = await db.execute(select(Music).where(Music.mood == mood))
    return result.scalar_one_or_none()


async def resolve_bed_track(
    db: AsyncSession, project: Any, requested: str | None
) -> Music | None:
    """The new video chain's music-bed resolution (音频三态, VIDEO_PROJECT
    §15): an explicit ``off`` is terminal (never re-opened by a default);
    absent a choice the persona skin's ``musicId``/``musicMood`` leads, then
    the curated Tech House default. ``None`` = no bed.
    """
    if requested == "off":
        return None
    from app.memory.brand import resolve_music_ref  # deferred: memory edge
    from app.platform.project_context import resolve_persona  # deferred: cycle

    persona = await resolve_persona(db, project)  # None-safe
    brand_ref: Any = None
    if persona is not None:
        block = persona.brand or {}
        brand_ref = block.get("musicId") or block.get("musicMood")
    for ref in (brand_ref, "mixkit-tech-house"):
        if not ref:
            continue
        track = await resolve_music_ref(db, ref)
        if track is not None and (
            track.is_public or track.generated_by_user_id == project.user_id
        ):
            return track
    return None


async def create_music_from_generation(
    db: AsyncSession,
    *,
    prompt: str,
    generated: GeneratedMusic,
    mood: str | None = None,
    title: str | None = None,
    user_id: UUID | None = None,
    license: str | None = None,
    source_url: str | None = None,
    attribution: str | None = None,
    is_public: bool = True,
) -> Music:
    """Persist generated audio to object storage and create the DB row.

    ``mood`` is the unique natural key; when omitted a ``custom-<short>`` key is
    derived from the new id. A mood collision with an existing piece is
    suffixed to keep the column unique.
    """
    music_id = uuid4()
    base_mood = (mood or f"custom-{music_id.hex[:8]}").strip().lower()
    if await get_music_by_mood(db, base_mood) is not None:
        base_mood = f"{base_mood}-{music_id.hex[:4]}"
    title = title or _default_title(prompt, base_mood)

    file_path, size_bytes = await persist_music(music_id, generated)
    # 节拍网格 (ADR-121 B3): computed at birth from the bytes already in
    # hand — the film cut snap reads ``meta.beats``; None = degrade-honest
    # (no grid, no snap). Analysis failure never blocks the birth.
    from app.tools.music.beats import analyze_beat_grid  # deferred: import cycle

    meta: dict[str, Any] | None = None
    try:
        meta = analyze_beat_grid(generated.audio_bytes)
    except Exception as e:  # noqa: BLE001 — analysis is best-effort
        logger.warning("beat_grid_birth_failed", music_id=str(music_id), error=str(e))
    music = Music(
        id=music_id,
        mood=base_mood,
        title=title,
        ext=generated.ext,
        file_path=file_path,
        size_bytes=size_bytes,
        duration_seconds=generated.duration_seconds,
        prompt=prompt,
        model=generated.model,
        generation_id=generated.generation_id,
        license=license,
        source_url=source_url,
        attribution=attribution,
        is_public=is_public,
        generated_by_user_id=user_id,
        meta=meta,
    )
    db.add(music)
    await db.commit()
    await db.refresh(music)
    logger.info("music_created", music_id=str(music_id), mood=base_mood, user_id=str(user_id))
    return music


async def update_music_metadata(
    db: AsyncSession,
    music_id: UUID,
    *,
    title: str | None = None,
    license: str | None = None,
    source_url: str | None = None,
    attribution: str | None = None,
    is_public: bool | None = None,
) -> Music | None:
    """Update editable metadata fields; returns None if the piece doesn't exist."""
    music = await db.get(Music, music_id)
    if music is None:
        return None
    if title is not None:
        music.title = title
    if license is not None:
        music.license = license
    if source_url is not None:
        music.source_url = source_url
    if attribution is not None:
        music.attribution = attribution
    if is_public is not None:
        music.is_public = is_public
    await db.commit()
    await db.refresh(music)
    return music


async def is_music_in_use(db: AsyncSession, music_id: UUID) -> int:
    """Count clip outputs whose render_spec.music references this piece.

    Portable Python-side scan (works on both Postgres and the SQLite test DB).
    On Postgres this could be a single JSONB-containment query; the library is
    small enough that the scan is fine and keeps tests dialect-agnostic.
    """
    target = str(music_id)
    result = await db.execute(
        select(Output.render_spec).where(Output.render_spec.isnot(None))
    )
    count = 0
    for (spec,) in result.all():
        if not isinstance(spec, dict):
            continue
        music = spec.get("music")
        if not isinstance(music, dict):
            continue
        # New contract: music_id; legacy: track_id (both carry the piece id).
        if music.get("music_id") == target or music.get("track_id") == target:
            count += 1
    return count


async def delete_music(db: AsyncSession, music_id: UUID) -> Music | None:
    """Delete a music piece's DB row and object storage file.

    Raises ``MusicInUseError`` (→ 409) if any clip references it. Returns the
    deleted row (for response shaping) or None if the piece doesn't exist.
    """
    music = await db.get(Music, music_id)
    if music is None:
        return None
    in_use = await is_music_in_use(db, music_id)
    if in_use > 0:
        raise MusicInUseError(music_id, in_use)
    await delete(music.file_path)
    await db.delete(music)
    await db.commit()
    logger.info("music_deleted", music_id=str(music_id), mood=music.mood)
    return music


async def _reconcile_curated_music(db: AsyncSession) -> list[Music]:
    """Reconcile imported local objects into complete, non-generated Music rows."""
    from app.tools.music.beats import analyze_beat_grid  # deferred: import cycle

    created: list[Music] = []
    changed = False
    for entry in CURATED_MUSIC_CATALOG:
        mood = entry["mood"]
        row = await get_music_by_mood(db, mood)
        music_id = row.id if row is not None else default_music_id(mood)
        key = row.file_path if row is not None else music_file_path(music_id)
        if row is None:
            try:
                object_exists = await exists(key)
            except Exception as e:  # noqa: BLE001 — storage unreachable at startup
                logger.error("curated_music_check_failed", mood=mood, error=str(e))
                continue
            if not object_exists:
                logger.warning("curated_music_missing_object", mood=mood, key=key)
                continue

        meta = dict((row.meta or {}) if row is not None else {})
        expected_digest = meta.get("content_sha256")
        needs_bytes = (
            row is None
            or not expected_digest
            or row.duration_seconds is None
            or not row.size_bytes
            or not meta.get("beats")
        )
        data: bytes | None = None
        duration_seconds: int | None = None
        if needs_bytes:
            try:
                data = await read(key)
                actual_digest = hashlib.sha256(data).hexdigest()
                duration_seconds = probe_music_duration_seconds(data)
            except Exception as e:  # noqa: BLE001 — per-piece startup degradation
                logger.warning("curated_music_probe_failed", mood=mood, error=str(e))
                continue
            if expected_digest is not None and actual_digest != expected_digest:
                logger.error(
                    "curated_music_digest_mismatch",
                    mood=mood,
                    expected=expected_digest,
                    actual=actual_digest,
                )
                continue
            meta["content_sha256"] = actual_digest
            if not meta.get("beats"):
                try:
                    grid = analyze_beat_grid(data)
                except Exception as e:  # noqa: BLE001 — analysis is best-effort
                    logger.warning("curated_beat_grid_failed", mood=mood, error=str(e))
                else:
                    if grid is not None:
                        meta.update(grid)

        meta.update({
            "author": entry["author"],
            "style": entry["style"],
            "reference_bpm": entry["reference_bpm"],
            "original_filename": entry["original_filename"],
            "provenance": entry["provenance"],
        })
        if row is None:
            if data is None or duration_seconds is None:
                raise RuntimeError(f"curated music {mood} was not probed")
            row = Music(
                id=music_id,
                mood=mood,
                title=entry["title"],
                ext=AUDIO_EXT,
                file_path=key,
                size_bytes=len(data),
                duration_seconds=duration_seconds,
                prompt=None,
                model=None,
                generation_id=None,
                license=entry["license"],
                source_url=entry["source_url"],
                attribution=entry["attribution"],
                is_public=True,
                generated_by_user_id=None,
                meta=meta,
            )
            db.add(row)
            created.append(row)
            changed = True
            continue

        updates: dict[str, Any] = {
            "title": entry["title"],
            "ext": AUDIO_EXT,
            "prompt": None,
            "model": None,
            "generation_id": None,
            "license": entry["license"],
            "source_url": entry["source_url"],
            "attribution": entry["attribution"],
            "is_public": True,
            "generated_by_user_id": None,
            "meta": meta,
        }
        if data is not None:
            updates["size_bytes"] = len(data)
            updates["duration_seconds"] = duration_seconds
        for field, value in updates.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True

    if changed:
        await db.commit()
        for row in created:
            await db.refresh(row)
        logger.info("curated_music_reconciled", created=len(created))
    return created


async def _remove_generated_platform_defaults(db: AsyncSession) -> None:
    """Remove the old generated platform rows without touching user-owned music.

    A legacy Output may still name a platform row in its render spec. Preserve
    that historical reference but make the row private so it can never re-enter
    the candidate library; unreferenced rows and their objects are deleted.
    """
    rows = list((await db.scalars(
        select(Music).where(
            Music.generated_by_user_id.is_(None),
            Music.mood.in_(("calm", "uplifting", "corporate")),
        )
    )).all())
    for row in rows:
        try:
            await delete_music(db, row.id)
        except MusicInUseError:
            if row.is_public:
                row.is_public = False
                await db.commit()
            logger.info("legacy_platform_music_hidden_in_use", music_id=str(row.id))


async def seed_default_music(db: AsyncSession) -> list[Music]:
    """Reconcile the five curated platform tracks already imported to storage.

    Startup never calls a model or creates audio objects. Missing objects remain
    an explicit warning; the old generated platform defaults are removed without
    touching user-owned music or immutable SourceSnapshots used by saved works.
    """
    await _remove_generated_platform_defaults(db)
    return await _reconcile_curated_music(db)


def _default_title(prompt: str, mood: str) -> str:
    """Best-effort title for a generated piece from its prompt/mood."""
    stripped = prompt.strip().splitlines()[0] if prompt.strip() else mood
    return stripped[:80] if stripped else mood


__all__ = [
    "AUDIO_EXT",
    "CURATED_MUSIC_CATALOG",
    "CuratedMusicAudio",
    "CuratedMusicEntry",
    "MusicInUseError",
    "USER_MODEL",
    "create_music_from_generation",
    "default_music_id",
    "delete_music",
    "generate_music",
    "get_music",
    "get_music_by_mood",
    "is_music_in_use",
    "list_music",
    "probe_music_duration_seconds",
    "resolve_bed_track",
    "seed_default_music",
    "update_music_metadata",
]

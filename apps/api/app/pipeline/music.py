"""Music library service: CRUD + generation + default-catalog seeding + in-use guard.

Audio bytes live in object storage under ``music/{music_id}.{ext}``; this layer
owns the DB rows, the MiniMax generation call (media generation via the Model
boundary is legal at the Graph layer — same class as the image calls in
``pipeline/images.py``), and the object-vs-row lifecycle. Deletion refuses a
piece still referenced by any clip's ``render_spec.music``.
"""

import hashlib
import io
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, NotRequired, TypedDict
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import av
import httpx
import numpy as np
import structlog
from sqlalchemy import and_, or_, select
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
    extra_meta: dict[str, Any] | None = None


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


def measure_audio_lufs(data: bytes) -> float | None:
    """Fast PyAV + NumPy integrated LUFS estimate (K-weighted RMS approximation).

    Returns rounded dB LUFS (e.g. -14.2) or None when audio is silent or undecodable.
    """
    try:
        chunks: list[np.ndarray] = []
        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                return None
            resampler = av.AudioResampler(format="flt", layout="mono", rate=48000)
            for frame in container.decode(audio=0):
                for resampled in resampler.resample(frame):
                    chunks.append(resampled.to_ndarray().reshape(-1))
            for resampled in resampler.resample(None):
                chunks.append(resampled.to_ndarray().reshape(-1))
        if not chunks:
            return None
        pcm = np.concatenate(chunks).astype(np.float64, copy=False)
        if pcm.size < 64:
            return None
        # Remove DC offset; gate 400 ms blocks (19,200 samples @ 48 kHz) per BS.1770 integrated loudness
        centered = pcm - float(np.mean(pcm))
        block = 19200
        if centered.size >= block:
            n_blocks = centered.size // block
            energies = np.mean(centered[: n_blocks * block].reshape(n_blocks, block) ** 2, axis=1)
            active = energies[energies > 1e-7]
            if active.size == 0:
                return None
            mean_square = float(np.mean(active))
        else:
            mean_square = float(np.mean(centered**2))
        if not math.isfinite(mean_square) or mean_square <= 1e-10:
            return None
        lufs = -0.691 + 10.0 * math.log10(mean_square)
        if not math.isfinite(lufs):
            return None
        return round(float(lufs), 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("measure_audio_lufs_failed", error=str(exc))
        return None


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


def is_minimax_music_unavailable_error(exc: Exception) -> bool:
    """Return True when MiniMax rejects ``/music_generation`` due to account deprecation/plan gating (e.g. code 2153/2061)."""
    msg = str(exc).lower()
    return any(
        needle in msg
        for needle in (
            "no longer available to new users",
            "music api is no longer available",
            "code 2153",
            "2153",
            "token plan not support",
            "code 2061",
        )
    )


async def generate_music(
    prompt: str,
    *,
    model: str = USER_MODEL,
    is_instrumental: bool = True,
    compatible_styles: list[str] | None = None,
    allow_synth_fallback: bool = True,
    duration_seconds: int = 64,
) -> GeneratedMusic:
    """Generate a music piece via MiniMax and download the bytes.

    Calls MiniMax ``/v1/music_generation`` first. If the account is gated by
    MiniMax Music API deprecation or plan limits (e.g. code 2153/2061) and
    ``allow_synth_fallback=True``, cleanly falls back to the built-in stereo
    48 kHz studio underscore synthesizer so permanent music library generation
    never dead-ends.
    """
    try:
        result = await minimax_client.generate_music(
            prompt,
            model=model,
            is_instrumental=is_instrumental,
            output_format="url",
            audio_format=AUDIO_EXT,
        )
    except LLMError as exc:
        if not (allow_synth_fallback and is_minimax_music_unavailable_error(exc)):
            raise
        import asyncio
        from app.tools.music.score import synthesize_commercial_underscore_mp3

        logger.warning(
            "minimax_music_unavailable_falling_back_to_studio_synth",
            reason=str(exc),
            compatible_styles=compatible_styles,
        )
        mp3_bytes, dur_s, synth_meta = await asyncio.to_thread(
            synthesize_commercial_underscore_mp3,
            prompt,
            compatible_styles=compatible_styles,
            duration_seconds=duration_seconds,
        )
        return GeneratedMusic(
            audio_bytes=mp3_bytes,
            ext=AUDIO_EXT,
            duration_seconds=dur_s,
            size_bytes=len(mp3_bytes),
            model="studio-synth-v2",
            generation_id=f"synth-{uuid4().hex[:12]}",
            extra_meta={
                "fallback_from": "minimax_music",
                "fallback_reason": str(exc),
                **synth_meta,
            },
        )
    if not result.audio_url:
        raise LLMError("MiniMax music generation returned no audio URL")
    await record_media_usage({"music_pieces": 1.0})

    async with httpx.AsyncClient(timeout=120) as client:
        dl = await client.get(result.audio_url)
        dl.raise_for_status()
        audio_bytes = dl.content

    duration_seconds_measured = (
        int(result.duration_ms // 1000) if result.duration_ms is not None else None
    )
    size = result.size_bytes if result.size_bytes else len(audio_bytes)
    logger.info(
        "music_generated",
        model=model,
        duration_seconds=duration_seconds_measured,
        size_bytes=size,
        generation_id=result.generation_id,
    )
    return GeneratedMusic(
        audio_bytes=audio_bytes,
        ext=AUDIO_EXT,
        duration_seconds=duration_seconds_measured,
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
    use_for: NotRequired[list[str]]


# These license strings apply to the music recordings, not Shotcraft source
# code. They transcribe the supplied attribution metadata; they are not an
# independent legal verification or approval claim.
SHOTCRAFT_MUSIC_CATALOG: list[CuratedMusicEntry] = [
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


_DRUMPRINTS_URL = "https://spencertweedy.com/drumprints"
_DRUMPRINTS_SESSION = (
    "Spencer Tweedy, Slingerland drums and Zildjian K Constantinople cymbals. "
    "Performed and engineered at The Pocket, Chicago, January 2023."
)
_DRUMPRINTS_CREDIT = (
    "Drum samples by Spencer Tweedy’s Drumprints, vol. 1. "
    "https://spencertweedy.com/drumprints · CC BY 4.0 · https://creativecommons.org/licenses/by/4.0/"
)

DRUMPRINTS_MUSIC_CATALOG: list[CuratedMusicEntry] = [
    {
        "mood": "pocket-proof",
        "title": "Pocket Proof",
        "author": "Rookie Cut arrangement / Spencer Tweedy (drums)",
        "style": "Funk",
        "reference_bpm": 101,
        "original_filename": "pocket-proof.mp3",
        "source_url": _DRUMPRINTS_URL,
        "license": "CC BY 4.0",
        "attribution": "Pocket Proof adapts DP2301 Longform 101 with new bass and tine chords. " + _DRUMPRINTS_CREDIT,
        "provenance": "Track 04, first 12 bars, closing hit at 28.515 s. " + _DRUMPRINTS_SESSION,
        "use_for": ["磁吸 CTA、短网址键入", "Twelve-bar launch edit with syncopated bass and a final downbeat"],
    },
    {
        "mood": "relay-glass",
        "title": "Relay Glass",
        "author": "Rookie Cut arrangement / Spencer Tweedy (drums)",
        "style": "Electro",
        "reference_bpm": 128,
        "original_filename": "relay-glass.mp3",
        "source_url": _DRUMPRINTS_URL,
        "license": "CC BY 4.0",
        "attribution": "Relay Glass adapts DP2301 Contact Sheet 128 with electronic bass and stereo bell pulses. " + _DRUMPRINTS_CREDIT,
        "provenance": "Track 01, first 16 bars, closing hit at 30.000 s. " + _DRUMPRINTS_SESSION,
        "use_for": ["黑白灰产品揭示", "Cut on bass pulses and reveal the product with the stereo bells"],
    },
    {
        "mood": "open-window",
        "title": "Open Window",
        "author": "Rookie Cut arrangement / Spencer Tweedy (drums)",
        "style": "Upbeat Indie",
        "reference_bpm": 158,
        "original_filename": "open-window.mp3",
        "source_url": _DRUMPRINTS_URL,
        "license": "CC BY 4.0",
        "attribution": "Open Window adapts DP2301 Longform 158 with bass and layered plucked strings. " + _DRUMPRINTS_CREDIT,
        "provenance": "Track 06, 16 bars from 6.076 s, closing chord at 24.304 s. " + _DRUMPRINTS_SESSION,
        "use_for": ["工作台铺陈至产品全景", "Build from sparse strums to the high plucked line in bar nine"],
    },
    {
        "mood": "contact-sheet-101-a",
        "title": "DP2301 Contact Sheet 101 A",
        "author": "Spencer Tweedy",
        "style": "Minimal Percussion",
        "reference_bpm": 101,
        "original_filename": "contact-sheet-101-a.mp3",
        "source_url": _DRUMPRINTS_URL,
        "license": "CC BY 4.0",
        "attribution": "DP2301 Contact Sheet 101 A, level adjusted and encoded as MP3. " + _DRUMPRINTS_CREDIT,
        "provenance": "Track 07, full solo drum performance. " + _DRUMPRINTS_SESSION,
        "use_for": ["界面细节特写与实录翻页", "Drums alone under a sequence of tactile actions"],
    },
]

CURATED_MUSIC_CATALOG = SHOTCRAFT_MUSIC_CATALOG + DRUMPRINTS_MUSIC_CATALOG


def default_music_id(mood: str) -> UUID:
    """Deterministic UUID for a default-catalog piece (stable across runs)."""
    return uuid5(NAMESPACE_DNS, f"repurposer:music:{mood}")


async def list_music(db: AsyncSession, user_id: UUID | None = None) -> list[Music]:
    """List visible music pieces (public/platform + caller's own, excluding archived)."""
    public_clause = or_(Music.is_public.is_(True), Music.scope == "platform")
    owner_clause = (
        or_(public_clause, Music.generated_by_user_id == user_id)
        if user_id is not None
        else public_clause
    )
    where_clause = and_(Music.status != "archived", owner_clause)
    result = await db.execute(
        select(Music).where(where_clause).order_by(Music.created_at.desc())
    )
    return list(result.scalars().all())


async def search_music_library(
    db: AsyncSession,
    *,
    owner_id: UUID | None = None,
    style_preset: str | None = None,
    mood: str | None = None,
    tags: list[str] | None = None,
    query: str | None = None,
    genre: str | None = None,
    energy: str | None = None,
    bpm: int | None = None,
    instrumental_only: bool = True,
    limit: int = 20,
) -> list[Music]:
    """Multi-facet reuse-first search over the permanent music library."""
    from app.catalog.audio_search import search_audio
    return await search_audio(db,Music,owner_id,query=query,style=style_preset,limit=limit,
                              mood=mood,tags=tags,genre=genre,energy=energy,bpm=bpm,instrumental_only=instrumental_only)


async def increment_music_use_count(db: AsyncSession, music_id: UUID) -> None:
    """Increment ``use_count`` on a library music row when attached to a composition."""
    row = await db.get(Music, music_id)
    if row is not None:
        row.use_count = int(row.use_count or 0) + 1
        await db.flush()


async def get_music(db: AsyncSession, music_id: UUID) -> Music | None:
    """Get a music piece by id."""
    return await db.get(Music, music_id)


async def get_music_by_mood(db: AsyncSession, mood: str) -> Music | None:
    """Get the first music piece matching a mood key (mood is non-unique)."""
    result = await db.execute(
        select(Music)
        .where(Music.mood == mood)
        .order_by(Music.is_favorite.desc(), Music.created_at.asc())
        .limit(1)
    )
    return result.scalars().first()


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
    tags: list[str] | None = None,
    compatible_styles: list[str] | None = None,
    scope: str | None = None,
    status: str | None = None,
    instrumental: bool = True,
    is_favorite: bool = False,
) -> Music:
    """Persist generated audio to object storage and create the DB row.

    Multiple tracks may share the same ``mood``; pieces are addressed by ``id``.
    """
    music_id = uuid4()
    base_mood = (mood or f"custom-{music_id.hex[:8]}").strip().lower()[:50]
    title = title or _default_title(prompt, base_mood)
    eff_scope = scope or ("platform" if user_id is None else "user")
    eff_status = status or ("curated" if eff_scope == "platform" else "ready")

    file_path, size_bytes = await persist_music(music_id, generated)
    from app.tools.music.beats import analyze_beat_grid  # deferred: import cycle

    meta: dict[str, Any] = {
        "content_sha256": hashlib.sha256(generated.audio_bytes).hexdigest(),
        **(generated.extra_meta or {}),
    }
    try:
        grid = analyze_beat_grid(generated.audio_bytes)
        if grid is not None:
            meta.update(grid)
    except Exception as e:  # noqa: BLE001 — analysis is best-effort
        logger.warning("beat_grid_birth_failed", music_id=str(music_id), error=str(e))

    lufs = measure_audio_lufs(generated.audio_bytes)
    duration_seconds = generated.duration_seconds
    if duration_seconds is None:
        try:
            duration_seconds = probe_music_duration_seconds(generated.audio_bytes)
        except Exception:  # noqa: BLE001
            duration_seconds = None

    music = Music(
        id=music_id,
        mood=base_mood,
        title=title,
        ext=generated.ext,
        file_path=file_path,
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        prompt=prompt,
        model=generated.model,
        generation_id=generated.generation_id,
        license=license,
        source_url=source_url,
        attribution=attribution,
        is_public=is_public,
        generated_by_user_id=user_id,
        scope=eff_scope,
        status=eff_status,
        tags=[str(t).strip().lower() for t in (tags or []) if str(t).strip()],
        compatible_styles=[str(s).strip() for s in (compatible_styles or []) if str(s).strip()],
        instrumental=instrumental,
        lufs=lufs,
        use_count=0,
        is_favorite=is_favorite,
        meta=meta,
    )
    db.add(music)
    await db.commit()
    await db.refresh(music)
    logger.info(
        "music_created",
        music_id=str(music_id),
        mood=base_mood,
        scope=eff_scope,
        lufs=lufs,
        user_id=str(user_id),
    )
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
        lufs_val = measure_audio_lufs(data) if data is not None else (row.lufs if row is not None else None)
        discovery = {
            "genre": entry["style"].lower(),
            "bpm": entry["reference_bpm"],
            "use_for": entry["use_for"],
        } if "use_for" in entry else {}
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
                scope="platform",
                status="curated",
                tags=[entry["style"].lower(), mood],
                compatible_styles=[],
                instrumental=True,
                lufs=lufs_val,
                meta=meta,
                **discovery,
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
            "scope": "platform",
            "status": "curated",
            "instrumental": True,
            "meta": meta,
            **discovery,
        }
        if lufs_val is not None:
            updates["lufs"] = lufs_val
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
    "increment_music_use_count",
    "is_music_in_use",
    "list_music",
    "measure_audio_lufs",
    "probe_music_duration_seconds",
    "resolve_bed_track",
    "search_music_library",
    "seed_default_music",
    "update_music_metadata",
]

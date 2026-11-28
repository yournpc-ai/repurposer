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


def compute_waveform_peaks(data: bytes, bins: int = 72) -> list[float]:
    """Compute normalized RMS waveform peaks (0..1) for Studio presets playback UI."""
    try:
        chunks: list[np.ndarray] = []
        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                return []
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                for resampled in resampler.resample(frame):
                    chunks.append(resampled.to_ndarray().reshape(-1))
            for resampled in resampler.resample(None):
                chunks.append(resampled.to_ndarray().reshape(-1))
        if not chunks:
            return []
        pcm = np.concatenate(chunks).astype(np.float32, copy=False)
        if pcm.size < bins:
            return []
        segments = np.array_split(pcm, bins)
        rms = [float(np.sqrt(np.mean(seg * seg))) for seg in segments]
        peak = max(rms) if rms else 0.0
        if peak <= 1e-6 or not math.isfinite(peak):
            return [0.05] * bins
        return [round(max(0.05, min(1.0, val / peak)), 3) for val in rms]
    except Exception as exc:  # noqa: BLE001
        logger.warning("compute_waveform_peaks_failed", error=str(exc))
        return []


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

# Default model for MiniMax music generation; platform catalog pieces are imported
# from curated MiniMax Music 3.0 renders and never generated implicitly at startup.
USER_MODEL = "music-3.0"


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


class CuratedMusicSectionSpec(TypedDict):
    """Normalized structural segment inside a curated BGM track."""

    name: str
    label: str
    label_zh: str
    start_ratio: NotRequired[float]
    end_ratio: NotRequired[float]
    start_seconds: NotRequired[float]
    end_seconds: NotRequired[float]
    energy: str
    voice_friendly: bool
    recommended: NotRequired[bool]
    note: NotRequired[str]
    note_zh: NotRequired[str]


class CuratedMusicEntry(TypedDict):
    """Code-declared provenance and Music 3.0 spec for one curated library piece."""

    mood: str
    title: str
    title_zh: str
    category: str  # vlog | visual_craft | product_promo | explainer
    format_kind: str  # arc_90s | short_hook
    energy: str  # calm | medium | energetic | dramatic
    author: str
    style: str
    reference_bpm: int
    target_duration_seconds: int
    original_filename: str
    source_url: str
    license: str
    attribution: str
    provenance: str
    summary: str
    generation_prompt: str
    use_for: list[str]
    avoid: list[str]
    compatible_styles: list[str]
    tags: list[str]
    section_specs: NotRequired[list[CuratedMusicSectionSpec]]


_ARC_90S_SECTIONS: list[CuratedMusicSectionSpec] = [
    {
        "name": "intro",
        "label": "Intro",
        "label_zh": "铺垫起势",
        "start_ratio": 0.0,
        "end_ratio": 0.16,
        "energy": "calm",
        "voice_friendly": True,
    },
    {
        "name": "groove",
        "label": "Groove",
        "label_zh": "稳定律动",
        "start_ratio": 0.16,
        "end_ratio": 0.50,
        "energy": "medium",
        "voice_friendly": True,
    },
    {
        "name": "drop",
        "label": "Drop",
        "label_zh": "高潮爆点",
        "start_ratio": 0.50,
        "end_ratio": 0.80,
        "energy": "energetic",
        "voice_friendly": False,
    },
    {
        "name": "outro",
        "label": "Outro",
        "label_zh": "自然收尾",
        "start_ratio": 0.80,
        "end_ratio": 1.0,
        "energy": "calm",
        "voice_friendly": True,
    },
]

_SHORT_HOOK_SECTIONS: list[CuratedMusicSectionSpec] = [
    {
        "name": "hook",
        "label": "Hook",
        "label_zh": "瞬时起势",
        "start_ratio": 0.0,
        "end_ratio": 0.20,
        "energy": "medium",
        "voice_friendly": False,
    },
    {
        "name": "peak",
        "label": "Peak",
        "label_zh": "密集卡点",
        "start_ratio": 0.20,
        "end_ratio": 0.85,
        "energy": "energetic",
        "voice_friendly": False,
    },
    {
        "name": "sting",
        "label": "Sting",
        "label_zh": "干脆收拍",
        "start_ratio": 0.85,
        "end_ratio": 1.0,
        "energy": "dramatic",
        "voice_friendly": False,
    },
]


def build_music_sections(
    entry: CuratedMusicEntry, duration_seconds: int | None
) -> list[dict[str, Any]]:
    """Expand curated section specs (exact seconds or normalized ratios) into concrete windows."""
    if not duration_seconds or duration_seconds <= 0:
        return []
    specs = entry.get("section_specs") or (
        _SHORT_HOOK_SECTIONS if entry.get("format_kind") == "short_hook" else _ARC_90S_SECTIONS
    )
    sections: list[dict[str, Any]] = []
    for spec in specs:
        if "start_seconds" in spec and "end_seconds" in spec:
            start = round(max(0.0, min(float(duration_seconds), float(spec["start_seconds"]))), 1)
            end = round(max(0.0, min(float(duration_seconds), float(spec["end_seconds"]))), 1)
        else:
            start = round(duration_seconds * float(spec.get("start_ratio", 0.0)), 1)
            end = round(duration_seconds * float(spec.get("end_ratio", 1.0)), 1)
        if end <= start:
            continue
        item: dict[str, Any] = {
            "name": spec["name"],
            "label": spec["label"],
            "label_zh": spec["label_zh"],
            "start_seconds": start,
            "end_seconds": end,
            "energy": spec["energy"],
            "voice_friendly": bool(spec["voice_friendly"]),
            "recommended": bool(spec.get("recommended", False)),
        }
        if spec.get("note"):
            item["note"] = spec["note"]
        if spec.get("note_zh"):
            item["note_zh"] = spec["note_zh"]
        sections.append(item)
    return sections


_MUSIC3_URL = "https://www.minimax.cn/blog/minimax-music-3-0-cn"
_MUSIC3_LICENSE = "MiniMax Music 3.0 — Rookie Studio Curated (verify commercial terms before public release)"

# Legacy Mixkit/Shotcraft/Drumprints moods retired in favor of the Music 3.0 curated library.
DEPRECATED_PLATFORM_MOODS: tuple[str, ...] = (
    "calm",
    "uplifting",
    "corporate",
    "mixkit-tech-house",
    "mixkit-cat-walk",
    "mixkit-g-eazy-nba-type",
    "mixkit-house-vibez",
    "mixkit-tonight-hiphop",
    "pocket-proof",
    "relay-glass",
    "open-window",
    "contact-sheet-101-a",
    "promo-editorial-truth",
)


def _m3_entry(
    *,
    mood: str,
    title: str,
    title_zh: str,
    category: str,
    format_kind: str,
    energy: str,
    style: str,
    bpm: int,
    target_duration_seconds: int,
    summary: str,
    generation_prompt: str,
    use_for: list[str],
    avoid: list[str],
    compatible_styles: list[str],
    tags: list[str],
    section_specs: list[CuratedMusicSectionSpec] | None = None,
) -> CuratedMusicEntry:
    entry: CuratedMusicEntry = {
        "mood": mood,
        "title": title,
        "title_zh": title_zh,
        "category": category,
        "format_kind": format_kind,
        "energy": energy,
        "author": "Rookie Studio / MiniMax Music 3.0",
        "style": style,
        "reference_bpm": bpm,
        "target_duration_seconds": target_duration_seconds,
        "original_filename": f"{mood}.mp3",
        "source_url": _MUSIC3_URL,
        "license": _MUSIC3_LICENSE,
        "attribution": f"{title} — Rookie Studio Curated (MiniMax Music 3.0)",
        "provenance": f"Curated MiniMax Music 3.0 instrumental ({format_kind}, {bpm} BPM)",
        "summary": summary,
        "generation_prompt": generation_prompt,
        "use_for": use_for,
        "avoid": avoid,
        "compatible_styles": compatible_styles,
        "tags": tags,
    }
    if section_specs:
        entry["section_specs"] = section_specs
    return entry


MUSIC3_CURATED_CATALOG: list[CuratedMusicEntry] = [
    # ---- 1. Vlog 旅拍与日常 (4 × 90s four-part arcs) ----
    _m3_entry(
        mood="vlog-nagoya-citypop",
        title="Sojourn City-Pop",
        title_zh="日系胶片旅拍",
        category="vlog",
        format_kind="arc_90s",
        energy="energetic",
        style="City Pop",
        bpm=116,
        target_duration_seconds=90,
        summary="Sunlit Japanese city-pop indie funk with crisp snare cuts, warm Rhodes chords, and bouncy bass.",
        generation_prompt=(
            "Pure instrumental Japanese city-pop and indie funk travel vlog soundtrack, 116 BPM, no vocals. "
            "Warm Fender Rhodes, sunlit clean electric guitar strums, crisp dry snare and tight slap-lite bassline. "
            "Four clear sections over ~90 seconds: [Intro] breezy 12s analog synth shimmer, [Verse] steady upbeat groove with clean midrange for dialogue, "
            "[Chorus] bright sparkling brass-synth lift with punchy beat cuts for travel montage, [Outro] clean resolved final chord."
        ),
        use_for=["日系胶片旅拍 Vlog", "快切节奏踩拍与城市漫步", "Upbeat travel film montage"],
        avoid=["暗黑悬疑", "严肃学术报告"],
        compatible_styles=["vox_editorial", "swiss_paper"],
        tags=["vlog", "travel", "city-pop", "indie-funk", "upbeat", "film"],
    ),
    _m3_entry(
        mood="vlog-cafe-acoustic",
        title="Morning Pour Lo-Fi",
        title_zh="治愈咖啡馆日常",
        category="vlog",
        format_kind="arc_90s",
        energy="calm",
        style="Lo-Fi Acoustic",
        bpm=88,
        target_duration_seconds=90,
        summary="Warm nylon guitar, brushed snare, and soft upright bass leaving wide midrange room for natural ambient sound.",
        generation_prompt=(
            "Pure instrumental warm lo-fi acoustic coffee shop vlog background music, 88 BPM, no vocals. "
            "Fingerpicked nylon acoustic guitar, gentle brushed drums, subtle upright bass, soft vinyl warmth, spacious midrange so spoken voice and cafe Foley stay crystal clear. "
            "Four sections over ~90 seconds: [Intro] gentle solo guitar, [Verse] cozy light groove, [Chorus] slightly fuller warm keys swell, [Outro] soft resolved acoustic fade."
        ),
        use_for=["探店与咖啡馆日常", "保留现场原声与轻声对话", "Aesthetic day-in-the-life"],
        avoid=["极速卡点", "高能科技发布"],
        compatible_styles=["swiss_paper", "vox_editorial"],
        tags=["vlog", "cafe", "lofi", "acoustic", "cozy", "voice-friendly"],
    ),
    _m3_entry(
        mood="vlog-night-rail",
        title="Midnight Transit Garage",
        title_zh="城市夜景氛围电音",
        category="vlog",
        format_kind="arc_90s",
        energy="medium",
        style="Ambient Garage",
        bpm=125,
        target_duration_seconds=90,
        summary="Moody nocturnal UK-garage pulse with deep sub-bass and shimmering pads built for night city rail and bloom focus intros.",
        generation_prompt=(
            "Atmospheric UK future garage and nocturnal ambient electronic instrumental, 125 BPM, F minor, no vocals. "
            "Emotional arc starts misty and weightless for a blur-to-focus night opening, locks into a sleek hypnotic transit pulse, expands into a glowing neon-lit climax, and settles into a clean lingering tail. "
            "Lush wide-stereo detuned synth pads swelling gently; crisp syncopated 2-step rimshots with subtle shuffled ghost hi-hats; deep clean sine sub-bass sliding smoothly beneath glassy bell plucks. "
            "Production features spacious hall reverb on atmospheric textures paired with tight, dry, punchy transients on drums and clean modern streaming master."
        ),
        use_for=["城市轻轨与夜景车流", "动感模糊聚焦与丁达尔高光开场", "Moody night city vlog"],
        avoid=["明亮儿童向", "轻喜剧"],
        compatible_styles=["institutional_dark", "kinetic_anime"],
        tags=["vlog", "night", "urban", "ambient-garage", "moody", "cinematic"],
    ),
    _m3_entry(
        mood="vlog-golden-cinema",
        title="Slow Horizon Cinema",
        title_zh="电影感慢镜日常",
        category="vlog",
        format_kind="arc_90s",
        energy="calm",
        style="Cinematic Indie",
        bpm=94,
        target_duration_seconds=90,
        summary="Felt piano, warm cello swells, and understated percussion crafted for 16:9 slow-motion storytelling and bilingual captions.",
        generation_prompt=(
            "Modern cinematic indie film underscore instrumental, 94 BPM, D major, no vocals. "
            "Emotional arc opens intimate and fragile, gradually warms into a hopeful narrative flow, rises to a heartfelt sweeping climax for scenic wide shots, and resolves peacefully into silence. "
            "Close-mic'd intimate felt piano playing delicate arpeggiated motifs with audible hammer warmth; legato solo cello carrying a lyrical countermelody; soft brushed percussion and muted pulsing bass entering mid-track; lush warm chamber strings swelling gently at the peak. "
            "Production has wide cinematic depth, natural concert room reverb, and dynamic breathing acoustic range."
        ),
        use_for=["16:9 电影感沉浸日常", "慢动作风景与双语电影字幕", "Emotional travel diary"],
        avoid=["高频硬切快剪", "硬核电音"],
        compatible_styles=["swiss_paper", "institutional_dark"],
        tags=["vlog", "cinematic", "piano", "strings", "slow-motion", "emotional"],
    ),
    # ---- 2. 创意合成 & 动态设计 (世界级设计工作室 Buck / ManvsMachine / A24 级：3 × 90s + 3 × 15–20s) ----
    _m3_entry(
        mood="craft-swiss-funk",
        title="Swiss Grid Funk",
        title_zh="瑞士网格极简律动（Buck 级）",
        category="visual_craft",
        format_kind="arc_90s",
        energy="medium",
        style="Minimal Groove",
        bpm=112,
        target_duration_seconds=90,
        summary="Buck/Oddfellows-grade ultra-dry minimalist studio groove with Swiss-watch negative space, elastic analog bass, and tactile rim snaps for editorial grids.",
        generation_prompt=(
            "Ultra-refined boutique design-studio minimalist electro-groove instrumental, 112 BPM, E minor, no vocals, zero cheesy retro funk or stock corporate brightness. "
            "Emotional arc opens with razor-crisp dry percussion and generous Swiss-watch negative space, settles into an effortlessly sophisticated modern pocket, tightens with clever syncopated staccato accents for geometric layout shifts, and ends on a dead-stop unison studio hit. "
            "Dry close-mic'd snare snaps and crisp brushed rimshots locking cleanly on beats 2 and 4; warm rubbery Moog-style analog bassline playing a minimalist syncopated riff; muted glass-soft analog synth plucks and whisper-brief Rhodes ghost chords marking bar transitions. "
            "Production has gallery-grade dry studio intimacy, ultra-crisp transient separation, zero muddy reverb, and expensive modern mastering headroom."
        ),
        use_for=["Buck/Oddfellows 级瑞士动态网格排版", "精准踩军鼓缩放与几何蒙版变形", "High-craft editorial kinetic design"],
        avoid=["廉价复古放克", "抒情慢摇与沉重史诗"],
        compatible_styles=["swiss_paper", "vox_editorial"],
        tags=["visual-craft", "swiss-grid", "boutique-groove", "minimal", "crisp-snare", "design-studio"],
    ),
    _m3_entry(
        mood="craft-tech-arpeggio",
        title="Intent Arpeggio",
        title_zh="雕塑感动态设计电子（ManvsMachine 级）",
        category="visual_craft",
        format_kind="arc_90s",
        energy="energetic",
        style="Kinetic IDM",
        bpm=126,
        target_duration_seconds=90,
        summary="ManvsMachine/Tendril-grade sculptural modular electronica and tactile IDM built for luxury 3D/React/SVG motion design showreels.",
        generation_prompt=(
            "High-fashion avant-garde kinetic electronica and sculptural modular IDM instrumental for luxury motion-design studio showreel, 126 BPM, A minor, no vocals, zero generic club tech-house or cheap EDM. "
            "Emotional arc emerges from tactile micro-granular clicks and a warm filtered analog pulse, unfolds into an intricate hypnotic syncopated electronic stride, expands into a crystalline wide-screen harmonic horizon for visual climaxes, and resolves cleanly on a poised architectural synth chord. "
            "Sculptural analog modular synthesizer weaving precision 16th-note polyrhythmic arpeggios with organic filter motion; sleek punchy syncopated sub-bass; crisp machined micro-percussion and glass-clear stereo hi-hat textures. "
            "Production has luxury commercial sound-design polish, vast stereo dimensionality, surgical transient clarity, and breathtaking dynamic headroom."
        ),
        use_for=["ManvsMachine 级动态设计师 Showreel", "多边形形变、点阵波纹与 3D 丝带", "High-fashion generative motion graphics"],
        avoid=["廉价夜店 Tech House", "田园民谣与慢速口播"],
        compatible_styles=["institutional_dark", "kinetic_anime"],
        tags=["visual-craft", "showreel", "idm", "sculptural-electronica", "motion-design", "luxury"],
    ),
    _m3_entry(
        mood="craft-dark-impact",
        title="Apex Dark Pulse",
        title_zh="暗黑雕塑重拍快剪（Porsche/A24 级）",
        category="visual_craft",
        format_kind="arc_90s",
        energy="dramatic",
        style="Dark Electronic",
        bpm=132,
        target_duration_seconds=90,
        summary="Porsche/Leica/A24-grade brutalist dark electronica with bone-dry sub-bass gravity, stark negative-space stops, and luxury industrial percussion for match-cuts.",
        generation_prompt=(
            "Avant-garde luxury brutalist dark electronica and precision industrial-minimalist percussion instrumental, 132 BPM, C minor, no vocals, zero cheap gaming dubstep or EDM wobble. "
            "Emotional arc opens with stark architectural tension and taut metallic silence, locks into a cold high-fashion percussive stride with sudden dramatic micro-silences, builds massive controlled sub-bass gravity for automotive speed-ramps and match-cuts, and finishes with one monumental clean sub-bass drop into pure silence. "
            "Deep bone-dry analog sub-bass pulses with immaculate weight; razor-sharp concrete-and-metal industrial percussion hits and ultra-dry crisp snare cracks; restrained ominous dark synth stabs framed by vast cavernous negative space. "
            "Production sounds like a cinema-grade luxury dark fashion or flagship sports-car film, with devastating clean low end, surgical transients, and distortion-free mastering authority."
        ),
        use_for=["Porsche/Leica/A24 级暗黑高端快剪", "相似形圆形匹配快剪与硬件变速卡点", "Luxury dark kinetic match-cut"],
        avoid=["廉价电竞 Dubstep", "温馨日常与柔和口播"],
        compatible_styles=["institutional_dark", "kinetic_anime"],
        tags=["visual-craft", "match-cut", "automotive", "brutalist-electronic", "luxury-dark", "speed-ramp"],
    ),
    _m3_entry(
        mood="hook-showreel-15s",
        title="Showreel Spark 15s",
        title_zh="15秒旗舰设计作品集短曲（ManvsMachine 级）",
        category="visual_craft",
        format_kind="short_hook",
        energy="energetic",
        style="Electronic Hook",
        bpm=126,
        target_duration_seconds=18,
        summary="Compact 15–20s luxury design-studio showreel sting with instant sculptural modular pulse, surgical cut accents, and an iconic crystalline brand hit.",
        generation_prompt=(
            "Compact luxury design-studio kinetic electronica showreel cue, 126 BPM, G minor, no vocals, zero generic stock synth risers or cheap club house, concise self-contained 15 to 20 second architecture. "
            "Immediate surgical tactile click snapping straight into an ultra-clean sculptural modular synth pulse and sleek dry syncopated percussion locking tightly to every four-beat visual cut, pausing for one razor-sharp split-second breath before an iconic deep analog sub-bass and crystalline harmonic brand hit. "
            "Production is hyper-refined, dry-transient forward, expensive, and effortless with zero wasted intro."
        ),
        use_for=["15 秒顶级动态设计 Showreel", "无需裁剪直接整首落轨", "Luxury kinetic studio portfolio cut"],
        avoid=["模板化电音扫频", "超过 45 秒的长片"],
        compatible_styles=["institutional_dark", "kinetic_anime", "swiss_paper"],
        tags=["short-hook", "showreel", "15s", "luxury-electronica", "stinger", "visual-craft"],
    ),
    _m3_entry(
        mood="hook-matchcut-15s",
        title="Kinetic Match-Cut 15s",
        title_zh="15秒精密打击快剪短曲（Apple 级）",
        category="visual_craft",
        format_kind="short_hook",
        energy="dramatic",
        style="Percussive Bass",
        bpm=134,
        target_duration_seconds=16,
        summary="Apple/Nike commercial-grade 15s hyper-dry foley-electronic percussion & sub-bass hit cue built for razor-sharp match-cuts and circular mask transitions.",
        generation_prompt=(
            "Ultra-clean luxury commercial tactile percussion and surgical sub-bass match-cut cue, 134 BPM, D minor, no vocals, zero cheesy trailer whooshes, compact 12 to 16 second rhythmic burst. "
            "Hyper-dry crisp snare cracks, machined titanium micro-clicks, and tight acoustic-electronic percussive snaps locking with laser precision to every downbeat, punctuated by deep clean sub-bass weight and razor-sharp negative-space stops, culminating in one massive clean final bass impact and absolute silence. "
            "Production is surgical, high-fashion, bone-dry, and devastatingly punchy for rapid match-cut transitions."
        ),
        use_for=["Apple/Nike 级精密踩拍匹配快剪", "圆形蒙版相似形 6–15 秒高能特效开场", "Luxury rhythmic match-cut montage"],
        avoid=["廉价预告片音效堆砌", "慢节奏叙事"],
        compatible_styles=["institutional_dark", "kinetic_anime"],
        tags=["short-hook", "match-cut", "tactile-percussion", "mask-transition", "luxury-commercial"],
    ),
    _m3_entry(
        mood="hook-editorial-20s",
        title="Grid Snap 20s",
        title_zh="20秒极简设计踩拍短曲（Buck 级）",
        category="visual_craft",
        format_kind="short_hook",
        energy="medium",
        style="Minimal Groove",
        bpm=114,
        target_duration_seconds=20,
        summary="Crisp 20s boutique studio minimalist electro-groove with bar-level metallic chime accents and Swiss-watch poise for geometric layout shifts.",
        generation_prompt=(
            "Ultra-clean boutique design-studio minimalist electro-groove cue, 114 BPM, A minor, no vocals, zero cheesy retro funk, tight self-contained 20 second architectural loop with instant downbeat poise. "
            "Razor-dry snare snaps and tactile rim clicks, elastic warm analog bassline with generous negative space, delicate stereo crystalline metallic chimes marking four-beat phrases, brief poised rhythmic break before a crisp tight unison studio stop. "
            "Production is ultra-clean, intimate, expensive dry studio mix with sparkling separation."
        ),
        use_for=["15–20 秒高级瑞士网格排版", "动态文字短片与快闪海报", "Boutique studio editorial typography"],
        avoid=["史诗大场面", "廉价广告轻快伴奏"],
        compatible_styles=["swiss_paper", "vox_editorial"],
        tags=["short-hook", "editorial", "minimal", "boutique-groove", "typography"],
    ),
    # ---- 3. 产品与演示 (4 首干净高级的科技网站宣传片 BGM：94 / 104 / 112 / 116 BPM，附实测能量乐段标注) ----
    _m3_entry(
        mood="promo-keynote-percussion",
        title="Precision Tech Pulse",
        title_zh="清透现代科技律动",
        category="product_promo",
        format_kind="arc_90s",
        energy="medium",
        style="Ambient Electro",
        bpm=112,
        target_duration_seconds=171,
        summary="Clean, polished modern tech launch electronica with gentle synth plucks, warm analog pads, and a light steady beat for UI showcases.",
        generation_prompt=(
            "Clean modern tech product launch instrumental, 112 BPM, modern ambient electronica and soft synth pop, no vocals. "
            "Gentle crisp synth pluck arpeggio, warm smooth analog synth pads, round deep bass, and a clean light electronic beat with soft shaker. "
            "Starts calm and intriguing, builds smoothly into an uplifting confident groove for product UI showcase, and resolves warmly on a clean sustained chord. "
            "Clean, polished, pleasant, spacious mix with no harsh or noisy sounds."
        ),
        use_for=["现代科技网站产品演示与 UI 展示", "商业官网与品牌宣传片（带/无旁白皆宜）", "Modern SaaS & AI website product film"],
        avoid=["嘈杂重金属电音", "奇怪实验噪点"],
        compatible_styles=["swiss_paper", "institutional_dark", "vox_editorial"],
        tags=["product-promo", "clean-electronic", "ambient-electro", "ui-demo", "website-promo", "voice-friendly"],
        section_specs=[
            {"name": "intro", "label": "Intro", "label_zh": "铺垫起势", "start_seconds": 0, "end_seconds": 20, "energy": "calm", "voice_friendly": True, "note": "Gentle opening texture", "note_zh": "轻柔引入"},
            {"name": "groove", "label": "UI Groove", "label_zh": "清透主律动", "start_seconds": 20, "end_seconds": 55, "energy": "medium", "voice_friendly": True, "recommended": True, "note": "Best entry for 30–60s voiced UI demos", "note_zh": "30–60s 带旁白 UI 演示推荐切入"},
            {"name": "highlight", "label": "Highlight Peak", "label_zh": "丰满高潮段", "start_seconds": 55, "end_seconds": 130, "energy": "energetic", "voice_friendly": False, "recommended": True, "note": "Full uplifting momentum for product highlights", "note_zh": "产品亮点展示精华段"},
            {"name": "bridge", "label": "Breath Bridge", "label_zh": "呼吸留白", "start_seconds": 130, "end_seconds": 150, "energy": "calm", "voice_friendly": True, "note": "Calm transition for key narrative pause", "note_zh": "轻盈过渡留白"},
            {"name": "finale", "label": "Finale Lift", "label_zh": "升华收束", "start_seconds": 150, "end_seconds": 171, "energy": "energetic", "voice_friendly": True, "note": "Warm confident closing lift", "note_zh": "收尾升华"},
        ],
    ),
    _m3_entry(
        mood="promo-hybrid-anthem",
        title="Institutional Deep Pulse",
        title_zh="大气前沿科技大片",
        category="product_promo",
        format_kind="arc_90s",
        energy="calm",
        style="Atmospheric Tech",
        bpm=94,
        target_duration_seconds=185,
        summary="Serene, prestigious atmospheric electronic and soft modern piano underscore crafted for authoritative brand films and executive presentations.",
        generation_prompt=(
            "Inspiring modern technology brand film instrumental, 94 BPM, atmospheric ambient electronic with soft modern piano, no vocals. "
            "Warm flowing analog synth pads, gentle clean piano notes, deep smooth sub bass pulse, and a soft understated electronic beat entering smoothly in the middle. "
            "Opens serene and visionary, grows steadily into a wide hopeful cinematic climax with luminous warm harmonies, and fades gracefully. "
            "Polished, spacious, prestigious, and calm for voiceover narration."
        ),
        use_for=["高管汇报与品牌愿景大片", "从容大气的前沿 AI / 金融科技宣传片", "Prestigious AI brand film & executive voiceover"],
        avoid=["急促快剪", "嘈杂重鼓"],
        compatible_styles=["institutional_dark", "swiss_paper"],
        tags=["product-promo", "atmospheric-tech", "institutional", "brand-film", "piano-electronic", "voice-friendly"],
        section_specs=[
            {"name": "intro", "label": "Vision Intro", "label_zh": "静谧起势", "start_seconds": 0, "end_seconds": 15, "energy": "calm", "voice_friendly": True, "note": "Serene piano & pad intro", "note_zh": "静谧钢琴引入"},
            {"name": "groove", "label": "Executive Bed", "label_zh": "沉稳叙事", "start_seconds": 15, "end_seconds": 65, "energy": "medium", "voice_friendly": True, "recommended": True, "note": "Best entry for authoritative voiced brand films", "note_zh": "高管/机构旁白推荐切入"},
            {"name": "peak", "label": "Horizon Peak", "label_zh": "宏大高潮", "start_seconds": 65, "end_seconds": 95, "energy": "dramatic", "voice_friendly": False, "recommended": True, "note": "Luminous wide-screen climax for big reveals", "note_zh": "品牌愿景宏大高潮段"},
            {"name": "interlude", "label": "Minimal Pause", "label_zh": "极简留白", "start_seconds": 95, "end_seconds": 120, "energy": "calm", "voice_friendly": True, "note": "Quiet reflective interlude", "note_zh": "安静留白间奏"},
            {"name": "climax", "label": "Second Climax", "label_zh": "二次升华", "start_seconds": 120, "end_seconds": 165, "energy": "dramatic", "voice_friendly": False, "note": "Full grand emotional finale", "note_zh": "终章情绪升华"},
            {"name": "outro", "label": "Graceful Fade", "label_zh": "优雅渐出", "start_seconds": 165, "end_seconds": 185, "energy": "calm", "voice_friendly": True, "note": "Soft lingering resolve", "note_zh": "优雅收尾"},
        ],
    ),
    _m3_entry(
        mood="hook-launch-22s",
        title="Kinetic Launch Groove",
        title_zh="干脆轻快产品亮点电子",
        category="product_promo",
        format_kind="arc_90s",
        energy="energetic",
        style="Clean Electro",
        bpm=116,
        target_duration_seconds=240,
        summary="Fresh, sleek 116 BPM modern indie-electronic showcase groove with tight clean drums and warm synth chords — jump in at 0:30 or 1:25 for crisp promo cuts.",
        generation_prompt=(
            "Crisp upbeat modern tech showcase instrumental, 116 BPM, clean indie electronic and soft house groove, no vocals. "
            "Tight clean electronic kick and soft snap percussion, smooth bouncy synth bass, bright warm analog synth chords and gentle melodic synth plucks. "
            "Starts immediately with an engaging clean groove, maintains an energetic yet polished rhythm for product feature highlights, and finishes with a neat clean ending. "
            "Fresh, sleek, pleasant, and balanced studio sound."
        ),
        use_for=["官网产品亮点快切与功能展示（建议从 0:30 切入）", "Figma / Apple 风格轻快高级科技短片", "Clean upbeat tech product highlight reel"],
        avoid=["刺耳重金属电子", "混乱噪点"],
        compatible_styles=["swiss_paper", "institutional_dark", "vox_editorial"],
        tags=["product-promo", "clean-electro", "upbeat-tech", "feature-showcase", "pleasant"],
        section_specs=[
            {"name": "intro", "label": "Soft Intro", "label_zh": "轻柔铺垫", "start_seconds": 0, "end_seconds": 30, "energy": "calm", "voice_friendly": True, "note": "Quiet 30s buildup (skip to 0:30 for snappy promos)", "note_zh": "30s 慢前奏（快节奏宣传片建议跳过）"},
            {"name": "groove", "label": "Upbeat Groove", "label_zh": "明快主律动", "start_seconds": 30, "end_seconds": 85, "energy": "energetic", "voice_friendly": True, "recommended": True, "note": "Best entry for 30–60s crisp product showcase", "note_zh": "30–60s 宣传片最佳切入点"},
            {"name": "highlight", "label": "Peak Showcase", "label_zh": "高能亮点段", "start_seconds": 85, "end_seconds": 145, "energy": "energetic", "voice_friendly": False, "recommended": True, "note": "Peak energy middle section for feature montages", "note_zh": "中段高能亮点连播"},
            {"name": "break", "label": "Breath Break", "label_zh": "呼吸间奏", "start_seconds": 145, "end_seconds": 160, "energy": "calm", "voice_friendly": True, "note": "Brief calm reset", "note_zh": "简短呼吸过渡"},
            {"name": "encore", "label": "Closing Groove", "label_zh": "稳健收官", "start_seconds": 160, "end_seconds": 225, "energy": "medium", "voice_friendly": True, "note": "Polished late-track groove", "note_zh": "后段稳健收官"},
            {"name": "outro", "label": "Clean Outro", "label_zh": "自然收尾", "start_seconds": 225, "end_seconds": 240, "energy": "calm", "voice_friendly": True, "note": "Gentle closing fade", "note_zh": "自然收尾"},
        ],
    ),
    # ---- 4. 观点与视觉化口播 (世界级杂志/纪录片 Bloomberg / NYT / MasterClass 级：2 × 90s 旁白安全母曲) ----
    _m3_entry(
        mood="explainer-vox-pluck",
        title="Editorial Pluck Bed",
        title_zh="顶级杂志智感口播铺底（NYT/Bloomberg 级）",
        category="explainer",
        format_kind="arc_90s",
        energy="medium",
        style="Editorial Pulse",
        bpm=100,
        target_duration_seconds=90,
        summary="NYT/Bloomberg Originals-grade intellectual minimalist chamber-electronica with muted felt piano, warm upright bass, and a pristine vocal pocket.",
        generation_prompt=(
            "Sophisticated prestige-journalism and documentary-editorial underscore instrumental, 100 BPM, D minor, no vocals, zero cheesy corporate kalimba or ukulele cliches. "
            "Emotional arc opens sharp, inquisitive, and intellectually poised, sustains a refined rhythmic momentum that elevates complex analytical storytelling, opens with subtle warm harmonic clarity for key data reveals, and closes on a crisp composed cadence. "
            "Close-mic'd dry muted felt piano playing a clever minimalist rhythmic ostinato; warm round pizzicato upright bass walking with understated confidence; feather-light brushed rim-clicks and subtle warm analog sub pulse. "
            "Production is audiophile-grade, intimately dry, with zero competing melody and an intentionally open uncluttered 300Hz to 3kHz midrange so spoken commentary remains razor-clear."
        ),
        use_for=["NYT / Bloomberg / Vox 级深度商业与科技口播", "数据图表拆解与高密度观点输出", "Prestige journalism & editorial explainer"],
        avoid=["廉价轻快尤克里里/卡林巴广告风", "喧宾夺主的主旋律"],
        compatible_styles=["vox_editorial", "swiss_paper", "institutional_dark"],
        tags=["explainer", "talking-head", "editorial", "prestige-journalism", "voice-friendly", "felt-piano"],
    ),
    _m3_entry(
        mood="explainer-minimal-rhodes",
        title="Deep Focus Rhodes",
        title_zh="深度纪录片极简电钢（MasterClass/A24 级）",
        category="explainer",
        format_kind="arc_90s",
        energy="calm",
        style="Minimal Rhodes",
        bpm=86,
        target_duration_seconds=90,
        summary="MasterClass/New Yorker-grade audiophile minimalist Fender Rhodes and subtle analog warmth with zero artificial lo-fi noise for calm, authoritative narration.",
        generation_prompt=(
            "Audiophile prestige-documentary minimalist Fender Rhodes and warm analog ambient underscore instrumental, 86 BPM, Eb major, no vocals, zero artificial vinyl crackle or amateur lo-fi fuzz. "
            "Emotional arc opens serene, composed, and deeply thoughtful, maintains an unhurried meditative intellectual flow with tasteful modern jazz harmonic voicings, glows subtly warmer in the third quarter for reflective insights, and resolves gracefully on a soft lingering chord. "
            "Silky studio-mic'd vintage Fender Rhodes playing slow spacious chords with subtle warm tremolo; whisper-soft pure analog sub pulse and barely-there brushed snare air. "
            "Production has mastering-grade tape warmth, pristine studio silence, zero distracting melody, and a vast open 300Hz to 3kHz vocal pocket for authoritative long-form essays and executive interviews."
        ),
        use_for=["MasterClass / 纽约客 / A24 级深度长口播与访谈", "冷静权威的研究解读与创始人独白", "Prestige video essay & calm authoritative narration"],
        avoid=["廉价 Lo-Fi 杂音", "高能快切"],
        compatible_styles=["institutional_dark", "swiss_paper", "vox_editorial"],
        tags=["explainer", "essay", "minimal", "rhodes", "audiophile", "calm", "voice-friendly"],
    ),
]

CURATED_MUSIC_CATALOG = MUSIC3_CURATED_CATALOG


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
    for ref in (brand_ref, "promo-keynote-percussion", "vlog-nagoya-citypop"):
        if not ref:
            continue
        track = await resolve_music_ref(db, ref)
        if track is not None and (
            track.is_public or track.generated_by_user_id == project.user_id
        ):
            return track
    available = await list_music(db, user_id=project.user_id)
    return available[0] if available else None


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
    if not meta.get("waveform_peaks"):
        peaks = compute_waveform_peaks(generated.audio_bytes)
        if peaks:
            meta["waveform_peaks"] = peaks

    lufs = measure_audio_lufs(generated.audio_bytes)
    duration_seconds = generated.duration_seconds
    if duration_seconds is None:
        try:
            duration_seconds = probe_music_duration_seconds(generated.audio_bytes)
        except Exception:  # noqa: BLE001
            duration_seconds = None

    clean_tags = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
    clean_styles = [str(s).strip() for s in (compatible_styles or []) if str(s).strip()]
    search_text = " ".join(
        part
        for part in [title, base_mood, prompt, *clean_tags, *clean_styles]
        if part
    )
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
        tags=clean_tags,
        compatible_styles=clean_styles,
        instrumental=instrumental,
        lufs=lufs,
        use_count=0,
        is_favorite=is_favorite,
        search_text=search_text,
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
            or not meta.get("waveform_peaks")
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
            if not meta.get("waveform_peaks"):
                peaks = compute_waveform_peaks(data)
                if peaks:
                    meta["waveform_peaks"] = peaks

        effective_duration = duration_seconds if duration_seconds is not None else (row.duration_seconds if row is not None else None)
        sections = build_music_sections(entry, effective_duration)
        meta.update({
            "title_zh": entry["title_zh"],
            "category": entry["category"],
            "format_kind": entry["format_kind"],
            "author": entry["author"],
            "style": entry["style"],
            "reference_bpm": entry["reference_bpm"],
            "original_filename": entry["original_filename"],
            "provenance": entry["provenance"],
            "generation_prompt": entry["generation_prompt"],
            "sections": sections,
        })
        lufs_val = measure_audio_lufs(data) if data is not None else (row.lufs if row is not None else None)
        search_text = " ".join(
            part
            for part in [
                entry["title"],
                entry["title_zh"],
                entry["mood"],
                entry["category"],
                entry["style"],
                entry["energy"],
                entry["format_kind"],
                entry["summary"],
                *entry["tags"],
                *entry["use_for"],
                *entry["compatible_styles"],
            ]
            if part
        )
        discovery: dict[str, Any] = {
            "genre": entry["style"].lower(),
            "energy": entry["energy"],
            "bpm": entry["reference_bpm"],
            "summary": entry["summary"],
            "tags": list(entry["tags"]),
            "compatible_styles": list(entry["compatible_styles"]),
            "use_for": list(entry["use_for"]),
            "avoid": list(entry["avoid"]),
            "search_text": search_text,
        }
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
                prompt=entry["generation_prompt"],
                model=USER_MODEL,
                generation_id=None,
                license=entry["license"],
                source_url=entry["source_url"],
                attribution=entry["attribution"],
                is_public=True,
                generated_by_user_id=None,
                scope="platform",
                status="curated",
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
            "prompt": entry["generation_prompt"],
            "model": USER_MODEL,
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


async def _retire_deprecated_platform_music(db: AsyncSession) -> None:
    """Remove retired platform music rows without touching user-owned music.

    A legacy Output may still name a retired platform row in its render spec.
    Preserve that historical reference by archiving/hiding the row so it never
    re-enters the candidate library; unreferenced rows and their objects are
    deleted cleanly.
    """
    rows = list((await db.scalars(
        select(Music).where(
            Music.generated_by_user_id.is_(None),
            Music.mood.in_(DEPRECATED_PLATFORM_MOODS),
        )
    )).all())
    for row in rows:
        try:
            await delete_music(db, row.id)
        except MusicInUseError:
            if row.is_public or row.status != "archived":
                row.is_public = False
                row.status = "archived"
                await db.commit()
            logger.info("legacy_platform_music_hidden_in_use", music_id=str(row.id), mood=row.mood)


async def seed_default_music(db: AsyncSession) -> list[Music]:
    """Reconcile curated Music 3.0 platform tracks already imported to storage.

    Startup never calls a model or creates audio objects. Missing objects remain
    an explicit warning; deprecated legacy platform tracks are retired without
    touching user-owned music or immutable SourceSnapshots used by saved works.
    """
    await _retire_deprecated_platform_music(db)
    return await _reconcile_curated_music(db)


def _default_title(prompt: str, mood: str) -> str:
    """Best-effort title for a generated piece from its prompt/mood."""
    stripped = prompt.strip().splitlines()[0] if prompt.strip() else mood
    return stripped[:80] if stripped else mood


__all__ = [
    "AUDIO_EXT",
    "CURATED_MUSIC_CATALOG",
    "DEPRECATED_PLATFORM_MOODS",
    "MUSIC3_CURATED_CATALOG",
    "CuratedMusicAudio",
    "CuratedMusicEntry",
    "CuratedMusicSectionSpec",
    "MusicInUseError",
    "USER_MODEL",
    "build_music_sections",
    "compute_waveform_peaks",
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

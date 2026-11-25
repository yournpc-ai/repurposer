"""Analyze and ingest a licensed WAV or MP3 recording into permanent object storage."""

import hashlib
import io
from fractions import Fraction
from pathlib import Path
from typing import Literal

import av
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.catalog.search import Energy
from app.catalog.sync import search_document
from app.models.tables import SoundEffect
from app.providers import storage

RATE = 48000


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    file: str
    name: str = Field(min_length=1, max_length=160)
    name_zh: str | None = None
    domain: Literal["interface", "video"] = "video"
    category: str
    subcategory: str | None = None
    moods: list[str]
    energy: Energy
    summary: str = Field(min_length=1, max_length=280)
    use_for: list[str]
    avoid: list[str]
    tags: list[str] = Field(default_factory=list)
    compatible_styles: list[str] = Field(default_factory=list)
    sync_cue: Literal["onset", "energy_peak", "end_peak"] = "energy_peak"
    mix_hint: str | None = Field(default=None, max_length=280)
    license: str = Field(min_length=1, max_length=100)
    source_provider: str = "curated"
    source_url: str | None = None
    attribution: str | None = None


def _integrated_loudness(pcm, layout):
    # BS.1770 K-weighting coefficients at 48 kHz, then absolute and relative gating.
    frame = av.AudioFrame.from_ndarray(pcm, format="fltp", layout=layout)
    frame.sample_rate, frame.time_base, frame.pts = RATE, Fraction(1, RATE), 0
    graph = av.filter.Graph()
    source = graph.add_abuffer(
        sample_rate=RATE, format="fltp", layout=layout, time_base=frame.time_base
    )
    shelf = graph.add(
        "biquad",
        "b0=1.53512485958697:b1=-2.69169618940638:b2=1.19839281085285:a0=1:a1=-1.69065929318241:a2=.73248077421585",
    )
    highpass = graph.add("biquad", "b0=1:b1=-2:b2=1:a0=1:a1=-1.99004745483398:a2=.99007225036621")
    sink = graph.add("abuffersink")
    source.link_to(shelf)
    shelf.link_to(highpass)
    highpass.link_to(sink)
    graph.configure()
    source.push(frame)
    source.push(None)
    filtered = []
    while True:
        try:
            filtered.append(sink.pull().to_ndarray())
        except av.error.EOFError:
            break
    channels = av.AudioLayout(layout).channels
    weights = {"LFE": 0.0, "LFE2": 0.0, "BL": 1.41, "BR": 1.41, "SL": 1.41, "SR": 1.41}
    power = np.array([weights.get(ch.name, 1.0) for ch in channels]) @ np.square(
        np.concatenate(filtered, axis=1), dtype=np.float64
    )
    # A sub-400 ms effect occupies a single zero-padded loudness block.
    block = RATE * 4 // 10
    power = np.pad(power, (0, max(0, block - len(power))))
    sums = np.concatenate(([0.0], np.cumsum(power)))
    starts = np.arange(0, len(power) - block + 1, RATE // 10)
    energies = (sums[starts + block] - sums[starts]) / block
    gated = energies[energies > 10 ** ((-70 + 0.691) / 10)]
    if not len(gated):
        return None
    return float(-0.691 + 10 * np.log10(gated[gated >= gated.mean() / 10].mean()))


def analyze_audio(data: bytes):
    with av.open(io.BytesIO(data)) as container:
        if not container.streams.audio:
            raise ValueError("Recording has no audio stream")
        stream = container.streams.audio[0]
        source_layout = stream.codec_context.layout
        layout = {1: "mono", 2: "stereo"}.get(len(source_layout.channels), source_layout.name)
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=RATE)
        chunks = [
            out.to_ndarray()
            for frame in container.decode(audio=0)
            for out in resampler.resample(frame)
        ]
        chunks.extend(out.to_ndarray() for out in resampler.resample(None))
    if not chunks:
        raise ValueError("Recording contains no decoded samples")
    pcm = np.concatenate(chunks, axis=1)
    if not np.isfinite(pcm).all():
        raise ValueError("Recording contains invalid PCM values")
    power = np.square(pcm, dtype=np.float64).sum(axis=0)
    window = min(len(power), RATE // 100)
    cumulative = np.concatenate(([0.0], np.cumsum(power)))
    peak = int(np.argmax(cumulative[window:] - cumulative[:-window])) + window // 2
    return dict(
        duration_ms=max(1, round(len(power) * 1000 / RATE)),
        peak_offset_ms=round(peak * 1000 / RATE),
        lufs=_integrated_loudness(pcm, layout),
        content_sha256=hashlib.sha256(data).hexdigest(),
    )


async def ingest_recording(db, entry: Recording, directory: Path, *, owner_id=None):
    path = (directory / entry.file).resolve()
    path.relative_to(directory.resolve())
    ext = path.suffix.lower().lstrip(".")
    if ext not in {"wav", "mp3"}:
        raise ValueError("Expected a WAV or MP3 file")
    data = path.read_bytes()
    facts = analyze_audio(data)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended("sfx/" + entry.slug, 0)))
    )
    row = await db.scalar(select(SoundEffect).where(SoundEffect.slug == entry.slug))
    if row and (
        row.owner_id != owner_id
        or row.engine_kind != "sample"
        or row.content_sha256 != facts["content_sha256"]
        or row.ext != ext
    ):
        raise ValueError("This slug already identifies a different asset")
    key = f"sfx/{entry.slug}.{ext}"
    if await storage.exists(key):
        if hashlib.sha256(await storage.read(key)).hexdigest() != facts["content_sha256"]:
            raise ValueError("Stored bytes do not match this immutable slug")
    else:
        await storage.save(key, data, "audio/wav" if ext == "wav" else "audio/mpeg")
    fields = {
        **entry.model_dump(exclude={"file"}),
        **facts,
        "storage_key": key,
        "ext": ext,
        "size_bytes": len(data),
    }
    fields["search_text"] = search_document(fields)
    if row is None:
        row = SoundEffect(
            engine_kind="sample",
            owner_id=owner_id,
            scope="user" if owner_id else "platform",
            status="ready" if owner_id else "curated",
            **fields,
        )
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    await db.flush()
    return row

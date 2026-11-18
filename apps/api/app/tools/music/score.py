"""Bounded electronic ScoreSpec, deterministic NumPy PCM and authored beats."""

from __future__ import annotations

import io
import math
import wave
from fractions import Fraction
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.editing.schemas import CompositionContent
from app.editing.timing import SOURCE_TIMEBASE, output_ticks_to_source_ticks, quantize_ticks
from app.models.schemas import canonical_json_hash

SCORE_SCHEMA_VERSION = 1
SYNTH_VERSION = "numpy-electronic-v1"
MAX_SCORE_SECONDS = 120
MAX_SCORE_EVENTS = 2048


class ScoreError(ValueError):
    pass


class Rational(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num: int = Field(gt=0)
    den: int = Field(default=1, gt=0)

    def fraction(self) -> Fraction:
        return Fraction(self.num, self.den)


class Meter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beats: int = Field(default=4, ge=1, le=12)
    beat_unit: Literal[2, 4, 8, 16] = 4


class ScoreSectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    intent: str = Field(min_length=1, max_length=1000)


class ScoreSection(ScoreSectionDraft):
    section_id: str
    start_tick: int = Field(ge=0)
    end_tick: int = Field(gt=0)
    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)

    @model_validator(mode="after")
    def _positive_ranges(self) -> ScoreSection:
        if self.end_tick <= self.start_tick or self.end_sample <= self.start_sample:
            raise ValueError("score sections need positive source and sample ranges")
        return self


def _beat_string(value: Any) -> str:
    try:
        parsed = Fraction(str(value))
    except (ValueError, TypeError) as exc:
        raise ValueError("beat positions must be rational numbers") from exc
    if not math.isfinite(float(parsed)):
        raise ValueError("beat positions must be finite")
    return str(parsed)


class HarmonyEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    start_beat: str
    duration_beats: str
    midi_notes: list[int] = Field(min_length=1, max_length=6)
    velocity: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)

    _beats = field_validator("start_beat", "duration_beats", mode="before")(_beat_string)

    @field_validator("midi_notes")
    @classmethod
    def _midi_range(cls, value: list[int]) -> list[int]:
        if any(note < 0 or note > 127 for note in value):
            raise ValueError("MIDI notes must be in 0..127")
        return value


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=1, max_length=64)
    kind: Literal["pad", "pluck", "bass", "kick", "hat"]
    wave: Literal["sine", "triangle", "saw", "square"] = "sine"
    gain_db: float = Field(default=-12, ge=-50, le=0, allow_inf_nan=False)
    pan: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    attack_seconds: float = Field(default=0.01, gt=0, le=1, allow_inf_nan=False)
    release_seconds: float = Field(default=0.1, gt=0, le=2, allow_inf_nan=False)


class ScoreEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    instrument_id: str = Field(min_length=1, max_length=64)
    start_beat: str
    duration_beats: str
    midi: int | None = Field(default=None, ge=0, le=127)
    velocity: float = Field(default=0.7, gt=0, le=1, allow_inf_nan=False)

    _beats = field_validator("start_beat", "duration_beats", mode="before")(_beat_string)


class ScoreDynamics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    gain_db: float = Field(ge=-36, le=6, allow_inf_nan=False)


class ScoreTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=64)
    fade_in_beats: str = "0"
    fade_out_beats: str = "0"

    _beats = field_validator("fade_in_beats", "fade_out_beats", mode="before")(_beat_string)


class ScoreSpecDraft(BaseModel):
    """The model's bounded creative input; no executable code or media commands."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCORE_SCHEMA_VERSION] = SCORE_SCHEMA_VERSION
    synth_version: Literal[SYNTH_VERSION] = SYNTH_VERSION
    bpm: Rational
    meter: Meter = Meter()
    sample_rate: Literal[32000, 44100, 48000] = 48000
    channels: Literal[1, 2] = 2
    sections: list[ScoreSectionDraft] = Field(min_length=1, max_length=64)
    harmony: list[HarmonyEvent] = Field(default_factory=list, max_length=512)
    instruments: list[Instrument] = Field(min_length=1, max_length=16)
    events: list[ScoreEvent] = Field(default_factory=list, max_length=MAX_SCORE_EVENTS)
    dynamics: list[ScoreDynamics] = Field(default_factory=list, max_length=64)
    transitions: list[ScoreTransition] = Field(default_factory=list, max_length=64)
    seed: int = Field(ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def _creative_bounds(self) -> ScoreSpecDraft:
        if self.bpm.fraction() <= 0 or self.bpm.fraction() > 300:
            raise ValueError("BPM must be in (0, 300]")
        ids = [instrument.instrument_id for instrument in self.instruments]
        if len(ids) != len(set(ids)):
            raise ValueError("instrument_id values must be unique")
        return self


class ScoreSpec(ScoreSpecDraft):
    sections: list[ScoreSection] = Field(min_length=1, max_length=64)
    source_timebase: int = SOURCE_TIMEBASE
    score_digest: str = Field(min_length=64, max_length=64)

    @property
    def sample_count(self) -> int:
        return self.sections[-1].end_sample

    @property
    def duration_ticks(self) -> int:
        return self.sections[-1].end_tick


def _fraction(value: str) -> Fraction:
    return Fraction(value)


def build_score_spec(creative: ScoreSpecDraft, draft: dict[str, Any]) -> ScoreSpec:
    """Resolve creative sections against current Scene truth, never model timestamps."""
    content = CompositionContent.model_validate(draft.get("content") or {})
    scenes = sorted(content.scenes, key=lambda scene: scene.range.start)
    if not scenes:
        raise ScoreError("a score needs the current draft's Scenes")
    if [item.scene_id for item in creative.sections] != [scene.scene_id for scene in scenes]:
        raise ScoreError("score sections must cover every current Scene once, in playback order")
    if any(current.range.start < previous.range.end for previous, current in zip(scenes, scenes[1:])):
        raise ScoreError("the current draft has overlapping Scene ranges")
    sections = []
    for scene, section in zip(scenes, creative.sections, strict=True):
        start_sample = quantize_ticks(
            Fraction(scene.range.start, content.settings.timebase) * creative.sample_rate
        )
        end_sample = quantize_ticks(
            Fraction(scene.range.end, content.settings.timebase) * creative.sample_rate
        )
        sections.append(ScoreSection(
            **section.model_dump(mode="json"),
            section_id=scene.scene_id,
            start_tick=output_ticks_to_source_ticks(scene.range.start, content.settings.timebase),
            end_tick=output_ticks_to_source_ticks(scene.range.end, content.settings.timebase),
            start_sample=start_sample,
            end_sample=end_sample,
        ))
    if sections[-1].end_sample > MAX_SCORE_SECONDS * creative.sample_rate:
        raise ScoreError("the score exceeds the 120-second synthesis resource budget")
    section_ids = {section.scene_id for section in sections}
    for collection in (creative.harmony, creative.events, creative.dynamics, creative.transitions):
        if any(item.scene_id not in section_ids for item in collection):
            raise ScoreError("score events reference a Scene outside the current draft")
    instrument_ids = {instrument.instrument_id for instrument in creative.instruments}
    if any(event.instrument_id not in instrument_ids for event in creative.events):
        raise ScoreError("score events reference an unknown instrument")
    payload = {
        **creative.model_dump(mode="json"),
        "sections": [section.model_dump(mode="json") for section in sections],
        "source_timebase": SOURCE_TIMEBASE,
    }
    score = ScoreSpec(score_digest=canonical_json_hash(payload), **payload)
    resolved_sections = {section.scene_id: section for section in score.sections}
    resolved_instruments = {instrument.instrument_id: instrument for instrument in score.instruments}
    for harmony in score.harmony:
        _event_window(score, resolved_sections[harmony.scene_id], harmony.start_beat, harmony.duration_beats)
    for event in score.events:
        _event_window(score, resolved_sections[event.scene_id], event.start_beat, event.duration_beats)
        if resolved_instruments[event.instrument_id].kind not in {"kick", "hat"} and event.midi is None:
            raise ScoreError("tonal events need an explicit MIDI note")
    for transition in score.transitions:
        if _fraction(transition.fade_in_beats) < 0 or _fraction(transition.fade_out_beats) < 0:
            raise ScoreError("transition fades must be non-negative")
    return score


def authored_beat_grid(score: ScoreSpec) -> dict[str, Any]:
    """The composition's own source-time grid; no audio estimator is involved."""
    beat_samples = []
    beat_ticks = []
    period = Fraction(60 * score.sample_rate, 1) / score.bpm.fraction()
    index = 0
    while True:
        sample = quantize_ticks(index * period)
        if sample >= score.sample_count:
            break
        beat_samples.append(sample)
        beat_ticks.append(quantize_ticks(
            Fraction(sample, score.sample_rate) * score.source_timebase
        ))
        index += 1
    return {
        "origin": "authored",
        "bpm": score.bpm.model_dump(mode="json"),
        "meter": score.meter.model_dump(mode="json"),
        "sample_rate": score.sample_rate,
        "source_timebase": score.source_timebase,
        "beat_samples": beat_samples,
        "beats": beat_ticks,
    }


def _event_window(
    score: ScoreSpec,
    section: ScoreSection,
    start_beat: str,
    duration_beats: str,
) -> tuple[int, int]:
    start = _fraction(start_beat)
    duration = _fraction(duration_beats)
    if start < 0 or duration <= 0:
        raise ScoreError("event start must be non-negative and duration positive")
    seconds_per_beat = Fraction(60, 1) / score.bpm.fraction()
    first = section.start_sample + quantize_ticks(start * seconds_per_beat * score.sample_rate)
    end = section.start_sample + quantize_ticks((start + duration) * seconds_per_beat * score.sample_rate)
    if first < section.start_sample or end > section.end_sample or end <= first:
        raise ScoreError(f"an event escapes Scene {section.scene_id}; no sample truncation is allowed")
    return first, end


def _waveform(instrument: Instrument, phase: np.ndarray) -> np.ndarray:
    sine = np.sin(phase)
    if instrument.wave == "sine":
        return sine
    if instrument.wave == "triangle":
        return 2 / np.pi * np.arcsin(sine)
    if instrument.wave == "saw":
        cycles = phase / (2 * np.pi)
        return 2 * (cycles - np.floor(cycles + 0.5))
    return np.sign(sine)


def _envelope(length: int, attack: float, release: float, sample_rate: int) -> np.ndarray:
    result = np.ones(length, dtype=np.float64)
    attack_samples = min(length, max(1, round(attack * sample_rate)))
    release_samples = min(length, max(1, round(release * sample_rate)))
    result[:attack_samples] *= np.linspace(0, 1, attack_samples, endpoint=True)
    result[-release_samples:] *= np.linspace(1, 0, release_samples, endpoint=True)
    return result


def _add_signal(
    mix: np.ndarray,
    signal: np.ndarray,
    *,
    start: int,
    instrument: Instrument,
    velocity: float,
    channels: int,
) -> None:
    signal = signal * (10 ** (instrument.gain_db / 20)) * velocity
    if channels == 1:
        mix[start:start + len(signal), 0] += signal
        return
    left = math.sqrt((1 - instrument.pan) / 2)
    right = math.sqrt((1 + instrument.pan) / 2)
    mix[start:start + len(signal), 0] += signal * left
    mix[start:start + len(signal), 1] += signal * right


def _tone(
    score: ScoreSpec,
    instrument: Instrument,
    midi: int,
    length: int,
) -> np.ndarray:
    time = np.arange(length, dtype=np.float64) / score.sample_rate
    frequency = 440 * 2 ** ((midi - 69) / 12)
    signal = _waveform(instrument, 2 * np.pi * frequency * time)
    return signal * _envelope(
        length, instrument.attack_seconds, instrument.release_seconds, score.sample_rate
    )


def _percussion(
    score: ScoreSpec,
    instrument: Instrument,
    length: int,
    seed: int,
) -> np.ndarray:
    time = np.arange(length, dtype=np.float64) / score.sample_rate
    if instrument.kind == "kick":
        phase = 2 * np.pi * (44 * time + 58 * (1 - np.exp(-time * 32)) / 32)
        signal = np.sin(phase) * np.exp(-time * 9)
    else:
        rng = np.random.default_rng([score.seed, seed])
        noise = rng.standard_normal(length)
        signal = np.concatenate((np.zeros(1), np.diff(noise))) * np.exp(-time * 36)
    return signal * _envelope(length, 0.001, instrument.release_seconds, score.sample_rate)


def synthesize_score(score: ScoreSpec) -> bytes:
    """Render only declared electronic oscillators/noise; no samples or voices."""
    mix = np.zeros((score.sample_count, score.channels), dtype=np.float64)
    sections = {section.scene_id: section for section in score.sections}
    instruments = {instrument.instrument_id: instrument for instrument in score.instruments}
    percussion_index = 0
    for harmony in score.harmony:
        section = sections[harmony.scene_id]
        start, end = _event_window(score, section, harmony.start_beat, harmony.duration_beats)
        for instrument in instruments.values():
            if instrument.kind != "pad":
                continue
            for note in harmony.midi_notes:
                signal = _tone(score, instrument, note, end - start)
                signal /= math.sqrt(len(harmony.midi_notes))
                _add_signal(
                    mix, signal, start=start, instrument=instrument,
                    velocity=harmony.velocity, channels=score.channels,
                )
    for event in score.events:
        instrument = instruments[event.instrument_id]
        section = sections[event.scene_id]
        start, end = _event_window(score, section, event.start_beat, event.duration_beats)
        length = end - start
        if instrument.kind in {"kick", "hat"}:
            signal = _percussion(score, instrument, length, percussion_index)
            percussion_index += 1
        else:
            if event.midi is None:
                raise ScoreError("tonal events need an explicit MIDI note")
            signal = _tone(score, instrument, event.midi, length)
        _add_signal(
            mix, signal, start=start, instrument=instrument,
            velocity=event.velocity, channels=score.channels,
        )
    for section in score.sections:
        gain = np.ones(section.end_sample - section.start_sample, dtype=np.float64)
        for dynamic in score.dynamics:
            if dynamic.scene_id == section.scene_id:
                gain *= 10 ** (dynamic.gain_db / 20)
        for transition in score.transitions:
            if transition.scene_id != section.scene_id:
                continue
            seconds_per_beat = 60 / float(score.bpm.fraction())
            for beats, ascending in (
                (_fraction(transition.fade_in_beats), True),
                (_fraction(transition.fade_out_beats), False),
            ):
                length = min(len(gain), quantize_ticks(beats * seconds_per_beat * score.sample_rate))
                if length <= 0:
                    continue
                ramp = np.linspace(0, 1, length) if ascending else np.linspace(1, 0, length)
                if ascending:
                    gain[:length] *= ramp
                else:
                    gain[-length:] *= ramp
        mix[section.start_sample:section.end_sample] *= gain[:, None]
    peak = float(np.max(np.abs(mix))) if mix.size else 0
    if peak <= 1e-8:
        raise ScoreError("the score produced an empty or silent signal")
    if peak > 0.95:
        mix *= 0.95 / peak
    pcm = np.rint(np.clip(mix, -1, 1) * 32767).astype("<i2", copy=False)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(score.channels)
        wav.setsampwidth(2)
        wav.setframerate(score.sample_rate)
        wav.writeframes(np.ascontiguousarray(pcm).tobytes())
    return output.getvalue()


__all__ = [
    "MAX_SCORE_EVENTS",
    "SCORE_SCHEMA_VERSION",
    "SYNTH_VERSION",
    "HarmonyEvent",
    "Instrument",
    "Meter",
    "Rational",
    "ScoreDynamics",
    "ScoreError",
    "ScoreEvent",
    "ScoreSection",
    "ScoreSectionDraft",
    "ScoreSpec",
    "ScoreSpecDraft",
    "ScoreTransition",
    "authored_beat_grid",
    "build_score_spec",
    "synthesize_score",
]

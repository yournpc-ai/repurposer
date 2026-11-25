import { createPrng } from "./dsp.js";
import { SAMPLE_RATE, type SoundGraph, type SoundTune, type SoundParamSpec } from "./types.js";

function axis(unit: string, min: number, max: number, step: number, initial: number, description: string): SoundParamSpec {
  return { unit, min, max, step, default: initial, description };
}

export const TUNE_SCHEMA = {
  pitch_st: axis("st", -12, 12, 0.5, 0, "Transpose resonances in semitones."),
  tone_pct: axis("%", -100, 100, 1, 0, "Darken or brighten the spectrum."),
  length_scale: axis("×", 0.25, 3, 0.05, 1, "Stretch the envelope while preserving pitch."),
  space_pct: axis("%", -100, 100, 1, 0, "Adjust room send and stereo width."),
  punch_pct: axis("%", -100, 100, 1, 0, "Soften or sharpen the attack."),
  variation_pct: axis("%", 0, 100, 1, 0, "Introduce seeded performance variation."),
  volume_db: axis("dB", -24, 6, 0.5, 0, "Trim the mastered output."),
} satisfies Record<keyof SoundTune, SoundParamSpec>;

const clamp = (x: number, min: number, max: number) => Math.min(max, Math.max(min, x));
const hz = (x: number) => clamp(x, 1, SAMPLE_RATE * 0.46);

export function normalizeSoundTune(input: SoundTune = {}): Required<SoundTune> {
  for (const key of Object.keys(input)) {
    if (!Object.hasOwn(TUNE_SCHEMA, key)) throw new Error("Unknown tune parameter " + key);
  }
  const values = {} as Required<SoundTune>;
  for (const key of Object.keys(TUNE_SCHEMA) as (keyof SoundTune)[]) {
    const def = TUNE_SCHEMA[key];
    const value = input[key] === undefined ? def.default : input[key];
    if (!Number.isFinite(value)) throw new Error("Invalid tune parameter " + key);
    // The step is a control increment. Preserve sub-step precision for millisecond targeting.
    const bounded = clamp(value, def.min, def.max);
    values[key] = key === "length_scale" ? Math.round(bounded * 1e6) / 1e6
      : Math.round(bounded / def.step) * def.step;
  }
  return values;
}

export function applySoundTune(base: SoundGraph, input: SoundTune, seed: number): SoundGraph {
  const t = normalizeSoundTune(input);
  const graph = structuredClone(base);
  graph.durationMs = clamp(Math.round(base.durationMs * t.length_scale), 25, 12000);
  const scale = graph.durationMs / base.durationMs;
  const random = createPrng(seed ^ 0x9e3779b9);
  const jitter = () => (2 * random() - 1) * t.variation_pct;
  const brightness = 2 ** (t.tone_pct / 50);
  for (const l of graph.layers) {
    const pitch = 2 ** (t.pitch_st / 12 + jitter() * 0.45 / 1200);
    const color = brightness * (1 + jitter() * 0.0012);
    if (l.kind === "fm") {
      l.carrierFreqStart = hz(l.carrierFreqStart * pitch);
      if (l.carrierFreqEnd) l.carrierFreqEnd = hz(l.carrierFreqEnd * pitch);
    } else if (l.kind !== "noise") {
      l.freqStart = hz(l.freqStart * pitch);
      if (l.kind === "oscillator") {
        if (l.freqEnd) l.freqEnd = hz(l.freqEnd * pitch);
        if (l.pitchDecayRate) l.pitchDecayRate /= scale;
      }
    }
    if (l.filter) {
      const ratio = color * (l.filter.kind === "bandpass" ? pitch : 1);
      l.filter.freqStart = hz(l.filter.freqStart * ratio);
      if (l.filter.freqEnd) l.filter.freqEnd = hz(l.filter.freqEnd * ratio);
    }
    l.startMs = Math.max(0, (l.startMs ?? 0) * scale + jitter() * 0.024);
    if (l.durationMs) l.durationMs *= scale;
    if (t.variation_pct) {
      const pan = jitter() * 0.001;
      l.pan = { start: (l.pan?.start ?? 0) + pan, end: (l.pan?.end ?? l.pan?.start ?? 0) + pan };
    }
    const env = l.envelope;
    if (env.attackMs <= 12) l.gain *= 2 ** (t.punch_pct / 150);
    env.attackMs *= (env.attackMs <= 12 ? scale ** 0.35 : scale) * 2 ** (-t.punch_pct / 35);
    for (const key of ["riseMs", "holdMs", "decayMs", "releaseMs"] as const) {
      if (env[key] !== undefined) env[key] *= scale;
    }
  }
  const space = t.space_pct / 100;
  if (graph.reverb || space > 0) {
    const room = graph.reverb ?? { predelayMs: 4, decaySec: 0.42, dampHz: 3600, mix: 0 };
    room.mix = space < 0 ? room.mix * (1 + space) : room.mix + (0.76 - room.mix) * space;
    room.decaySec *= scale * 2 ** space;
    graph.reverb = room;
  }
  graph.width = (graph.width ?? 1) * (1 + space);
  if (graph.reflections) graph.reflections.amount *= 1 + space;
  if (graph.lowpass) graph.lowpass = hz(graph.lowpass * brightness);
  graph.tiltDb = t.tone_pct * 0.08;
  graph.drive = (graph.drive ?? 0) + Math.max(0, t.punch_pct) / 125;
  graph.volumeDb = t.volume_db;
  return graph;
}

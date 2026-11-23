export const SOUND_ENGINE_NAME = "repurposer-sound-engine" as const;
export const SOUND_ENGINE_VERSION = 2 as const;
export const SAMPLE_RATE = 48000 as const;
export const CHANNELS = 2 as const;

export type SoundDomain = "video" | "interface";

export type SoundCategory =
  | "motion"
  | "impact"
  | "riser"
  | "stinger"
  | "transition"
  | "drop"
  | "title"
  | "accent"
  | "ambience"
  | "tension"
  | "tap"
  | "select"
  | "toggle"
  | "feedback";

export type SyncCue = "onset" | "energy_peak" | "end_peak";

export interface CatalogMetadataHeader<TDomain extends string, TCategory extends string> {
  id: string;
  version: number;
  domain: TDomain;
  category: TCategory;
  name: string;
  desc: string;
  use_for: readonly string[];
  avoid: readonly string[];
}

export interface SoundParamSpec {
  unit: string;
  default: number;
  min: number;
  max: number;
  step: number;
  description: string;
}

export interface SoundRecipeCatalogEntry extends CatalogMetadataHeader<SoundDomain, SoundCategory> {
  suggested_duration_ms: readonly [number, number];
  sync_cue: SyncCue;
  mix_hint: string;
  params: Readonly<Record<string, SoundParamSpec>>;
}

export type FilterKind = "lowpass" | "highpass" | "bandpass" | "peaking" | "notch";

export interface FilterConfig {
  kind: FilterKind;
  freqStart: number;
  freqEnd?: number;
  q: number;
  curve?: number;
  gainDb?: number; // peaking EQ
}

export interface EnvelopeConfig {
  attackMs: number;
  riseMs?: number;
  holdMs?: number;
  decayMs?: number;
  attackCurve?: number;
  riseCurve?: number;
  decayCurve?: number;
  releaseCurve?: number;
  sustain?: number;
  releaseMs?: number;
  /** Optional symmetric or asymmetric bell curve exponent (e.g. whoosh) */
  bellPower?: number;
  /** Optional exponential crescendo power (e.g. riser) */
  risePower?: number;
}

export interface PanConfig {
  start: number; // -1 (left) .. +1 (right)
  end?: number;
}

export interface OscillatorLayer {
  kind: "oscillator";
  waveform: "sine" | "triangle" | "sawtooth" | "square";
  voices?: number;
  detune?: number; // cents from center to outermost voice
  curve?: number;
  gain: number;
  startMs?: number;
  durationMs?: number;
  freqStart: number;
  freqEnd?: number;
  /** Exponential pitch decay rate (1/s) from freqStart toward freqEnd */
  pitchDecayRate?: number;
  envelope: EnvelopeConfig;
  filter?: FilterConfig;
  pan?: PanConfig;
}

export interface NoiseLayer {
  kind: "noise";
  color?: "white" | "pink" | "brown";
  gain: number;
  startMs?: number;
  durationMs?: number;
  envelope: EnvelopeConfig;
  filter: FilterConfig;
  pan?: PanConfig;
}

export type Layer = OscillatorLayer | NoiseLayer;

export interface ReflectionTap {
  channel: 0 | 1;
  delayMs: number;
  gain: number;
}

export interface SoundGraph {
  durationMs: number;
  layers: Layer[];
  reflections?: {
    amount: number; // 0..1
    taps: readonly ReflectionTap[];
  };
  reverb?: { predelayMs: number; decaySec: number; dampHz: number; mix: number };
  width?: number; // M/S side gain, unity preserves the stereo image
  highpass?: number; // Hz, defaults to 24
  lowpass?: number; // Hz
  tailFadeMs?: number;
}

/**
 * Pure synthesis identity. Discovery metadata (name, desc, domain, category,
 * use_for, avoid) MUST NEVER enter this object so prompt/catalog edits never
 * invalidate audio caches.
 */
export interface SoundSynthesisSpec {
  engine: typeof SOUND_ENGINE_NAME;
  engine_version: typeof SOUND_ENGINE_VERSION;
  recipe_id: string;
  recipe_version: number;
  params: Record<string, number>;
  seed: number;
  sample_rate: typeof SAMPLE_RATE;
  channels: typeof CHANNELS;
}

export interface AcousticMetrics {
  sample_rate: typeof SAMPLE_RATE;
  channels: typeof CHANNELS;
  duration_ms: number;
  peak_offset_ms: number;
  peak_dbfs: number;
  rms_dbfs: number;
  lufs: number;
  spectral_centroid_hz: number;
  waveform_peaks: number[];
}

export interface SynthesisResult {
  left: Float32Array;
  right: Float32Array;
  sampleRate: typeof SAMPLE_RATE;
  channels: typeof CHANNELS;
  spec: SoundSynthesisSpec;
  acoustics: AcousticMetrics;
}

export interface WavSynthesisResult extends SynthesisResult {
  wav: Uint8Array;
}

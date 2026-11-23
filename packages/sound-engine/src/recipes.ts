import type {
  ReflectionTap,
  SoundGraph,
  SoundParamSpec,
  SoundRecipeCatalogEntry,
} from "./types.js";

export interface InternalSoundRecipe {
  catalog: SoundRecipeCatalogEntry;
  buildGraph: (params: Record<string, number>) => SoundGraph;
}

const STUDIO_REFLECTIONS: readonly ReflectionTap[] = [
  { channel: 0, delayMs: 11, gain: 0.30 },
  { channel: 1, delayMs: 17, gain: 0.26 },
  { channel: 0, delayMs: 30, gain: 0.13 },
  { channel: 1, delayMs: 39, gain: 0.14 },
];

const WIDE_REFLECTIONS: readonly ReflectionTap[] = [
  { channel: 0, delayMs: 16, gain: 0.28 },
  { channel: 1, delayMs: 24, gain: 0.25 },
  { channel: 0, delayMs: 44, gain: 0.15 },
  { channel: 1, delayMs: 57, gain: 0.14 },
];

const param = (
  unit: string,
  def: number,
  min: number,
  max: number,
  description: string,
  step = 1,
): SoundParamSpec => ({ unit, default: def, min, max, step, description });

const WHOOSH_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "whoosh",
    version: 1,
    domain: "video",
    category: "motion",
    name: "Air Whoosh",
    desc: "Clean directional air sweep that swells across the stereo field and dissipates softly.",
    use_for: ["kinetic title entrance", "product card slide-in", "scene motion cue"],
    avoid: ["static text hold", "realistic outdoor wind"],
    suggested_duration_ms: [320, 700],
    sync_cue: "energy_peak",
    mix_hint: "Align peak_offset_ms with fastest visual velocity; lower tone over sibilant narration.",
    params: {
      length: param("ms", 540, 180, 1100, "Total air sweep duration."),
      pitch: param("Hz", 410, 180, 760, "Center resonance of body airflow and subtle tonal glide."),
      tone: param("%", 54, 10, 90, "High-frequency air sheen; lower to sit cleanly under speech."),
      punch: param("%", 46, 15, 90, "Tightness of the central swell crest."),
      space: param("%", 64, 0, 100, "Stereo travel width and subtle spatial spread."),
    },
  },
  buildGraph(p) {
    const length = p.length;
    const pitch = p.pitch;
    const tone = p.tone / 100;
    const punch = p.punch / 100;
    const space = p.space / 100;
    const bellPower = 1.35 + punch * 1.1;
    const panSpan = 0.82 * space;

    return {
      durationMs: length,
      layers: [
        {
          kind: "noise",
          gain: 0.24,
          envelope: { attackMs: 10, bellPower },
          filter: {
            kind: "bandpass",
            freqStart: pitch * 0.65,
            freqEnd: pitch * (1.15 + 0.55 * space),
            q: 1.5,
          },
          pan: { start: -panSpan, end: panSpan },
        },
        {
          kind: "noise",
          gain: 0.14 + 0.16 * tone,
          envelope: { attackMs: 10, bellPower: bellPower + 0.7 },
          filter: {
            kind: "bandpass",
            freqStart: 950 + 1800 * tone,
            freqEnd: 1500 + 3000 * tone,
            q: 2.0,
          },
          pan: { start: -panSpan * 0.85, end: panSpan * 0.85 },
        },
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.045,
          freqStart: pitch * 0.48,
          freqEnd: pitch * (0.95 + 0.45 * space),
          envelope: { attackMs: 12, bellPower: bellPower + 0.2 },
          pan: { start: -panSpan * 0.6, end: panSpan * 0.6 },
        },
      ],
      reflections: { amount: 0.18 * space, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 8,
    };
  },
};

const IMPACT_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "impact",
    version: 1,
    domain: "video",
    category: "impact",
    name: "Soft Impact",
    desc: "Restrained tactile settle with warm low-end body and clean studio reflections.",
    use_for: ["title lock-in", "product card landing", "headline emphasis"],
    avoid: ["rapid UI clicks", "cinematic explosion"],
    suggested_duration_ms: [220, 560],
    sync_cue: "onset",
    mix_hint: "Align clip start (onset) with visual settle frame; lower pitch for deeper weight.",
    params: {
      pitch: param("Hz", 112, 48, 185, "Fundamental body resonance; lower values sound deeper and heavier."),
      punch: param("%", 48, 5, 95, "Initial transient attack sharpness and upper harmonic click."),
      tone: param("%", 44, 10, 90, "Brightness of the overtone and filtered thump."),
      length: param("ms", 380, 140, 820, "Low-end decay tail length."),
      space: param("%", 26, 0, 85, "Stereo early-reflection ambience."),
    },
  },
  buildGraph(p) {
    const pitch = p.pitch;
    const punch = p.punch / 100;
    const tone = p.tone / 100;
    const length = p.length;
    const space = p.space / 100;

    return {
      durationMs: length,
      layers: [
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.42,
          freqStart: pitch * (1.85 + 0.85 * punch),
          freqEnd: pitch,
          pitchDecayRate: 48 + 30 * punch,
          envelope: {
            attackMs: Math.max(1.2, 7.5 - 6.0 * punch),
            decayMs: Math.max(45, length * 0.30),
            sustain: 0,
            releaseMs: 18,
          },
        },
        {
          kind: "oscillator",
          waveform: "triangle",
          gain: (0.08 + 0.16 * punch) * (0.55 + 0.65 * tone),
          durationMs: Math.min(length, 120),
          freqStart: pitch * (2.6 + 1.1 * tone),
          freqEnd: pitch * 1.9,
          pitchDecayRate: 70,
          envelope: {
            attackMs: Math.max(0.6, 3.8 - 3.0 * punch),
            decayMs: 18 + 20 * tone,
            sustain: 0,
            releaseMs: 10,
          },
          filter: { kind: "lowpass", freqStart: 500 + 2600 * tone, q: 0.9 },
        },
        {
          kind: "noise",
          gain: 0.12 * punch * (0.4 + 0.8 * tone),
          durationMs: Math.min(length, 75),
          envelope: {
            attackMs: 0.8,
            decayMs: 14 + 14 * tone,
            sustain: 0,
            releaseMs: 8,
          },
          filter: { kind: "lowpass", freqStart: 420 + 2200 * tone, q: 0.8 },
        },
      ],
      reflections: { amount: space, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 8,
    };
  },
};

const CLICK_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "click",
    version: 1,
    domain: "interface",
    category: "tap",
    name: "Tactile Click",
    desc: "Crisp micro interface tap with subtle cavity resonance and zero harshness.",
    use_for: ["button tap", "cursor selection", "metric highlight"],
    avoid: ["scene transitions", "dramatic landings"],
    suggested_duration_ms: [45, 95],
    sync_cue: "onset",
    mix_hint: "Keep gain restrained (-12 to -8 dB) so rapid interactions never distract from speech.",
    params: {
      pitch: param("Hz", 840, 380, 1500, "Primary cavity resonance pitch."),
      punch: param("%", 54, 5, 95, "Attack crispness and short harmonic snap."),
      tone: param("%", 50, 10, 90, "Upper overtone brightness."),
      length: param("ms", 65, 32, 130, "Decay window of the tap."),
      space: param("%", 10, 0, 60, "Subtle room reflection amount."),
    },
  },
  buildGraph(p) {
    const pitch = p.pitch;
    const punch = p.punch / 100;
    const tone = p.tone / 100;
    const length = p.length;
    const space = p.space / 100;

    return {
      durationMs: length,
      layers: [
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.34,
          freqStart: pitch * 1.38,
          freqEnd: pitch,
          pitchDecayRate: 210,
          envelope: {
            attackMs: Math.max(0.5, 4.0 - 3.3 * punch),
            decayMs: Math.max(8, length * 0.22),
            sustain: 0,
            releaseMs: 6,
          },
        },
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.16 * punch * (0.45 + 0.75 * tone),
          durationMs: Math.min(length, 42),
          freqStart: pitch * 2.72,
          freqEnd: pitch * 2.35,
          pitchDecayRate: 240,
          envelope: {
            attackMs: 0.5,
            decayMs: 7 + 8 * tone,
            sustain: 0,
            releaseMs: 5,
          },
        },
        {
          kind: "noise",
          gain: 0.08 * punch,
          durationMs: Math.min(length, 18),
          envelope: { attackMs: 0.4, decayMs: 4, sustain: 0, releaseMs: 4 },
          filter: { kind: "bandpass", freqStart: 1400 + 2400 * tone, q: 1.6 },
        },
      ],
      reflections: { amount: space * 0.5, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 4,
    };
  },
};

const RISER_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "riser",
    version: 1,
    domain: "video",
    category: "riser",
    name: "Tension Riser",
    desc: "Smooth upward shimmer and harmonic swell building cleanly into a reveal cut.",
    use_for: ["pre-reveal build", "interface zoom anticipation", "transition lead-in"],
    avoid: ["after reveal", "background bed"],
    suggested_duration_ms: [600, 1600],
    sync_cue: "end_peak",
    mix_hint: "End clip right at the reveal frame so peak_offset_ms hands off into the impact or cut.",
    params: {
      length: param("ms", 1050, 400, 2400, "Build duration leading into the reveal."),
      pitch: param("Hz", 260, 140, 540, "Starting harmonic center of the upward sweep."),
      tone: param("%", 58, 15, 90, "Upper shimmer brightness at the climax."),
      punch: param("%", 55, 15, 90, "Steepness of the crescendo curve."),
      space: param("%", 42, 0, 90, "Stereo widening and reflection tail."),
    },
  },
  buildGraph(p) {
    const length = p.length;
    const pitch = p.pitch;
    const tone = p.tone / 100;
    const punch = p.punch / 100;
    const space = p.space / 100;
    const risePower = 1.4 + punch * 1.4;

    return {
      durationMs: length,
      layers: [
        {
          kind: "noise",
          gain: 0.24 * (0.55 + 0.65 * tone),
          envelope: { attackMs: 20, risePower },
          filter: {
            kind: "bandpass",
            freqStart: Math.max(200, pitch * 1.2),
            freqEnd: 1800 + 4200 * tone,
            q: 2.6,
          },
          pan: { start: -0.35 * space, end: 0.35 * space },
        },
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.14,
          freqStart: pitch,
          freqEnd: pitch * 2.0,
          envelope: { attackMs: 25, risePower: risePower * 0.9 },
          pan: { start: -0.2 * space, end: -0.35 * space },
        },
        {
          kind: "oscillator",
          waveform: "triangle",
          gain: 0.08 * tone,
          freqStart: pitch * 1.5,
          freqEnd: pitch * 3.0,
          envelope: { attackMs: 25, risePower: risePower * 1.1 },
          filter: { kind: "lowpass", freqStart: 900, freqEnd: 2400 + 2600 * tone, q: 1.0 },
          pan: { start: 0.2 * space, end: 0.35 * space },
        },
      ],
      reflections: { amount: 0.35 * space, taps: WIDE_REFLECTIONS },
      tailFadeMs: 10,
    };
  },
};

const STINGER_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "stinger",
    version: 1,
    domain: "video",
    category: "stinger",
    name: "Brand Stinger",
    desc: "Restrained institutional harmonic chime with crystalline overtones for logo or title lockups.",
    use_for: ["brand mark reveal", "opening statement accent", "closing lockup"],
    avoid: ["dense narration syllables", "frequent UI actions"],
    suggested_duration_ms: [480, 1200],
    sync_cue: "onset",
    mix_hint: "Place on open beat or title lockup; keep gain modest if BGM already has strong harmony.",
    params: {
      pitch: param("Hz", 330, 196, 587, "Root note frequency (330 Hz ≈ E4, 262 Hz ≈ C4)."),
      tone: param("%", 54, 15, 90, "Upper harmonic sheen and bell shimmer."),
      length: param("ms", 760, 350, 1500, "Resonant sustain tail."),
      punch: param("%", 46, 10, 90, "Attack clarity on the initial chime."),
      space: param("%", 48, 10, 90, "Stereo spread and early reflections."),
    },
  },
  buildGraph(p) {
    const pitch = p.pitch;
    const tone = p.tone / 100;
    const length = p.length;
    const punch = p.punch / 100;
    const space = p.space / 100;
    const attackMs = Math.max(1.5, 11 - 8.5 * punch);
    const spread = 0.45 * space;

    return {
      durationMs: length,
      layers: [
        // Root
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.22,
          freqStart: pitch,
          envelope: { attackMs, decayMs: length * 0.36, sustain: 0, releaseMs: 24 },
          pan: { start: 0 },
        },
        // Perfect fifth
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.14,
          startMs: 14,
          freqStart: pitch * 1.498,
          envelope: { attackMs: attackMs + 1, decayMs: length * 0.32, sustain: 0, releaseMs: 24 },
          pan: { start: -spread },
        },
        // Octave
        {
          kind: "oscillator",
          waveform: "triangle",
          gain: 0.08 + 0.08 * tone,
          startMs: 24,
          freqStart: pitch * 2.0,
          envelope: { attackMs: attackMs + 1.5, decayMs: length * 0.26, sustain: 0, releaseMs: 24 },
          filter: { kind: "lowpass", freqStart: 1200 + 3600 * tone, q: 0.8 },
          pan: { start: spread },
        },
        // Major ninth sparkle
        {
          kind: "oscillator",
          waveform: "sine",
          gain: 0.04 + 0.07 * tone,
          startMs: 36,
          freqStart: pitch * 2.245,
          envelope: { attackMs: attackMs + 2, decayMs: length * 0.22, sustain: 0, releaseMs: 20 },
          pan: { start: spread * 0.6, end: -spread * 0.6 },
        },
      ],
      reflections: { amount: 0.55 * space, taps: WIDE_REFLECTIONS },
      tailFadeMs: 14,
    };
  },
};

export const INTERNAL_SOUND_RECIPES: Readonly<Record<string, InternalSoundRecipe>> = {
  whoosh: WHOOSH_RECIPE,
  impact: IMPACT_RECIPE,
  click: CLICK_RECIPE,
  riser: RISER_RECIPE,
  stinger: STINGER_RECIPE,
};

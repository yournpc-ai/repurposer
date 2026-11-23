import type {
  EnvelopeConfig,
  Layer,
  NoiseLayer,
  OscillatorLayer,
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

function roomBus(space: number, predelayMs: number, decaySec: number, dampHz: number, wet: number) {
  return {
    width: 0.65 + space * 0.7,
    reverb: { predelayMs, decaySec, dampHz, mix: space * wet },
  };
}

const WHOOSH_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "whoosh",
    version: 2,
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
          color: "pink",
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
          waveform: "triangle",
          voices: 3,
          detune: 5,
          gain: 0.045,
          freqStart: pitch * 0.48,
          freqEnd: pitch * (0.95 + 0.45 * space),
          envelope: { attackMs: 12, bellPower: bellPower + 0.2 },
          pan: { start: -panSpan * 0.6, end: panSpan * 0.6 },
        },
      ],
      ...roomBus(space, 8, 0.32, 2800, 0.12),
      reflections: { amount: 0.18 * space, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 8,
    };
  },
};

const IMPACT_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "impact",
    version: 2,
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
          waveform: "sawtooth",
          voices: 2,
          detune: 3,
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
          color: "brown",
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
      ...roomBus(space, 5, 0.34, 1700, 0.16),
      reflections: { amount: space, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 8,
    };
  },
};

const CLICK_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "click",
    version: 2,
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
          waveform: "triangle",
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
          color: "pink",
          gain: 0.08 * punch,
          durationMs: Math.min(length, 18),
          envelope: { attackMs: 0.4, decayMs: 4, sustain: 0, releaseMs: 4 },
          filter: { kind: "bandpass", freqStart: 1400 + 2400 * tone, q: 1.6 },
        },
      ],
      ...roomBus(space, 0, 0.10, 3400, 0.08),
      reflections: { amount: space * 0.5, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 4,
    };
  },
};

const RISER_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "riser",
    version: 2,
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
          color: "pink",
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
          waveform: "sawtooth",
          voices: 4,
          detune: 7,
          gain: 0.08 * tone,
          freqStart: pitch * 1.5,
          freqEnd: pitch * 3.0,
          envelope: { attackMs: 25, risePower: risePower * 1.1 },
          filter: { kind: "lowpass", freqStart: 900, freqEnd: 2400 + 2600 * tone, q: 1.0 },
          pan: { start: 0.2 * space, end: 0.35 * space },
        },
      ],
      ...roomBus(space, 14, 0.46, 4200, 0.17),
      reflections: { amount: 0.35 * space, taps: WIDE_REFLECTIONS },
      tailFadeMs: 10,
    };
  },
};

const STINGER_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "stinger",
    version: 2,
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
          voices: 3,
          detune: 4,
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
      ...roomBus(space, 16, 0.72, 2900, 0.23),
      reflections: { amount: 0.55 * space, taps: WIDE_REFLECTIONS },
      tailFadeMs: 14,
    };
  },
};

const SWOOSH_CUT_RECIPE: InternalSoundRecipe = {
  catalog: {
    id: "swoosh_cut",
    version: 2,
    domain: "video",
    category: "transition",
    name: "Swoosh Cut",
    desc: "Compact symmetrical bidirectional air-and-body sweep designed specifically for crossfade scene cuts.",
    use_for: ["scene crossfade cut", "act-to-act handoff", "product view switch"],
    avoid: ["static holds", "consecutive cuts less than 2s apart"],
    suggested_duration_ms: [240, 420],
    sync_cue: "energy_peak",
    mix_hint: "Center peak_offset_ms right on the crossfade cut frame; keep gain -14 to -11 dB under narration.",
    params: {
      length: param("ms", 320, 200, 520, "Total symmetrical cut-sweep duration."),
      pitch: param("Hz", 520, 260, 920, "Center filter resonance of the cut body."),
      tone: param("%", 48, 12, 88, "Upper air sheen; reduce under sibilant speech."),
      punch: param("%", 56, 15, 92, "Tightness of the center crossing crest."),
      space: param("%", 52, 0, 90, "Stereo cross-panning width and subtle room tail."),
    },
  },
  buildGraph(p) {
    const length = p.length;
    const pitch = p.pitch;
    const tone = p.tone / 100;
    const punch = p.punch / 100;
    const space = p.space / 100;
    const bellPower = 2.0 + punch * 1.4;
    const panSpan = 0.68 * space;

    return {
      durationMs: length,
      layers: [
        // Symmetrical fast filtered air body sweeping upward then releasing cleanly
        {
          kind: "noise",
          color: "brown",
          gain: 0.28,
          envelope: { attackMs: 8, bellPower },
          filter: {
            kind: "bandpass",
            freqStart: pitch * 0.72,
            freqEnd: pitch * (1.55 + 0.45 * tone),
            q: 2.1,
          },
          pan: { start: -panSpan, end: panSpan },
        },
        // Subtle crisp center shimmer for editorial precision
        {
          kind: "noise",
          gain: 0.12 + 0.14 * tone,
          envelope: { attackMs: 6, bellPower: bellPower + 0.9 },
          filter: {
            kind: "bandpass",
            freqStart: 1200 + 1600 * tone,
            freqEnd: 1800 + 2600 * tone,
            q: 2.4,
          },
          pan: { start: panSpan * 0.5, end: -panSpan * 0.5 },
        },
        // Soft warm tonal breath anchoring the cut midpoint
        {
          kind: "oscillator",
          waveform: "triangle",
          voices: 2,
          detune: 6,
          gain: 0.085 * (0.65 + 0.5 * punch),
          freqStart: pitch * 0.42,
          freqEnd: pitch * 0.78,
          envelope: { attackMs: 10, bellPower: bellPower + 0.3 },
          pan: { start: -panSpan * 0.4, end: panSpan * 0.4 },
        },
      ],
      ...roomBus(space, 4, 0.22, 3200, 0.11),
      reflections: { amount: 0.14 * space, taps: STUDIO_REFLECTIONS },
      tailFadeMs: 8,
    };
  },
};

// Each instrument specifies its resonances and timing in musical terms. The
// three shared controls edit the duration, resonant center and room send.
type Range = readonly [initial: number, min: number, max: number];

function instrument(
  id: string, name: string, category: SoundRecipeCatalogEntry["category"],
  cue: SoundRecipeCatalogEntry["sync_cue"], description: string, use: string,
  length: Range, pitch: Range, space: number,
  layers: (ms: number, hz: number) => Layer[],
): InternalSoundRecipe {
  const ui = ["tap", "toggle", "select", "feedback"].includes(category);
  const catalog: SoundRecipeCatalogEntry = {
    id, version: 2, domain: ui ? "interface" : "video", category, name,
    desc: description, use_for: [use], avoid: [ui ? "continuous pointer movement" : "static narration"],
    suggested_duration_ms: [length[1], length[2]], sync_cue: cue,
    mix_hint: "Use sparingly at −14 to −10 dB under narration.",
    params: {
      length: param("ms", ...length, "Duration including the release."),
      pitch: param("Hz", ...pitch, "Resonant center of the instrument."),
      space: param("%", space, 0, 100, "Room send and stereo width."),
    },
  };
  return {
    catalog,
    buildGraph(p) {
      return {
        durationMs: p.length, layers: layers(p.length, p.pitch),
        ...roomBus(p.space / 100, ui ? 1 : 9, Math.min(0.84, p.length / 1300), ui ? 3700 : 2700, ui ? 0.13 : 0.25),
        tailFadeMs: Math.min(32, p.length * 0.13),
      };
    },
  };
}

function note(
  waveform: OscillatorLayer["waveform"], hz: number, gain: number,
  envelope: EnvelopeConfig, options: Partial<Omit<OscillatorLayer, "kind" | "waveform" | "freqStart" | "gain" | "envelope">> = {},
): OscillatorLayer {
  return { kind: "oscillator", waveform, freqStart: hz, gain, envelope, ...options };
}

function breath(
  color: NoiseLayer["color"], gain: number, filter: NoiseLayer["filter"],
  envelope: EnvelopeConfig, options: Pick<NoiseLayer, "pan" | "startMs" | "durationMs"> = {},
): NoiseLayer {
  return { kind: "noise", color, gain, filter, envelope, ...options };
}

const instruments = [
  instrument("sub_swell", "Sub Swell", "riser", "end_peak",
    "Low bowed octave rising gently into an opening frame.", "opening title reveal",
    [920, 420, 2000], [68, 45, 110], 29, (ms, hz) => [
      note("sine", hz * 0.68, 0.48, { attackMs: 20, risePower: 1.55, releaseMs: ms * 0.043 }, { freqEnd: hz, curve: 0.72 }),
      note("triangle", hz * 1.6, 0.12, { attackMs: 35, risePower: 2.2 }, { freqEnd: hz * 2, voices: 3, detune: 6 }),
    ]),
  instrument("shimmer_lift", "Shimmer Lift", "riser", "end_peak",
    "A climbing fifth with a fine, diffuse high register.", "reveal anticipation",
    [1150, 510, 1900], [480, 290, 720], 64, (_ms, hz) => [
      note("triangle", hz, 0.24, { attackMs: 16, risePower: 1.5 }, { freqEnd: hz * 1.5, voices: 3, detune: 4 }),
      note("sine", hz * 2, 0.14, { attackMs: 30, risePower: 2.8 }, { freqEnd: hz * 3.01, pan: { start: -0.3, end: 0.32 } }),
      breath("pink", 0.19, { kind: "bandpass", freqStart: hz * 2, freqEnd: hz * 8, q: 0.85, curve: 1.4 }, { attackMs: 12, risePower: 2 }),
    ]),
  instrument("deep_hit", "Deep Hit", "impact", "onset",
    "A felted bass strike with a brief grain of contact.", "anchor a chapter heading",
    [530, 240, 960], [67, 48, 105], 38, (ms, hz) => [
      note("sine", hz * 2.7, 0.49, { attackMs: 3, decayMs: ms * 0.16 }, { freqEnd: hz, pitchDecayRate: 48 }),
      breath("brown", 0.2, { kind: "bandpass", freqStart: hz * 5, q: 1 }, { attackMs: 2, decayMs: 17 }),
    ]),
  instrument("sub_drop", "Sub Drop", "drop", "onset",
    "A falling low register leaves space after a change of argument.", "pain-point pivot",
    [660, 300, 1250], [105, 74, 165], 22, (ms, hz) => [
      note("sine", hz * 1.45, 0.46, { attackMs: 5, decayMs: ms * 0.26 }, { freqEnd: hz * 0.39, curve: 0.64 }),
      note("triangle", hz * 2.9, 0.13, { attackMs: 2, decayMs: ms * 0.10 }, { freqEnd: hz * 0.8, curve: 0.62 }),
    ]),
  instrument("kinetic_thud", "Kinetic Thud", "impact", "onset",
    "Two close contacts suggest a panel seating in its frame.", "product panel landing",
    [270, 140, 520], [147, 85, 220], 23, (ms, hz) => [
      note("triangle", hz * 1.6, 0.35, { attackMs: 1.8, decayMs: ms * 0.15 }, { freqEnd: hz, pitchDecayRate: 90 }),
      note("sine", hz * 0.75, 0.22, { attackMs: 2, decayMs: ms * 0.11 }, { startMs: 14 }),
      breath("pink", 0.16, { kind: "lowpass", freqStart: hz * 9, q: 0.72 }, { attackMs: 1, decayMs: 8 }),
    ]),
  instrument("velvet_pass", "Velvet Pass", "transition", "energy_peak",
    "A dark fabric-like sweep crosses the frame.", "soft lateral crossfade",
    [510, 240, 920], [340, 195, 580], 71, (_ms, hz) => [
      breath("pink", 0.5, { kind: "lowpass", freqStart: hz, freqEnd: hz * 3.3, q: 0.8 }, { attackMs: 10, bellPower: 3.6 }, { pan: { start: -0.72, end: 0.72 } }),
      note("sine", hz * 0.51, 0.18, { attackMs: 6, bellPower: 2.8 }, { freqEnd: hz * 0.72, voices: 2, detune: 5 }),
    ]),
  instrument("page_turn", "Page Turn", "transition", "energy_peak",
    "A papery lift followed by the short brush of a settling leaf.", "document page change",
    [365, 210, 680], [1300, 780, 2300], 43, (ms, hz) => [
      breath("pink", 0.55, { kind: "bandpass", freqStart: hz * 0.6, freqEnd: hz * 2.4, q: 0.75 }, { attackMs: 5, bellPower: 2.2 }, { durationMs: ms * 0.89, pan: { start: -0.55, end: 0.36 } }),
      breath("white", 0.29, { kind: "bandpass", freqStart: hz * 2.3, freqEnd: hz, q: 1.3 }, { attackMs: 6, bellPower: 3 }, { startMs: ms * 0.42, durationMs: ms * 0.29, pan: { start: 0.32 } }),
    ]),
  instrument("title_bloom", "Title Bloom", "title", "energy_peak",
    "A slowly voiced open fifth comes into focus under a headline.", "opening title",
    [780, 400, 1350], [220, 147, 350], 56, (ms, hz) => [
      note("triangle", hz, 0.33, { attackMs: ms * 0.2, riseMs: ms * 0.21, riseCurve: 1.4, holdMs: ms * 0.035, decayMs: ms * 0.13 }, { voices: 3, detune: 4 }),
      note("sine", hz * 1.5, 0.16, { attackMs: 12, bellPower: 2.8 }, { pan: { start: 0.28 } }),
    ]),
  instrument("metric_chime", "Metric Chime", "accent", "onset",
    "A measured glass strike with a short, clear upper partial.", "data-card arrival",
    [460, 230, 800], [659, 370, 990], 36, (ms, hz) => [
      note("sine", hz, 0.32, { attackMs: 3, decayMs: ms * 0.24 }),
      note("sine", hz * 2.41, 0.11, { attackMs: 1.4, decayMs: ms * 0.09 }, { voices: 2, detune: 3 }),
    ]),
  instrument("callout_ping", "Callout Ping", "accent", "onset",
    "A single narrow focus tone settles a few cents downward.", "selection box focus",
    [235, 115, 470], [910, 520, 1400], 19, (ms, hz) => [
      note("sine", hz * 1.045, 0.4, { attackMs: 3.5, decayMs: ms * 0.16 }, { freqEnd: hz, pitchDecayRate: 70 }),
      note("sine", hz * 1.99, 0.055, { attackMs: 2, decayMs: 13 }),
    ]),
  instrument("studio_air", "Studio Air", "ambience", "energy_peak",
    "A brief pocket of room air with a soft center and quiet edges.", "pause before an interview reveal",
    [1550, 700, 2800], [330, 190, 610], 78, (_ms, hz) => [
      ...[-0.7, 0.7].map(start => breath("pink", 0.32, { kind: "lowpass", freqStart: hz * 3.7, q: 0.68 }, { attackMs: 30, bellPower: 3.2 }, { pan: { start } })),
      breath("brown", 0.16, { kind: "bandpass", freqStart: hz, q: 0.72 }, { attackMs: 22, bellPower: 2.6 }),
    ]),
  instrument("pulse_bed", "Pulse Bed", "tension", "energy_peak",
    "Five muted pulses grow toward a central editorial beat.", "brief analytical pause",
    [1380, 720, 2300], [109, 70, 172], 33, (ms, hz) =>
      [0.20, 0.46, 1, 0.50, 0.24].map((gain, i) =>
        note("triangle", hz * 1.18, gain * 0.38, { attackMs: 8, decayMs: ms * 0.049 },
          { startMs: ms * (0.065 + i * 0.19), durationMs: ms * 0.17, freqEnd: hz, pitchDecayRate: 43 }))),
  instrument("soft_pop", "Soft Pop", "tap", "onset",
    "A rounded descending bubble for a light press.", "button press",
    [96, 55, 185], [425, 275, 740], 12, (ms, hz) => [
      note("sine", hz * 1.75, 0.37, { attackMs: 1.7, decayMs: ms * 0.16 }, { freqEnd: hz * 0.78, pitchDecayRate: 85 }),
    ]),
  instrument("toggle_on", "Toggle On", "toggle", "onset",
    "A compact upward latch with a softer answering contact.", "enable a switch",
    [138, 85, 220], [540, 330, 820], 14, (ms, hz) => [
      note("triangle", hz, 0.34, { attackMs: 2, decayMs: ms * 0.11 }),
      note("sine", hz * 1.5, 0.24, { attackMs: 2, decayMs: ms * 0.13 }, { startMs: ms * 0.22 }),
    ]),
  instrument("select_tick", "Select Tick", "select", "onset",
    "A dry pin-sized contact with a hollow wooden resonance.", "single item selection",
    [64, 38, 112], [1120, 630, 1780], 7, (ms, hz) => [
      note("square", hz, 0.21, { attackMs: 0.8, decayMs: ms * 0.095 }, { filter: { kind: "lowpass", freqStart: hz * 1.9, q: 0.72 } }),
      breath("pink", 0.18, { kind: "bandpass", freqStart: hz * 2.1, q: 1.2 }, { attackMs: 0.6, decayMs: 4 }),
    ]),
  instrument("confirm_chime", "Confirm Chime", "feedback", "onset",
    "Two consonant notes resolve upward on completion.", "successful form submission",
    [340, 180, 590], [523, 349, 784], 32, (ms, hz) => [
      note("sine", hz, 0.34, { attackMs: 3, decayMs: ms * 0.13 }),
      note("triangle", hz * 1.25, 0.24, { attackMs: 3.5, decayMs: ms * 0.19 }, { startMs: ms * 0.20, voices: 2, detune: 2.5 }),
    ]),
];

export const INTERNAL_SOUND_RECIPES: Readonly<Record<string, InternalSoundRecipe>> = {
  whoosh: WHOOSH_RECIPE,
  impact: IMPACT_RECIPE,
  click: CLICK_RECIPE,
  riser: RISER_RECIPE,
  stinger: STINGER_RECIPE,
  swoosh_cut: SWOOSH_CUT_RECIPE,
  ...Object.fromEntries(instruments.map(recipe => [recipe.catalog.id, recipe])),
};

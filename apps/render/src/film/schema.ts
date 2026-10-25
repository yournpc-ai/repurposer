import { z } from "zod";

/**
 * film-spec — the second spec family (peer of clip-spec, ADR-016 contract law
 * unchanged: the spec describes WHAT, zero renderer concepts; the renderer is
 * a black box that reads no DB and resolves no URLs).
 *
 * A film spec is a storyboard: an ordered scene list over a canvas whose
 * dimensions key on ``aspect`` (16:9 / 1:1 / 9:16, all @30fps). The LLM
 * authors the storyboard upstream; this schema is the
 * render-side boundary and stays MINIMAL ON PURPOSE — shape only. Semantic
 * grounding (on-screen strings quoted from the research manifest, camera
 * focus within [0,1]³, per-screen copy caps, scene-count/duration ranges)
 * is the orchestration-side grounding validator's seat. One law, one seat:
 * do not re-declare content constraints here.
 *
 * Duration contract: scenes carry integer FRAMES, already allocated upstream
 * (deterministic frame allocation — fixed fps, total = Σ scene frames). The
 * renderer never derives or re-rounds durations; it sums integers.
 */

const themeSchema = z.object({
  canvas: z.string(),
  ink: z.string(),
  // Reserved for scene variants; the current component vocabulary renders
  // the monochrome pair above (accent = inverted ink/canvas chip).
  accent: z.string().optional(),
  accent2: z.string().optional(),
});

/** Integer frames for this scene (fps is fixed at 30 — see Root.tsx). */
const frames = { frames: z.number().int().positive() };

/** Independent scene-relative subtitle cues and shared visual style.
 * Audio is optional and never creates subtitles implicitly. */
export const subtitleTrackSchema = z.object({
  cues: z.array(z.object({
    at: z.number().finite().nonnegative(),
    end: z.number().finite().positive(),
    text: z.string().trim().min(1),
  }).strict()).min(1),
  style: z.object({
    color: z.string().regex(/^#[0-9a-fA-F]{6}$/).default("#FFFFFF"),
    background: z.string().regex(/^#[0-9a-fA-F]{6}$/).default("#000000"),
    font_size: z.number().finite().min(12).max(120).default(34),
    font_weight: z.union([z.literal(400), z.literal(500), z.literal(600), z.literal(700), z.literal(800)]).default(600),
    bottom: z.number().finite().min(0).max(0.8).default(0.04),
    width: z.number().finite().positive().max(1).default(0.8),
    enter: z.enum(["none", "fade", "rise"]).default("fade"),
    exit: z.enum(["none", "fade"]).default("fade"),
    fade_seconds: z.number().finite().positive().max(2).default(0.2),
  }).strict().default({}),
}).strict().superRefine((track, ctx) => {
  track.cues.forEach((cue, i) => {
    if (cue.end <= cue.at || (i > 0 && cue.at < track.cues[i - 1].end)) {
      ctx.addIssue({code: z.ZodIssueCode.custom, message: "Subtitle cues must be ordered, nonoverlapping, with end > at"});
    }
  });
});
export type SubtitleTrack = z.infer<typeof subtitleTrackSchema>;
export type SubtitleCue = SubtitleTrack["cues"][number];
const narration = {
  audio: z.string().nullish(),
  subtitle_track: subtitleTrackSchema.nullish(),
};

const wordsScene = z.object({
  type: z.literal("words"),
  ...frames,
  ...narration,
  dark: z.boolean(),
  lines: z.array(z.string()).min(1),
  // Text-plane vocabulary (ADR-138 §7.6 — closed enums, renderer-implemented):
  // motion = camera move on the text plane (absent = static); enter = the
  // text's entrance rhythm ("lines" = per-line stagger, the pre-vocabulary
  // default; "words" = word-by-word).
  motion: z.enum(["static", "push", "pull"]).nullish(),
  enter: z.enum(["lines", "words"]).nullish(),
  // Batch B precise timing (scene-relative seconds, quantized to frames with
  // floor(seconds * fps + 0.5 + 1e-9)). Absent keys keep the legacy formulas;
  // explicit zero is a real value. enter_* schedules the selected unit:
  // word tokens for enter="words", whole lines for enter="lines"/absent
  // (unparameterized lines keep their legacy 8-frame stagger). The motion
  // window requires motion push/pull (the backend validator owns the concrete
  // conflict report). An explicit enter_hold_until is a HARD endpoint: the
  // text leaves at that frame (with exit_duration it fades out across that
  // final window; without it the hold simply ends);
  // absent = hold to the scene end.
  enter_start: z.number().finite().nonnegative().nullish(),
  enter_interval: z.number().finite().nonnegative().nullish(),
  enter_duration: z.number().finite().nonnegative().nullish(),
  enter_hold_until: z.number().finite().nonnegative().nullish(),
  motion_start: z.number().finite().nonnegative().nullish(),
  motion_end: z.number().finite().nonnegative().nullish(),
  // Exit fade (seconds, quantized with the same formula): the words fade
  // out over this window ending at the hold endpoint (enter_hold_until,
  // absent = the scene end). The BACKGROUND never fades — only the text.
  exit_duration: z.number().finite().positive().nullish(),
  // The push/pull move's scale amplitude (default 1.06; subtle ≈ 1.02–1.04).
  // Requires motion push/pull (the backend validator owns the conflict).
  motion_scale: z.number().gt(1).max(1.25).nullish(),
  // Presentation knobs (absent = the legacy look): align "center" centers
  // the text block; size picks the font tier (medium = the legacy 168px);
  // accent_style "color" renders *emphasis* spans in the theme accent
  // instead of the inverted chip.
  align: z.enum(["left", "center"]).nullish(),
  size: z.enum(["small", "medium", "large"]).nullish(),
  accent_style: z.enum(["chip", "color"]).nullish(),
  // The entrance EFFECT (orthogonal to enter's organization): "rise" = the
  // legacy fade+rise+blur; "fade" = opacity only; "slide" = deterministic
  // translate-only motion with exact endpoints, no opacity ramp or blur.
  enter_style: z.enum(["rise", "fade", "slide"]).nullish(),
}).strict();

const heroScene = z.object({
  type: z.literal("hero"),
  ...frames,
  ...narration,
  word: z.string(),
  sub: z.string(),
}).strict();

const uiScene = z.object({
  type: z.literal("ui"),
  ...frames,
  ...narration,
  // Absolute image URL (baked upstream from the captured page screenshot);
  // staged to loopback before render. Never a bundle-relative path.
  image: z.string(),
  // Display text inside the browser chrome address pill (not fetched).
  url: z.string(),
  // true = the page inside a browser-chrome card (the "this is a real page"
  // beat); false = full-bleed — the camera fills the canvas with the page
  // itself (the immersive push). Default true for pre-flag persisted specs.
  frame: z.boolean().default(true),
  // Camera plan: `at` in seconds from scene start; x/y/zoom are plain
  // numbers here — the [0,1]³ bounds check lives in the grounding validator.
  focuses: z
    .array(z.object({ at: z.number(), x: z.number(), y: z.number(), zoom: z.number() }))
    .min(1),
}).strict();

const dividerScene = z.object({
  type: z.literal("divider"),
  ...frames,
  ...narration,
  index: z.string(),
  label: z.string(),
  roll: z.array(z.string()).min(1),
}).strict();

/**
 * The numbers beat: 2–4 glass cards over a calm procedural backdrop. A
 * card's `big` is the number/short mark (null = a phrase card — the label
 * carries it). The backdrop is a named deterministic gradient, never an
 * image asset — nothing to stage.
 */
const plateScene = z.object({
  type: z.literal("plate"),
  ...frames,
  ...narration,
  title: z.string(),
  cards: z.array(z.object({ big: z.string().nullable(), label: z.string() })).min(1),
  backdrop: z.enum(["aurora", "dunes", "mist", "tide"]),
}).strict();

const revealScene = z.object({
  type: z.literal("reveal"),
  ...frames,
  ...narration,
  lead: z.string(),
  // The split reveal (lead → beat pause → word): the lead holds alone, then
  // fades out one REAL beat interval (the bed's bpm / beats grid — ADR-130)
  // before the word lands at this frame; the spec builder snaps the onset
  // onto the music grid. Pre-split persisted specs read as 1.6s.
  lead_frames: z.number().int().positive().default(48),
  word: z.string(),
  sub: z.string(),
}).strict();

/**
 * The composition scene (ADR-140): media elements (a video SOURCE range
 * played inside an OUTPUT window / a placed image) plus independently timed
 * text elements, composited over the scene's polarity background. Every
 * element carries a placement rect (normalized canvas fractions) and a z
 * (paint order, ascending). Two time spaces, never conflated: source
 * seconds (source_start/source_end) vs scene-relative output seconds
 * (at/until/duration). A text element's enter/motion timing is
 * ELEMENT-WINDOW-relative seconds — quantized with the same
 * seconds→frames formula as the words plane; its window's end (until,
 * absent = scene end) IS the leave moment — with exit_duration the text
 * fades out across that final window, without it the window simply ends
 * (no enter_hold_until on an element — `until` plays that role). A video element whose play window ends LEAVES the
 * screen — no freeze frame; keep_audio is the explicit original-sound
 * switch (the source trim and the audio trim are one cut).
 */
const elementRect = z.object({
  x: z.number().min(0).max(1),
  y: z.number().min(0).max(1),
  w: z.number().positive().max(1),
  h: z.number().positive().max(1),
});
const FULL_RECT = { x: 0, y: 0, w: 1, h: 1 };

const videoElement = z.object({
  kind: z.literal("video"),
  id: z.string().nullish(),
  // Absolute video URL (baked upstream from the asset); staged to loopback
  // before render. Never a bundle-relative path.
  src: z.string(),
  source_start: z.number().min(0),
  source_end: z.number().positive(),
  // Scene-relative output start; duration = the play window (absent = the
  // full source range).
  at: z.number().min(0).default(0),
  duration: z.number().positive().nullish(),
  rect: elementRect.default(FULL_RECT),
  fit: z.enum(["cover", "contain"]).default("cover"),
  keep_audio: z.boolean().default(false),
  z: z.number().int().default(0),
});

const imageElement = z.object({
  kind: z.literal("image"),
  id: z.string().nullish(),
  src: z.string(),
  at: z.number().min(0).default(0),
  until: z.number().positive().nullish(),
  rect: elementRect.default(FULL_RECT),
  fit: z.enum(["cover", "contain"]).default("cover"),
  z: z.number().int().default(0),
});

const textElement = z.object({
  kind: z.literal("text"),
  id: z.string().nullish(),
  lines: z.array(z.string()).min(1),
  // Ink polarity: light = light text over the composition (the words
  // plane's dark-scene twin; accent chips invert the same way); accent =
  // the whole block renders in the theme accent color.
  tone: z.enum(["light", "dark", "accent"]).default("light"),
  at: z.number().min(0).default(0),
  until: z.number().positive().nullish(),
  rect: elementRect.default(FULL_RECT),
  enter: z.enum(["lines", "words"]).nullish(),
  motion: z.enum(["static", "push", "pull"]).nullish(),
  enter_start: z.number().finite().nonnegative().nullish(),
  enter_interval: z.number().finite().nonnegative().nullish(),
  enter_duration: z.number().finite().nonnegative().nullish(),
  motion_start: z.number().finite().nonnegative().nullish(),
  motion_end: z.number().finite().nonnegative().nullish(),
  // The words plane's exit/motion-scale/style knobs, element-scoped
  // (element-window-relative seconds; absent = the legacy look).
  exit_duration: z.number().finite().positive().nullish(),
  motion_scale: z.number().gt(1).max(1.25).nullish(),
  align: z.enum(["left", "center"]).nullish(),
  size: z.enum(["small", "medium", "large"]).nullish(),
  accent_style: z.enum(["chip", "color"]).nullish(),
  // The entrance EFFECT (orthogonal to enter's organization): "rise" = the
  // legacy fade+rise+blur; "fade" = opacity only; "slide" = deterministic
  // translate-only motion with exact endpoints, no opacity ramp or blur.
  enter_style: z.enum(["rise", "fade", "slide"]).nullish(),
  z: z.number().int().default(0),
});

const compositeElement = z.discriminatedUnion("kind", [
  videoElement,
  imageElement,
  textElement,
]);

const compositeScene = z.object({
  type: z.literal("composite"),
  ...frames,
  ...narration,
  dark: z.boolean().default(false),
  elements: z.array(compositeElement).min(1),
}).strict();

const endScene = z.object({
  type: z.literal("end"),
  ...frames,
  ...narration,
  name: z.string(),
  tagline: z.string(),
  url: z.string(),
  // Absolute URL of the brand mark shown next to `name`; absent = text-only.
  logo_url: z.string().nullish(),
}).strict();

export const filmSceneSchema = z.discriminatedUnion("type", [
  wordsScene,
  heroScene,
  uiScene,
  dividerScene,
  plateScene,
  revealScene,
  compositeScene,
  endScene,
]).superRefine((scene, ctx) => {
  if (scene.subtitle_track?.cues.some(cue => cue.end > scene.frames / 30 + 1e-9)) {
    ctx.addIssue({code: z.ZodIssueCode.custom, message: "Subtitle cues exceed the scene duration"});
  }
});

export const filmSpecSchema = z.object({
  family: z.literal("film"),
  // LLM-chosen storyboard name (two-source display-copy law). Null-read
  // tolerant: null reads as absent, never a render failure.
  name: z.string().nullish(),
  theme: themeSchema,
  // Canvas aspect + frame rate (16:9 @30fps default) — calculateMetadata
  // reads ``aspect``; fps is pinned by the Composition and this literal, so
  // the spec still carries its own timing contract for every consumer.
  aspect: z.enum(["16:9", "1:1", "9:16"]).default("16:9"),
  fps: z.literal(30).default(30),
  // The background-music bed: absolute URL + gain (clip-spec's ClipMusic
  // semantics, minus the id — the film-spec resolves upstream). BPM/beats
  // ride as the timing provenance the cut was snapped against; the renderer
  // needs no re-analysis. Absent = no bed.
  music: z
    .object({
      url: z.string(),
      gain_db: z.number(),
      bpm: z.number().positive().optional(),
      beats: z.array(z.number()).optional(),
    })
    .nullish(),
  // Provenance digests (ADR-129): the presented storyboard's content digest
  // and the execution snapshot's digest this spec was built from — 呈现稿
  // digest = run context digest = render spec digest, one truth. Absent on
  // specs built before versioning.
  provenance: z
    .object({
      storyboard_digest: z.string().optional(),
      execution_digest: z.string().optional(),
    })
    .nullish(),
  scenes: z.array(filmSceneSchema).min(1),
});

export type FilmSpec = z.infer<typeof filmSpecSchema>;
export type FilmScene = z.infer<typeof filmSceneSchema>;
export type CompositeElement = z.infer<typeof compositeElement>;
export type FilmTheme = z.infer<typeof themeSchema>;

/** Total duration in frames = Σ scene frames (allocation is upstream). */
export function filmTotalFrames(spec: FilmSpec): number {
  return spec.scenes.reduce((acc, s) => acc + s.frames, 0);
}

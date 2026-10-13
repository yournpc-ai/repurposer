import { z } from "zod";

/**
 * film-spec — the second spec family (peer of clip-spec, ADR-016 contract law
 * unchanged: the spec describes WHAT, zero renderer concepts; the renderer is
 * a black box that reads no DB and resolves no URLs).
 *
 * A film spec is a storyboard: an ordered scene list over a fixed 1920×1080@30
 * canvas. The LLM authors the storyboard upstream; this schema is the
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

const wordsScene = z.object({
  type: z.literal("words"),
  ...frames,
  dark: z.boolean(),
  lines: z.array(z.string()).min(1),
});

const heroScene = z.object({
  type: z.literal("hero"),
  ...frames,
  word: z.string(),
  sub: z.string(),
});

const uiScene = z.object({
  type: z.literal("ui"),
  ...frames,
  // Absolute image URL (baked upstream from the captured page screenshot);
  // staged to loopback before render. Never a bundle-relative path.
  image: z.string(),
  // Display text inside the browser chrome address pill (not fetched).
  url: z.string(),
  // Camera plan: `at` in seconds from scene start; x/y/zoom are plain
  // numbers here — the [0,1]³ bounds check lives in the grounding validator.
  focuses: z
    .array(z.object({ at: z.number(), x: z.number(), y: z.number(), zoom: z.number() }))
    .min(1),
  captions: z.array(z.object({ at: z.number(), text: z.string() })).default([]),
});

const dividerScene = z.object({
  type: z.literal("divider"),
  ...frames,
  index: z.string(),
  label: z.string(),
  roll: z.array(z.string()).min(1),
});

const revealScene = z.object({
  type: z.literal("reveal"),
  ...frames,
  lead: z.string(),
  word: z.string(),
  sub: z.string(),
});

const endScene = z.object({
  type: z.literal("end"),
  ...frames,
  name: z.string(),
  tagline: z.string(),
  url: z.string(),
  // Absolute URL of the brand mark shown next to `name`; absent = text-only.
  logo_url: z.string().nullish(),
});

export const filmSceneSchema = z.discriminatedUnion("type", [
  wordsScene,
  heroScene,
  uiScene,
  dividerScene,
  revealScene,
  endScene,
]);

export const filmSpecSchema = z.object({
  family: z.literal("film"),
  // LLM-chosen storyboard name (two-source display-copy law). Null-read
  // tolerant: null reads as absent, never a render failure.
  name: z.string().nullish(),
  theme: themeSchema,
  scenes: z.array(filmSceneSchema).min(1),
});

export type FilmSpec = z.infer<typeof filmSpecSchema>;
export type FilmScene = z.infer<typeof filmSceneSchema>;
export type FilmTheme = z.infer<typeof themeSchema>;

/** Total duration in frames = Σ scene frames (allocation is upstream). */
export function filmTotalFrames(spec: FilmSpec): number {
  return spec.scenes.reduce((acc, s) => acc + s.frames, 0);
}

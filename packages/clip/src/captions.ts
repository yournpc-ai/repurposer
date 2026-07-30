/**
 * Caption preset catalog — THE single source of truth for caption styles
 * (docs/RECIPES.md §3). Every caption style is a registered combination of
 * three orthogonal primitives; the clip-spec carries only the preset id
 * string (renderer-agnostic contract, docs/VIDEO_EDITOR.md §4).
 *
 * Adding a STYLE = one registry line here (type, Python enum mirror, and both
 * frontend selectors follow automatically — Python validates id membership
 * only, behavior never sinks into Python).
 *
 * Adding a PRIMITIVE VALUE (a new layout / entrance / highlight mode) is the
 * rare case that writes code: one branch in Clip.tsx, which serves BOTH the
 * editor <Player> and the render service (preview == render stays
 * structural). Before a new primitive value may register here it MUST pass
 * the libass mapping check below (the CSS ∩ libass subset discipline —
 * keeps a future hand-rolled-FFmpeg renderer swap cheap):
 *
 *   layout single   -> one event per line, replaced as lines advance
 *   layout stack    -> one event PER revealed line: start = reveal moment,
 *                      end = clip end (slide-out needs none in v1), each line
 *                      shifted via \pos — old lines persist on screen; the
 *                      block grows downward from a top-half anchor, upward
 *                      from a bottom-half anchor (newest stays at the bottom)
 *   entrance none   -> static
 *   entrance fade-in   -> \fad(200,0)
 *   entrance pop-in    -> \t(\fscx,\fscy) overshoot scale
 *   entrance slide-up  -> \move upward into place
 *   wordHighlight   -> per-word \c color swap (karaoke \k timing)
 */

export const CAPTION_PRESETS = {
  "clean-bottom": { layout: "single", entrance: "none", wordHighlight: false },
  "karaoke-highlight": { layout: "single", entrance: "none", wordHighlight: true },
  "fade-in": { layout: "single", entrance: "fade-in", wordHighlight: false },
  "pop-in": { layout: "single", entrance: "pop-in", wordHighlight: false },
  "slide-up": { layout: "single", entrance: "slide-up", wordHighlight: false },
  /** 堆叠: new lines fade in, revealed lines persist, sliding window of the
   * last `maxLines` lines (the oldest leave without animation in v1). */
  stacking: { layout: "stack", entrance: "fade-in", wordHighlight: false, maxLines: 5 },
} as const;

/** Preset id — derived from the catalog, never hand-written. */
export type CaptionStylePreset = keyof typeof CAPTION_PRESETS;

export type CaptionLayout = "single" | "stack";
export type CaptionEntrance = "none" | "fade-in" | "pop-in" | "slide-up";

export interface CaptionPreset {
  layout: CaptionLayout;
  entrance: CaptionEntrance;
  wordHighlight: boolean;
  /** stack layout only: sliding-window size. */
  maxLines?: number;
}

/** Catalog lookup with a defensive default for out-of-catalog ids (e.g. an
 * old stored spec whose preset was retired): falls back to clean-bottom. */
export function captionPreset(id: string): CaptionPreset {
  return (CAPTION_PRESETS as Record<string, CaptionPreset>)[id] ?? CAPTION_PRESETS["clean-bottom"];
}

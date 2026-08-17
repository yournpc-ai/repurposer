/**
 * TRACK_REGISTRY — the single catalog of clip-spec tracks (ADR-044).
 *
 * A track = a named partition of the clip-spec: one registry declaration per
 * track, with consumers folding through it (bake seam / C2PA provenance /
 * pricing / ops addressing) instead of per-field special cases. The spec
 * itself stays FLAT — a `tracks: {}` container is rejected (ADR-044 D9).
 *
 * Double-end discipline (CAPTION_PRESETS 同款): this catalog is the source of
 * truth; TS types derive from it; the Python mirror (app/pipeline/tracks.py)
 * validates membership and consumes declarations only. Drift guard:
 * apps/api/scripts/check_track_registry.py diffs the two ends — which is why
 * the keys below are snake_case (the spec domain's own casing, zero-friction
 * diff).
 *
 * Adding a track = one registry entry (+ one renderer piece for a new
 * family). The `fields` partition is enforced on both ends: type-level below
 * (every ClipSpec key must be declared) and at API/worker boot (each key
 * declared exactly once). Forgetting the registration = the service refuses
 * to boot.
 */
import type { ClipSpec } from "./types";

export type TrackFamily = "sequence" | "data" | "layer" | "block";
/** Declared per track, never IMPLEMENTED per track — remap lives in one function. */
export type TrackTimeline = "source" | "output" | "derived";
/** ADR-026 classifier fold: does this track make the product synthetic media? */
export type TrackProvenance = "real" | "generated";

export interface TrackDef {
  readonly family: TrackFamily;
  readonly timeline: TrackTimeline;
  /** Sole writer skill(s) post-birth (the birthplace writes any track). */
  readonly owner: readonly string[];
  /** Mutually-exclusive slot labels (dub ⇄ original audio). */
  readonly mutex: readonly string[];
  /** Declared pairings (translation ⇄ caption — an existing coupling on record). */
  readonly pairs: readonly string[];
  readonly provenance: TrackProvenance;
  /** Dotted spec paths the bake seam absolutizes; `[*]` expands a list at that part. */
  readonly url_fields: readonly string[];
  /** Deterministic craft checks — residents arrive with their skill package. */
  readonly checks: readonly string[];
  /** The ClipSpec top-level keys this track owns (the partition). */
  readonly fields: readonly (keyof ClipSpec)[];
}

export const TRACK_REGISTRY = {
  main: {
    family: "sequence",
    timeline: "source",
    owner: ["select_clips", "materialize_source"],
    mutex: [],
    pairs: [],
    provenance: "real",
    // segments[*].url: hetero splice donor URLs (切 op) ride the same seam
    url_fields: ["source.url", "source.image_urls[*]", "segments[*].url"],
    checks: [],
    fields: ["source", "segments", "aspect", "target_language"],
  },
  caption: {
    family: "data",
    timeline: "source",
    owner: ["preprocess", "remove_filler"],
    mutex: [],
    pairs: [],
    provenance: "real",
    url_fields: [],
    checks: [],
    fields: ["caption_track", "caption_style_preset", "caption_position", "caption_enabled"],
  },
  translation: {
    family: "data",
    timeline: "source",
    owner: ["translate_clip"],
    mutex: [],
    pairs: ["caption"],
    provenance: "real",
    url_fields: [],
    checks: [],
    fields: ["translation_track"],
  },
  crop: {
    family: "data",
    timeline: "source",
    // birth default today; reframe_clip becomes the writer on the 08-19 line
    owner: ["select_clips", "materialize_source"],
    mutex: [],
    pairs: [],
    provenance: "real",
    url_fields: [],
    // 08-19 residents: crop-stays-on-face / min-dwell / anti-jump-cut easing
    checks: [],
    // + "crop_track" on the 08-19 line — the boot partition check forces the registration
    fields: ["crop"],
  },
  title: {
    family: "block",
    timeline: "output",
    owner: ["select_clips", "materialize_source"],
    mutex: [],
    pairs: [],
    provenance: "real",
    url_fields: [],
    checks: [],
    fields: ["title"],
  },
  music: {
    family: "block",
    timeline: "output",
    owner: ["add_music"],
    mutex: [],
    pairs: [],
    provenance: "real",
    url_fields: ["music.url"],
    checks: [],
    fields: ["music"],
  },
  dub: {
    family: "block",
    timeline: "output",
    owner: ["dub_clip"],
    mutex: ["original_audio"], // dub.enabled ⇒ the main track's original audio mutes
    pairs: [],
    provenance: "generated", // voice clone = synthetic track (ADR-026)
    url_fields: ["dub.url"],
    checks: [],
    fields: ["dub"],
  },
  intro_outro: {
    family: "block",
    timeline: "output",
    owner: [], // persona-skin bake at generation; no skill writes post-birth
    mutex: [],
    pairs: [],
    provenance: "real",
    url_fields: ["brand.intro.media_url", "brand.outro.media_url"],
    checks: [],
    fields: ["brand", "brand_ref"],
  },
} as const satisfies Record<string, TrackDef>;

/** Track id — derived from the catalog, never hand-written. */
export type TrackId = keyof typeof TRACK_REGISTRY;

/**
 * Compile-time partition assertion (completeness direction): every ClipSpec
 * top-level key must be declared by some track's `fields`. The boot-time
 * Python check covers the rest (declared fields exist on the model; each key
 * declared exactly once).
 */
type DeclaredField = (typeof TRACK_REGISTRY)[TrackId]["fields"][number];
type UnregisteredSpecField = Exclude<keyof ClipSpec, DeclaredField>;
const _partitionComplete: UnregisteredSpecField extends never ? true : never = true;
export { _partitionComplete };

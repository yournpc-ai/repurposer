/**
 * The clip-spec track partition (ADR-044) — TS end.
 *
 * A track = a named partition of the clip-spec's top-level fields. This end
 * declares ONLY the partition: the type-level assertion below forces every
 * ClipSpec key into exactly one track at tsc time (adding a spec field
 * without registering it = compile error). The EXECUTABLE catalog (owner /
 * provenance / url_fields / depends — consumed by the bake seam / C2PA fold /
 * ops addressing / the one-writer 422) lives server-side in
 * apps/api/app/pipeline/tracks.py: Python is the only runtime end. The
 * family/timeline taxonomy is documentation (docs/RENDERING.md §4), not
 * executable schema.
 *
 * Adding a track = one entry here + one TrackDef there + one renderer piece.
 * The spec itself stays FLAT — a `tracks: {}` container is rejected
 * (ADR-044 D9).
 */
import type { ClipSpec } from "./types";

export const TRACK_FIELDS = {
  main: ["source", "segments", "aspect", "target_language"],
  caption: ["caption_track", "caption_style_preset", "caption_position", "caption_enabled"],
  translation: ["translation_track"],
  crop: ["crop", "crop_track"],
  layers: ["layers"],
  title: ["title"],
  music: ["music"],
  dub: ["dub"],
  intro_outro: ["brand", "brand_ref"],
} as const satisfies Record<string, readonly (keyof ClipSpec)[]>;

/** Track id — derived from the partition, never hand-written. */
export type TrackId = keyof typeof TRACK_FIELDS;

/**
 * Compile-time partition assertion (completeness direction): every ClipSpec
 * top-level key must be declared by some track. The boot-time Python check
 * covers the rest (declared fields exist on the model; each key declared
 * exactly once).
 */
type DeclaredField = (typeof TRACK_FIELDS)[TrackId][number];
type UnregisteredSpecField = Exclude<keyof ClipSpec, DeclaredField>;
const _partitionComplete: UnregisteredSpecField extends never ? true : never = true;
export { _partitionComplete };

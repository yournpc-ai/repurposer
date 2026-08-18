/**
 * TypeScript mirror of the backend `ClipSpec` Pydantic contract
 * (apps/api/app/models/schemas.py — see docs/VIDEO_EDITOR.md §4).
 *
 * This is the renderer-agnostic render contract. Keep it in lockstep with the
 * Python model; it carries no Remotion/React concepts so the renderer behind it
 * stays swappable.
 */

/** The fixed render tiers. */
export type FixedAspect = "9:16" | "1:1" | "16:9";

/**
 * "original" (2026-08-17, whole-source materialization follows the source):
 * no fixed tier — the renderer resolves the source's own dimensions in
 * calculateMetadata. Only whole-source materializations carry it; excerpt
 * clips are always a fixed tier.
 */
export type Aspect = FixedAspect | "original";

// The preset id type is DERIVED from the catalog (captions.ts) — adding a
// style there updates this type automatically. Re-exported here so the
// contract mirror's surface stays stable for existing importers.
import type { CaptionStylePreset } from "./captions";
export type { CaptionStylePreset } from "./captions";

/**
 * What backs the clip's visual: a real on-camera video, or a "stills" audiogram
 * (image[s] + optional speech audio). Absent on old specs -> treated as "video".
 */
export type SourceKind = "video" | "stills";

export interface ClipSource {
  asset_id: string;
  /** "video" (default) or "stills" (image-backed audiogram). */
  kind?: SourceKind;
  /**
   * Browser-playable URL via the storage seam (api Range endpoint or S3).
   * video: the video file. stills: the optional speech audio ("" when none).
   */
  url: string;
  /**
   * stills only: ordered backing images. 0 -> solid background; 1 -> full-frame
   * for the whole clip; N -> even hard-cut slideshow across the duration.
   */
  image_urls?: string[];
  fps: number;
  /** Source length in seconds (trim slider upper bound); optional for old specs. */
  duration?: number | null;
}

/** Entry-edge dissolve into a segment (枚举可、画廊不可, ADR-016 L3 修订):
 * `none` hard cut, `fade` through black, `dip` white flash. Cap: at most 3
 * non-none transitions per clip — enforced where the op is registered. */
export type SegmentTransition = "none" | "fade" | "dip";

export interface ClipSegment {
  /**
   * Stable entity identity — the anchor-addressable piece (ADR-044). Minted
   * at birth / on split (server-side default factory backfills old specs on
   * the first validating read).
   */
  id: string;
  /**
   * Hetero main-track splice (切 op): the donor asset + its storage-seam URL
   * resolved at write. Both null = the homogeneous default (the spec's own
   * `source`).
   */
  asset_id?: string | null;
  url?: string | null;
  start: number;
  end: number;
  /** Non-destructive delete (transcript "delete sentence"). Skipped on render. */
  hidden: boolean;
  /** "generated" marks a synthetic segment (None/absent = real). */
  provenance?: "real" | "generated" | null;
  transition: SegmentTransition;
}

/** Segment id mint — opaque 12-hex, same shape as the Python default factory. */
export const mintSegmentId = (): string =>
  crypto.randomUUID().replace(/-/g, "").slice(0, 12);

/**
 * Where a layer pins — the storage truth (存法 C: 锚是真相, ADR-044). Absolute
 * timecodes never persist; lane positions are a compile artifact. Three forms:
 * `segment` (段锚: segment_id + source-clock offset), `edge` (边锚: head/tail
 * of the kept-video portion + offset; tail resolves to video_end − offset),
 * `ratio` (比例锚: fraction of the kept-video duration).
 */
export interface ClipAnchor {
  kind: "segment" | "edge" | "ratio";
  segment_id?: string | null;
  edge?: "head" | "tail" | null;
  ratio?: number | null;
  offset_seconds: number;
}

/** Normalized rectangle of the composition (CSS ∩ libass expressible). */
export interface ClipRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A layer's content: one branch by media type. */
export interface LayerMedia {
  kind: "video" | "image" | "text";
  /** video/image: storage-seam URL */
  url?: string | null;
  /** text: the callout content */
  text?: string | null;
}

export type LayerKind = "broll" | "text_callout" | "pip" | "motion_graphic";

/**
 * An overlay item on the layer track (ADR-044; "overlay" 词禁用于视频层).
 * Position = anchor + duration_seconds; the output-timeline window is
 * projected at the bake seam, never persisted. `provenance` is REQUIRED.
 */
export interface ClipLayer {
  id: string;
  kind: LayerKind;
  anchor: ClipAnchor;
  duration_seconds: number;
  rect: ClipRect;
  z: number;
  /** The entity reference the LLM proposed from (never an absolute timecode). */
  source_ref?: Record<string, unknown> | null;
  media?: LayerMedia | null;
  provenance: "real" | "generated";
}

export interface ClipCrop {
  /** Normalized center + scale; applied via CSS transform (not object-position). */
  x: number;
  y: number;
  scale: number;
}

/**
 * One framing decision on the SOURCE timeline (ADR-045): from source second
 * `t`, hold this normalized center + scale. The crop data track is a sparse
 * list of these — a keyframe is a decision ("switch to A here"), never
 * per-frame data. Writer guarantees strictly ascending `t`. Anti-dizzy
 * parameters (dwell / deadzone / slew) are WRITE-side constraints of the
 * skill, never serialized here.
 */
export interface CropKeyframe {
  t: number;
  x: number;
  y: number;
  scale: number;
}

const _smoothstep = (u: number): number => {
  const s = Math.min(1, Math.max(0, u));
  return s * s * (3 - 2 * s);
};

/**
 * Sample the crop data track at a SOURCE second (data tracks don't project —
 * they sample, ADR-044 §8.6): hold the latest keyframe's framing, easing into
 * it over CROP_EASE_SECONDS after its `t`. An empty/absent track degrades to
 * the static `crop` (语义不变). Python twin: clip_spec.sample_crop — parity
 * must be exact (scripts/crop_track_parity.py).
 */
export const sampleCrop = (spec: ClipSpec, sourceTime: number): ClipCrop => {
  const track = spec.crop_track;
  if (!track || track.length === 0) return spec.crop;
  if (sourceTime <= track[0].t) {
    const f = track[0];
    return { x: f.x, y: f.y, scale: f.scale };
  }
  // Last keyframe with t <= sourceTime (the active framing decision).
  let i = track.length - 1;
  for (let k = 1; k < track.length; k += 1) {
    if (track[k].t > sourceTime) {
      i = k - 1;
      break;
    }
  }
  const cur = track[i];
  if (i === 0 || sourceTime - cur.t >= CROP_EASE_SECONDS) {
    return { x: cur.x, y: cur.y, scale: cur.scale };
  }
  const prev = track[i - 1];
  const s = _smoothstep((sourceTime - cur.t) / CROP_EASE_SECONDS);
  return {
    x: prev.x + (cur.x - prev.x) * s,
    y: prev.y + (cur.y - prev.y) * s,
    scale: prev.scale + (cur.scale - prev.scale) * s,
  };
};

export interface CaptionCue {
  start: number;
  end: number;
  text: string;
  lang: string;
}

export interface ClipTitle {
  text: string;
  enabled: boolean;
  /** Font size in composition px (renderer scales). Null -> renderer default. */
  size?: number | null;
  /** Normalized center point (CSS translate / libass \pos). Null -> default. */
  position?: Point | null;
}

/** Normalized center point in [0,1] of the composition (CSS + libass \pos expressible). */
export interface Point {
  x: number;
  y: number;
}

export interface ClipMusic {
  /** The Music row's UUID (string). */
  music_id?: string | null;
  /** @deprecated use music_id; kept so old render_spec JSON still type-checks. */
  track_id?: string | null;
  url?: string | null;
  enabled: boolean;
  gain_db: number;
}

/** Cloned-voice dubbed speech in the target language (overrides the source audio). */
export interface ClipDub {
  url?: string | null;
  enabled: boolean;
  gain_db: number;
}

/** Intro/outro brand card: text, image, or a short video. */
export interface IntroOutroCard {
  kind: "text" | "image" | "video";
  /** kind === "text" */
  text?: string | null;
  /** kind === "image" | "video" (storage-seam URL) */
  media_url?: string | null;
  /** How long the card displays, in seconds. Null -> renderer default (2s). */
  duration_seconds?: number | null;
}

/** Resolved brand values baked into the spec by the API (renderer-agnostic). */
export interface ClipBrand {
  caption_color?: string | null;
  caption_size?: number | null;
  caption_font?: string | null;
  intro?: IntroOutroCard | null;
  outro?: IntroOutroCard | null;
  fill_mode?: "fill" | "fit";
  caption_enabled?: boolean;
}

export interface ClipSpec {
  source: ClipSource;
  aspect: Aspect;
  segments: ClipSegment[];
  crop: ClipCrop;
  /** Crop data track (ADR-045): sparse framing decisions on the source
   * timeline, sampled per frame via `sampleCrop`. Absent/empty = the static
   * `crop` above (degenerate form, 语义不变). Nullable on the wire — the
   * Python side serializes None. */
  crop_track?: CropKeyframe[] | null;
  caption_track: CaptionCue[];
  /** 双语对照轨: the translated half of a bilingual caption pair — unit-level
   * cues (no karaoke word timing), paired with caption_track's original lines
   * by time overlap. Absent/empty = single-language captions. */
  translation_track?: CaptionCue[];
  caption_style_preset: CaptionStylePreset;
  /** Normalized center point of the caption block. Null -> default (bottom). */
  caption_position?: Point | null;
  /** When false, the renderer skips burned-in captions even if caption_track is non-empty. */
  caption_enabled?: boolean;
  title: ClipTitle;
  music: ClipMusic;
  /** Cloned-voice dub; when enabled, replaces the source's original audio. */
  dub?: ClipDub | null;
  /** Layer track (ADR-044): anchor-pinned overlay items. Empty = no layers. */
  layers: ClipLayer[];
  brand?: ClipBrand | null;
  brand_ref: string | null;
  target_language: string;
}

export const ASPECT_DIMENSIONS: Record<FixedAspect, { width: number; height: number }> = {
  "9:16": { width: 1080, height: 1920 },
  "1:1": { width: 1080, height: 1080 },
  "16:9": { width: 1920, height: 1080 },
};

/** H.264 wants even dimensions — round down to the nearest even pixel. */
export const evenDim = (n: number): number => Math.max(2, Math.floor(n / 2) * 2);

/** A synchronous frame for chrome that must know dims without loading media
 * (the clip editor's preview Player). "original" resolves to the landscape
 * tier — only the renderer learns the source's real dims. */
export const fixedAspectDimensions = (aspect: Aspect): { width: number; height: number } =>
  aspect === "original" ? ASPECT_DIMENSIONS["16:9"] : ASPECT_DIMENSIONS[aspect];

/** Composition timeline fps (independent of the source's fps). */
export const COMPOSITION_FPS = 30;

/** Fixed render-side ease after each crop keyframe: ~8 composition frames of
 * smoothstep. A render constant, not contract data (transition-enum 哲学:
 * 枚举可、参数画廊不可). */
export const CROP_EASE_SECONDS = 8 / COMPOSITION_FPS;

/** Default duration (seconds) for a brand intro/outro card with no explicit duration_seconds. */
export const INTRO_SECONDS = 2;
export const OUTRO_SECONDS = 2;

/** Intro card duration for this spec (0 when no brand intro card). */
export const introSeconds = (spec: ClipSpec): number =>
  spec.brand?.intro ? spec.brand.intro.duration_seconds || INTRO_SECONDS : 0;

/** Outro card duration for this spec (0 when no brand outro card). */
export const outroSeconds = (spec: ClipSpec): number =>
  spec.brand?.outro ? spec.brand.outro.duration_seconds || OUTRO_SECONDS : 0;

/** Non-hidden segments in order. */
export const keptSegments = (spec: ClipSpec): ClipSegment[] =>
  spec.segments.filter((s) => !s.hidden);

/** Kept video duration in seconds (excludes intro/outro cards). */
export const videoDurationSeconds = (spec: ClipSpec): number =>
  keptSegments(spec).reduce((acc, s) => acc + Math.max(0, s.end - s.start), 0);

/** Total clip duration: intro card + kept video + outro card (>= a frame). */
export const totalDurationSeconds = (spec: ClipSpec): number => {
  const total = introSeconds(spec) + videoDurationSeconds(spec) + outroSeconds(spec);
  return total > 0 ? total : 1 / COMPOSITION_FPS;
};

// ---------------------------------------------------------------------------
// Lane projection (存法 C, ADR-044): the storage truth is anchors + per-segment
// source spans; the OUTPUT clock below is a compile artifact — computed here,
// never persisted. Python mirror: app/pipeline/clip_spec.py (snake_case twins).
// ---------------------------------------------------------------------------

/** One kept segment laid out on the VIDEO-LOCAL output clock. */
export interface TimelineEntry {
  seg: ClipSegment;
  /** Output seconds (video-local, intro excluded) where this segment starts. */
  outStart: number;
  dur: number;
}

/** Kept segments concatenated onto the video-local output clock, in order. */
export const videoTimeline = (spec: ClipSpec): TimelineEntry[] => {
  let acc = 0;
  return keptSegments(spec).map((seg) => {
    const dur = Math.max(0, seg.end - seg.start);
    const entry = { seg, outStart: acc, dur };
    acc += dur;
    return entry;
  });
};

/**
 * Output → source remap (single home): which SOURCE second shows at this
 * FULL-CLOCK output second (intro card included in the clock). Null when the
 * output second sits outside the video portion — a transition veil is a
 * visual overlay and does not shift the mapping (single-sided, no time eat).
 */
export const sourceTimeAtOutputTime = (spec: ClipSpec, outputSeconds: number): number | null => {
  const local = outputSeconds - introSeconds(spec);
  if (local < 0 || local >= videoDurationSeconds(spec)) return null;
  const entry = videoTimeline(spec).find((t) => local >= t.outStart && local < t.outStart + t.dur);
  return entry ? entry.seg.start + (local - entry.outStart) : null;
};

/**
 * Source → output remap: the FULL-CLOCK output second at which this source
 * second appears. Null when the source second is cut (hidden) or uncovered.
 */
export const outputTimeAtSourceTime = (spec: ClipSpec, sourceSeconds: number): number | null => {
  const entry = videoTimeline(spec).find(
    (t) => sourceSeconds >= t.seg.start && sourceSeconds < t.seg.end,
  );
  return entry ? introSeconds(spec) + entry.outStart + (sourceSeconds - entry.seg.start) : null;
};

/** A layer with its anchor resolved to a full-clock output window. */
export interface ProjectedLayer {
  layer: ClipLayer;
  /** Full-clock output seconds [start, end]; clamped to the video portion. */
  window: { start: number; end: number };
}

/**
 * Layer lane projection: resolve every layer's anchor to its output window.
 * Unresolvable anchors (segment deleted/hidden, malformed form) come back in
 * `unresolved` — the stored anchor is never rewritten, the item is simply not
 * rendered (non-destructive, like a hidden segment).
 */
export const projectLayers = (
  spec: ClipSpec,
): { resolved: ProjectedLayer[]; unresolved: ClipLayer[] } => {
  const intro = introSeconds(spec);
  const videoDur = videoDurationSeconds(spec);
  const timeline = videoTimeline(spec);
  const resolved: ProjectedLayer[] = [];
  const unresolved: ClipLayer[] = [];
  for (const layer of spec.layers ?? []) {
    const a = layer.anchor;
    let anchorOut: number | null = null;
    if (a.kind === "segment") {
      const entry = timeline.find((t) => t.seg.id === a.segment_id);
      if (entry) anchorOut = intro + entry.outStart + Math.min(Math.max(0, a.offset_seconds), entry.dur);
    } else if (a.kind === "edge") {
      anchorOut = a.edge === "tail" ? intro + videoDur - a.offset_seconds : intro + a.offset_seconds;
    } else if (a.kind === "ratio") {
      anchorOut = intro + (a.ratio ?? 0) * videoDur;
    }
    if (anchorOut === null) {
      unresolved.push(layer);
      continue;
    }
    // Clamp to the video portion — a layer never bleeds into the brand cards.
    const start = Math.min(Math.max(anchorOut, intro), intro + videoDur);
    const end = Math.min(start + layer.duration_seconds, intro + videoDur);
    resolved.push({ layer, window: { start, end } });
  }
  return { resolved, unresolved };
};

/**
 * Non-destructively remove a source time range [start, end] (transcript "delete
 * sentence" = cut): the overlapped part of each kept segment becomes a `hidden`
 * segment (recoverable), and caption cues inside the range are dropped.
 *
 * Segment ids (ADR-044): the FIRST kept piece of a split segment inherits the
 * parent's id (anchors ride the surviving kept content); hidden pieces and
 * later kept pieces mint fresh ids. Hetero splices (asset_id/url) carry their
 * donor identity onto every piece. Mirror: app/pipeline/clip_spec.py.
 */
export const removeRange = (spec: ClipSpec, start: number, end: number): ClipSpec => {
  if (end <= start) return spec;
  const segments: ClipSegment[] = [];
  for (const s of spec.segments) {
    if (s.hidden) {
      segments.push(s);
      continue;
    }
    const a = Math.max(start, s.start);
    const b = Math.min(end, s.end);
    if (a >= b) {
      segments.push(s);
      continue;
    }
    const donor = { asset_id: s.asset_id ?? null, url: s.url ?? null, provenance: s.provenance ?? null };
    // The transition lives on the ENTRY edge: only the piece that still
    // starts at s.start inherits it; cut-born pieces hard-cut in.
    const entry = { transition: s.transition };
    const cut = { transition: "none" as const };
    const pieces: ClipSegment[] = [];
    if (s.start < a)
      pieces.push({ id: mintSegmentId(), start: s.start, end: a, hidden: false, ...donor, ...entry });
    pieces.push({ id: mintSegmentId(), start: a, end: b, hidden: true, ...donor, ...cut });
    if (b < s.end)
      pieces.push({ id: mintSegmentId(), start: b, end: s.end, hidden: false, ...donor, ...cut });
    // First kept piece keeps the parent id; the rest ride minted ids.
    const firstKept = pieces.find((p) => !p.hidden);
    if (firstKept && s.id) firstKept.id = s.id;
    segments.push(...pieces);
  }
  const eps = 1e-6;
  const caption_track = spec.caption_track.filter(
    (c) => !(c.start >= start - eps && c.end <= end + eps),
  );
  return { ...spec, segments, caption_track };
};

/** Best-known source duration (seconds) for the trim slider's upper bound. */
export const sourceDuration = (spec: ClipSpec): number => {
  if (spec.source.duration && spec.source.duration > 0) return spec.source.duration;
  const segEnd = spec.segments.reduce((m, s) => Math.max(m, s.end), 0);
  const capEnd = spec.caption_track.reduce((m, c) => Math.max(m, c.end), 0);
  return Math.max(segEnd, capEnd, 1);
};

/** Outer [start, end] of kept content — the current trim window. */
export const trimBounds = (spec: ClipSpec): [number, number] => {
  const kept = keptSegments(spec);
  if (kept.length === 0) return [0, sourceDuration(spec)];
  return [kept[0].start, kept[kept.length - 1].end];
};

/** Set the outer in/out by moving the first/last kept segment boundaries. */
export const setTrim = (spec: ClipSpec, start: number, end: number): ClipSpec => {
  if (end <= start) return spec;
  const keptIdx = spec.segments
    .map((s, i) => ({ s, i }))
    .filter((x) => !x.s.hidden);
  if (keptIdx.length === 0) return spec;
  const firstI = keptIdx[0].i;
  const lastI = keptIdx[keptIdx.length - 1].i;
  const segments = spec.segments.map((s, i) => {
    let ns = s;
    if (i === firstI) ns = { ...ns, start };
    if (i === lastI) ns = { ...ns, end };
    return ns;
  });
  return { ...spec, segments };
};

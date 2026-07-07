/**
 * TypeScript mirror of the backend `ClipSpec` Pydantic contract
 * (apps/api/app/models/schemas.py — see docs/VIDEO_EDITOR.md §4).
 *
 * This is the renderer-agnostic render contract. Keep it in lockstep with the
 * Python model; it carries no Remotion/React concepts so the renderer behind it
 * stays swappable.
 */

export type Aspect = "9:16" | "1:1";

export type CaptionStylePreset = "clean-bottom" | "karaoke-highlight";

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

export interface ClipSegment {
  start: number;
  end: number;
  /** Non-destructive delete (transcript "delete sentence"). Skipped on render. */
  hidden: boolean;
}

export interface ClipCrop {
  /** Normalized center + scale; applied via CSS transform (not object-position). */
  x: number;
  y: number;
  scale: number;
}

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

/** Resolved brand values baked into the spec by the API (renderer-agnostic). */
export interface ClipBrand {
  logo_url?: string | null;
  cta?: string | null;
  /** Normalized center point of the CTA. Null -> default (bottom). */
  cta_position?: Point | null;
  caption_color?: string | null;
  caption_size?: number | null;
  caption_font?: string | null;
  intro_text?: string | null;
  outro_text?: string | null;
  fill_mode?: "fill" | "fit";
}

export interface ClipSpec {
  source: ClipSource;
  aspect: Aspect;
  segments: ClipSegment[];
  crop: ClipCrop;
  caption_track: CaptionCue[];
  caption_style_preset: CaptionStylePreset;
  /** Normalized center point of the caption block. Null -> default (bottom). */
  caption_position?: Point | null;
  title: ClipTitle;
  music: ClipMusic;
  /** Cloned-voice dub; when enabled, replaces the source's original audio. */
  dub?: ClipDub | null;
  brand?: ClipBrand | null;
  brand_ref: string | null;
  target_language: string;
}

export const ASPECT_DIMENSIONS: Record<Aspect, { width: number; height: number }> = {
  "9:16": { width: 1080, height: 1920 },
  "1:1": { width: 1080, height: 1080 },
};

/** Composition timeline fps (independent of the source's fps). */
export const COMPOSITION_FPS = 30;

/** Fixed durations (seconds) for brand intro/outro title cards. */
export const INTRO_SECONDS = 2;
export const OUTRO_SECONDS = 2;

/** Intro card duration for this spec (0 when no brand intro text). */
export const introSeconds = (spec: ClipSpec): number =>
  spec.brand?.intro_text ? INTRO_SECONDS : 0;

/** Outro card duration for this spec (0 when no brand outro text). */
export const outroSeconds = (spec: ClipSpec): number =>
  spec.brand?.outro_text ? OUTRO_SECONDS : 0;

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

/**
 * Non-destructively remove a source time range [start, end] (transcript "delete
 * sentence" = cut): the overlapped part of each kept segment becomes a `hidden`
 * segment (recoverable), and caption cues inside the range are dropped.
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
    if (s.start < a) segments.push({ start: s.start, end: a, hidden: false });
    segments.push({ start: a, end: b, hidden: true });
    if (b < s.end) segments.push({ start: b, end: s.end, hidden: false });
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

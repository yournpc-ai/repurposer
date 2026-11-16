import { videoSpecSchema, type VideoSpec } from "@repurposer/video-spec"
import { assertVideoSupported } from "@repurposer/video-remotion"
import type { VideoScrubTarget } from "../../timeline/types"

export interface PreviewIdentity {
  composition_id: string
  composition_version_id: string
  content_digest: string
}

/** Admit only a supported spec compiled for this exact immutable version. */
export function parsePreviewSpec(
  value: unknown,
  expected: PreviewIdentity,
): VideoSpec {
  const result = videoSpecSchema.safeParse(value)
  if (!result.success) throw new Error("Invalid video preview spec")
  const spec = result.data
  assertVideoSupported(spec)
  if (
    spec.provenance.composition_id !== expected.composition_id ||
    spec.provenance.composition_version_id !== expected.composition_version_id ||
    spec.provenance.content_digest !== expected.content_digest
  ) {
    throw new Error("Video preview identity mismatch")
  }
  return spec
}

export interface VideoScrubScope {
  target: VideoScrubTarget
  source_range_seconds: { start: number; end: number }
  isolated_object: boolean
  clip_ids: string[]
}

/** Admit only a spec whose server projection carries an explicit local scope. */
export function parseScopedPreviewSpec(
  value: unknown,
  scope: VideoScrubScope | undefined,
  expected: PreviewIdentity,
): VideoSpec {
  if (!scope?.target || !Array.isArray(scope.clip_ids) || scope.clip_ids.length === 0) {
    throw new Error("Video preview scope missing")
  }
  const spec = parsePreviewSpec(value, expected)
  const clips = spec.tracks.flatMap((track) => track.clips)
  if (clips.length === 0 || clips.some((clip) => !scope.clip_ids.some((id) =>
    clip.clip_id === id || clip.clip_id.startsWith(`${id}:cue:`),
  ))) {
    throw new Error("Video preview escaped its Scrub scope")
  }
  if (scope.target.kind === "object") {
    const objectId = scope.target.object_id
    if (!scope.isolated_object || clips.some((clip) =>
      clip.object.object_id !== objectId && !clip.object.object_id.startsWith(`${objectId}:cue:`),
    )) {
      throw new Error("Isolated Object preview contains another Object")
    }
  }
  return spec
}

export function previewWithTextFontSize(
  spec: VideoSpec,
  clipId: string,
  fontSize: number,
): VideoSpec {
  return {
    ...spec,
    tracks: spec.tracks.map((track) => ({
      ...track,
      clips: track.clips.map((clip) =>
        clip.clip_id === clipId && clip.object.kind === "text"
          ? {
              ...clip,
              object: {
                ...clip.object,
                style: { ...clip.object.style, font_size: fontSize },
              },
            }
          : clip,
      ),
    })),
  }
}

import React from "react";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { getImageDimensions, getVideoMetadata } from "@remotion/media-utils";
import { Clip } from "./Clip";
import {
  ASPECT_DIMENSIONS,
  COMPOSITION_FPS,
  evenDim,
  fixedAspectDimensions,
  type ClipSpec,
  totalDurationSeconds,
} from "./types";

/** A minimal valid spec for Remotion's required defaultProps / studio preview. */
export const DEFAULT_SPEC: ClipSpec = {
  source: { asset_id: "", kind: "video", url: "", fps: 30, image_urls: [] },
  aspect: "9:16",
  segments: [{ id: "default", start: 0, end: 1, hidden: false, transition: "none" }],
  crop: { x: 0.5, y: 0.5, scale: 1 },
  caption_track: [],
  caption_style_preset: "clean-bottom",
  caption_enabled: true,
  title: { text: "", enabled: false },
  music: { music_id: null, enabled: false, gain_db: -18 },
  layers: [],
  brand_ref: null,
  target_language: "en",
};

const calculateClipMetadata: CalculateMetadataFunction<{ spec: ClipSpec }> = async ({ props }) => {
  const spec = props.spec;
  let sourceDim: { width: number; height: number } | undefined;
  if (spec.aspect === "original") {
    // Whole-source materialization (2026-08-17): the composition takes
    // the SOURCE's own dimensions — video metadata, else the first
    // backing image; failure falls back to the landscape tier below.
    try {
      if (spec.source.kind !== "stills" && spec.source.url) {
        const meta = await getVideoMetadata(spec.source.url);
        sourceDim = { width: evenDim(meta.width), height: evenDim(meta.height) };
      } else if (spec.source.image_urls && spec.source.image_urls.length > 0) {
        const meta = await getImageDimensions(spec.source.image_urls[0]);
        sourceDim = { width: evenDim(meta.width), height: evenDim(meta.height) };
      }
    } catch {
      sourceDim = undefined;
    }
  }
  const dim = sourceDim ?? fixedAspectDimensions(spec.aspect);
  return {
    width: dim.width,
    height: dim.height,
    durationInFrames: Math.max(1, Math.round(totalDurationSeconds(spec) * COMPOSITION_FPS)),
  };
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Clip"
    component={Clip}
    fps={COMPOSITION_FPS}
    width={ASPECT_DIMENSIONS["9:16"].width}
    height={ASPECT_DIMENSIONS["9:16"].height}
    durationInFrames={COMPOSITION_FPS}
    defaultProps={{ spec: DEFAULT_SPEC }}
    // Dimensions + duration come from the spec at render time.
    calculateMetadata={calculateClipMetadata}
  />
);

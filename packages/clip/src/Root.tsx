import React from "react";
import { Composition } from "remotion";
import { Clip } from "./Clip";
import {
  ASPECT_DIMENSIONS,
  COMPOSITION_FPS,
  type ClipSpec,
  totalDurationSeconds,
} from "./types";

/** A minimal valid spec for Remotion's required defaultProps / studio preview. */
export const DEFAULT_SPEC: ClipSpec = {
  source: { asset_id: "", kind: "video", url: "", fps: 30, image_urls: [] },
  aspect: "9:16",
  segments: [{ start: 0, end: 1, hidden: false }],
  crop: { x: 0.5, y: 0.5, scale: 1 },
  caption_track: [],
  caption_style_preset: "clean-bottom",
  title: { text: "", enabled: false },
  music: { music_id: null, enabled: false, gain_db: -18 },
  brand_ref: null,
  target_language: "en",
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
    calculateMetadata={({ props }) => {
      const spec = props.spec;
      const dim = ASPECT_DIMENSIONS[spec.aspect] ?? ASPECT_DIMENSIONS["9:16"];
      return {
        width: dim.width,
        height: dim.height,
        durationInFrames: Math.max(1, Math.round(totalDurationSeconds(spec) * COMPOSITION_FPS)),
      };
    }}
  />
);

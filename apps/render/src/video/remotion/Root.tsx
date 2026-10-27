// Video composition root. Everything time-like is already quantized integer
// frames in the spec — fps/width/height/duration read straight off it
// (the renderer never re-derives durations).
import React from "react";
import { Composition } from "remotion";

import type { VideoSpec } from "@repurposer/video-spec";

import { Video } from "./Video";

/** Empty default for Remotion Studio; production always supplies inputProps. */
const DEFAULT_SPEC: VideoSpec = {
  family: "video",
  format: 1,
  fps: { num: 30, den: 1 },
  width: 1920,
  height: 1080,
  background: "#000000",
  sample_rate: 48000,
  duration_frames: 30,
  fonts: [],
  tracks: [
    {
      track_id: "t_main",
      kind: "visual",
      role: "main",
      order: 0,
      clips: [],
    },
  ],
  provenance: {
    composition_id: "default",
    composition_version_id: "default",
    content_digest: "0".repeat(64),
  },
};

export const VideoRoot: React.FC = () => (
  <Composition
    id="Video"
    component={Video}
    fps={30}
    width={1920}
    height={1080}
    durationInFrames={30}
    defaultProps={{ spec: DEFAULT_SPEC }}
    calculateMetadata={({ props }) => ({
      fps: props.spec.fps.num / props.spec.fps.den,
      width: props.spec.width,
      height: props.spec.height,
      durationInFrames: props.spec.duration_frames,
    })}
  />
);

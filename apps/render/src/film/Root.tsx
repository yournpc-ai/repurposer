// Film composition root. The canvas dimensions key on the spec's `aspect`
// (16:9 landscape default / 1:1 square / 9:16 portrait — ADR-120 E3).
// Duration comes from the storyboard at render time via calculateMetadata —
// total = Σ scene frames, fixed 30 fps.
import React from "react";
import { Composition } from "remotion";

import { Film } from "./Film";
import { filmTotalFrames, type FilmSpec } from "./schema";

export const FILM_FPS = 30;

/** Canvas dimensions per aspect (the probe's FILM_DIMENSIONS mirror —
 * one law, mirrored where consumed). */
export const FILM_DIMENSIONS: Record<
  FilmSpec["aspect"],
  { width: number; height: number }
> = {
  "16:9": { width: 1920, height: 1080 },
  "1:1": { width: 1080, height: 1080 },
  "9:16": { width: 1080, height: 1920 },
};

/** Minimal valid spec for Remotion's required defaultProps / studio preview. */
const DEFAULT_SPEC: FilmSpec = {
  family: "film",
  theme: { canvas: "#F7F6F2", ink: "#141414" },
  aspect: "16:9",
  scenes: [{ type: "words", frames: FILM_FPS, dark: false, lines: ["Film"] }],
};

export const FilmRoot: React.FC = () => (
  <Composition
    id="Film"
    component={Film}
    fps={FILM_FPS}
    width={FILM_DIMENSIONS["16:9"].width}
    height={FILM_DIMENSIONS["16:9"].height}
    durationInFrames={FILM_FPS}
    defaultProps={{ spec: DEFAULT_SPEC }}
    calculateMetadata={({ props }) => ({
      durationInFrames: filmTotalFrames(props.spec),
      ...FILM_DIMENSIONS[props.spec.aspect ?? "16:9"],
    })}
  />
);

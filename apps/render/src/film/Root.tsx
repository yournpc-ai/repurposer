// Film composition root. v1 is landscape-only (16:9 = LinkedIn / institution
// site, the positioning channels); a portrait variant is a later batch.
// Duration comes from the storyboard at render time via calculateMetadata —
// total = Σ scene frames, fixed 30 fps.
import React from "react";
import { Composition } from "remotion";

import { Film } from "./Film";
import { filmTotalFrames, type FilmSpec } from "./schema";

export const FILM_FPS = 30;
export const FILM_WIDTH = 1920;
export const FILM_HEIGHT = 1080;

/** Minimal valid spec for Remotion's required defaultProps / studio preview. */
const DEFAULT_SPEC: FilmSpec = {
  family: "film",
  theme: { canvas: "#F7F6F2", ink: "#141414" },
  scenes: [{ type: "words", frames: FILM_FPS, dark: false, lines: ["Film"] }],
};

export const FilmRoot: React.FC = () => (
  <Composition
    id="Film"
    component={Film}
    fps={FILM_FPS}
    width={FILM_WIDTH}
    height={FILM_HEIGHT}
    durationInFrames={FILM_FPS}
    defaultProps={{ spec: DEFAULT_SPEC }}
    calculateMetadata={({ props }) => ({
      durationInFrames: filmTotalFrames(props.spec),
    })}
  />
);

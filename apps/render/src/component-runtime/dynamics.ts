import { createHash } from "node:crypto";

import { ComponentPolicyError } from "./policy";

export interface ComponentFrameSample {
  frame: number;
  png: Buffer;
}

/** Bounded counterpart of draw-2d's real-pixel motion diagnostic. Source
 * API usage proves nothing: compare a few actual rendered frames instead of
 * scanning for useCurrentFrame or inspecting the whole film pixel by pixel. */
export function assertDynamicComponentFrames(
  samples: readonly ComponentFrameSample[],
): void {
  if (samples.length < 2) {
    throw new ComponentPolicyError(
      "remotion-project needs at least two sampled frames to verify real motion",
    );
  }
  const uniquePixels = new Set(
    samples.map(({ png }) => createHash("sha256").update(png).digest("hex")),
  );
  if (uniquePixels.size < 2) {
    throw new ComponentPolicyError(
      "remotion-project produced identical pixels at every sampled frame; add real motion",
    );
  }
}

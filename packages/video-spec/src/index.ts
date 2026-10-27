// Public contract surface of the video-spec family. This package never
// imports React/Remotion (check_gates enforces) — renderer adapters consume
// it from the outside.
export { videoSpecSchema } from "./schema";
export type {
  VideoSpec,
  VideoClip,
  VideoAnimation,
  VideoKeyframe,
  VideoTextObject,
  VideoTextPart,
} from "./schema";
export { ticksToFrames, secondsToTicks, ticksToSeconds } from "./timing";
export { evaluateKeyframes, evaluateProperty } from "./animation";
export type { AnimValue } from "./animation";
export { deriveTextParts, deriveTextPartFamilies, SEGMENTATION_VERSION, LAYOUT_VERSION } from "./text";
export type { TextPart, TextPartKind, TextRange } from "./text";

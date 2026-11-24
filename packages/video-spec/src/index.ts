// Public contract surface of the video-spec family. This package never
// imports React/Remotion — renderer adapters consume it from the outside.
export {
  transitionKinds,
  stylePresetIds,
  backdropStyles,
  cardTreatments,
  headlineTreatments,
  textBackgroundModes,
  textTransforms,
  videoStyleSchema,
  videoSpecSchema,
} from "./schema";
export type {
  VideoStyle,
  VideoSpec,
  VideoClip,
  VideoAnimation,
  VideoKeyframe,
  VideoTextObject,
  VideoTextPart,
  VideoMotionBlockObject,
} from "./schema";
export { ticksToFrames, secondsToTicks, ticksToSeconds } from "./timing";
export { evaluateKeyframes, evaluateProperty } from "./animation";
export type { AnimValue } from "./animation";
export { deriveTextParts, deriveTextPartFamilies, SEGMENTATION_VERSION, LAYOUT_VERSION } from "./text";
export type { TextPart, TextPartKind, TextRange } from "./text";

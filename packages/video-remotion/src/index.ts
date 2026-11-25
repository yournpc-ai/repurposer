export { DeviceFrame } from "./engine/DeviceFrame";
export { clickCameraScale } from "./engine/cursor";
export { Video } from "./Video";
export {
  VIDEO_CAPABILITIES,
  VideoCapabilityError,
  assertVideoSupported,
} from "./capabilities";
export {
  STYLE_PRESETS,
  resolveStyleTokens,
  resolveBlockStyle,
  cardSurfaceStyle,
  highlightTapeStyle,
  contrastRatio,
  relativeLuminance,
  pickContrastInk,
  ensureContrastText,
  type StylePresetId,
  type BackdropStyle,
  type CardTreatment,
  type HeadlineTreatment,
  type CompositionStyleInput,
  type ResolvedStyleTokens,
  type ResolvedBlockStyle,
} from "./engine/styles";
export {
  TEXT_STYLE_PRESETS,
  cloneTextStylePresetToken,
  resolveTextPresetToken,
  type TextPresetStyleContext,
  type TextStylePresetId,
  type TextBackgroundMode,
  type TextTransform,
  type TextBorderToken,
  type TextStrokeToken,
  type TextShadowToken,
  type TextStylePresetToken,
} from "./engine/textPresets";

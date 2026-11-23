import { clamp01, cueProgress, easeInOutCubic, easeInOutSine, easeOutCubic, easeOutQuart, lerp } from "./math";

export type CameraPreset = "flat" | "tilt_left" | "tilt_right" | "dolly_zoom" | "scroll_reveal";
type CameraMotion = "subtle_push" | "settle_tilt" | "drift_focus" | "static";

export function evaluateCamera(
  preset: CameraPreset, tSec: number, durSec: number, focusX: number, focusY: number,
  zoomScale: number, scrollFromY: number, scrollToY: number,
  { motion = "settle_tilt", entranceSec = 0.9, unit = 1 }: { motion?: CameraMotion; entranceSec?: number; unit?: number } = {},
) {
  const progress = cueProgress(tSec, 0, durSec);
  const travel = easeInOutCubic(progress);
  const enter = easeOutQuart(tSec / entranceSec);
  const settle = 1 - easeOutCubic(cueProgress(tSec, 0, Math.min(durSec, 1.8)));
  const side = preset === "tilt_left" ? -1 : preset === "tilt_right" ? 1 : 0;
  const flat = preset === "flat";
  const rise = motion === "static" ? 0 : (1 - enter) * 38 * unit;
  const scale = motion === "static" ? 1 : lerp(0.945, 1, enter);
  const pitch = flat && motion === "settle_tilt" ? (1 - enter) * 6.5 : Math.abs(side) * 4 * settle;
  const hold = easeInOutSine(progress);
  const drift = flat && motion === "drift_focus" ? hold * unit : 0;
  const push = flat && motion !== "static" ? hold : preset === "dolly_zoom" ? travel : 0;
  const cropX = Math.round(focusX * 100);
  return {
    perspective: (flat ? 1800 : 1400) * unit,
    opacity: easeOutCubic(tSec / Math.max(0.2, entranceSec * 0.65)),
    stage: `translateY(${rise}px) scale(${scale}) rotateX(${pitch}deg) rotateY(${side * 10 * settle}deg)`,
    viewport: `translate(${(0.5 - focusX) * 48 * drift}px, ${(0.5 - focusY) * 32 * drift}px) scale(${lerp(1, zoomScale, push)})`,
    blur: preset === "dolly_zoom" ? 3 * settle * unit : 0,
    origin: `${cropX}% ${Math.round(focusY * 100)}%`,
    cropX,
    // Matching top and translateY percentages pan only the excess source height.
    cropY: preset === "scroll_reveal" ? lerp(scrollFromY, scrollToY, travel) * 100
      : Math.round(clamp01((focusY - 0.35) / 0.55) * 100),
  };
}

import React from "react";
import { Img } from "remotion";
import type { VideoClip, VideoMotionBlockObject, VideoSpec } from "@repurposer/video-spec";

import { clamp01, cueProgress, easeOutCubic, easeOutExpo, easeOutQuart, hexToRgba, springOut } from "./engine/math";
import { StudioBackdrop, studioInk, type BackdropStyle } from "./engine/backdrop";
import { evaluateCamera, type CameraPreset } from "./engine/camera";
import { VirtualCursor, type CursorCue } from "./engine/cursor";

import { ImageAdapter, type Frame } from "./blocks/Stage";
import { ChatDemoBlock } from "./blocks/ChatDemoBlock";
import { DeviceMockupBlock } from "./blocks/DeviceMockupBlock";
import { FlowDiagramBlock } from "./blocks/FlowDiagramBlock";
import { SplitCompareBlock } from "./blocks/SplitCompareBlock";
import { StepTimelineBlock } from "./blocks/StepTimelineBlock";
import { BentoFeaturesBlock } from "./blocks/BentoFeaturesBlock";
import { DataChartBlock } from "./blocks/DataChartBlock";
import { QuoteProofBlock } from "./blocks/QuoteProofBlock";

function fontStack(fonts: VideoSpec["fonts"]): string {
  const pinned = Array.from(new Set(fonts.map((f) => JSON.stringify(f.family))));
  return [...pinned, '"Inter"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"].join(", ");
}

function resolveResourceUrl(clip: VideoClip, obj: VideoMotionBlockObject, index = 0): string | null {
  const res = obj.resources[index];
  if (!res) return index === 0 ? (clip.source?.url ?? null) : null;
  if (index === 0 && clip.source && clip.source.digest === res.digest) {
    return clip.source.url;
  }
  return res.url;
}

/** Deterministically rolls the first numeric token inside a KPI string from 0 -> target. */
function formatCountUp(raw: string, progress: number): string {
  const match = raw.match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
  if (!match) return raw;
  const [, prefix, numText, suffix] = match;
  const hasCommas = numText.includes(",");
  const dotIdx = numText.indexOf(".");
  const decimals = dotIdx >= 0 ? numText.length - dotIdx - 1 : 0;
  const target = parseFloat(numText.replace(/,/g, ""));
  if (!Number.isFinite(target)) return raw;
  const current = target * easeOutExpo(progress);
  const fixed = decimals > 0 ? current.toFixed(decimals) : String(Math.round(current));
  if (!hasCommas) return `${prefix}${fixed}${suffix}`;
  const [intPart, decPart] = fixed.split(".");
  const withCommas = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${prefix}${decPart !== undefined ? `${withCommas}.${decPart}` : withCommas}${suffix}`;
}

/** Split a headline line into reveal tokens (Latin words or CJK chunks). */
function tokenizeLine(line: string): string[] {
  if (/\s/.test(line)) {
    return line.split(/(\s+)/).filter((part) => part.length > 0 && !/^\s+$/.test(part));
  }
  const chars = Array.from(line);
  if (chars.length <= 8) return chars;
  const chunks: string[] = [];
  for (let i = 0; i < chars.length; i += 2) {
    chunks.push(chars.slice(i, i + 2).join(""));
  }
  return chunks;
}

interface ProductShowcaseCallout {
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string | null;
}

const ProductShowcaseBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
  cueOffsetFrames: number;
}> = ({ clip, fonts, fps, cueOffsetFrames, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    url_bar?: string | null;
    badge?: string | null;
    theme?: "dark" | "light";
    chrome_mode?: "browser" | "frameless";
    camera_motion?: "subtle_push" | "settle_tilt" | "drift_focus" | "static";
    entrance_duration_s?: number;
    zoom_scale?: number;
    focus_x?: number;
    focus_y?: number;
    camera_preset?: CameraPreset;
    scroll_from_y?: number;
    scroll_to_y?: number;
    cursor?: CursorCue | null;
    callout_steps?: (ProductShowcaseCallout & { start_s: number; end_s: number })[];
    callout?: ProductShowcaseCallout | null;
    accent_color?: string;
    backdrop_style?: BackdropStyle;
    show_backdrop?: boolean;
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const durationFrames = Math.max(1, clip.end_frame - clip.start_frame);
  const tSec = frame / fps;

  const theme = props.theme ?? "light";
  const isDark = theme === "dark";
  const chromeMode = props.chrome_mode ?? "browser";
  const accent = props.accent_color ?? "#0D9488";
  const showBackdrop = props.show_backdrop ?? true;
  const cameraMotion = props.camera_motion ?? "settle_tilt";
  const entranceDur = Math.max(0.2, props.entrance_duration_s ?? 0.9);
  const zoomScale = Math.max(1.0, Math.min(1.35, props.zoom_scale ?? 1.05));
  const focusX = Math.max(0.1, Math.min(0.9, props.focus_x ?? 0.5));
  const focusY = Math.max(0.1, Math.min(0.9, props.focus_y ?? 0.35));

  const camera = evaluateCamera(
    props.camera_preset ?? "flat", tSec, Math.max(1, durationFrames - 1) / fps,
    focusX, focusY, zoomScale, props.scroll_from_y ?? 0, props.scroll_to_y ?? 1,
    { motion: cameraMotion, entranceSec: entranceDur, unit: scaleUnit },
  );
  const imageUrl = resolveResourceUrl(clip, obj, 0);
  const padX = Math.round((chromeMode === "frameless" ? 72 : 96) * scaleUnit);
  const padTop = Math.round((chromeMode === "frameless" ? 50 : 62) * scaleUnit);
  const padBottom = Math.round((chromeMode === "frameless" ? 56 : 78) * scaleUnit);
  const radius = Math.round(16 * scaleUnit);
  const chromeHeight = Math.round(38 * scaleUnit);
  const dotSize = Math.max(6, Math.round(9 * scaleUnit));

  const chromeBg = isDark ? "#11141C" : "#FFFFFF";
  const borderColor = isDark ? "rgba(255, 255, 255, 0.12)" : "rgba(15, 23, 42, 0.11)";
  const dividerColor = isDark ? "rgba(255, 255, 255, 0.07)" : "rgba(15, 23, 42, 0.08)";
  const urlBg = isDark ? "rgba(255, 255, 255, 0.045)" : "rgba(15, 23, 42, 0.045)";
  const urlText = isDark ? "#BFCAD3" : "#3A474C";

  const { cropX, cropY } = camera;
  const sizeCapture = React.useCallback((image: HTMLImageElement) => {
    // Remotion calls this after decode, before releasing the frame for capture.
    if (image.parentElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
      image.parentElement.style.setProperty("--capture-ratio", String(image.naturalWidth / image.naturalHeight));
    }
  }, []);

  const cueSec = (frame - cueOffsetFrames) / fps;
  const step = props.callout_steps?.find(s => s.start_s <= cueSec && cueSec < s.end_s);
  const callout = props.callout_steps?.length ? step : props.callout;
  const sinceReveal = step ? cueSec - step.start_s : tSec - entranceDur * 0.68;
  const calloutT = callout ? springOut(Math.max(0, sinceReveal), 11.5, 0.84) : 0;
  const calloutAlpha = callout ? easeOutCubic(sinceReveal / 0.42) : 0;
  const bracketLen = Math.round(18 * scaleUnit);
  const bracketThick = Math.max(2, Math.round(3 * scaleUnit));

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: showBackdrop ? (isDark ? "#070B11" : "#F5F7FA") : "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {showBackdrop ? (
        <StudioBackdrop theme={isDark ? "dark" : "light"} accent={accent} scaleUnit={scaleUnit} style={props.backdrop_style} tSec={tSec} />
      ) : null}

      <div
        style={{
          position: "absolute",
          left: padX,
          right: padX,
          top: padTop,
          bottom: padBottom,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          perspective: camera.perspective,
        }}
      >
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "100%",
            borderRadius: radius,
            overflow: "hidden",
            border: `1px solid ${borderColor}`,
            background: chromeBg,
            opacity: camera.opacity,
            transform: camera.stage,
            transformOrigin: "50% 60%",
            boxShadow: isDark
              ? `0 ${Math.round(36 * scaleUnit)}px ${Math.round(90 * scaleUnit)}px rgba(0, 0, 0, 0.62), 0 ${Math.round(6 * scaleUnit)}px ${Math.round(20 * scaleUnit)}px rgba(0, 0, 0, 0.4)`
              : `0 ${Math.round(28 * scaleUnit)}px ${Math.round(72 * scaleUnit)}px rgba(15, 23, 42, 0.14), 0 ${Math.round(4 * scaleUnit)}px ${Math.round(14 * scaleUnit)}px rgba(15, 23, 42, 0.06)`,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Precision specular top edge highlight */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: "12%",
              right: "12%",
              height: 1,
              background: isDark
                ? "linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent)"
                : "linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent)",
              pointerEvents: "none",
              zIndex: 4,
            }}
          />

          {chromeMode === "browser" ? (
            <div
              style={{
                height: chromeHeight,
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: `0 ${Math.round(16 * scaleUnit)}px`,
                background: chromeBg,
                borderBottom: `1px solid ${dividerColor}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: Math.round(7 * scaleUnit), width: "22%" }}>
                {["#B8776B", "#B59963", "#739883"].map(color => (
                  <span key={color} style={{ width: dotSize, height: dotSize, borderRadius: "50%", background: color }} />
                ))}
              </div>

              {props.url_bar ? (
                <div
                  style={{
                    padding: `${Math.round(4 * scaleUnit)}px ${Math.round(16 * scaleUnit)}px`,
                    borderRadius: Math.round(6 * scaleUnit),
                    background: urlBg,
                    color: urlText,
                    fontSize: Math.max(11, Math.round(13 * scaleUnit)),
                    letterSpacing: "0.02em",
                    fontWeight: 500,
                    maxWidth: "52%",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {props.url_bar}
                </div>
              ) : (
                <div />
              )}

              <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", width: "22%" }}>
                {props.badge ? (
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: Math.round(6 * scaleUnit),
                      padding: `${Math.round(3 * scaleUnit)}px ${Math.round(10 * scaleUnit)}px`,
                      borderRadius: 999,
                      background: hexToRgba(accent, isDark ? 0.16 : 0.12),
                      border: `1px solid ${hexToRgba(accent, 0.34)}`,
                      color: isDark ? "#E2E8F0" : "#0F172A",
                      fontSize: Math.max(10, Math.round(11.5 * scaleUnit)),
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                    }}
                  >
                    <span
                      style={{
                        width: Math.max(5, Math.round(6 * scaleUnit)),
                        height: Math.max(5, Math.round(6 * scaleUnit)),
                        borderRadius: "50%",
                        background: accent,
                      }}
                    />
                    {props.badge}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* Captured UI viewport with subtle camera push-in & optional precision callout */}
          <div
            style={{
              position: "relative",
              flex: 1,
              overflow: "hidden",
              background: isDark ? "#0B0E14" : "#FFFFFF",
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: 0,
                containerType: "size",
                transformOrigin: camera.origin,
                filter: camera.blur > 0 ? `blur(${camera.blur}px)` : undefined,
                transform: camera.viewport,
              }}
            >
              {/* Crop one source-sized plane so the image and its normalized box travel together. */}
              <div
                style={{
                  position: "absolute",
                  left: `${cropX}%`,
                  top: `${cropY}%`,
                  transform: `translate(-${cropX}%, -${cropY}%)`,
                  width: "max(100%, calc(100cqh * var(--capture-ratio, 1.7778)))",
                }}
              >
                {imageUrl ? (
                  <Img src={imageUrl} onImageFrame={sizeCapture} style={{ display: "block", width: "100%" }} />
                ) : null}

                {props.cursor && <VirtualCursor cue={props.cursor} tSec={cueSec} scaleUnit={scaleUnit} accent={accent} />}
                {callout && calloutAlpha > 0.005 ? (
                  <div
                    style={{
                      position: "absolute",
                      left: `${callout.x * 100}%`,
                      top: `${callout.y * 100}%`,
                      width: `${callout.width * 100}%`,
                      height: `${callout.height * 100}%`,
                      borderRadius: Math.round(12 * scaleUnit),
                      boxSizing: "border-box",
                      border: `1.5px solid ${hexToRgba(accent, 0.85)}`,
                      boxShadow: `0 0 0 9999px rgba(7, 11, 17, ${0.26 * calloutAlpha}), 0 0 ${Math.round(28 * scaleUnit)}px ${hexToRgba(accent, 0.32)}`,
                      opacity: calloutAlpha,
                      transform: step ? undefined : `scale(${0.96 + 0.04 * calloutT})`,
                      pointerEvents: "none",
                      zIndex: 3,
                    }}
                  >
                    {/* Precision corner L-brackets */}
                    <span style={{ position: "absolute", top: -1, left: -1, width: bracketLen, height: bracketLen, borderTop: `${bracketThick}px solid ${accent}`, borderLeft: `${bracketThick}px solid ${accent}`, borderTopLeftRadius: Math.round(10 * scaleUnit) }} />
                    <span style={{ position: "absolute", top: -1, right: -1, width: bracketLen, height: bracketLen, borderTop: `${bracketThick}px solid ${accent}`, borderRight: `${bracketThick}px solid ${accent}`, borderTopRightRadius: Math.round(10 * scaleUnit) }} />
                    <span style={{ position: "absolute", bottom: -1, left: -1, width: bracketLen, height: bracketLen, borderBottom: `${bracketThick}px solid ${accent}`, borderLeft: `${bracketThick}px solid ${accent}`, borderBottomLeftRadius: Math.round(10 * scaleUnit) }} />
                    <span style={{ position: "absolute", bottom: -1, right: -1, width: bracketLen, height: bracketLen, borderBottom: `${bracketThick}px solid ${accent}`, borderRight: `${bracketThick}px solid ${accent}`, borderBottomRightRadius: Math.round(10 * scaleUnit) }} />

                    {callout.label ? (
                      <div
                        style={{
                          position: "absolute",
                          left: 0,
                          ...(callout.y > 0.14
                            ? { bottom: "100%", marginBottom: Math.round(10 * scaleUnit) }
                            : { top: "100%", marginTop: Math.round(10 * scaleUnit) }),
                          display: "inline-flex",
                          alignItems: "center",
                          gap: Math.round(8 * scaleUnit),
                          padding: `${Math.round(7 * scaleUnit)}px ${Math.round(14 * scaleUnit)}px`,
                          borderRadius: 999,
                          background: "rgba(9, 17, 24, 0.92)",
                          border: `1px solid ${hexToRgba(accent, 0.55)}`,
                          color: "#F8FAFC",
                          fontSize: Math.max(12, Math.round(14 * scaleUnit)),
                          fontWeight: 600,
                          letterSpacing: "0.02em",
                          whiteSpace: "nowrap",
                          boxShadow: `0 ${Math.round(10 * scaleUnit)}px ${Math.round(28 * scaleUnit)}px rgba(0, 0, 0, 0.38)`,
                        }}
                      >
                        <span style={{ width: Math.max(6, Math.round(7 * scaleUnit)), height: Math.max(6, Math.round(7 * scaleUnit)), borderRadius: "50%", background: accent }} />
                        {callout.label}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const KineticTitleBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
}> = ({ clip, fonts, fps, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    headline: string;
    eyebrow?: string | null;
    subheadline?: string | null;
    align?: "left" | "center" | "right";
    position?: "top" | "center" | "bottom" | "bottom_left" | "top_left";
    entrance_duration_s?: number;
    exit_duration_s?: number;
    accent_color?: string;
    text_color?: string;
    surface_style?: "transparent" | "scrim" | "glass_card" | "light_card" | "pill_caption";
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const durationFrames = Math.max(1, clip.end_frame - clip.start_frame);
  const durationSec = durationFrames / fps;
  const tSec = frame / fps;

  const align = props.align ?? "left";
  const position = props.position ?? "bottom_left";
  const entranceDur = Math.max(0.2, props.entrance_duration_s ?? 0.75);
  const exitDur = Math.max(0, Math.min(durationSec * 0.4, props.exit_duration_s ?? 0.4));
  const accent = props.accent_color ?? "#14B8A6";
  const textColor = props.text_color ?? "#F8FAFC";
  const surfaceStyle = props.surface_style ?? "glass_card";

  const exitProgress =
    exitDur > 0 && tSec > durationSec - exitDur
      ? easeOutCubic((tSec - (durationSec - exitDur)) / exitDur)
      : 0;
  const globalAlpha = 1 - exitProgress;
  const exitLift = -exitProgress * 12 * scaleUnit;

  const justifyContent =
    position === "top" || position === "top_left"
      ? "flex-start"
      : position === "center"
        ? "center"
        : "flex-end";
  const alignItems =
    position === "bottom_left" || position === "top_left" || align === "left"
      ? "flex-start"
      : align === "right"
        ? "flex-end"
        : "center";

  // Compact contextual pill caption — avoids obscuring webpage hero text
  if (surfaceStyle === "pill_caption") {
    const pillT = springOut(tSec / Math.max(0.45, entranceDur * 0.85) * 0.7, 13.0, 0.82);
    const pillOpacity = easeOutCubic(tSec / Math.max(0.18, entranceDur * 0.5)) * globalAlpha;
    return (
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          overflow: "hidden",
          background: "transparent",
          fontFamily: fontStack(fonts),
          display: "flex",
          flexDirection: "column",
          justifyContent,
          alignItems,
          padding: `${Math.round((position === "top_left" ? 6 : 52) * scaleUnit)}px ${Math.round(96 * scaleUnit)}px`,
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: Math.round(14 * scaleUnit),
            padding: `${Math.round((position === "top_left" ? 6 : 13) * scaleUnit)}px ${Math.round(24 * scaleUnit)}px`,
            borderRadius: 999,
            background: "rgba(9, 17, 24, 0.97)",
            backdropFilter: "blur(20px)",
            border: `1px solid ${hexToRgba(accent, 0.42)}`,
            boxShadow: `0 ${Math.round(18 * scaleUnit)}px ${Math.round(44 * scaleUnit)}px rgba(0, 0, 0, 0.36)`,
            opacity: pillOpacity,
            transform: `translateY(${(1 - pillT) * (position === "top_left" ? -6 : 20) * scaleUnit + exitLift}px) scale(${0.96 + 0.04 * pillT})`,
            maxWidth: `${Math.round(1100 * scaleUnit)}px`,
          }}
        >
          <span
            style={{
              width: Math.max(7, Math.round(9 * scaleUnit)),
              height: Math.max(7, Math.round(9 * scaleUnit)),
              borderRadius: "50%",
              background: accent,
              boxShadow: `0 0 ${Math.round(12 * scaleUnit)}px ${hexToRgba(accent, 0.75)}`,
              flexShrink: 0,
            }}
          />
          {props.eyebrow ? (
            <span
              style={{
                fontSize: Math.max(12, Math.round(14 * scaleUnit)),
                fontWeight: 700,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: studioInk(accent, true),
                flexShrink: 0,
              }}
            >
              {props.eyebrow}
            </span>
          ) : null}
          {props.eyebrow ? (
            <span style={{ width: 1, height: Math.round(16 * scaleUnit), background: "rgba(255,255,255,0.20)", flexShrink: 0 }} />
          ) : null}
          <span
            style={{
              fontSize: Math.max(16, Math.round(21 * scaleUnit)),
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: studioInk(textColor, true),
              lineHeight: 1.2,
            }}
          >
            {props.headline.replace(/\n+/g, " ")}
          </span>
        </div>
      </div>
    );
  }

  const eyebrowT = easeOutQuart(tSec / Math.max(0.18, entranceDur * 0.55));
  const subT = easeOutQuart((tSec - entranceDur * 0.32) / Math.max(0.2, entranceDur * 0.68));
  const scrimAlpha = easeOutCubic(tSec / Math.max(0.2, entranceDur * 0.5)) * globalAlpha;

  const lines = props.headline
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const longestLine = Math.max(1, ...lines.map((l) => l.length));
  const baseHeadlinePx = longestLine > 44 ? 46 : longestLine > 28 ? 56 : 66;
  const headlineSize = Math.round(baseHeadlinePx * scaleUnit);
  const eyebrowSize = Math.max(12, Math.round(15 * scaleUnit));
  const subSize = Math.max(16, Math.round(24 * scaleUnit));

  const scrimGradient =
    position === "top" || position === "top_left"
      ? "linear-gradient(to bottom, rgba(7, 13, 17, 0.94) 0%, rgba(7, 13, 17, 0.68) 42%, rgba(7, 13, 17, 0) 76%)"
      : position === "center"
        ? "radial-gradient(ellipse 78% 66% at 50% 50%, rgba(7, 13, 17, 0.88) 0%, rgba(7, 13, 17, 0.50) 58%, rgba(7, 13, 17, 0) 100%)"
        : "linear-gradient(to top, rgba(7, 13, 17, 0.95) 0%, rgba(7, 13, 17, 0.72) 38%, rgba(7, 13, 17, 0) 72%)";

  const cardStyle: React.CSSProperties =
    surfaceStyle === "glass_card"
      ? {
          background: "rgba(10, 20, 24, 0.92)",
          backdropFilter: "blur(24px)",
          border: "1px solid rgba(255, 255, 255, 0.14)",
          borderRadius: Math.round(16 * scaleUnit),
          padding: `${Math.round(30 * scaleUnit)}px ${Math.round(38 * scaleUnit)}px`,
          boxShadow: `0 ${Math.round(28 * scaleUnit)}px ${Math.round(68 * scaleUnit)}px rgba(0, 0, 0, 0.48)`,
        }
      : surfaceStyle === "light_card"
        ? {
            background: "rgba(255, 255, 255, 0.94)",
            backdropFilter: "blur(24px)",
            border: "1px solid rgba(15, 23, 42, 0.10)",
            borderRadius: Math.round(16 * scaleUnit),
            padding: `${Math.round(30 * scaleUnit)}px ${Math.round(38 * scaleUnit)}px`,
            boxShadow: `0 ${Math.round(24 * scaleUnit)}px ${Math.round(60 * scaleUnit)}px rgba(15, 23, 42, 0.14)`,
          }
        : {};

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {surfaceStyle === "scrim" ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: scrimGradient,
            opacity: scrimAlpha,
            pointerEvents: "none",
          }}
        />
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 2,
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent,
          alignItems,
          padding: `${Math.round(68 * scaleUnit)}px ${Math.round(96 * scaleUnit)}px`,
          boxSizing: "border-box",
          opacity: globalAlpha,
          transform: `translateY(${exitLift}px)`,
        }}
      >
        <div
          style={{
            maxWidth: `${Math.round(1180 * scaleUnit)}px`,
            textAlign: align,
            display: "flex",
            flexDirection: "column",
            alignItems,
            gap: Math.round(14 * scaleUnit),
            ...cardStyle,
          }}
        >
          {props.eyebrow ? (
            <div style={{ overflow: "hidden", paddingBottom: 2 }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: Math.round(10 * scaleUnit),
                  fontSize: eyebrowSize,
                  fontWeight: 600,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: accent,
                  opacity: eyebrowT,
                  transform: `translateY(${(1 - eyebrowT) * 18 * scaleUnit}px)`,
                }}
              >
                <span
                  style={{
                    width: Math.round(22 * scaleUnit * eyebrowT),
                    height: Math.max(2, Math.round(2 * scaleUnit)),
                    background: accent,
                    borderRadius: 2,
                    display: "inline-block",
                  }}
                />
                <span>{props.eyebrow}</span>
              </div>
            </div>
          ) : null}

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems,
              gap: Math.round(4 * scaleUnit),
            }}
          >
            {lines.map((line, index) => {
              const stagger = index * (entranceDur * 0.14);
              const lineWindow = Math.max(0.22, entranceDur * 0.72);
              const lineT = easeOutQuart((tSec - stagger) / lineWindow);
              return (
                <div
                  key={`${index}:${line}`}
                  style={{
                    overflow: "hidden",
                    paddingBottom: Math.round(6 * scaleUnit),
                    marginBottom: -Math.round(6 * scaleUnit),
                  }}
                >
                  <div
                    style={{
                      fontSize: headlineSize,
                      fontWeight: 700,
                      lineHeight: 1.08,
                      letterSpacing: `${-0.028 + (1 - lineT) * 0.015}em`,
                      color: textColor,
                      opacity: clamp01(lineT * 1.15),
                      transform: `translateY(${(1 - lineT) * 105}%)`,
                      textShadow:
                        surfaceStyle === "transparent"
                          ? "0 2px 24px rgba(0, 0, 0, 0.55)"
                          : surfaceStyle === "light_card"
                            ? "none"
                            : "0 1px 16px rgba(0, 0, 0, 0.28)",
                    }}
                  >
                    {line}
                  </div>
                </div>
              );
            })}
          </div>

          {props.subheadline ? (
            <div style={{ overflow: "hidden", paddingTop: Math.round(2 * scaleUnit) }}>
              <div
                style={{
                  fontSize: subSize,
                  fontWeight: 400,
                  lineHeight: 1.42,
                  letterSpacing: "-0.005em",
                  color: textColor,
                  opacity: subT * 0.84,
                  transform: `translateY(${(1 - subT) * 20 * scaleUnit}px)`,
                  maxWidth: `${Math.round(880 * scaleUnit)}px`,
                }}
              >
                {props.subheadline}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

/**
 * 1. StatementHookBlock — standalone editorial typography opener / act divider
 * with masked word-by-word spring reveal and animated highlight phrase sweep.
 */
const StatementHookBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
  cueOffsetFrames: number;
}> = ({ clip, fonts, fps, cueOffsetFrames, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    headline: string;
    eyebrow?: string | null;
    highlight_phrase?: string | null;
    highlight_at_s?: number | null;
    subheadline?: string | null;
    theme?: "light" | "dark";
    layout_variant?: "centered" | "editorial_left";
    accent_color?: string;
    entrance_duration_s?: number;
    exit_duration_s?: number;
    backdrop_style?: BackdropStyle;
    show_backdrop?: boolean;
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const durationFrames = Math.max(1, clip.end_frame - clip.start_frame);
  const durationSec = durationFrames / fps;
  const tSec = frame / fps;

  const isDark = (props.theme ?? "light") === "dark";
  const isCentered = (props.layout_variant ?? "centered") === "centered";
  const accent = props.accent_color ?? "#0D9488";
  const showBackdrop = props.show_backdrop ?? true;
  const entranceDur = Math.max(0.25, props.entrance_duration_s ?? 0.9);
  const exitDur = Math.max(0, Math.min(durationSec * 0.35, props.exit_duration_s ?? 0.35));

  const exitProgress =
    exitDur > 0 && tSec > durationSec - exitDur
      ? easeOutCubic((tSec - (durationSec - exitDur)) / exitDur)
      : 0;
  const globalAlpha = 1 - exitProgress;
  const exitLift = -exitProgress * 18 * scaleUnit;

  const inkPrimary = isDark ? "#F8FAFC" : "#0F172A";
  const inkMuted = isDark ? "#BFCAD3" : "#3A474C";
  const ruleColor = isDark ? "rgba(255, 255, 255, 0.14)" : "rgba(15, 23, 42, 0.12)";

  const eyebrowT = springOut(tSec, 13.5, 0.84);
  const ruleT = easeOutQuart((tSec - 0.08) / Math.max(0.35, entranceDur * 0.65));

  const lines = props.headline
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const totalChars = props.headline.length;
  const baseHeadlinePx = totalChars > 72 ? 62 : totalChars > 42 ? 78 : 94;
  const headlineSize = Math.round(baseHeadlinePx * scaleUnit);
  const highlightNeedle = (props.highlight_phrase ?? "").trim().toLowerCase();

  let runningTokenIdx = 0;
  const totalTokens = Math.max(1, lines.reduce((sum, l) => sum + tokenizeLine(l).length, 0));
  const tokenStep = Math.min(0.055, (entranceDur * 0.55) / Math.max(1, totalTokens));
  const subStart = entranceDur * 0.58;
  const subT = easeOutQuart((tSec - subStart) / Math.max(0.28, entranceDur * 0.6));
  const highlightStart = props.highlight_at_s == null ? entranceDur * 0.52 : props.highlight_at_s + cueOffsetFrames / fps;
  const highlightSweep = easeOutQuart(cueProgress(tSec, highlightStart, 0.55));

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: showBackdrop ? (isDark ? "#070B11" : "#F5F7FA") : "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {showBackdrop ? (
        <StudioBackdrop theme={isDark ? "dark" : "light"} accent={accent} scaleUnit={scaleUnit} style={props.backdrop_style} tSec={tSec} />
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 2,
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: isCentered ? "center" : "flex-start",
          padding: `${Math.round(80 * scaleUnit)}px ${Math.round(140 * scaleUnit)}px`,
          boxSizing: "border-box",
          opacity: globalAlpha,
          transform: `translateY(${exitLift}px)`,
        }}
      >
        <div
          style={{
            maxWidth: `${Math.round(1480 * scaleUnit)}px`,
            width: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: isCentered ? "center" : "flex-start",
            textAlign: isCentered ? "center" : "left",
            gap: Math.round(24 * scaleUnit),
          }}
        >
          {props.eyebrow ? (
            <div style={{ overflow: "hidden", paddingBottom: 2 }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: Math.round(12 * scaleUnit),
                  padding: `${Math.round(7 * scaleUnit)}px ${Math.round(16 * scaleUnit)}px`,
                  borderRadius: 999,
                  background: hexToRgba(accent, isDark ? 0.14 : 0.10),
                  border: `1px solid ${hexToRgba(accent, isDark ? 0.34 : 0.28)}`,
                  fontSize: Math.max(13, Math.round(15 * scaleUnit)),
                  fontWeight: 600,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                  color: studioInk(accent, isDark),
                  opacity: clamp01(eyebrowT * 1.15),
                  transform: `translateY(${(1 - eyebrowT) * 20 * scaleUnit}px)`,
                }}
              >
                <span style={{ width: Math.max(6, Math.round(7 * scaleUnit)), height: Math.max(6, Math.round(7 * scaleUnit)), borderRadius: "50%", background: accent }} />
                {props.eyebrow}
              </div>
            </div>
          ) : null}

          {/* Masked word-by-word editorial headline with optional highlight sweep */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: isCentered ? "center" : "flex-start",
              gap: Math.round(10 * scaleUnit),
            }}
          >
            {lines.map((line, lineIdx) => {
              const lowerLine = line.toLowerCase();
              const matchIdx = highlightNeedle ? lowerLine.indexOf(highlightNeedle) : -1;
              const matchEnd = matchIdx >= 0 ? matchIdx + highlightNeedle.length : -1;
              const hasSpaces = /\s/.test(line);
              const tokens = tokenizeLine(line);
              let cursor = 0;

              return (
                <div
                  key={`${lineIdx}:${line}`}
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: isCentered ? "center" : "flex-start",
                    columnGap: hasSpaces ? Math.round(headlineSize * 0.24) : 0,
                    rowGap: Math.round(8 * scaleUnit),
                  }}
                >
                  {tokens.map((tok, tokIdx) => {
                    const tokPos = line.indexOf(tok, cursor);
                    if (tokPos >= 0) cursor = tokPos + tok.length;
                    const inHighlight =
                      matchIdx >= 0 &&
                      tokPos >= 0 &&
                      tokPos >= matchIdx &&
                      tokPos + tok.length <= matchEnd;
                    const delay = 0.08 + runningTokenIdx * tokenStep;
                    runningTokenIdx += 1;
                    const localT = Math.max(0, tSec - delay);
                    const s = springOut(localT, 12.5, 0.80);
                    const op = easeOutCubic(localT / 0.26);

                    return (
                      <span
                        key={`${lineIdx}:${tokIdx}:${tok}`}
                        style={{
                          display: "inline-block",
                          overflow: "hidden",
                          padding: `${Math.round(4 * scaleUnit)}px ${inHighlight ? Math.round(10 * scaleUnit) : 0}px`,
                          margin: `-${Math.round(4 * scaleUnit)}px ${inHighlight ? -Math.round(4 * scaleUnit) : 0}px`,
                          position: "relative",
                        }}
                      >
                        {inHighlight ? (
                          <span
                            style={{
                              position: "absolute",
                              left: 0,
                              right: 0,
                              bottom: Math.round(6 * scaleUnit),
                              height: "36%",
                              borderRadius: Math.round(8 * scaleUnit),
                              background: hexToRgba(accent, isDark ? 0.12 : 0.14),
                              transformOrigin: "left center",
                              transform: `scaleX(${highlightSweep})`,
                              pointerEvents: "none",
                            }}
                          />
                        ) : null}
                        <span
                          style={{
                            position: "relative",
                            display: "inline-block",
                            fontSize: headlineSize,
                            fontWeight: 700,
                            lineHeight: 1.08,
                            letterSpacing: `${-0.032 + (1 - clamp01(s)) * 0.014}em`,
                            color: inHighlight ? `color-mix(in srgb, ${studioInk(accent, isDark)} ${highlightSweep * 100}%, ${inkPrimary})` : inkPrimary,
                            opacity: op,
                            transform: `translateY(${(1 - s) * 108}%)`,
                          }}
                        >
                          {tok}
                        </span>
                      </span>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Precision expanding accent divider */}
          <div
            style={{
              width: `${Math.round(96 * scaleUnit)}px`,
              height: Math.max(2, Math.round(3 * scaleUnit)),
              borderRadius: 99,
              background: `linear-gradient(90deg, ${accent}, ${hexToRgba(accent, 0.25)})`,
              transformOrigin: isCentered ? "center" : "left",
              transform: `scaleX(${ruleT})`,
              opacity: ruleT,
            }}
          />

          {props.subheadline ? (
            <div style={{ overflow: "hidden", maxWidth: `${Math.round(1040 * scaleUnit)}px` }}>
              <div
                style={{
                  fontSize: Math.round(28 * scaleUnit),
                  fontWeight: 400,
                  lineHeight: 1.48,
                  letterSpacing: "-0.008em",
                  color: inkMuted,
                  opacity: subT,
                  transform: `translateY(${(1 - subT) * 26 * scaleUnit}px)`,
                }}
              >
                {props.subheadline}
              </div>
            </div>
          ) : null}

          {/* Subtle institutional architectural hairline footer */}
          <div
            style={{
              position: "absolute",
              left: Math.round(140 * scaleUnit),
              right: Math.round(140 * scaleUnit),
              bottom: Math.round(54 * scaleUnit),
              height: 1,
              background: ruleColor,
              transformOrigin: "left",
              transform: `scaleX(${easeOutQuart(tSec / 1.1)})`,
              opacity: 0.7,
            }}
          />
        </div>
      </div>
    </div>
  );
};

interface MetricGridItem {
  reveal_at_s?: number | null;
  value: string;
  label: string;
  detail?: string | null;
  badge?: string | null;
}

/**
 * 2. MetricGridBlock — 2-4 elevated institutional metric/capability cards with
 * staggered damped spring settle, deterministic numeric count-up, top specular
 * sheen sweep across each card.
 */
const MetricGridBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
  cueOffsetFrames: number;
}> = ({ clip, fonts, fps, cueOffsetFrames, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    eyebrow?: string | null;
    title?: string | null;
    items: MetricGridItem[];
    columns?: 2 | 3;
    theme?: "light" | "dark";
    accent_color?: string;
    stagger_s?: number;
    count_up?: boolean;
    backdrop_style?: BackdropStyle;
    show_backdrop?: boolean;
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const tSec = frame / fps;

  const isDark = (props.theme ?? "light") === "dark";
  const accent = props.accent_color ?? "#0D9488";
  const showBackdrop = props.show_backdrop ?? true;
  const stagger = props.stagger_s ?? 0.14;
  const countUp = props.count_up ?? true;
  const items = props.items ?? [];
  const cols = items.length === 2 || items.length === 4 ? 2 : (props.columns ?? 3);

  const inkPrimary = isDark ? "#F8FAFC" : "#0F172A";
  const inkSecondary = isDark ? "#BFCAD3" : "#3A474C";
  const cardBg = isDark ? "rgba(15, 22, 33, 0.88)" : "rgba(255, 255, 255, 0.94)";
  const cardBorder = isDark ? "rgba(255, 255, 255, 0.10)" : "rgba(15, 23, 42, 0.09)";

  const headerT = springOut(tSec, 13.0, 0.84);
  const headerOp = easeOutCubic(tSec / 0.35);
  const hasDetail = items.some((item) => item.detail);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: showBackdrop ? (isDark ? "#070B11" : "#F5F7FA") : "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {showBackdrop ? (
        <StudioBackdrop theme={isDark ? "dark" : "light"} accent={accent} scaleUnit={scaleUnit} style={props.backdrop_style} tSec={tSec} />
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 2,
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: `${Math.round(72 * scaleUnit)}px ${Math.round(112 * scaleUnit)}px`,
          boxSizing: "border-box",
          gap: Math.round(44 * scaleUnit),
        }}
      >
        {(props.eyebrow || props.title) ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: Math.round(12 * scaleUnit),
              opacity: headerOp,
              transform: `translateY(${(1 - headerT) * 24 * scaleUnit}px)`,
            }}
          >
            {props.eyebrow ? (
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: Math.round(10 * scaleUnit),
                  fontSize: Math.max(13, Math.round(15 * scaleUnit)),
                  fontWeight: 600,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: studioInk(accent, isDark),
                }}
              >
                <span style={{ width: Math.round(24 * scaleUnit * clamp01(headerT)), height: Math.max(2, Math.round(2.5 * scaleUnit)), background: accent, borderRadius: 2 }} />
                {props.eyebrow}
              </div>
            ) : null}
            {props.title ? (
              <div
                style={{
                  fontSize: Math.round(52 * scaleUnit),
                  fontWeight: 700,
                  lineHeight: 1.12,
                  letterSpacing: "-0.028em",
                  color: inkPrimary,
                  maxWidth: `${Math.round(1260 * scaleUnit)}px`,
                }}
              >
                {props.title}
              </div>
            ) : null}
          </div>
        ) : null}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
            gap: Math.round(28 * scaleUnit),
            width: "100%",
          }}
        >
          {items.map((item, idx) => {
            const cardDelay = item.reveal_at_s == null ? 0.22 + idx * stagger : item.reveal_at_s + cueOffsetFrames / fps;
            const localT = Math.max(0, tSec - cardDelay);
            const settle = springOut(localT, 12.2, 0.80);
            const alpha = easeOutCubic(localT / 0.34);
            const countProgress = countUp ? clamp01((localT - 0.06) / 0.92) : 1;
            const shownValue = countUp ? formatCountUp(item.value, countProgress) : item.value;
            const sheenX = -40 + easeOutQuart((localT - 0.18) / 0.9) * 180;
            const valueSize = item.value.length > 8 ? 50 : 66;

            return (
              <div
                key={`${idx}:${item.label}`}
                style={{
                  position: "relative",
                  overflow: "hidden",
                  borderRadius: Math.round(20 * scaleUnit),
                  background: cardBg,
                  border: `1px solid ${cardBorder}`,
                  padding: `${Math.round((hasDetail ? 34 : 24) * scaleUnit)}px ${Math.round(34 * scaleUnit)}px`,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  opacity: alpha,
                  transform: `translateY(${(1 - settle) * 34 * scaleUnit}px) scale(${0.955 + 0.045 * settle})`,
                  boxShadow: isDark
                    ? `0 ${Math.round(24 * scaleUnit)}px ${Math.round(64 * scaleUnit)}px rgba(0, 0, 0, 0.48)`
                    : `0 ${Math.round(20 * scaleUnit)}px ${Math.round(52 * scaleUnit)}px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(15, 23, 42, 0.04)`,
                }}
              >
                {/* Animated top-edge specular sheen */}
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: `${sheenX}%`,
                    width: "45%",
                    height: Math.max(2, Math.round(2.5 * scaleUnit)),
                    background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
                    opacity: localT > 0.15 && localT < 1.3 ? 0.85 : 0.25,
                    pointerEvents: "none",
                  }}
                />

                <div style={{ display: "flex", flexDirection: "column", gap: Math.round(12 * scaleUnit) }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                    <span
                      style={{
                        fontSize: Math.max(13, Math.round(16 * scaleUnit)),
                        fontWeight: 600,
                        letterSpacing: "0.04em",
                        color: inkSecondary,
                      }}
                    >
                      {item.label}
                    </span>
                    {item.badge ? (
                      <span
                        style={{
                          padding: `${Math.round(4 * scaleUnit)}px ${Math.round(11 * scaleUnit)}px`,
                          borderRadius: 999,
                          background: hexToRgba(accent, isDark ? 0.16 : 0.11),
                          border: `1px solid ${hexToRgba(accent, 0.30)}`,
                          color: studioInk(accent, isDark),
                          fontSize: Math.max(11, Math.round(12.5 * scaleUnit)),
                          fontWeight: 600,
                          letterSpacing: "0.04em",
                        }}
                      >
                        {item.badge}
                      </span>
                    ) : null}
                  </div>

                  <div
                    style={{
                      fontSize: Math.round(valueSize * scaleUnit),
                      fontWeight: 700,
                      lineHeight: 1.04,
                      letterSpacing: "-0.035em",
                      fontVariantNumeric: "tabular-nums",
                      color: inkPrimary,
                    }}
                  >
                    {shownValue}
                  </div>

                  {item.detail ? (
                    <div
                      style={{
                        fontSize: Math.round(19 * scaleUnit),
                        fontWeight: 400,
                        lineHeight: 1.45,
                        color: inkSecondary,
                      }}
                    >
                      {item.detail}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/**
 * 3. ClosingCtaBlock — authoritative brand finale with optional protected logo
 * pill (light_pill | raw), pure-typography fallback, expanding hairline, and
 * glowing CTA/URL capsule.
 */
const ClosingCtaBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
}> = ({ clip, fonts, fps, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    brand_name: string;
    tagline: string;
    cta_label?: string | null;
    url_text?: string | null;
    theme?: "light" | "dark";
    accent_color?: string;
    entrance_duration_s?: number;
    logo_surface?: "light_pill" | "raw";
    backdrop_style?: BackdropStyle;
    show_backdrop?: boolean;
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const durationFrames = Math.max(1, clip.end_frame - clip.start_frame);
  const tSec = frame / fps;
  const progressAll = clamp01(frame / Math.max(1, durationFrames - 1));

  const isDark = (props.theme ?? "dark") === "dark";
  const accent = props.accent_color ?? "#14B8A6";
  const showBackdrop = props.show_backdrop ?? true;
  const entranceDur = Math.max(0.25, props.entrance_duration_s ?? 0.9);
  const logoSurface = props.logo_surface ?? "light_pill";
  const logoUrl = resolveResourceUrl(clip, obj, 0);

  const inkPrimary = isDark ? "#F8FAFC" : "#0F172A";
  const inkMuted = isDark ? "#BFCAD3" : "#3A474C";
  const tickColor = isDark ? "rgba(255, 255, 255, 0.16)" : "rgba(15, 23, 42, 0.16)";

  const brandT = springOut(tSec, 12.0, 0.82);
  const brandOp = easeOutCubic(tSec / Math.max(0.22, entranceDur * 0.45));
  const dividerT = easeOutQuart((tSec - entranceDur * 0.22) / 0.55);
  const tagT = easeOutQuart((tSec - entranceDur * 0.30) / 0.55);
  const ctaT = springOut(Math.max(0, tSec - entranceDur * 0.48), 11.5, 0.82);
  const ctaOp = easeOutCubic((tSec - entranceDur * 0.48) / 0.36);
  const shimmerPos = -30 + easeOutQuart((tSec - entranceDur * 0.85) / 1.1) * 160;
  const arrowNudge = Math.sin(progressAll * Math.PI * 2) * 3 * scaleUnit;

  const markSize = Math.round(20 * scaleUnit);
  const inset = Math.round(52 * scaleUnit);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: showBackdrop ? (isDark ? "#070B11" : "#F5F7FA") : "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {showBackdrop ? (
        <StudioBackdrop theme={isDark ? "dark" : "light"} accent={accent} scaleUnit={scaleUnit} style={props.backdrop_style} tSec={tSec} />
      ) : null}

      {/* Faint institutional studio corner registration marks */}
      {showBackdrop ? (
        <>
          <span style={{ position: "absolute", top: inset, left: inset, width: markSize, height: markSize, borderTop: `1.5px solid ${tickColor}`, borderLeft: `1.5px solid ${tickColor}` }} />
          <span style={{ position: "absolute", top: inset, right: inset, width: markSize, height: markSize, borderTop: `1.5px solid ${tickColor}`, borderRight: `1.5px solid ${tickColor}` }} />
          <span style={{ position: "absolute", bottom: inset, left: inset, width: markSize, height: markSize, borderBottom: `1.5px solid ${tickColor}`, borderLeft: `1.5px solid ${tickColor}` }} />
          <span style={{ position: "absolute", bottom: inset, right: inset, width: markSize, height: markSize, borderBottom: `1.5px solid ${tickColor}`, borderRight: `1.5px solid ${tickColor}` }} />
        </>
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 2,
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
          padding: `${Math.round(80 * scaleUnit)}px ${Math.round(140 * scaleUnit)}px`,
          boxSizing: "border-box",
          gap: Math.round(28 * scaleUnit),
        }}
      >
        {/* Optional protected logo pill or refined pure-typography emblem */}
        {logoUrl ? (
          <div
            style={{
              opacity: brandOp,
              transform: `translateY(${(1 - brandT) * 20 * scaleUnit}px) scale(${0.94 + 0.06 * brandT})`,
              ...(logoSurface === "light_pill"
                ? {
                    background: "#FFFFFF",
                    padding: `${Math.round(14 * scaleUnit)}px ${Math.round(28 * scaleUnit)}px`,
                    borderRadius: Math.round(18 * scaleUnit),
                    border: "1px solid rgba(15, 23, 42, 0.08)",
                    boxShadow: `0 ${Math.round(16 * scaleUnit)}px ${Math.round(44 * scaleUnit)}px rgba(0, 0, 0, 0.28)`,
                  }
                : {}),
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Img
              src={logoUrl}
              style={{
                maxHeight: Math.round(72 * scaleUnit),
                maxWidth: Math.round(260 * scaleUnit),
                objectFit: "contain",
              }}
            />
          </div>
        ) : (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: Math.round(10 * scaleUnit),
              opacity: brandOp,
              transform: `translateY(${(1 - brandT) * 16 * scaleUnit}px)`,
            }}
          >
            <span
              style={{
                width: Math.round(10 * scaleUnit),
                height: Math.round(10 * scaleUnit),
                borderRadius: Math.round(3 * scaleUnit),
                background: accent,
                transform: "rotate(45deg)",
                display: "inline-block",
              }}
            />
            <span
              style={{
                width: Math.round(38 * scaleUnit * dividerT),
                height: Math.max(2, Math.round(2 * scaleUnit)),
                background: hexToRgba(accent, 0.6),
                borderRadius: 2,
              }}
            />
          </div>
        )}

        {/* Brand name masked rise */}
        <div style={{ overflow: "hidden", paddingBottom: Math.round(6 * scaleUnit) }}>
          <div
            style={{
              fontSize: Math.round(84 * scaleUnit),
              fontWeight: 700,
              lineHeight: 1.04,
              letterSpacing: `${-0.035 + (1 - clamp01(brandT)) * 0.015}em`,
              color: inkPrimary,
              opacity: brandOp,
              transform: `translateY(${(1 - brandT) * 90}%)`,
            }}
          >
            {props.brand_name}
          </div>
        </div>

        {/* Expanding precision hairline */}
        <div
          style={{
            width: `${Math.round(132 * scaleUnit)}px`,
            height: Math.max(2, Math.round(3 * scaleUnit)),
            borderRadius: 99,
            background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
            transform: `scaleX(${dividerT})`,
            opacity: dividerT,
          }}
        />

        {/* Tagline */}
        <div style={{ overflow: "hidden", maxWidth: `${Math.round(980 * scaleUnit)}px` }}>
          <div
            style={{
              fontSize: Math.round(30 * scaleUnit),
              fontWeight: 400,
              lineHeight: 1.44,
              letterSpacing: "-0.01em",
              color: inkMuted,
              opacity: tagT,
              transform: `translateY(${(1 - tagT) * 24 * scaleUnit}px)`,
            }}
          >
            {props.tagline}
          </div>
        </div>

        {/* CTA / URL capsule */}
        {(props.cta_label || props.url_text) ? (
          <div
            style={{
              marginTop: Math.round(12 * scaleUnit),
              position: "relative",
              overflow: "hidden",
              display: "inline-flex",
              alignItems: "center",
              gap: Math.round(16 * scaleUnit),
              padding: `${Math.round(16 * scaleUnit)}px ${Math.round(32 * scaleUnit)}px`,
              borderRadius: 999,
              background: isDark ? "rgba(15, 25, 34, 0.92)" : "#0F172A",
              border: `1px solid ${hexToRgba(accent, 0.55)}`,
              boxShadow: `0 ${Math.round(20 * scaleUnit)}px ${Math.round(52 * scaleUnit)}px ${hexToRgba(accent, isDark ? 0.22 : 0.18)}`,
              opacity: ctaOp,
              transform: `translateY(${(1 - ctaT) * 24 * scaleUnit}px) scale(${0.95 + 0.05 * ctaT})`,
            }}
          >
            {/* Subtle animated specular shimmer */}
            <div
              style={{
                position: "absolute",
                top: 0,
                bottom: 0,
                left: `${shimmerPos}%`,
                width: "28%",
                background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent)",
                pointerEvents: "none",
              }}
            />
            {props.cta_label ? (
              <span
                style={{
                  fontSize: Math.round(18 * scaleUnit),
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                  color: studioInk(accent, true),
                }}
              >
                {props.cta_label}
              </span>
            ) : null}
            {props.cta_label && props.url_text ? (
              <span style={{ width: 1, height: Math.round(18 * scaleUnit), background: "rgba(255,255,255,0.22)" }} />
            ) : null}
            {props.url_text ? (
              <span
                style={{
                  fontSize: Math.round(21 * scaleUnit),
                  fontWeight: 600,
                  letterSpacing: "0.01em",
                  color: "#F8FAFC",
                }}
              >
                {props.url_text}
              </span>
            ) : null}
            <svg
              width={Math.round(18 * scaleUnit)}
              height={Math.round(18 * scaleUnit)}
              viewBox="0 0 20 20"
              fill="none"
              role="presentation"
              style={{ transform: `translateX(${arrowNudge}px)` }}
            >
              <path
                d="M4 10H16M16 10L11 5M16 10L11 15"
                stroke={accent}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        ) : null}
      </div>
    </div>
  );
};

// The API validates each closed prop model before the JSON reaches video-spec.
function narrative<P>(Block: React.ComponentType<{ props: P; frame: Frame }>) {
  return (props: VideoMotionBlockObject["props"], frame: Frame) => <Block props={props as P} frame={frame} />;
}

const narratives = {
  chat_demo: narrative(ChatDemoBlock),
  device_mockup: narrative(DeviceMockupBlock),
  flow_diagram: narrative(FlowDiagramBlock),
  split_compare: narrative(SplitCompareBlock),
  step_timeline: narrative(StepTimelineBlock),
  bento_features: narrative(BentoFeaturesBlock),
  data_chart: narrative(DataChartBlock),
  quote_proof: narrative(QuoteProofBlock),
} as const;

export const MotionBlockView: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
  cueOffsetFrames?: number;
  tailFrames?: number;
  containerStyle: React.CSSProperties;
}> = ({ clip, fonts, fps, cueOffsetFrames = 0, tailFrames = 0, frame, containerStyle }) => {
  const id = clip.object.block_id;
  if (id in narratives) {
    const render = narratives[id as keyof typeof narratives];
    const { layout, resources, props } = clip.object;
    const timing: Frame = {
      tSec: (frame - cueOffsetFrames) / fps,
      durSec: (clip.end_frame - clip.start_frame - cueOffsetFrames - tailFrames) / fps,
      scaleUnit: Math.min(layout.width / 1920, layout.height / 1080),
      fontFamily: fontStack(fonts),
      resources: resources.map((resource, i) => resolveResourceUrl(clip, clip.object, i) ?? resource.url),
    };
    return (
      <div style={containerStyle}>
        <ImageAdapter.Provider value={Img}>{render(props, timing)}</ImageAdapter.Provider>
      </div>
    );
  }
  return (
    <div style={containerStyle}>
      {id === "product_showcase" ? (
        <ProductShowcaseBlock cueOffsetFrames={cueOffsetFrames} clip={clip} fonts={fonts} fps={fps} frame={frame} />
      ) : id === "statement_hook" ? (
        <StatementHookBlock cueOffsetFrames={cueOffsetFrames} clip={clip} fonts={fonts} fps={fps} frame={frame} />
      ) : id === "metric_grid" ? (
        <MetricGridBlock cueOffsetFrames={cueOffsetFrames} clip={clip} fonts={fonts} fps={fps} frame={frame} />
      ) : id === "closing_cta" ? (
        <ClosingCtaBlock clip={clip} fonts={fonts} fps={fps} frame={frame} />
      ) : (
        <KineticTitleBlock clip={clip} fonts={fonts} fps={fps} frame={frame} />
      )}
    </div>
  );
};

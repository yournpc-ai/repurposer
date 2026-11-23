import React from "react";
import { Img } from "remotion";
import type { VideoClip, VideoMotionBlockObject, VideoSpec } from "@repurposer/video-spec";

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function easeOutQuart(t: number): number {
  const u = 1 - clamp01(t);
  return 1 - u * u * u * u;
}

function easeOutCubic(t: number): number {
  const u = 1 - clamp01(t);
  return 1 - u * u * u;
}

function easeInOutSine(t: number): number {
  return -(Math.cos(Math.PI * clamp01(t)) - 1) / 2;
}

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return `rgba(59, 130, 246, ${alpha})`;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function fontStack(fonts: VideoSpec["fonts"]): string {
  const pinned = Array.from(new Set(fonts.map((f) => JSON.stringify(f.family))));
  return [...pinned, '"Inter"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"].join(", ");
}

function resolvePrimaryImageUrl(clip: VideoClip, obj: VideoMotionBlockObject): string | null {
  const first = obj.resources[0];
  if (!first) return clip.source?.url ?? null;
  if (clip.source && clip.source.digest === first.digest) {
    return clip.source.url;
  }
  return first.url;
}

const ProductShowcaseBlock: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
}> = ({ clip, fonts, fps, frame }) => {
  const obj = clip.object;
  const props = obj.props as {
    url_bar?: string | null;
    badge?: string | null;
    theme?: "dark" | "light";
    camera_motion?: "subtle_push" | "settle_tilt" | "drift_focus" | "static";
    entrance_duration_s?: number;
    zoom_scale?: number;
    focus_x?: number;
    focus_y?: number;
    accent_color?: string;
    show_backdrop?: boolean;
  };

  const width = obj.layout.width;
  const height = obj.layout.height;
  const scaleUnit = Math.min(width / 1920, height / 1080);
  const durationFrames = Math.max(1, clip.end_frame - clip.start_frame);
  const tSec = frame / fps;
  const progressAll = clamp01(frame / Math.max(1, durationFrames - 1));

  const theme = props.theme ?? "light";
  const isDark = theme === "dark";
  const accent = props.accent_color ?? "#0D9488";
  const showBackdrop = props.show_backdrop ?? true;
  const cameraMotion = props.camera_motion ?? "settle_tilt";
  const entranceDur = Math.max(0.2, props.entrance_duration_s ?? 0.9);
  const zoomScale = Math.max(1.0, Math.min(1.35, props.zoom_scale ?? 1.05));
  const focusX = Math.max(0.1, Math.min(0.9, props.focus_x ?? 0.5));
  const focusY = Math.max(0.1, Math.min(0.9, props.focus_y ?? 0.35));

  const enterT = easeOutQuart(tSec / entranceDur);
  const enterOpacity = easeOutCubic(tSec / Math.max(0.2, entranceDur * 0.65));

  const tiltDeg = cameraMotion === "settle_tilt" ? (1 - enterT) * 6.5 : 0;
  const risePx = cameraMotion === "static" ? 0 : (1 - enterT) * 38 * scaleUnit;
  const frameScale = cameraMotion === "static" ? 1 : 0.945 + 0.055 * enterT;

  const holdCurve = easeInOutSine(progressAll);
  const innerZoom =
    cameraMotion === "static"
      ? 1
      : 1 + (zoomScale - 1) * holdCurve;
  const driftX =
    cameraMotion === "drift_focus"
      ? (0.5 - focusX) * 48 * scaleUnit * holdCurve
      : 0;
  const driftY =
    cameraMotion === "drift_focus"
      ? (0.5 - focusY) * 32 * scaleUnit * holdCurve
      : 0;

  const imageUrl = resolvePrimaryImageUrl(clip, obj);
  const padX = Math.round(96 * scaleUnit);
  const padTop = Math.round(62 * scaleUnit);
  const padBottom = Math.round(78 * scaleUnit);
  const radius = Math.round(16 * scaleUnit);
  const chromeHeight = Math.round(38 * scaleUnit);
  const dotSize = Math.max(6, Math.round(9 * scaleUnit));

  const bgColor = isDark ? "#080A0F" : "#F4F6F9";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.032)" : "rgba(15, 23, 42, 0.045)";
  const chromeBg = isDark ? "#11141C" : "#FFFFFF";
  const borderColor = isDark ? "rgba(255, 255, 255, 0.11)" : "rgba(15, 23, 42, 0.11)";
  const dividerColor = isDark ? "rgba(255, 255, 255, 0.07)" : "rgba(15, 23, 42, 0.08)";
  const urlBg = isDark ? "rgba(255, 255, 255, 0.045)" : "rgba(15, 23, 42, 0.045)";
  const urlText = isDark ? "rgba(226, 232, 240, 0.72)" : "rgba(30, 41, 59, 0.72)";
  const dotColor = isDark ? "rgba(255, 255, 255, 0.22)" : "rgba(15, 23, 42, 0.18)";

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: showBackdrop ? bgColor : "transparent",
        fontFamily: fontStack(fonts),
      }}
    >
      {showBackdrop ? (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `linear-gradient(to right, ${gridColor} 1px, transparent 1px), linear-gradient(to bottom, ${gridColor} 1px, transparent 1px)`,
              backgroundSize: `${Math.round(56 * scaleUnit)}px ${Math.round(56 * scaleUnit)}px`,
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `radial-gradient(ellipse 68% 54% at 50% 34%, ${hexToRgba(accent, isDark ? 0.14 : 0.09)}, transparent 72%)`,
            }}
          />
        </>
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
          perspective: `${Math.round(1800 * scaleUnit)}px`,
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
            opacity: enterOpacity,
            transform: `translateY(${risePx}px) scale(${frameScale}) rotateX(${tiltDeg}deg)`,
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
                ? `linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent)`
                : `linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent)`,
              pointerEvents: "none",
              zIndex: 3,
            }}
          />

          {/* Minimal institutional browser bar */}
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
              <span style={{ width: dotSize, height: dotSize, borderRadius: "50%", background: dotColor }} />
              <span style={{ width: dotSize, height: dotSize, borderRadius: "50%", background: dotColor }} />
              <span style={{ width: dotSize, height: dotSize, borderRadius: "50%", background: dotColor }} />
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

          {/* Captured UI viewport with subtle camera push-in */}
          <div
            style={{
              position: "relative",
              flex: 1,
              overflow: "hidden",
              background: isDark ? "#0B0E14" : "#FFFFFF",
            }}
          >
            {imageUrl ? (
              <Img
                src={imageUrl}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  objectPosition: `${Math.round(focusX * 100)}% ${Math.round(clamp01((focusY - 0.35) / 0.55) * 100)}%`,
                  transformOrigin: `${Math.round(focusX * 100)}% ${Math.round(focusY * 100)}%`,
                  transform: `translate(${driftX}px, ${driftY}px) scale(${innerZoom})`,
                }}
              />
            ) : null}
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
    surface_style?: "transparent" | "scrim" | "glass_card" | "light_card";
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

export const MotionBlockView: React.FC<{
  clip: VideoClip & { object: VideoMotionBlockObject };
  fonts: VideoSpec["fonts"];
  fps: number;
  frame: number;
  containerStyle: React.CSSProperties;
}> = ({ clip, fonts, fps, frame, containerStyle }) => {
  return (
    <div style={containerStyle}>
      {clip.object.block_id === "product_showcase" ? (
        <ProductShowcaseBlock clip={clip} fonts={fonts} fps={fps} frame={frame} />
      ) : (
        <KineticTitleBlock clip={clip} fonts={fonts} fps={fps} frame={frame} />
      )}
    </div>
  );
};

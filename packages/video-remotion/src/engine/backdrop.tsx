import React from "react";
import { hexToRgba } from "./math";
import type { BackdropStyle } from "./styles";

export type { BackdropStyle };

// Keep text ink within a narrow luminance range even for an arbitrary brand swatch.
// Saturated, unmodified accent is reserved for non-text rules, brackets and fills.
export function studioInk(accent: string, darkSurface: boolean): string {
  return `color-mix(in srgb, ${accent} 20%, ${darkSurface ? "#ffffff" : "#071018"})`;
}

export function StudioBackdrop({
  theme,
  accent,
  accentSecondary,
  canvasBg,
  lineColor,
  style = "ambient_mesh",
  tSec,
  scaleUnit,
}: {
  theme: "dark" | "light";
  accent: string;
  accentSecondary?: string;
  canvasBg?: string;
  lineColor?: string;
  style?: BackdropStyle;
  tSec: number;
  scaleUnit: number;
}): React.JSX.Element {
  const dark = theme === "dark";
  const paper = style === "editorial_paper";
  const grid = style === "architectural_grid";
  const kinetic = style === "kinetic_diagonal";
  const secondary = accentSecondary ?? accent;

  const base =
    canvasBg ??
    (dark
      ? paper
        ? "#161716"
        : kinetic
          ? "#0D0B14"
          : "#0B1016"
      : paper
        ? "#F5F2E9"
        : "#F4F6F8");

  const drift = Math.sin(tSec * 0.28);
  const gridLine = lineColor
    ? hexToRgba(lineColor, dark ? 0.22 : 0.38)
    : dark
      ? "rgba(226,238,246,.06)"
      : "rgba(29,42,54,.06)";
  const paperDot = lineColor
    ? hexToRgba(lineColor, dark ? 0.14 : 0.09)
    : dark
      ? "rgba(226,238,246,.06)"
      : "rgba(29,42,54,.07)";
  const cell = 54 * scaleUnit;

  return (
    <div aria-hidden style={{ position: "absolute", inset: 0, overflow: "hidden", background: base }}>
      {style === "ambient_mesh" && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse at ${38 + drift * 6}% 28%, ${hexToRgba(accent, 0.11 + drift * 0.018)}, transparent 65%),
              radial-gradient(ellipse at 78% ${72 - drift * 4}%, ${hexToRgba(secondary, 0.075)}, transparent 54%)`,
          }}
        />
      )}

      {grid && (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `linear-gradient(90deg, ${gridLine} 1px, transparent 1px), linear-gradient(${gridLine} 1px, transparent 1px)`,
              backgroundSize: `${cell}px ${cell}px`,
              backgroundPosition: `${drift * cell * 0.12}px ${Math.sin(tSec * 0.2) * cell * 0.08}px`,
            }}
          />
          {/* Swiss architectural perimeter hairline */}
          <div
            style={{
              position: "absolute",
              top: Math.round(28 * scaleUnit),
              left: Math.round(36 * scaleUnit),
              right: Math.round(36 * scaleUnit),
              height: Math.max(1, Math.round(1.5 * scaleUnit)),
              background: lineColor ? hexToRgba(lineColor, 0.75) : gridLine,
            }}
          />
          <div
            style={{
              position: "absolute",
              top: Math.round(28 * scaleUnit),
              left: Math.round(36 * scaleUnit),
              width: Math.round(72 * scaleUnit),
              height: Math.max(2, Math.round(3 * scaleUnit)),
              background: accent,
            }}
          />
        </>
      )}

      {paper && (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `radial-gradient(${paperDot} 0.65px, transparent 0.9px)`,
              backgroundSize: `${4 * scaleUnit}px ${4 * scaleUnit}px`,
            }}
          />
          {/* Editorial print top rule */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: Math.max(6, Math.round(8 * scaleUnit)),
              background: accent,
              borderBottom: `${Math.max(1.5, Math.round(2 * scaleUnit))}px solid ${lineColor ?? "#141413"}`,
            }}
          />
        </>
      )}

      {kinetic && (
        <>
          {/* Repeating diagonal kinetic scanlines */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `repeating-linear-gradient(135deg, ${hexToRgba(
                "#FFFFFF",
                0.032,
              )} 0px, ${hexToRgba("#FFFFFF", 0.032)} ${Math.max(1, Math.round(2 * scaleUnit))}px, transparent ${Math.max(1, Math.round(2 * scaleUnit))}px, transparent ${Math.round(28 * scaleUnit)}px)`,
              backgroundPosition: `${Math.round(tSec * 14 * scaleUnit)}px 0px`,
            }}
          />
          {/* Subtle dual-corner poster energy glow */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `radial-gradient(ellipse at 14% 16%, ${hexToRgba(accent, 0.16)}, transparent 44%),
                radial-gradient(ellipse at 88% 86%, ${hexToRgba(secondary, 0.14)}, transparent 46%)`,
            }}
          />
          {/* Top-left & bottom-right geometric energy corner slashes */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: Math.round(140 * scaleUnit),
              height: Math.round(10 * scaleUnit),
              background: accent,
              transformOrigin: "top left",
              transform: "skewX(-24deg)",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: Math.round(14 * scaleUnit),
              left: 0,
              width: Math.round(84 * scaleUnit),
              height: Math.round(4 * scaleUnit),
              background: secondary,
              transformOrigin: "top left",
              transform: "skewX(-24deg)",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              right: 0,
              width: Math.round(140 * scaleUnit),
              height: Math.round(10 * scaleUnit),
              background: secondary,
              transformOrigin: "bottom right",
              transform: "skewX(-24deg)",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: Math.round(14 * scaleUnit),
              right: 0,
              width: Math.round(84 * scaleUnit),
              height: Math.round(4 * scaleUnit),
              background: accent,
              transformOrigin: "bottom right",
              transform: "skewX(-24deg)",
            }}
          />
        </>
      )}

      {!grid && !paper && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "radial-gradient(ellipse at center, transparent 44%, rgba(12,17,20,.055) 100%)",
          }}
        />
      )}
    </div>
  );
}

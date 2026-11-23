import React from "react";
import { hexToRgba } from "./math";

export type BackdropStyle = "ambient_mesh" | "architectural_grid" | "editorial_paper" | "clean";

// Keep text ink within a narrow luminance range even for an arbitrary brand swatch.
// Saturated, unmodified accent is reserved for non-text rules, brackets and fills.
export function studioInk(accent: string, darkSurface: boolean): string {
  return `color-mix(in srgb, ${accent} 20%, ${darkSurface ? "#ffffff" : "#071018"})`;
}

export function StudioBackdrop({ theme, accent, style = "ambient_mesh", tSec, scaleUnit }: {
  theme: "dark" | "light";
  accent: string;
  style?: BackdropStyle;
  tSec: number;
  scaleUnit: number;
}) {
  const dark = theme === "dark";
  const paper = style === "editorial_paper";
  const base = dark ? (paper ? "#161716" : "#0B1016") : (paper ? "#F5F2E9" : "#F4F6F8");
  const drift = Math.sin(tSec * 0.28);
  const grid = style === "architectural_grid";
  const line = dark ? "rgba(226,238,246,.06)" : "rgba(29,42,54,.06)";
  const cell = 54 * scaleUnit;
  return (
    <div aria-hidden style={{ position: "absolute", inset: 0, overflow: "hidden", background: base }}>
      {style === "ambient_mesh" && <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse at ${38 + drift * 6}% 28%, ${hexToRgba(accent, 0.095 + drift * 0.018)}, transparent 65%),
          radial-gradient(ellipse at 78% ${72 - drift * 4}%, ${hexToRgba(accent, 0.05)}, transparent 50%)`,
      }} />}
      {grid && <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `linear-gradient(90deg, ${line} 1px, transparent 1px), linear-gradient(${line} 1px, transparent 1px)`,
        backgroundSize: `${cell}px ${cell}px`,
        backgroundPosition: `${drift * cell * 0.12}px ${Math.sin(tSec * 0.2) * cell * 0.08}px`,
      }} />}
      {paper && <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `radial-gradient(${line} 0.55px, transparent 0.8px)`,
        backgroundSize: `${3 * scaleUnit}px ${3 * scaleUnit}px`,
      }} />}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at center, transparent 44%, rgba(12,17,20,.055) 100%)" }} />
    </div>
  );
}

import React, { type CSSProperties, type ReactNode } from "react";
import { StudioBackdrop, type BackdropStyle } from "../engine/backdrop";
import { cueProgress, easeOutQuart, springOut } from "../engine/math";

export interface StudioStyle {
  theme?: "dark" | "light";
  accent_color?: string;
  backdrop_style?: BackdropStyle;
  show_backdrop?: boolean;
}

export interface Frame {
  tSec: number;
  durSec: number;
  scaleUnit: number;
  fontFamily: string;
  resources: string[];
}

// The composition supplies its render-aware image adapter; frame props remain serializable.
export const ImageAdapter =
  React.createContext<React.ElementType<{ src: string; style?: CSSProperties }>>("img");

export function PinnedImage({ src }: { src: string }): React.JSX.Element {
  const Image = React.useContext(ImageAdapter);
  return (
    <Image src={src} style={{ width: "100%", height: "100%", display: "block", objectFit: "contain" }} />
  );
}

export interface Palette {
  ink: string;
  secondary: string;
  surface: string;
  line: string;
  accent: string;
  tint: string;
}

export function palette(style: StudioStyle): Palette {
  const light = style.theme === "light";
  const accent = style.accent_color ?? "#20968B";
  const surface = light ? "#FFFFFF" : "#172129";
  return {
    accent,
    surface,
    ink: light ? "#15232B" : "#F6F8F9",
    secondary: light ? "#293A46" : "#CCD7DD",
    line: light ? "#B6C2C7" : "#52606A",
    tint: `color-mix(in srgb, ${accent} 12%, ${surface})`,
  };
}

// Layout uses a 1920 × 1080 design space inside the full-size backdrop.
export function Stage({
  style,
  frame,
  children,
}: {
  style: StudioStyle;
  frame: Frame;
  children: ReactNode;
}): React.JSX.Element {
  return (
    <div style={{ position: "relative", height: "100%", width: "100%", overflow: "hidden" }}>
      {style.show_backdrop !== false && (
        <StudioBackdrop
          theme={style.theme ?? "dark"}
          accent={palette(style).accent}
          style={style.backdrop_style}
          tSec={frame.tSec}
          scaleUnit={frame.scaleUnit}
        />
      )}
      <div
        style={{
          position: "absolute",
          width: 1920,
          height: 1080,
          top: "50%",
          left: "50%",
          transform: `translate(-50%, -50%) scale(${frame.scaleUnit})`,
          fontFamily: frame.fontFamily,
          color: palette(style).ink,
          overflowWrap: "anywhere",
          lineHeight: 1.3,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {children}
      </div>
    </div>
  );
}

// Budget both line width and height for replacement text, including unbroken CJK.
export function typeSize(text: string, ideal: number, width: number, lines = 1): number {
  const ems = Array.from(text).reduce((sum, ch) => sum + (/^[\x20-\x7e]$/.test(ch) ? 0.73 : 1.05), 0);
  return Math.min(ideal, Math.floor((width * (lines === 1 ? 1 : lines * 0.82)) / Math.max(1, ems)));
}

export function appear(tSec: number, start: number): CSSProperties {
  const elapsed = tSec - start;
  return {
    opacity: easeOutQuart(cueProgress(tSec, start, 0.32)),
    transform: `translateY(${(1 - springOut(elapsed)) * 28}px)`,
  };
}

export function itemTime(cue: number | null | undefined, index: number, count: number, dur: number): number {
  return cue ?? 0.25 + (index * Math.max(0, dur * 0.72 - 0.25)) / Math.max(count - 1, 1);
}

export function Heading({
  title,
  eyebrow,
  colors,
}: {
  title?: string | null;
  eyebrow?: string | null;
  colors: Palette;
}): React.JSX.Element {
  return (
    <header style={{ position: "absolute", top: 100, left: 132, right: 132 }}>
      {eyebrow && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            fontSize: 24,
            letterSpacing: "0.06em",
            color: colors.secondary,
          }}
        >
          <i style={{ width: 40, height: 3, background: colors.accent }} />
          {eyebrow}
        </div>
      )}
      {title && (
        <div
          style={{
            fontWeight: 700,
            marginTop: 16,
            lineHeight: 1.12,
            letterSpacing: "-0.035em",
            fontSize: typeSize(title, 72, 1640, 2),
          }}
        >
          {title}
        </div>
      )}
    </header>
  );
}

export const cardFace = (c: Palette): CSSProperties => ({
  background: c.surface,
  border: `1px solid ${c.line}`,
  borderRadius: 22,
  boxSizing: "border-box",
});

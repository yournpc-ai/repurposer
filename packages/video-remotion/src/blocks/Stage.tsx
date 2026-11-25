import React, { type CSSProperties, type ReactNode } from "react";
import { StudioBackdrop, type BackdropStyle } from "../engine/backdrop";
import { cueProgress, easeOutQuart, springOut } from "../engine/math";
import {
  cardSurfaceStyle,
  resolveBlockStyle,
  type CardTreatment,
  type HeadlineTreatment,
  type ResolvedBlockStyle,
  type ResolvedStyleTokens,
} from "../engine/styles";

export interface StudioStyle {
  theme?: "dark" | "light" | null;
  accent_color?: string | null;
  backdrop_style?: BackdropStyle | null;
  show_backdrop?: boolean;
}

export interface Frame {
  width: number;
  height: number;
  tSec: number;
  durSec: number;
  scaleUnit: number;
  fontFamily: string;
  resources: string[];
  compositionStyle?: ResolvedStyleTokens;
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
  canvasBg: string;
  line: string;
  accent: string;
  accentSecondary: string;
  accentInk: string;
  accentText: string;
  tint: string;
  cardTreatment: CardTreatment;
  headlineTreatment: HeadlineTreatment;
  headingWeight: 700 | 900;
  tokens: ResolvedBlockStyle;
}

export function palette(style: StudioStyle, compositionStyle?: ResolvedStyleTokens): Palette {
  const tokens = resolveBlockStyle(compositionStyle, style, {
    theme: "dark",
    accent: "#20968B",
    backdrop_style: "ambient_mesh",
  });
  return {
    ink: tokens.ink,
    secondary: tokens.secondaryInk,
    surface: tokens.surfaceBg,
    canvasBg: tokens.canvasBg,
    line: tokens.lineColor,
    accent: tokens.accent,
    accentSecondary: tokens.accentSecondary,
    accentInk: tokens.accentInk,
    accentText: tokens.accentText,
    tint: tokens.tint,
    cardTreatment: tokens.cardTreatment,
    headlineTreatment: tokens.headlineTreatment,
    headingWeight: tokens.headingWeight,
    tokens,
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
  const c = palette(style, frame.compositionStyle);
  return (
    <div style={{ position: "relative", height: "100%", width: "100%", overflow: "hidden" }}>
      {style.show_backdrop !== false && (
        <StudioBackdrop
          theme={c.tokens.theme}
          accent={c.accent}
          accentSecondary={c.accentSecondary}
          canvasBg={c.tokens.hasCompositionStyle ? c.canvasBg : undefined}
          lineColor={c.tokens.hasCompositionStyle ? c.line : undefined}
          style={c.tokens.backdropStyle}
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
          color: c.ink,
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
  const treatment = colors.headlineTreatment;
  return (
    <header style={{ position: "absolute", top: 100, left: 132, right: 132 }}>
      {treatment === "swiss_rule" && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            width: "100%",
            marginBottom: 16,
          }}
        >
          <span style={{ width: 92, height: 4, background: colors.accent }} />
          <span style={{ flex: 1, height: 1.5, background: colors.line }} />
        </div>
      )}
      {eyebrow && (
        <div
          style={
            treatment === "highlight_tape"
              ? {
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "6px 16px",
                  fontSize: 22,
                  fontWeight: 900,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  background: colors.accent,
                  color: colors.accentInk,
                  border: `2px solid ${colors.line}`,
                  borderRadius: 3,
                  boxShadow: `3px 3px 0px ${colors.line}`,
                }
              : treatment === "outlined_impact"
                ? {
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 18px",
                    fontSize: 22,
                    fontWeight: 900,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    background: colors.accent,
                    color: colors.accentInk,
                    borderRadius: 2,
                    transform: "skewX(-10deg)",
                    boxShadow: `4px 4px 0px ${colors.accentSecondary}`,
                  }
                : {
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    fontSize: 24,
                    fontWeight: treatment === "swiss_rule" ? 700 : 600,
                    letterSpacing: treatment === "swiss_rule" ? "0.12em" : "0.06em",
                    textTransform: treatment === "swiss_rule" ? "uppercase" : undefined,
                    color: treatment === "swiss_rule" ? colors.accentText : colors.secondary,
                  }
          }
        >
          {treatment === "clean" && <i style={{ width: 40, height: 3, background: colors.accent }} />}
          {treatment === "swiss_rule" && (
            <i style={{ width: 10, height: 10, background: colors.accent, display: "inline-block" }} />
          )}
          <span style={treatment === "outlined_impact" ? { transform: "skewX(10deg)" } : undefined}>
            {eyebrow}
          </span>
        </div>
      )}
      {title && (
        <div
          style={{
            fontWeight: colors.headingWeight,
            marginTop: treatment === "highlight_tape" || treatment === "outlined_impact" ? 18 : 16,
            lineHeight: 1.1,
            letterSpacing: treatment === "swiss_rule" ? "-0.042em" : "-0.035em",
            fontSize: typeSize(title, 72, 1640, 2),
            textShadow:
              treatment === "outlined_impact" ? `3px 3px 0px ${colors.accent}` : undefined,
          }}
        >
          {title}
        </div>
      )}
    </header>
  );
}

export const cardFace = (
  c: Palette,
  options?: { selected?: boolean; elevated?: boolean },
): CSSProperties => {
  if (!c.tokens.hasCompositionStyle) {
    return {
      background: options?.selected ? c.tint : c.surface,
      border: `1px solid ${options?.selected ? c.accent : c.line}`,
      borderRadius: 22,
      boxSizing: "border-box",
    };
  }
  return cardSurfaceStyle(c.tokens, {
    scaleUnit: 1,
    selected: options?.selected,
    elevated: options?.elevated,
  });
};

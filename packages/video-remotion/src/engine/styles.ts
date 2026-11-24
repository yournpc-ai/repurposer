import type { CSSProperties } from "react";
import { hexToRgba } from "./math";

export type StylePresetId =
  | "institutional_dark"
  | "swiss_paper"
  | "vox_editorial"
  | "kinetic_anime";

export type BackdropStyle =
  | "ambient_mesh"
  | "architectural_grid"
  | "editorial_paper"
  | "kinetic_diagonal"
  | "clean";

export type CardTreatment =
  | "glass_soft"
  | "minimal_hairline"
  | "editorial_rule"
  | "brutal_offset";

export type HeadlineTreatment =
  | "clean"
  | "swiss_rule"
  | "highlight_tape"
  | "outlined_impact";

export type StyleTransitionKind =
  | "crossfade"
  | "whip_pan"
  | "wipe_reveal"
  | "zoom_through"
  | "iris_focus";

export interface CompositionStyleInput {
  preset_id: StylePresetId;
  accent_color?: string | null;
  backdrop_style?: BackdropStyle | null;
  theme?: "dark" | "light" | null;
}

export interface CaptionStrokeToken {
  color: string;
  width: number;
}

export interface CaptionShadowToken {
  color: string;
  offset: [number, number];
  blur: number;
}

export interface CaptionStyleToken {
  color: string;
  weight: 400 | 700 | 900;
  background: string | null;
  stroke: CaptionStrokeToken | null;
  shadow: CaptionShadowToken | null;
}

export interface ResolvedStyleTokens {
  preset_id: StylePresetId;
  theme: "dark" | "light";
  backdrop_style: BackdropStyle;
  canvas_bg: string;
  surface_bg: string;
  ink: string;
  secondary_ink: string;
  line_color: string;
  accent: string;
  accent_secondary: string;
  accent_ink: string;
  accent_text: string;
  card_treatment: CardTreatment;
  headline_treatment: HeadlineTreatment;
  heading_weight: 700 | 900;
  default_transition: StyleTransitionKind;
  caption_style: CaptionStyleToken;
}

/**
 * Mirrors apps/api/app/editing/styles.py STYLE_PRESETS verbatim.
 * Verified for exact zero-drift parity in Python core tests via Node subprocess.
 */
export const STYLE_PRESETS: Record<StylePresetId, ResolvedStyleTokens> = {
  institutional_dark: {
    preset_id: "institutional_dark",
    theme: "dark",
    backdrop_style: "ambient_mesh",
    canvas_bg: "#0A0F16",
    surface_bg: "#141E28",
    ink: "#F4F7FA",
    secondary_ink: "#B8C7D4",
    line_color: "#2D3F4F",
    accent: "#14B8A6",
    accent_secondary: "#38BDF8",
    accent_ink: "#061318",
    accent_text: "#5EEAD4",
    card_treatment: "glass_soft",
    headline_treatment: "clean",
    heading_weight: 700,
    default_transition: "crossfade",
    caption_style: {
      color: "#F8FAFC",
      weight: 700,
      background: null,
      stroke: { color: "#0A0F16", width: 3.0 },
      shadow: { color: "#0A0F16", offset: [0.0, 2.0], blur: 8.0 },
    },
  },
  swiss_paper: {
    preset_id: "swiss_paper",
    theme: "light",
    backdrop_style: "architectural_grid",
    canvas_bg: "#F6F5F0",
    surface_bg: "#FFFFFF",
    ink: "#111820",
    secondary_ink: "#455360",
    line_color: "#CBD3DA",
    accent: "#D94626",
    accent_secondary: "#111820",
    accent_ink: "#FFFFFF",
    accent_text: "#B93216",
    card_treatment: "minimal_hairline",
    headline_treatment: "swiss_rule",
    heading_weight: 700,
    default_transition: "wipe_reveal",
    caption_style: {
      color: "#111820",
      weight: 700,
      background: null,
      stroke: { color: "#F6F5F0", width: 4.0 },
      shadow: null,
    },
  },
  vox_editorial: {
    preset_id: "vox_editorial",
    theme: "light",
    backdrop_style: "editorial_paper",
    canvas_bg: "#F4EFE2",
    surface_bg: "#FFFDF7",
    ink: "#141413",
    secondary_ink: "#3E3D39",
    line_color: "#141413",
    accent: "#FACC15",
    accent_secondary: "#2563EB",
    accent_ink: "#141413",
    accent_text: "#1D4ED8",
    card_treatment: "editorial_rule",
    headline_treatment: "highlight_tape",
    heading_weight: 900,
    default_transition: "wipe_reveal",
    caption_style: {
      color: "#FFFDF7",
      weight: 700,
      background: "#141413",
      stroke: null,
      shadow: null,
    },
  },
  kinetic_anime: {
    preset_id: "kinetic_anime",
    theme: "dark",
    backdrop_style: "kinetic_diagonal",
    canvas_bg: "#0D0B14",
    surface_bg: "#181426",
    ink: "#FFFFFF",
    secondary_ink: "#D4D0E8",
    line_color: "#3F345C",
    accent: "#FF2E63",
    accent_secondary: "#00F0FF",
    accent_ink: "#FFFFFF",
    accent_text: "#FF6B8E",
    card_treatment: "brutal_offset",
    headline_treatment: "outlined_impact",
    heading_weight: 900,
    default_transition: "whip_pan",
    caption_style: {
      color: "#FFFFFF",
      weight: 900,
      background: null,
      stroke: { color: "#0D0B14", width: 4.0 },
      shadow: { color: "#0D0B14", offset: [3.0, 3.0], blur: 0.0 },
    },
  },
};

const THEME_BASES: Record<"dark" | "light", {
  canvas_bg: string;
  surface_bg: string;
  ink: string;
  secondary_ink: string;
  line_color: string;
}> = {
  dark: {
    canvas_bg: "#0A0F16",
    surface_bg: "#141E28",
    ink: "#F4F7FA",
    secondary_ink: "#B8C7D4",
    line_color: "#2D3F4F",
  },
  light: {
    canvas_bg: "#F6F5F0",
    surface_bg: "#FFFFFF",
    ink: "#111820",
    secondary_ink: "#455360",
    line_color: "#CBD3DA",
  },
};

function parseHex(hex: string): [number, number, number] {
  const clean = hex.replace(/^#/, "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function roundHalfUp(value: number): number {
  return Math.max(0, Math.min(255, Math.floor(value + 0.5)));
}

function toHex(r: number, g: number, b: number): string {
  const h = (n: number) => n.toString(16).toUpperCase().padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = parseHex(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(hexA: string, hexB: string): number {
  const la = relativeLuminance(hexA);
  const lb = relativeLuminance(hexB);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

export function mixHex(hexA: string, hexB: string, t: number): string {
  const [r1, g1, b1] = parseHex(hexA);
  const [r2, g2, b2] = parseHex(hexB);
  return toHex(
    roundHalfUp(r1 + (r2 - r1) * t),
    roundHalfUp(g1 + (g2 - g1) * t),
    roundHalfUp(b1 + (b2 - b1) * t),
  );
}

export function pickContrastInk(
  bgHex: string,
  darkCandidate = "#111820",
  lightCandidate = "#FFFFFF",
): string {
  return contrastRatio(bgHex, darkCandidate) >= contrastRatio(bgHex, lightCandidate)
    ? darkCandidate
    : lightCandidate;
}

export function ensureContrastText(
  fgHex: string,
  canvasBg: string,
  surfaceBg: string,
  darkSurface: boolean,
  minRatio = 4.5,
): string {
  const base = fgHex.toUpperCase();
  if (contrastRatio(base, canvasBg) >= minRatio && contrastRatio(base, surfaceBg) >= minRatio) {
    return base;
  }
  const target = darkSurface ? "#FFFFFF" : "#111820";
  for (let step = 1; step <= 20; step += 1) {
    const candidate = mixHex(base, target, step / 20);
    if (
      contrastRatio(candidate, canvasBg) >= minRatio &&
      contrastRatio(candidate, surfaceBg) >= minRatio
    ) {
      return candidate;
    }
  }
  return target;
}

export function resolveStyleTokens(style: CompositionStyleInput): ResolvedStyleTokens {
  const preset = STYLE_PRESETS[style.preset_id];
  const tokens: ResolvedStyleTokens = {
    ...preset,
    caption_style: {
      color: preset.caption_style.color,
      weight: preset.caption_style.weight,
      background: preset.caption_style.background,
      stroke: preset.caption_style.stroke ? { ...preset.caption_style.stroke } : null,
      shadow: preset.caption_style.shadow
        ? {
            color: preset.caption_style.shadow.color,
            offset: [...preset.caption_style.shadow.offset] as [number, number],
            blur: preset.caption_style.shadow.blur,
          }
        : null,
    },
  };

  const themeChanged = style.theme != null && style.theme !== preset.theme;
  if (themeChanged && style.theme) {
    const base = THEME_BASES[style.theme];
    tokens.theme = style.theme;
    tokens.canvas_bg = base.canvas_bg;
    tokens.surface_bg = base.surface_bg;
    tokens.ink = base.ink;
    tokens.secondary_ink = base.secondary_ink;
    tokens.line_color = base.line_color;
    if (tokens.caption_style.background === null) {
      tokens.caption_style =
        style.theme === "dark"
          ? {
              color: "#F8FAFC",
              weight: tokens.caption_style.weight,
              background: null,
              stroke: { color: "#0A0F16", width: 3.0 },
              shadow: { color: "#0A0F16", offset: [0.0, 2.0], blur: 8.0 },
            }
          : {
              color: "#111820",
              weight: tokens.caption_style.weight,
              background: null,
              stroke: { color: "#F6F5F0", width: 4.0 },
              shadow: null,
            };
    }
  }

  if (style.backdrop_style != null) {
    tokens.backdrop_style = style.backdrop_style;
  }

  const isDark = tokens.theme === "dark";
  if (style.accent_color != null) {
    const accent = style.accent_color.toUpperCase();
    tokens.accent = accent;
    tokens.accent_ink = pickContrastInk(accent);
    tokens.accent_text = ensureContrastText(
      accent,
      tokens.canvas_bg,
      tokens.surface_bg,
      isDark,
      4.5,
    );
  } else if (themeChanged) {
    tokens.accent_text = ensureContrastText(
      tokens.accent,
      tokens.canvas_bg,
      tokens.surface_bg,
      isDark,
      4.5,
    );
  }

  return tokens;
}

export interface LegacyBlockFallback {
  theme: "dark" | "light";
  accent: string;
  backdrop_style: BackdropStyle;
}

export interface BlockStyleOverrides {
  theme?: "dark" | "light" | null;
  accent_color?: string | null;
  backdrop_style?: BackdropStyle | null;
}

export interface ResolvedBlockStyle {
  hasCompositionStyle: boolean;
  presetId: StylePresetId | null;
  theme: "dark" | "light";
  isDark: boolean;
  backdropStyle: BackdropStyle;
  canvasBg: string;
  surfaceBg: string;
  ink: string;
  secondaryInk: string;
  lineColor: string;
  accent: string;
  accentSecondary: string;
  accentInk: string;
  accentText: string;
  tint: string;
  cardTreatment: CardTreatment;
  headlineTreatment: HeadlineTreatment;
  headingWeight: 700 | 900;
}

/**
 * Resolve effective block tokens from optional composition-level style + per-block overrides.
 * When specStyle is absent, preserves legacy per-block defaults without altering legacy drafts.
 */
export function resolveBlockStyle(
  specStyle: ResolvedStyleTokens | undefined,
  props: BlockStyleOverrides,
  legacyFallback: LegacyBlockFallback,
): ResolvedBlockStyle {
  if (!specStyle) {
    const theme = props.theme ?? legacyFallback.theme;
    const isDark = theme === "dark";
    const accent = (props.accent_color ?? legacyFallback.accent).toUpperCase();
    const backdropStyle = props.backdrop_style ?? legacyFallback.backdrop_style;
    const paper = backdropStyle === "editorial_paper";
    const canvasBg = isDark ? (paper ? "#161716" : "#0B1016") : (paper ? "#F5F2E9" : "#F4F6F8");
    const surfaceBg = isDark ? "#172129" : "#FFFFFF";
    return {
      hasCompositionStyle: false,
      presetId: null,
      theme,
      isDark,
      backdropStyle,
      canvasBg,
      surfaceBg,
      ink: isDark ? "#F6F8F9" : "#15232B",
      secondaryInk: isDark ? "#CCD7DD" : "#293A46",
      lineColor: isDark ? "#52606A" : "#B6C2C7",
      accent,
      accentSecondary: accent,
      accentInk: pickContrastInk(accent),
      accentText: ensureContrastText(accent, canvasBg, surfaceBg, isDark, 4.5),
      tint: `color-mix(in srgb, ${accent} 12%, ${surfaceBg})`,
      cardTreatment: "glass_soft",
      headlineTreatment: "clean",
      headingWeight: 700,
    };
  }

  const theme = props.theme ?? specStyle.theme;
  const themeOverridden = props.theme != null && props.theme !== specStyle.theme;
  const isDark = theme === "dark";
  const backdropStyle = props.backdrop_style ?? specStyle.backdrop_style;

  const baseSurface = themeOverridden
    ? THEME_BASES[theme]
    : {
        canvas_bg: specStyle.canvas_bg,
        surface_bg: specStyle.surface_bg,
        ink: specStyle.ink,
        secondary_ink: specStyle.secondary_ink,
        line_color: specStyle.line_color,
      };

  const accentOverridden = props.accent_color != null;
  const accent = (props.accent_color ?? specStyle.accent).toUpperCase();
  const accentInk = accentOverridden ? pickContrastInk(accent) : specStyle.accent_ink;
  const accentText =
    accentOverridden || themeOverridden
      ? ensureContrastText(accent, baseSurface.canvas_bg, baseSurface.surface_bg, isDark, 4.5)
      : specStyle.accent_text;

  const tintAlpha =
    specStyle.card_treatment === "editorial_rule"
      ? 0.22
      : specStyle.card_treatment === "brutal_offset"
        ? 0.16
        : isDark
          ? 0.14
          : 0.10;

  return {
    hasCompositionStyle: true,
    presetId: specStyle.preset_id,
    theme,
    isDark,
    backdropStyle,
    canvasBg: baseSurface.canvas_bg,
    surfaceBg: baseSurface.surface_bg,
    ink: baseSurface.ink,
    secondaryInk: baseSurface.secondary_ink,
    lineColor: baseSurface.line_color,
    accent,
    accentSecondary: specStyle.accent_secondary,
    accentInk,
    accentText,
    tint: mixHex(baseSurface.surface_bg, accent, tintAlpha),
    cardTreatment: specStyle.card_treatment,
    headlineTreatment: specStyle.headline_treatment,
    headingWeight: specStyle.heading_weight,
  };
}

export interface CardSurfaceOptions {
  scaleUnit?: number;
  selected?: boolean;
  elevated?: boolean;
}

export function cardSurfaceStyle(
  tokens: ResolvedBlockStyle,
  options: CardSurfaceOptions = {},
): CSSProperties {
  const s = options.scaleUnit ?? 1;
  const selected = options.selected ?? false;
  const elevated = options.elevated ?? false;

  switch (tokens.cardTreatment) {
    case "minimal_hairline":
      return {
        background: selected ? tokens.tint : tokens.surfaceBg,
        border: `${Math.max(1, Math.round(1.5 * s * 10) / 10)}px solid ${selected ? tokens.accent : tokens.lineColor}`,
        borderRadius: Math.round(6 * s),
        boxShadow: "none",
        boxSizing: "border-box",
      };
    case "editorial_rule": {
      const off = Math.max(3, Math.round((elevated ? 6 : 4) * s));
      return {
        background: selected ? tokens.tint : tokens.surfaceBg,
        border: `${Math.max(1.5, Math.round(2 * s))}px solid ${tokens.lineColor}`,
        borderRadius: Math.round(4 * s),
        boxShadow: `${off}px ${off}px 0px ${selected ? tokens.accent : tokens.lineColor}`,
        boxSizing: "border-box",
      };
    }
    case "brutal_offset": {
      const off = Math.max(4, Math.round((elevated ? 8 : 6) * s));
      return {
        background: selected ? tokens.tint : tokens.surfaceBg,
        border: `${Math.max(1.5, Math.round(2 * s))}px solid ${selected ? tokens.accentSecondary : tokens.accent}`,
        borderRadius: Math.round(2 * s),
        boxShadow: `${off}px ${off}px 0px ${selected ? tokens.accentSecondary : tokens.accent}`,
        boxSizing: "border-box",
      };
    }
    case "glass_soft":
    default:
      return {
        background: selected ? tokens.tint : tokens.surfaceBg,
        border: `1px solid ${selected ? tokens.accent : tokens.lineColor}`,
        borderRadius: Math.round(22 * s),
        boxShadow: elevated
          ? tokens.isDark
            ? `0 ${Math.round(28 * s)}px ${Math.round(72 * s)}px rgba(0, 0, 0, 0.56), inset 0 1px 0 ${hexToRgba("#FFFFFF", 0.08)}`
            : `0 ${Math.round(22 * s)}px ${Math.round(56 * s)}px rgba(15, 23, 42, 0.12)`
          : tokens.isDark
            ? `0 ${Math.round(14 * s)}px ${Math.round(36 * s)}px rgba(0, 0, 0, 0.36)`
            : `0 ${Math.round(12 * s)}px ${Math.round(32 * s)}px rgba(15, 23, 42, 0.07)`,
        boxSizing: "border-box",
      };
  }
}

export function highlightTapeStyle(
  tokens: ResolvedBlockStyle,
  progress: number,
  scaleUnit = 1,
): CSSProperties {
  const clamped = Math.max(0, Math.min(1, progress));
  if (tokens.headlineTreatment === "highlight_tape") {
    return {
      position: "absolute",
      left: -Math.round(6 * scaleUnit),
      right: -Math.round(6 * scaleUnit),
      top: Math.round(2 * scaleUnit),
      bottom: Math.round(2 * scaleUnit),
      background: tokens.accent,
      borderRadius: Math.round(3 * scaleUnit),
      transformOrigin: "left center",
      transform: `scaleX(${clamped})`,
      pointerEvents: "none",
    };
  }
  if (tokens.headlineTreatment === "outlined_impact") {
    return {
      position: "absolute",
      left: -Math.round(8 * scaleUnit),
      right: -Math.round(8 * scaleUnit),
      top: Math.round(1 * scaleUnit),
      bottom: Math.round(1 * scaleUnit),
      background: tokens.accent,
      borderRadius: Math.round(2 * scaleUnit),
      transformOrigin: "left center",
      transform: `skewX(-8deg) scaleX(${clamped})`,
      boxShadow: `${Math.round(4 * scaleUnit)}px ${Math.round(4 * scaleUnit)}px 0px ${tokens.accentSecondary}`,
      pointerEvents: "none",
    };
  }
  return {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: Math.round(6 * scaleUnit),
    height: "36%",
    borderRadius: Math.round(8 * scaleUnit),
    background: hexToRgba(tokens.accent, tokens.isDark ? 0.16 : 0.14),
    transformOrigin: "left center",
    transform: `scaleX(${clamped})`,
    pointerEvents: "none",
  };
}

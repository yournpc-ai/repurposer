export type TextStylePresetId =
  | "clean_broadcast"
  | "cinema_glass"
  | "minimal_light"
  | "vox_label"
  | "vox_highlighter"
  | "creator_pop"
  | "kinetic_impact"
  | "editorial_callout"
  | "lower_third_tag"
  | "karaoke_focus"
  | "bilingual_cinema";

export type TextBackgroundMode = "box" | "pill" | "line";
export type TextTransform = "none" | "uppercase";

export interface TextBorderToken {
  color: string;
  width: number;
}

export interface TextStrokeToken {
  color: string;
  width: number;
}

export interface TextShadowToken {
  color: string;
  offset: [number, number];
  blur: number;
}

export interface TextStylePresetToken {
  color: string;
  weight: 400 | 500 | 600 | 700 | 800 | 900;
  background: string | null;
  background_mode: TextBackgroundMode;
  background_opacity: number;
  background_padding: [number, number];
  background_radius: number;
  border: TextBorderToken | null;
  stroke: TextStrokeToken | null;
  shadow: TextShadowToken | null;
  text_transform: TextTransform;
  secondary_line_scale: number;
  secondary_line_opacity: number;
}

/**
 * Mirrors apps/api/app/editing/text_presets.py TEXT_STYLE_PRESETS verbatim.
 * Verified for exact zero-drift parity in Python core tests via Node subprocess.
 */
export const TEXT_STYLE_PRESETS: Record<TextStylePresetId, TextStylePresetToken> = {
  clean_broadcast: {
    color: "#F8FAFC",
    weight: 700,
    background: null,
    background_mode: "box",
    background_opacity: 1.0,
    background_padding: [0.0, 0.0],
    background_radius: 0.0,
    border: null,
    stroke: { color: "#0A0F16", width: 3.0 },
    shadow: { color: "#0A0F16", offset: [0.0, 2.0], blur: 8.0 },
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  cinema_glass: {
    color: "#F8FAFC",
    weight: 600,
    background: "#0B1016",
    background_mode: "pill",
    background_opacity: 0.72,
    background_padding: [26.0, 10.0],
    background_radius: 12.0,
    border: null,
    stroke: null,
    shadow: null,
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  minimal_light: {
    color: "#111820",
    weight: 700,
    background: null,
    background_mode: "box",
    background_opacity: 1.0,
    background_padding: [0.0, 0.0],
    background_radius: 0.0,
    border: null,
    stroke: { color: "#F6F5F0", width: 4.0 },
    shadow: null,
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  vox_label: {
    color: "#FFFDF7",
    weight: 700,
    background: "#141413",
    background_mode: "line",
    background_opacity: 1.0,
    background_padding: [20.0, 8.0],
    background_radius: 4.0,
    border: null,
    stroke: null,
    shadow: null,
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  vox_highlighter: {
    color: "#141413",
    weight: 900,
    background: "#FACC15",
    background_mode: "line",
    background_opacity: 1.0,
    background_padding: [20.0, 8.0],
    background_radius: 4.0,
    border: { color: "#141413", width: 2.0 },
    stroke: null,
    shadow: null,
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  creator_pop: {
    color: "#FFFFFF",
    weight: 900,
    background: null,
    background_mode: "box",
    background_opacity: 1.0,
    background_padding: [0.0, 0.0],
    background_radius: 0.0,
    border: null,
    stroke: { color: "#0B0D12", width: 6.0 },
    shadow: { color: "#0B0D12", offset: [0.0, 4.0], blur: 0.0 },
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  kinetic_impact: {
    color: "#FFFFFF",
    weight: 900,
    background: null,
    background_mode: "box",
    background_opacity: 1.0,
    background_padding: [0.0, 0.0],
    background_radius: 0.0,
    border: null,
    stroke: { color: "#0D0B14", width: 5.0 },
    shadow: { color: "#FF2E63", offset: [4.0, 4.0], blur: 0.0 },
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  editorial_callout: {
    color: "#111820",
    weight: 700,
    background: "#FFFFFF",
    background_mode: "pill",
    background_opacity: 0.95,
    background_padding: [22.0, 10.0],
    background_radius: 10.0,
    border: { color: "#CBD3DA", width: 1.5 },
    stroke: null,
    shadow: null,
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  lower_third_tag: {
    color: "#F8FAFC",
    weight: 700,
    background: "#0F172A",
    background_mode: "pill",
    background_opacity: 0.86,
    background_padding: [22.0, 10.0],
    background_radius: 6.0,
    border: { color: "#14B8A6", width: 2.0 },
    stroke: null,
    shadow: null,
    text_transform: "uppercase",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  karaoke_focus: {
    color: "#FFFFFF",
    weight: 900,
    background: null,
    background_mode: "box",
    background_opacity: 1.0,
    background_padding: [0.0, 0.0],
    background_radius: 0.0,
    border: null,
    stroke: { color: "#0B0D12", width: 6.0 },
    shadow: { color: "#0B0D12", offset: [0.0, 4.0], blur: 0.0 },
    text_transform: "none",
    secondary_line_scale: 1.0,
    secondary_line_opacity: 1.0,
  },
  bilingual_cinema: {
    color: "#FFFFFF",
    weight: 700,
    background: "#111318",
    background_mode: "pill",
    background_opacity: 0.76,
    background_padding: [20.0, 10.0],
    background_radius: 10.0,
    border: null,
    stroke: null,
    shadow: { color: "#0A0F16", offset: [0.0, 1.0], blur: 4.0 },
    text_transform: "none",
    secondary_line_scale: 0.74,
    secondary_line_opacity: 0.88,
  },
};

export function cloneTextStylePresetToken(token: TextStylePresetToken): TextStylePresetToken {
  return {
    color: token.color,
    weight: token.weight,
    background: token.background,
    background_mode: token.background_mode,
    background_opacity: token.background_opacity,
    background_padding: [...token.background_padding] as [number, number],
    background_radius: token.background_radius,
    border: token.border ? { ...token.border } : null,
    stroke: token.stroke ? { ...token.stroke } : null,
    shadow: token.shadow
      ? {
          color: token.shadow.color,
          offset: [...token.shadow.offset] as [number, number],
          blur: token.shadow.blur,
        }
      : null,
    text_transform: token.text_transform,
    secondary_line_scale: token.secondary_line_scale,
    secondary_line_opacity: token.secondary_line_opacity,
  };
}

export interface TextPresetStyleContext {
  theme: "dark" | "light";
  ink: string;
  canvas_bg: string;
  accent: string;
}

export function resolveTextPresetToken(
  presetId: TextStylePresetId,
  styleTokens?: TextPresetStyleContext | null,
): TextStylePresetToken {
  const token = cloneTextStylePresetToken(TEXT_STYLE_PRESETS[presetId]);
  if (!styleTokens) return token;
  if (presetId === "lower_third_tag" && token.border !== null) {
    token.border.color = styleTokens.accent;
  } else if (presetId === "bilingual_cinema" && styleTokens.theme === "light") {
    token.color = "#F8FAFC";
    token.background = "#111318";
    token.background_mode = "pill";
    token.background_opacity = 0.82;
    token.background_padding = [20.0, 10.0];
    token.background_radius = 10.0;
    token.stroke = null;
    token.shadow = null;
  }
  return token;
}

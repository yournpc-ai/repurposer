// Film scene components — the human-owned render vocabulary of the film
// family (LLMs never write or modify these; they only author storyboards).
// Scenes: words / hero / ui / divider / reveal / end.
// Layout law (ADR-120 E3): every absolute px scales by `s = width/1920` —
// the 16:9 canvas IS the design grid, 1:1 and 9:16 are uniform scalings of
// it (portrait keeps the same vocabulary with more vertical air).
// Promoted line-by-line from the verified spike (apps/render/scratch-spike);
// debug residue (bundled storyboard import, staticFile public dir) removed.
import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type { FilmTheme } from "./schema";

// Latin-first system stack with the same CJK fallback law as the clip package
// (fonts.ts CJK_FALLBACK_STACK) — the render image registers vendored Noto
// Sans SC into fontconfig, so CJK storyboard copy doesn't tofu in Docker.
const FONT =
  "-apple-system, 'Helvetica Neue', 'Segoe UI', Arial, " +
  "'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";

/** *word* → highlight chip (ink tile + canvas text — our monochrome accent). */
export const accentize = (line: string, dark: boolean, theme: FilmTheme) =>
  line.split(/\*([^*]+)\*/g).map((p, i) =>
    i % 2 ? (
      <span
        key={i}
        style={{
          background: dark ? theme.canvas : theme.ink,
          color: dark ? theme.ink : theme.canvas,
          borderRadius: "0.18em",
          padding: "0 0.22em",
        }}
      >
        {p}
      </span>
    ) : (
      p
    ),
  );

/** The aspect scale: the 16:9 grid is the design base (1920 wide). */
const useScale = () => useVideoConfig().width / 1920;

const enter = (frame: number, delay: number, fps: number, s = 1) => {
  const p = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 46 * s}px)`,
    filter: `blur(${(1 - p) * 10}px)`,
  };
};

export const Words: React.FC<{ lines: string[]; dark: boolean; theme: FilmTheme }> = ({
  lines,
  dark,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  return (
    <AbsoluteFill
      style={{ background: dark ? theme.ink : theme.canvas, justifyContent: "center", paddingLeft: 220 * s }}
    >
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 168 * s,
            letterSpacing: "-0.035em",
            lineHeight: 1.04,
            color: dark ? theme.canvas : theme.ink,
            ...enter(frame, i * 8, fps, s),
          }}
        >
          {accentize(l, dark, theme)}
        </div>
      ))}
    </AbsoluteFill>
  );
};

export const Hero: React.FC<{ word: string; sub: string; theme: FilmTheme }> = ({
  word,
  sub,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const settle = interpolate(frame, [0, 24], [1.07, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: "center", alignItems: "center" }}>
      <div
        style={{
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: 200 * s,
          letterSpacing: "-0.04em",
          color: theme.ink,
          transform: `scale(${settle})`,
        }}
      >
        {word}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 44 * s, color: "#6b6b6b", marginTop: 26 * s, ...enter(frame, 10, fps, s) }}>
        {sub}
      </div>
    </AbsoluteFill>
  );
};

export const Divider: React.FC<{ index: string; label: string; roll: string[]; theme: FilmTheme }> = ({
  index,
  label,
  roll,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const perWord = 13;
  return (
    <AbsoluteFill style={{ background: theme.ink }}>
      <div style={{ position: "absolute", top: 110 * s, left: 140 * s, fontFamily: FONT, fontSize: 44 * s, color: "#888" }}>
        {index}
      </div>
      <div
        style={{
          position: "absolute",
          top: 200 * s,
          left: 220 * s,
          right: 220 * s,
          fontFamily: FONT,
          fontSize: 54 * s,
          fontWeight: 600,
          color: "#999",
          ...enter(frame, 0, fps, s),
        }}
      >
        {label}
      </div>
      <div style={{ position: "absolute", top: 300 * s, left: 220 * s, right: 220 * s, height: 220 * s, overflow: "hidden" }}>
        {roll.map((w, i) => {
          const start = i * perWord;
          const isLast = i === roll.length - 1;
          const p = spring({ frame: frame - start, fps, config: { damping: 200 } });
          const out = isLast ? 0 : spring({ frame: frame - (start + perWord), fps, config: { damping: 200 } });
          const y = ((1 - p) * 90 - out * 90) * s;
          const blur = Math.max(0, Math.max((1 - p) * 8, out * 8));
          if (frame < start - 1 || (!isLast && frame > start + perWord + 12)) return null;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: 150 * s,
                letterSpacing: "-0.03em",
                color: isLast ? theme.canvas : "#777",
                transform: `translateY(${y}px)`,
                filter: `blur(${blur}px)`,
                opacity: p - out,
              }}
            >
              {w}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const UiScene: React.FC<{
  image: string;
  url: string;
  theme: FilmTheme;
  dur: number;
  focuses: { at: number; x: number; y: number; zoom: number }[];
  captions: { at: number; text: string }[];
}> = ({ image, url, theme, dur, focuses, captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const t = frame / fps;
  const W = 1440 * s,
    H = 900 * s;
  const ts = focuses.map((f) => f.at);
  const x = interpolate(t, ts, focuses.map((f) => f.x), {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const y = interpolate(t, ts, focuses.map((f) => f.y), {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const z = interpolate(t, ts, focuses.map((f) => f.zoom), {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const inP = spring({ frame, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: "center", alignItems: "center" }}>
      <div
        style={{
          width: W,
          background: "white",
          borderRadius: 26 * s,
          overflow: "hidden",
          boxShadow: `0 ${40 * s}px ${120 * s}px rgba(20,20,20,0.16), 0 ${4 * s}px ${18 * s}px rgba(20,20,20,0.08)`,
          border: "1px solid rgba(20,20,20,0.08)",
          transform: `translateY(${(1 - inP) * 60 * s}px) scale(${0.96 + inP * 0.04})`,
          opacity: inP,
        }}
      >
        {/* browser chrome */}
        <div
          style={{
            height: 58 * s,
            display: "flex",
            alignItems: "center",
            gap: 10 * s,
            padding: `0 ${22 * s}px`,
            borderBottom: "1px solid rgba(20,20,20,0.07)",
            background: "#fbfbfa",
          }}
        >
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ width: 16 * s, height: 16 * s, borderRadius: 99, background: "#e2e1de" }} />
          ))}
          <div
            style={{
              marginLeft: 18 * s,
              background: "white",
              border: "1px solid rgba(20,20,20,0.08)",
              borderRadius: 12 * s,
              padding: `${6 * s}px ${18 * s}px`,
              fontFamily: FONT,
              fontSize: 22 * s,
              color: "#666",
            }}
          >
            {url}
          </div>
        </div>
        {/* viewport with camera */}
        <div style={{ width: W, height: H, overflow: "hidden", position: "relative" }}>
          <Img
            src={image}
            style={{
              width: W,
              height: H,
              transformOrigin: "0 0",
              transform: `translate(${W / 2 - x * W * z}px, ${H / 2 - y * H * z}px) scale(${z})`,
            }}
          />
        </div>
      </div>
      {captions.map((c, i) => {
        const startF = c.at * fps;
        const endF = (captions[i + 1]?.at ?? dur / fps - 0.3) * fps;
        if (frame < startF - 1 || frame > endF) return null;
        const p = spring({ frame: frame - startF, fps, config: { damping: 200 } });
        const out = interpolate(frame, [endF - 8, endF], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              bottom: 44 * s,
              left: 0,
              right: 0,
              display: "flex",
              justifyContent: "center",
              opacity: p * (1 - out),
              transform: `translateY(${(1 - p) * 30}px)`,
            }}
          >
            <div
              style={{
                background: "#141414",
                color: "#f7f6f2",
                borderRadius: 999,
                padding: `${16 * s}px ${40 * s}px`,
                fontFamily: FONT,
                fontSize: 34 * s,
                fontWeight: 600,
              }}
            >
              {c.text}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const Reveal: React.FC<{ lead: string; word: string; sub: string; theme: FilmTheme }> = ({
  lead,
  word,
  sub,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: "center", alignItems: "center" }}>
      <div style={{ fontFamily: FONT, fontSize: 40 * s, color: "#8a8a8a", marginBottom: 30 * s, ...enter(frame, 0, fps, s) }}>
        {lead}
      </div>
      <div
        style={{
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: 150 * s,
          letterSpacing: "-0.03em",
          color: theme.ink,
          ...enter(frame, 6, fps, s),
        }}
      >
        {accentize(word, false, theme)}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 40 * s, color: "#6b6b6b", marginTop: 30 * s, ...enter(frame, 14, fps, s) }}>
        {sub}
      </div>
    </AbsoluteFill>
  );
};

export const End: React.FC<{
  name: string;
  tagline: string;
  url: string;
  logoUrl?: string | null;
  theme: FilmTheme;
}> = ({ name, tagline, url, logoUrl, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: "center", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 28 * s, ...enter(frame, 0, fps, s) }}>
        {logoUrl ? <Img src={logoUrl} style={{ width: 92 * s, height: 92 * s }} /> : null}
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 110 * s,
            letterSpacing: "-0.035em",
            color: theme.ink,
          }}
        >
          {name}
        </div>
      </div>
      <div style={{ fontFamily: FONT, fontSize: 40 * s, color: "#6b6b6b", marginTop: 26 * s, ...enter(frame, 8, fps, s) }}>
        {tagline}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 30 * s, color: "#9a9a9a", marginTop: 54 * s, ...enter(frame, 16, fps, s) }}>
        {url}
      </div>
    </AbsoluteFill>
  );
};

/** Per-scene in/out fade veil (7 frames in, 7 frames out). */
export const Fade: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [0, 7], [0, 1], { extrapolateRight: "clamp" });
  const out = interpolate(frame, [dur - 7, dur - 1], [1, 0], { extrapolateLeft: "clamp" });
  return <AbsoluteFill style={{ opacity: Math.min(o, 1) * out }}>{children}</AbsoluteFill>;
};

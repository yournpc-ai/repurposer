// Film scene components — the human-owned render vocabulary of the film
// family (LLMs never write or modify these; they only author storyboards).
// Scenes: words / hero / ui / divider / plate / reveal / video / end.
// Layout law (ADR-130): every absolute px scales by `s = width/1920` —
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
  OffthreadVideo,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type { CompositeElement, FilmTheme } from "./schema";

// Latin-first system stack with the same CJK fallback law as the clip package
// (fonts.ts CJK_FALLBACK_STACK) — the render image registers vendored Noto
// Sans SC into fontconfig, so CJK storyboard copy doesn't tofu in Docker.
const FONT =
  "-apple-system, 'Helvetica Neue', 'Segoe UI', Arial, " +
  "'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";

/** The theme's accent color, with the polarity pair as the honest fallback
 * (pre-accent persisted specs carry no accent — an accent request there
 * degrades to the plane's own ink, never a crash). */
const accentColor = (theme: FilmTheme, dark: boolean) =>
  theme.accent ?? (dark ? theme.canvas : theme.ink);

/** *word* → emphasis. "chip" (default) = the inverted ink/canvas tile;
 * "color" = the theme accent color, no tile. */
export const accentize = (
  line: string,
  dark: boolean,
  theme: FilmTheme,
  accentStyle?: "chip" | "color" | null,
) =>
  line.split(/\*([^*]+)\*/g).map((p, i) =>
    i % 2 ? (
      accentStyle === "color" ? (
        <span key={i} style={{ color: accentColor(theme, dark) }}>
          {p}
        </span>
      ) : (
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
      )
    ) : (
      p
    ),
  );

/** The aspect scale: the 16:9 grid is the design base (1920 wide). */
const useScale = () => useVideoConfig().width / 1920;

/** Measure each rolling chapter title on the design canvas, then shrink it
 * just enough to stay on ONE line inside the scroll mask. The mask remains
 * the animation window; it must never become a second-line clipping bug. */
const useDividerFontSizes = (roll: string[], scale: number) =>
  React.useMemo(() => {
    const designFontSize = 150;
    const availableWidth = 1920 - 220 * 2;
    let measure: (text: string) => number;
    if (typeof document !== "undefined") {
      const context = document.createElement("canvas").getContext("2d");
      if (context) {
        context.font = `800 ${designFontSize}px ${FONT}`;
        measure = (text) => {
          const letterSpacing = -0.03 * designFontSize;
          return Math.max(
            1,
            context.measureText(text).width +
              Math.max(0, Array.from(text).length - 1) * letterSpacing,
          );
        };
      } else {
        measure = (text) => Math.max(1, Array.from(text).length * designFontSize * 0.65);
      }
    } else {
      // Non-browser composition probes have no canvas; Remotion's real render
      // takes the measured branch above.
      measure = (text) => Math.max(1, Array.from(text).length * designFontSize * 0.65);
    }
    return roll.map((text) => {
      const width = measure(text);
      const fitted = Math.min(designFontSize, designFontSize * (availableWidth * 0.96) / width);
      return fitted * scale;
    });
  }, [roll, scale]);

type EnterStyle = "rise" | "fade" | "slide";
type EnterFrameStyle = React.CSSProperties & { opacity: number };

const enter = (
  frame: number,
  delay: number,
  fps: number,
  s = 1,
  durationFrames?: number,
  enterStyle?: EnterStyle | null,
): EnterFrameStyle => {
  // slide is the additive, exact-endpoint entrance: no opacity ramp and no
  // blur. Before its start the line is hidden by visibility (not faded); the
  // transform then eases from the entrance offset to zero in the named frame
  // window. The legacy rise/fade branches below remain byte-for-byte intact.
  if (enterStyle === "slide") {
    const duration = durationFrames ?? 12;
    const p =
      duration <= 0
        ? frame < delay
          ? 0
          : 1
        : interpolate(frame, [delay, delay + duration], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.cubic),
          });
    return {
      opacity: 1,
      visibility: frame < delay ? "hidden" : "visible",
      transform: `translateY(${(1 - p) * 46 * s}px)`,
      filter: "none",
    };
  }
  // Batch B: a supplied duration is a real render parameter (Remotion stretches
  // the spring to that frame count); zero is the legal instant entrance.
  const p =
    durationFrames === undefined
      ? spring({ frame: frame - delay, fps, config: { damping: 200 } })
      : durationFrames <= 0
        ? frame < delay
          ? 0
          : 1
        : spring({
            frame: frame - delay,
            fps,
            config: { damping: 200 },
            durationInFrames: durationFrames,
            durationRestThreshold: 0.001,
          });
  // enterStyle is the entrance EFFECT, orthogonal to the lines/words
  // organization: "fade" = opacity only (no rise, no blur); null/"rise" =
  // the legacy fade+rise+blur.
  if (enterStyle === "fade") {
    return { opacity: p };
  }
  return {
    opacity: p,
    transform: `translateY(${(1 - p) * 46 * s}px)`,
    filter: `blur(${(1 - p) * 10}px)`,
  };
};

/** Batch B seconds→frames quantization: nearest frame, halves up, with the
 * same 1e-9 epsilon as the API's film_seconds_to_frames — ONE float64
 * formula on both sides, so a half-frame boundary (0.25s → 7.5 → f8) never
 * splits between backend validation and rendering. */
const secondsToFrames = (seconds: number, fps: number) =>
  Math.max(0, Math.floor(seconds * fps + 0.5 + 1e-9));

/** Word-by-word tokenizer for enter="words": latin runs split on
 * whitespace, CJK glyphs land one per token; *accent* spans split out FIRST
 * (the chip edge is a token edge — a latin run never merges across it) and
 * keep the chip on their tokens. Returns {text, accent} tokens per line. */
const tokenizeWords = (line: string): { text: string; accent: boolean }[] => {
  const tokens: { text: string; accent: boolean }[] = [];
  // Split on accent markers first — odd indices are the accented spans.
  line.split(/\*([^*]+)\*/g).forEach((part, i) => {
    const accent = i % 2 === 1;
    const re = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[^\s\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(part)) !== null) tokens.push({ text: m[0], accent });
  });
  return tokens.filter((t) => t.text.length > 0);
};

/**
 * The text plane, layout-free (ADR-140): the words scene's FULL animation
 * vocabulary (per-line stagger / word-by-word tokens, the Batch B timing
 * schedule, the motion camera, accent chips) with the canvas background and
 * padding stripped out, so both the full-canvas words scene AND composite
 * text elements ride the SAME rendering seat. `fontSize` is the only
 * typographic knob (px on the 1920 design grid; the words plane's 168 is
 * its own signature). Timing fields are relative to the plane's OWN window
 * (`dur` frames — scene frames for a words scene, the element window for a
 * text element); a null enterHoldUntil holds to the window's end.
 *
 * `exitDuration` (seconds) fades the TEXT out across the window's final
 * stretch — ending at the hold endpoint (words: enterHoldUntil, absent =
 * the window end; elements: the window end). The background never fades.
 * `motionScale` is the push/pull amplitude (legacy 1.06). `align` "center"
 * centers the block and the camera origin. `colorOverride` replaces the
 * polarity ink (a tone="accent" element passes the theme accent).
 */
export const TextPlane: React.FC<{
  lines: string[];
  dark: boolean;
  theme: FilmTheme;
  motion?: "static" | "push" | "pull" | null;
  enterMode?: "lines" | "words" | null;
  enterStart?: number | null;
  enterInterval?: number | null;
  enterDuration?: number | null;
  enterHoldUntil?: number | null;
  motionStart?: number | null;
  motionEnd?: number | null;
  exitDuration?: number | null;
  motionScale?: number | null;
  align?: "left" | "center" | null;
  accentStyle?: "chip" | "color" | null;
  enterStyle?: EnterStyle | null;
  colorOverride?: string | null;
  dur: number;
  fontSize?: number;
}> = ({
  lines,
  dark,
  theme,
  motion,
  enterMode,
  enterStart,
  enterInterval,
  enterDuration,
  enterHoldUntil,
  motionStart,
  motionEnd,
  exitDuration,
  motionScale,
  align,
  accentStyle,
  enterStyle,
  colorOverride,
  dur,
  fontSize = 168,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const motionFrom = motionStart == null ? 0 : secondsToFrames(motionStart, fps);
  const motionTo = motionEnd == null ? dur : secondsToFrames(motionEnd, fps);
  // Text-plane camera (ADR-138 §7.6): a slow scale drift over the scene —
  // push = settle in, pull = ease out; static/absent = fixed plane. Batch B
  // bounds the same existing move to an explicit frame window when given;
  // motionScale tunes the amplitude (legacy 1.06; subtle ≈ 1.02–1.04).
  const amp = motionScale ?? 1.06;
  const scale =
    motion === "push"
      ? interpolate(frame, [motionFrom, motionTo], [1, amp], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : motion === "pull"
        ? interpolate(frame, [motionFrom, motionTo], [amp, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        : 1;
  const centered = align === "center";
  const origin = centered ? "center center" : "left center";
  const ink = colorOverride ?? (dark ? theme.canvas : theme.ink);
  // The exit fade multiplier — the words leave over the window's final
  // exitDuration seconds, ending at the hold endpoint; the background is
  // never part of this plane.
  const exitEnd =
    enterHoldUntil == null ? dur : secondsToFrames(enterHoldUntil, fps);
  const exitF = exitDuration == null ? 0 : secondsToFrames(exitDuration, fps);
  const exitOpacity =
    exitF > 0
      ? interpolate(frame, [exitEnd - exitF, exitEnd], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  if ((enterMode ?? "lines") === "words") {
    // Word-by-word. With no timing keys this is byte-for-byte the legacy
    // cadence: a fixed 2–4 frame step plus the unparameterized spring. Any
    // timing key switches the scene to the deterministic schedule — start,
    // adjacent-token interval and per-token duration all land through the
    // shared seconds→frames quantization; a null hold means scene end.
    const tokenLines = lines.map(tokenizeWords);
    const total = tokenLines.reduce((acc, l) => acc + l.length, 0);
    const legacyStep = Math.max(2, Math.min(4, Math.floor((dur * 0.6) / Math.max(1, total))));
    const hasTiming =
      enterStart != null ||
      enterInterval != null ||
      enterDuration != null ||
      enterHoldUntil != null;
    const startAt = enterStart == null ? 0 : secondsToFrames(enterStart, fps);
    const step = enterInterval == null ? legacyStep : secondsToFrames(enterInterval, fps);
    const tokenDuration =
      enterDuration == null ? 12 : secondsToFrames(enterDuration, fps);
    const holdUntil = exitEnd;
    let cursor = 0;
    return (
      <div style={{ transform: `scale(${scale})`, transformOrigin: origin }}>
        {tokenLines.map((tokens, li) => (
            <div
              key={li}
              style={{
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: fontSize * s,
                letterSpacing: "-0.035em",
                lineHeight: 1.04,
                color: ink,
                textAlign: centered ? "center" : "left",
              }}
            >
              {tokens.map((t, ti) => {
                const delay = startAt + cursor;
                cursor += step;
                const chip = t.accent
                  ? accentStyle === "color" || colorOverride
                    ? // Color-style emphasis (and a whole-accent block's
                      // marks): the accent color, no tile.
                      { color: accentColor(theme, dark) }
                    : {
                        background: dark ? theme.canvas : theme.ink,
                        color: dark ? theme.ink : theme.canvas,
                        borderRadius: "0.18em",
                        padding: "0 0.22em",
                      }
                  : {};
                const style = enter(
                  frame,
                  delay,
                  fps,
                  s,
                  hasTiming ? tokenDuration : undefined,
                  enterStyle,
                );
                style.opacity *= exitOpacity;
                if (hasTiming && frame >= holdUntil) style.opacity = 0;
                return (
                  <span key={ti} style={{ display: "inline-block", whiteSpace: "pre", ...chip, ...style }}>
                    {t.text}
                    {/[^\s\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(t.text) ? " " : ""}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
    );
  }
  // Lines keep the legacy fixed 8-frame stagger until at least one timing key
  // is present. Explicit timing switches to the same quantized schedule as
  // word-by-word, with LINES as the units; slide uses exact interpolation
  // endpoints, so interval >= duration means the previous line is fully in
  // before the next one starts.
  const hasLineTiming =
    enterStart != null ||
    enterInterval != null ||
    enterDuration != null ||
    enterHoldUntil != null;
  const lineStart = enterStart == null ? 0 : secondsToFrames(enterStart, fps);
  const lineStep = enterInterval == null ? 8 : secondsToFrames(enterInterval, fps);
  const lineDuration = enterDuration == null ? 12 : secondsToFrames(enterDuration, fps);
  return (
    <div style={{ transform: `scale(${scale})`, transformOrigin: origin }}>
      {lines.map((l, i) => {
        const delay = hasLineTiming ? lineStart + i * lineStep : i * 8;
        const style = enter(
          frame,
          delay,
          fps,
          s,
          hasLineTiming ? lineDuration : undefined,
          enterStyle,
        );
        style.opacity *= exitOpacity;
        if (hasLineTiming && frame >= exitEnd) style.opacity = 0;
        return (
          <div
            key={i}
            style={{
              fontFamily: FONT,
              fontWeight: 800,
              fontSize: fontSize * s,
              letterSpacing: "-0.035em",
              lineHeight: 1.04,
              color: ink,
              textAlign: centered ? "center" : "left",
              ...style,
            }}
          >
            {accentize(l, dark, theme, accentStyle)}
          </div>
        );
      })}
      </div>
  );
};

/** The size tiers' font px on the 1920 design grid — the mirror of the
 * API's FILM_TEXT_SIZE_PX (ONE table per side, same numbers; the capacity
 * validator there assumes exactly these). medium = the legacy signature
 * (words 168 / element 80). */
export const TEXT_SIZE_PX = {
  words: { small: 120, medium: 168, large: 232 },
  element: { small: 56, medium: 80, large: 120 },
} as const;

export const Words: React.FC<{
  lines: string[];
  dark: boolean;
  theme: FilmTheme;
  motion?: "static" | "push" | "pull" | null;
  enterMode?: "lines" | "words" | null;
  enterStart?: number | null;
  enterInterval?: number | null;
  enterDuration?: number | null;
  enterHoldUntil?: number | null;
  motionStart?: number | null;
  motionEnd?: number | null;
  exitDuration?: number | null;
  motionScale?: number | null;
  align?: "left" | "center" | null;
  size?: "small" | "medium" | "large" | null;
  accentStyle?: "chip" | "color" | null;
  enterStyle?: EnterStyle | null;
  dur: number;
}> = (props) => {
  const s = useScale();
  const { size, ...plane } = props;
  // The background is painted by the sequencer (Film.tsx) at CONSTANT
  // opacity — the per-scene fade veil covers only this content, so a dark
  // scene never dips toward the root canvas at a boundary.
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        paddingLeft: 220 * s,
        // Symmetric right bound: long lines wrap instead of clipping at
        // the canvas edge (the push scale also drifts the right edge
        // ~6% outward — the right margin absorbs it).
        paddingRight: 220 * s,
      }}
    >
      <TextPlane {...plane} fontSize={TEXT_SIZE_PX.words[size ?? "medium"]} />
    </AbsoluteFill>
  );
};

/**
 * The composition scene (ADR-140): z-ordered elements over the scene's
 * polarity background. Each element lives in its OWN window Sequence
 * (scene-relative `at`; the window's end trims honestly — a video element
 * whose play window ends LEAVES the screen, no freeze frame; a text/image
 * element's `until` — absent = scene end — is the hard leave). Inside an
 * element's Sequence the local frame IS the element window's timeline, so
 * a text element's enter/motion timing (element-window-relative seconds)
 * plays through the words plane's own TextPlane seat unchanged. Source
 * seconds and output seconds never mix: OffthreadVideo's startFrom/endAt
 * trim the SOURCE, the Sequence window places the OUTPUT.
 *
 * The fade veil is PER-ELEMENT, never scene-wide (one element's exit fade
 * must never wash its siblings): the default 7f veil rides the element's
 * scene-touching edges (at=0 in / window-end=scene-end out — the legacy
 * scene veil's exact coverage), and an element's EXPLICIT animation owns
 * its direction instead (a text element's enter timing / enter_style drops
 * the in-veil; its exit_duration drops the out-veil).
 */
export const CompositeScene: React.FC<{
  dark: boolean;
  elements: CompositeElement[];
  theme: FilmTheme;
  dur: number;
}> = ({ dark, elements, theme, dur }) => {
  const { fps, width, height } = useVideoConfig();
  const sorted = [...elements].sort((a, b) => a.z - b.z);
  // The polarity background is painted by the sequencer (Film.tsx) at
  // constant opacity — this root only lays out the element windows.
  return (
    <AbsoluteFill>
      {sorted.map((el, i) => {
        const atF = secondsToFrames(el.at, fps);
        const rect: React.CSSProperties = {
          position: "absolute",
          left: el.rect.x * width,
          top: el.rect.y * height,
          width: el.rect.w * width,
          height: el.rect.h * height,
        };
        if (el.kind === "video") {
          // ONE quantization contract with the validator (复审①/②): the
          // source endpoints quantize first (startFrom/endAt); the default
          // play window IS the quantized span — never quantize-the-delta
          // (which can claim a frame the trim never shows); an explicit
          // duration quantizes on its own and is ≤ the span by law. The
          // renderer renders EXACTLY those frames — it never pads.
          const startF = secondsToFrames(el.source_start, fps);
          const endF = secondsToFrames(el.source_end, fps);
          const winF =
            el.duration != null
              ? secondsToFrames(el.duration, fps)
              : endF - startF;
          return (
            <Sequence key={el.id ?? i} from={atF} durationInFrames={winF}>
              <Fade
                dur={winF}
                fadeIn={atF === 0 ? 7 : 0}
                fadeOut={atF + winF >= dur ? 7 : 0}
              >
                <div style={{ ...rect, overflow: "hidden" }}>
                  <OffthreadVideo
                    src={el.src}
                    startFrom={startF}
                    endAt={endF}
                    muted={!el.keep_audio}
                    style={{ width: "100%", height: "100%", objectFit: el.fit }}
                  />
                </div>
              </Fade>
            </Sequence>
          );
        }
        const untilF = el.until == null ? dur : secondsToFrames(el.until, fps);
        const winF = untilF - atF; // ≥1 frame by the same upstream law
        if (el.kind === "image") {
          return (
            <Sequence key={el.id ?? i} from={atF} durationInFrames={winF}>
              <Fade
                dur={winF}
                fadeIn={atF === 0 ? 7 : 0}
                fadeOut={untilF >= dur ? 7 : 0}
              >
                <div style={{ ...rect, overflow: "hidden" }}>
                  <Img
                    src={el.src}
                    style={{ width: "100%", height: "100%", objectFit: el.fit }}
                  />
                </div>
              </Fade>
            </Sequence>
          );
        }
        // text element — the words plane's seat inside the rect; tone
        // "light" = light ink over the composition (the words plane's
        // dark-scene twin), "accent" = the whole block in the theme accent.
        // An explicit entrance (timing keys or enter_style) OWNS the in-edge
        // and an exit_duration owns the out-edge — the veil never doubles
        // them; otherwise the default 7f veil rides the scene-touching edges.
        const explicitEnter =
          el.enter_start != null ||
          el.enter_interval != null ||
          el.enter_duration != null ||
          el.enter_style != null;
        return (
          <Sequence key={el.id ?? i} from={atF} durationInFrames={winF}>
            <Fade
              dur={winF}
              fadeIn={explicitEnter ? 0 : atF === 0 ? 7 : 0}
              fadeOut={el.exit_duration != null ? 0 : untilF >= dur ? 7 : 0}
            >
              <div
                style={{
                  ...rect,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  overflow: "hidden",
                }}
              >
                <TextPlane
                  lines={el.lines}
                  dark={el.tone !== "dark"}
                  theme={theme}
                  motion={el.motion}
                  enterMode={el.enter}
                  enterStart={el.enter_start}
                  enterInterval={el.enter_interval}
                  enterDuration={el.enter_duration}
                  enterHoldUntil={null}
                  motionStart={el.motion_start}
                  motionEnd={el.motion_end}
                  exitDuration={el.exit_duration}
                  motionScale={el.motion_scale}
                  align={el.align}
                  accentStyle={el.accent_style}
                  enterStyle={el.enter_style}
                  colorOverride={
                    el.tone === "accent" ? accentColor(theme, dark) : null
                  }
                  dur={winF}
                  fontSize={TEXT_SIZE_PX.element[el.size ?? "medium"]}
                />
              </div>
            </Fade>
          </Sequence>
        );
      })}
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
  const fontSizes = useDividerFontSizes(roll, s);
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
                top: 0,
                left: 0,
                width: "100%",
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: fontSizes[i],
                lineHeight: 1.2,
                whiteSpace: "nowrap",
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
  frame: boolean;
  theme: FilmTheme;
  dur: number;
  focuses: { at: number; x: number; y: number; zoom: number }[];
}> = ({ image, url, frame: framed, theme, dur, focuses }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
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
  if (!framed) {
    // Full-bleed: the page fills the canvas (no chrome card) — the same
    // camera law over canvas dimensions instead of the card's viewport.
    return (
      <AbsoluteFill style={{ background: theme.canvas, overflow: "hidden" }}>
        <Img
          src={image}
          style={{
            width,
            height,
            transformOrigin: "0 0",
            transform: `translate(${width / 2 - x * width * z}px, ${height / 2 - y * height * z}px) scale(${z})`,
          }}
        />
      </AbsoluteFill>
    );
  }
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
    </AbsoluteFill>
  );
};

/**
 * The numbers beat: glass cards over a calm procedural backdrop. Backdrops
 * are deterministic gradients (no image asset, nothing to stage); cards are
 * frosted glass so the numbers float over the atmosphere.
 */
const PLATE_BACKDROPS: Record<string, { base: string; blobs: [string, string, string] }> = {
  aurora: {
    base: "#0d1210",
    blobs: [
      "radial-gradient(ellipse 900px 620px at 22% 28%, rgba(64,160,120,0.35), transparent 70%)",
      "radial-gradient(ellipse 820px 600px at 74% 66%, rgba(70,110,180,0.30), transparent 70%)",
      "radial-gradient(ellipse 700px 500px at 55% 20%, rgba(140,90,180,0.22), transparent 70%)",
    ],
  },
  dunes: {
    base: "#191410",
    blobs: [
      "radial-gradient(ellipse 1000px 640px at 30% 80%, rgba(200,140,70,0.30), transparent 70%)",
      "radial-gradient(ellipse 860px 560px at 78% 24%, rgba(220,170,100,0.20), transparent 70%)",
      "radial-gradient(ellipse 720px 520px at 55% 55%, rgba(120,80,50,0.25), transparent 70%)",
    ],
  },
  mist: {
    base: "#23262b",
    blobs: [
      "radial-gradient(ellipse 940px 640px at 25% 30%, rgba(170,180,195,0.22), transparent 70%)",
      "radial-gradient(ellipse 820px 580px at 75% 70%, rgba(140,150,170,0.20), transparent 70%)",
      "radial-gradient(ellipse 680px 480px at 55% 15%, rgba(200,205,215,0.14), transparent 70%)",
    ],
  },
  tide: {
    base: "#0c1420",
    blobs: [
      "radial-gradient(ellipse 980px 660px at 28% 72%, rgba(50,110,170,0.32), transparent 70%)",
      "radial-gradient(ellipse 800px 560px at 76% 26%, rgba(40,80,140,0.28), transparent 70%)",
      "radial-gradient(ellipse 700px 500px at 50% 50%, rgba(90,140,190,0.16), transparent 70%)",
    ],
  },
};

export const Plate: React.FC<{
  title: string;
  cards: { big: string | null; label: string }[];
  backdrop: keyof typeof PLATE_BACKDROPS;
}> = ({ title, cards, backdrop }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const bg = PLATE_BACKDROPS[backdrop] ?? PLATE_BACKDROPS.mist;
  return (
    <AbsoluteFill style={{ background: bg.base, justifyContent: "center", alignItems: "center" }}>
      {/* procedural atmosphere: layered soft blobs over the base wash */}
      {bg.blobs.map((b, i) => (
        <AbsoluteFill key={i} style={{ background: b }} />
      ))}
      <div
        style={{
          position: "absolute",
          top: 150 * s,
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: FONT,
          fontSize: 52 * s,
          fontWeight: 600,
          color: "rgba(255,255,255,0.82)",
          ...enter(frame, 0, fps, s),
        }}
      >
        {title}
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 44 * s,
          maxWidth: 1640 * s,
          padding: `0 ${120 * s}px`,
        }}
      >
        {cards.map((c, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              background: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(255,255,255,0.18)",
              borderRadius: 28 * s,
              backdropFilter: `blur(${18 * s}px)`,
              padding: `${56 * s}px ${64 * s}px`,
              minWidth: 300 * s,
              textAlign: "center",
              ...enter(frame, 6 + i * 6, fps, s),
            }}
          >
            {c.big ? (
              <div
                style={{
                  fontFamily: FONT,
                  fontWeight: 800,
                  fontSize: 110 * s,
                  letterSpacing: "-0.03em",
                  color: "#ffffff",
                  lineHeight: 1.05,
                }}
              >
                {c.big}
              </div>
            ) : null}
            <div
              style={{
                fontFamily: FONT,
                fontSize: 30 * s,
                color: "rgba(255,255,255,0.72)",
                marginTop: c.big ? 18 * s : 0,
              }}
            >
              {c.label}
            </div>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const Reveal: React.FC<{
  lead: string;
  leadFrames: number;
  word: string;
  sub: string;
  theme: FilmTheme;
  beatFrames?: number;
}> = ({ lead, leadFrames, word, sub, theme, beatFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  // lead → beat pause → word: the spec's leadFrames IS the word's onset
  // (already snapped onto the music grid upstream). The pause IS the bed's
  // real beat interval (ADR-130 — the black frame reads as a beat because
  // it IS one); no bed → 0, the lead hands straight to the word and no
  // fabricated pause pretends to be rhythm.
  const wordAt = Math.max(12, leadFrames);
  const pause = Math.max(0, Math.round(beatFrames ?? 0));
  const leadOut = interpolate(
    frame,
    [Math.max(0, wordAt - pause - 8), Math.max(8, wordAt - pause)],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const leadIn = enter(frame, 0, fps, s);
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: "center", alignItems: "center" }}>
      <div
        style={{
          fontFamily: FONT,
          fontSize: 68 * s,
          fontWeight: 600,
          lineHeight: 1.2,
          color: "#6b6b6b",
          maxWidth: 1320 * s,
          padding: `0 ${40 * s}px`,
          textAlign: "center",
          marginBottom: 36 * s,
          ...leadIn,
          opacity: leadIn.opacity * leadOut,
        }}
      >
        {lead}
      </div>
      <div
        style={{
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: 150 * s,
          letterSpacing: "-0.03em",
          color: theme.ink,
          ...enter(frame, wordAt, fps, s),
        }}
      >
        {accentize(word, false, theme)}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 44 * s, lineHeight: 1.3, color: "#6b6b6b", maxWidth: 1440 * s, padding: `0 ${40 * s}px`, textAlign: "center", marginTop: 30 * s, ...enter(frame, wordAt + 10, fps, s) }}>
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

/** Independent scene subtitles, outside the scene fade/camera transform. */
export const Subtitles: React.FC<{
  track: import("./schema").SubtitleTrack;
}> = ({ track }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();
  const seconds = frame / fps;
  const cue = track.cues.find(c => seconds >= c.at && seconds < c.end);
  if (!cue) return null;
  const style = track.style;
  const fade = Math.min(style.fade_seconds, (cue.end - cue.at) / 2);
  const entrance = Math.min(1, Math.max(0, (seconds - cue.at) / fade));
  const exit = Math.min(1, Math.max(0, (cue.end - seconds) / fade));
  const opacity = (style.enter === "none" ? 1 : entrance) * (style.exit === "none" ? 1 : exit);
  return (
    <div style={{ position: "absolute", bottom: `${style.bottom * 100}%`,
      left: 0, right: 0, display: "flex", justifyContent: "center",
      pointerEvents: "none", opacity,
      transform: style.enter === "rise" ? `translateY(${(1 - entrance) * 30 * s}px)` : undefined }}>
      <div style={{ maxWidth: `${style.width * 100}%`, boxSizing: "border-box",
        background: style.background, color: style.color, borderRadius: 8 * s,
        fontFamily: FONT, fontSize: style.font_size * s, fontWeight: style.font_weight,
        lineHeight: 1.3, padding: `${12 * s}px ${24 * s}px`, textAlign: "center",
        whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
        {cue.text}
      </div>
    </div>
  );
};

/** Per-scene in/out fade veil (default 7 frames each side; 0 disables a
 * side — a words scene with its own exit fade drops the out veil). */
export const Fade: React.FC<{
  dur: number;
  fadeIn?: number;
  fadeOut?: number;
  children: React.ReactNode;
}> = ({ dur, fadeIn = 7, fadeOut = 7, children }) => {
  const frame = useCurrentFrame();
  const o =
    fadeIn > 0
      ? interpolate(frame, [0, fadeIn], [0, 1], { extrapolateRight: "clamp" })
      : 1;
  const out =
    fadeOut > 0
      ? interpolate(frame, [dur - fadeOut, dur - 1], [1, 0], {
          extrapolateLeft: "clamp",
        })
      : 1;
  return <AbsoluteFill style={{ opacity: Math.min(o, 1) * out }}>{children}</AbsoluteFill>;
};

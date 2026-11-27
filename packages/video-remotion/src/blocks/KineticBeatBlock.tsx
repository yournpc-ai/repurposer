import React from "react";
import { StudioBackdrop } from "../engine/backdrop";
import { clamp01, springOut } from "../engine/math";
import { resolveBlockStyle } from "../engine/styles";
import { type Frame, type StudioStyle, typeSize } from "./Stage";

const segmenter = typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

const paths = {
  sparkle: "M12 2l2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8z",
  bolt: "M13 2L4 14h7l-1 8 10-13h-8z",
  cursor: "M4 3l15 9-7 1-3 7z",
  play: "M7 4l13 8-13 8z",
  code: "M8 7l-5 5 5 5m8-10 5 5-5 5m-3-14-3 18",
  layers: "M2 8l10-5 10 5-10 5zM3 13l9 5 9-5M3 17l9 5 9-5",
  globe: "M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0zM2 12h20M12 2c6 5 6 15 0 20-6-5-6-15 0-20z",
  wand: "M3 20L15 8l3 3L6 23zM12 11l3 3M18 2v4m-2-2h4m1 11v4m-2-2h4",
};
type Icon = keyof typeof paths;
function Glyph({ icon }: { icon: Icon }) {
  return <svg width="0.78em" height="0.78em" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"><path d={paths[icon]} /></svg>;
}
interface Props extends StudioStyle {
  mode: "impact_cut" | "typewriter_swap" | "slot_flip" | "inline_badge_split" | "marquee_wall";
  headline?: string; highlight_phrase?: string; prefix?: string; words: string[];
  word_reveals_s?: number[];
  left_text?: string; right_text?: string; badge_text?: string; badge_icon?: Icon;
  items: {text: string; icon?: Icon}[]; rows: number;
  scale_emphasis?: string; entrance_duration_s: number;
}

function Marquee({ props, frame, accent }: { props: Props; frame: Frame; accent: string }) {
  const u = frame.scaleUnit;
  const widths = props.items.map(item => (170 + 70 * Array.from(item.text).length) * u);
  const cycle = widths.reduce((a, b) => a + b, 0);
  const repeats = Math.max(3, Math.ceil(frame.width / cycle) + 2);
  const offset = Math.max(0, frame.tSec) * 280 * u % cycle;
  return <div style={{ width: "100%", overflow: "hidden", maskImage: "linear-gradient(90deg, transparent, black 8%, black 92%, transparent)" }}>
    {Array.from({ length: props.rows }, (_, row) => <div key={row} style={{
      display: "flex", height: 155 * u, alignItems: "center", opacity: row === Math.floor(props.rows / 2) ? 1 : 0.55,
      transform: "translateX(" + (row % 2 ? offset - cycle : -offset) + "px)",
    }}>{Array.from({ length: repeats }, (_, copy) => props.items.map((item, i) =>
      <div key={copy + "-" + i} style={{ flex: "0 0 " + widths[i] + "px", display: "flex", gap: 24 * u,
        alignItems: "center", fontSize: Math.min(100, typeSize(item.text, 100, widths[i] / u - 140)) * u }}>
        {item.text}<span style={{ border: "0.035em solid", borderRadius: "0.2em", padding: "0.1em", display: "flex",
          color: i === 1 ? accent : undefined }}><Glyph icon={item.icon ?? "sparkle"} /></span>
      </div>))}</div>)}
  </div>;
}

export function KineticBeatBlock({ props, frame }: { props: Props; frame: Frame }) {
  const { width, height, scaleUnit: u } = frame;
  const t = Math.max(0, frame.tSec);
  const progress = clamp01(t / frame.durSec);
  const style = resolveBlockStyle(frame.compositionStyle, props, { theme: "dark", accent: "#F59E0B", backdrop_style: "clean" });
  const words = props.words ?? [];
  const position = Math.min(words.length - 0.000001, progress * words.length);
  const times = props.word_reveals_s;
  const timed = times && times.length > 0 && times.length === words.length;
  const index = timed ? Math.max(0, times.filter(at => at <= t).length - 1) : Math.floor(position);
  const phase = timed
    ? clamp01((t - times[index]) / Math.max(0.001, (times[index + 1] ?? frame.durSec) - times[index]))
    : position - index;
  const portrait = height > width;
  const budget = width * 0.91 / u;
  const fit = (text: string, ideal: number) => u * typeSize(text, ideal, budget);
  const ink = style.isDark ? "#FAFAFA" : "#09090B";
  const accent = style.accentText;
  let body: React.ReactNode;
  switch (props.mode) {
    case "impact_cut": {
      const title = props.headline ?? "";
      const hit = springOut(t / props.entrance_duration_s, 16, 0.82);
      const phrase = props.highlight_phrase;
      const at = phrase ? title.indexOf(phrase) : -1;
      body = <div style={{ fontSize: fit(title, props.scale_emphasis === "oversized" ? 168 : 132),
        transform: "translateY(" + (1 - hit) * 28 * u + "px) scale(" + (0.9 + 0.1 * hit) + ")" }}>
        {at >= 0 && phrase ? <>{title.slice(0, at)}<span style={{ color: accent }}>{phrase}</span>{title.slice(at + phrase.length)}</> : title}
      </div>;
      break;
    }
    case "typewriter_swap": {
      const chars = segmenter ? Array.from(segmenter.segment(words[index]), part => part.segment) : Array.from(words[index]);
      const erasing = index < words.length - 1 && phase >= 0.7;
      const fraction = erasing ? clamp01(1 - (phase - 0.7) / 0.2) : clamp01(phase / 0.35);
      const lit = phase < 0.35 || (erasing && phase < 0.9) || Math.floor(t * 4) % 2 === 0;
      body = <div style={{ fontSize: Math.min(...words.map(w => fit(w + "|", 145))), display: "flex", alignItems: "center" }}>
        {chars.slice(0, Math.ceil(fraction * chars.length)).join("")}
        <span style={{ width: Math.max(3, 5 * u), height: "1.05em", marginLeft: 8 * u, background: accent, opacity: lit ? 1 : 0 }} />
      </div>;
      break;
    }
    case "slot_flip": {
      const enter = index ? springOut(phase / 0.6, 15, 0.84) : 1;
      const size = Math.min(...words.map(w => fit(portrait ? w : (props.prefix ?? "") + " " + w, 140)),
        fit(props.prefix ?? "", 140));
      body = <div style={{ display: "flex", alignItems: "center", gap: "0.18em", flexDirection: portrait ? "column" : "row", fontSize: size }}>
        {props.prefix}<div style={{ display: "grid", overflow: "hidden", height: "1.18em", lineHeight: 1.18, color: accent }}>
          {words.map((word, i) => <span key={i} style={{ gridArea: "1 / 1", visibility: i === index || i === index - 1 ? "visible" : "hidden",
            opacity: i === index ? enter : 1 - enter, transform: "translateY(" + (i === index ? 1 - enter : -enter) * 100 + "%)" }}>{word}</span>)}
        </div>
      </div>;
      break;
    }
    case "inline_badge_split": {
      const reveal = clamp01((progress - 0.22) / 0.38);
      const open = clamp01(springOut(reveal, 9, 0.64));
      const scale = open + 0.08 * Math.sin(Math.PI * reveal) * open;
      const badgeWidth = props.badge_text ? 1.2 + Array.from(props.badge_text).length * 0.63 : 1.16;
      const size = fit((props.left_text ?? "") + (props.right_text ?? "") + "WW" + (props.badge_text ?? ""), 142);
      body = <div style={{ display: "flex", alignItems: "center", fontSize: size }}>
        {props.left_text}<div style={{ display: "grid", placeItems: "center", width: badgeWidth * size * open,
          marginInline: 0.12 * size * open, transform: "rotate(" + (-28 * (1 - open)) + "deg) scale(" + scale + ")" }}>
          <span style={{ background: style.accent, color: style.accentInk, borderRadius: "0.45em", padding: "0.22em 0.3em",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: props.badge_text ? "0.56em" : "0.86em" }}>
            {props.badge_text || <Glyph icon={props.badge_icon ?? "sparkle"} />}
          </span></div>{props.right_text}
      </div>;
      break;
    }
    case "marquee_wall":
      body = <Marquee props={props} frame={frame} accent={accent} />;
  }
  return <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden",
    background: style.isDark ? "#09090B" : "#FAFAFA", color: ink, fontFamily: frame.fontFamily,
    fontWeight: 900, letterSpacing: "-0.035em", whiteSpace: "pre", lineHeight: 1.08 }}>
    {props.show_backdrop && <StudioBackdrop theme={style.theme} accent={style.accent} style={style.backdropStyle}
      tSec={t} scaleUnit={u} canvasBg={style.canvasBg} />}
    <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", visibility: timed && frame.tSec < times[0] ? "hidden" : undefined }}>{body}</div>
  </div>;
}

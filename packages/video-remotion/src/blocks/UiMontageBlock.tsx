import React from "react";
import { StudioBackdrop } from "../engine/backdrop";
import { clamp01, easeOutExpo } from "../engine/math";
import { palette, PinnedImage, type Frame, type StudioStyle, typeSize } from "./Stage";

interface Props extends StudioStyle {
  layout_mode: "rapid_cut" | "fan_slide" | "cascade_3d";
  headline?: string; badge?: string; cut_interval_s?: number; entrance_duration_s: number;
}

export function UiMontageBlock({ props, frame }: { props: Props; frame: Frame }): React.JSX.Element {
  const { width, height, scaleUnit: u, resources } = frame;
  const t = Math.max(0, frame.tSec);
  const progress = clamp01(t / frame.durSec);
  const c = palette(props, frame.compositionStyle);
  const count = resources.length;
  const interval = props.cut_interval_s ?? frame.durSec / count;
  const cut = Math.floor(t / interval) % count;
  const focus = progress * (count - 1);
  const rapid = props.layout_mode === "rapid_cut";
  const fan = props.layout_mode === "fan_slide";
  const hasHeading = Boolean(props.headline || props.badge);
  const cardWidth = Math.min(width * (rapid ? 0.86 : 0.69), height * (hasHeading ? 0.95 : 1.25));
  const bank = rapid ? "" : fan ? "rotateY(-8deg) rotateX(3deg)" : "rotateX(12deg) rotateY(-14deg) rotateZ(2deg)";
  const intro = easeOutExpo(t / (props.entrance_duration_s ?? 0.35));
  return <div style={{ position: "relative", width, height, overflow: "hidden", fontFamily: frame.fontFamily, color: c.ink }}>
    {props.show_backdrop !== false && <StudioBackdrop theme={c.tokens.theme} accent={c.accent} style={c.tokens.backdropStyle}
      tSec={t} scaleUnit={u} canvasBg={c.canvasBg} />}
    {hasHeading && <header style={{ position: "absolute", top: "4%", width: "94%", left: "3%", textAlign: "center" }}>
      {props.badge && <span style={{ display: "inline-block", padding: "0.2em 0.85em", border: "1px solid " + c.line,
        borderRadius: "1em", fontSize: 24 * u, fontWeight: 700 }}>{props.badge}</span>}
      {props.headline && <div style={{ fontSize: typeSize(props.headline, 82, width * 0.92 / u) * u,
        fontWeight: 900, letterSpacing: "-0.04em" }}>{props.headline}</div>}
    </header>}
    <div style={{ position: "absolute", inset: hasHeading ? "20% 0 0" : 0, display: "grid", placeItems: "center",
      perspective: (fan ? 1600 : 1400) * u }}>
      <div style={{ position: "relative", width: cardWidth, aspectRatio: "16/10", transformStyle: "preserve-3d",
        transform: bank + " translateY(" + (1 - intro) * 16 * u + "px)" }}>
        {resources.map((src, index) => {
          if (rapid && index !== cut) return null;
          const d = index - focus;
          const distance = Math.abs(d);
          let transform: string;
          if (count === 1) transform = "rotateY(" + (-4 + 6 * progress) + "deg) scale(" + (1 + progress * 0.08) + ")";
          else if (rapid) transform = "scale(" + (1.055 - 0.04 * easeOutExpo((t % interval) / 0.14)) + ")";
          else if (fan) transform = "translateX(" + d * cardWidth * 1.06 + "px) scale(" + (1 - 0.06 * Math.min(1, distance)) + ")";
          else transform = "translate3d(" + d * cardWidth * 0.38 + "px," + d * cardWidth * -0.19 + "px," +
            -distance * 210 * u + "px) scale(" + (1.025 - 0.025 * Math.min(1, distance)) + ")";
          return <div key={index} style={{ position: "absolute", inset: 0, transform,
            opacity: rapid ? 1 : Math.max(0, 1 - distance * 0.27), zIndex: count * 10 - Math.round(distance * 10),
            borderRadius: 16 * u, overflow: "hidden", background: c.surface, border: Math.max(1, 2 * u) + "px solid " + c.line,
            boxShadow: "0 " + 18 * u + "px " + 54 * u + "px rgba(0,0,0,0.24)" }}>
            <PinnedImage src={src} />
            <div style={{ position: "absolute", inset: "0 0 auto", height: Math.max(1, u), background: "rgba(255,255,255,0.38)" }} />
          </div>;
        })}
      </div>
    </div>
  </div>;
}

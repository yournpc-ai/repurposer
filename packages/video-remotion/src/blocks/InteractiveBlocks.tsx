import React, { type CSSProperties, type ReactNode } from "react";
import { Img } from "remotion";
import type { InteractiveBlockProps } from "@repurposer/video-spec";
import { DeviceFrame } from "../engine/DeviceFrame";
import { VirtualCursor } from "../engine/cursor";
import { cueProgress, easeInOutCubic, easeOutCubic, springOut } from "../engine/math";
import { ImageAdapter, palette, Stage, type Frame, type StudioStyle, typeSize } from "./Stage";

type Block<K extends keyof InteractiveBlockProps> = { props: InteractiveBlockProps[K]; frame: Frame };

function studioStyle(props: StudioStyle, frame: Frame, darkBackdrop: "warm_obsidian" | "studio_spotlight"): StudioStyle {
  if (frame.compositionStyle) return props;
  const theme = props.theme ?? (props.backdrop_style === "editorial_studio" ? "light" : "dark");
  return { ...props, theme, backdrop_style: props.backdrop_style ?? (theme === "light" ? "editorial_studio" : darkBackdrop) };
}

export function CursorMagneticClick({ props, frame }: Block<"cursor_magnetic_click">) {
  const style = studioStyle(props, frame, "warm_obsidian");
  const c = palette(style, frame.compositionStyle);
  const click = props.click_at_s ?? frame.durSec * 0.48;
  const elapsed = frame.tSec - click;
  const attract = easeInOutCubic(cueProgress(frame.tSec, click - 0.48, 0.45));
  const release = springOut(elapsed, 13, 0.76);
  const press = elapsed < 0 ? easeOutCubic((elapsed + 0.09) / 0.09) : 1 - springOut(elapsed, 24, 0.56);
  const glow = easeOutCubic(elapsed / 0.25);
  const ripple = cueProgress(elapsed, 0, 0.55);
  const target = { x: 0.53, y: 0.641, start_x: 0.78, start_y: 0.87, click_at_s: click };
  const dark = c.tokens.isDark;
  const buttonText = dark ? "#221e1a" : "#fcfaf7";

  return <Stage style={style} frame={frame}>
    <div style={{ position: "absolute", bottom: 525, left: 128, right: 128, textAlign: "center" }}>
      {props.eyebrow && <div style={{ color: c.secondary, fontSize: 24, fontWeight: 700, letterSpacing: ".15em",
        textTransform: "uppercase", marginBottom: 30 }}>{props.eyebrow}</div>}
      <div style={{ fontSize: typeSize(props.headline, 152, 1600, 2), fontWeight: 900, lineHeight: 1,
        letterSpacing: "-.063em", textWrap: "balance" }}>{props.headline}</div>
      {props.subcopy && <div style={{ marginTop: 25, color: c.secondary,
        fontSize: typeSize(props.subcopy, 34, 1500), lineHeight: 1.28 }}>{props.subcopy}</div>}
    </div>
    <div style={{
      position: "absolute", left: "50%", top: 676,
      transform: `translate(-50%, -50%) translate(${12 * attract * (1 - release)}px, ${5 * attract * (1 - release)}px) scale(${1 - 0.06 * press})`,
      padding: "4px", borderRadius: 100, background: "linear-gradient(150deg,#fffcf1,#897e75 48%,#514d49 78%,#dbd5ca)",
      boxShadow: `0 16px 28px #0706044d, 0 38px 72px #07060450, 0 0 ${glow * 42}px color-mix(in srgb, ${c.accent} 25%, transparent)`,
    }}>
      {elapsed >= 0 && ripple < 1 && <i style={{
        position: "absolute", inset: 0, border: `2px solid ${c.accent}`, borderRadius: "inherit",
        opacity: (1 - ripple) * 0.8, transform: `scale(${1 + 0.19 * easeOutCubic(ripple)})`,
        boxShadow: `0 0 12px color-mix(in srgb, ${c.accent} 35%, transparent)`,
      }} />}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 24, padding: "0 48px",
        minWidth: 240, height: 98, borderRadius: 100, color: buttonText,
        background: dark ? "linear-gradient(165deg,#fffdf6,#d4cbc0)" : "linear-gradient(165deg,#454441,#242423)",
        boxShadow: "inset 0 2px 2px #ffffff70, inset 0 -3px 4px #0003",
        fontSize: typeSize(props.cta_label, 36, 640), fontWeight: 700, letterSpacing: "-.025em" }}>
        <i style={{ width: 15, height: 15, borderRadius: "50%", background: glow ? c.accent : "#817c77",
          boxShadow: `0 0 ${14 * glow}px ${c.accent}, 0 0 0 3px #0002` }} />
        {props.cta_label}
      </div>
    </div>
    <VirtualCursor cue={target} tSec={frame.tSec} scaleUnit={1.5} accent={c.accent} />
  </Stage>;
}

const screenWidth = 1456;
const screenHeight = 772;

function ScreenStage({ frame, style, headline, children }: {
  frame: Frame; style: StudioStyle; headline?: string | null; children: ReactNode;
}) {
  return <Stage frame={frame} style={style}>
    {headline && <div style={{ position: "absolute", left: 228, right: 228, bottom: 934,
      fontSize: typeSize(headline, 69, 1450), fontWeight: 900, letterSpacing: "-.052em", lineHeight: 1.1 }}>{headline}</div>}
    <DeviceFrame variant="tablet" style={{ position: "absolute", left: 228, top: headline ? 191 : 148,
      padding: 4, width: screenWidth + 8, height: screenHeight + 9 }}>
      {children}
    </DeviceFrame>
  </Stage>;
}

const centered: CSSProperties = { display: "flex", alignItems: "center", justifyContent: "center" };

export function ZoomFollowsClick({ props, frame }: Block<"zoom_follows_click">) {
  const style = studioStyle(props, frame, "studio_spotlight");
  const c = palette(style, frame.compositionStyle);
  const fitImage = React.useCallback((image: HTMLImageElement) => {
    if (image.naturalHeight > 0) {
      image.style.width = `${Math.min(screenWidth, screenHeight * image.naturalWidth / image.naturalHeight)}px`;
    }
  }, []);
  const click = props.click_at_s ?? frame.durSec * (props.click_at_ratio ?? 0.4);
  const focus = springOut(frame.tSec - click, 9, 0.85);
  const zoom = props.zoom_scale ?? 1.85;
  const scale = 1 + (zoom - 1) * focus;
  // Pan toward the selected pixel until the nearest screenshot edge meets the viewport.
  const pan = (coordinate: number) => Math.min(0, Math.max(1 - zoom, 0.5 - zoom * coordinate)) * focus * 100;
  const cue = { x: props.target_x, y: props.target_y, click_at_s: click };
  return <ScreenStage frame={frame} style={style} headline={props.headline}>
    <div style={{ ...centered, position: "relative", height: "100%", background: "#17191b" }}>
      <div style={{ position: "relative", overflow: "hidden", lineHeight: 0 }}>
        <div style={{ position: "relative", transformOrigin: "0 0",
          transform: `translate(${pan(cue.x)}%, ${pan(cue.y)}%) scale(${scale})` }}>
          <Img src={frame.resources[0]} onImageFrame={fitImage}
            style={{ display: "block", maxWidth: screenWidth, maxHeight: screenHeight, height: "auto" }} />
          <VirtualCursor cue={cue} tSec={frame.tSec} scaleUnit={1.4 / scale} accent={c.accent} />
        </div>
      </div>
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: focus * 0.44,
        background: "radial-gradient(ellipse at center,transparent 47%,#11161c 130%)" }} />
      {props.callout_label && <div style={{ position: "absolute", bottom: 36, right: 40, padding: "12px 27px",
        border: "1px solid #ffffff4d", borderRadius: 60, background: "#191b1eed", color: "#fffaf1",
        boxShadow: "0 7px 18px #0004", fontSize: 28, fontWeight: 700, opacity: focus,
        transform: `translateY(${(1 - focus) * 14}px)` }}>{props.callout_label}</div>}
    </div>
  </ScreenStage>;
}

export function BrowserUrlLoad({ props, frame }: Block<"browser_url_load">) {
  const style = studioStyle(props, frame, "studio_spotlight");
  const c = palette(style, frame.compositionStyle);
  const Image = React.useContext(ImageAdapter);
  const { tSec, durSec } = frame;
  const typeAt = props.type_at_s ?? Math.min(0.055 * durSec, props.load_at_s ?? durSec);
  const loadAt = props.load_at_s ?? typeAt + 0.36 * durSec;
  const revealAt = props.load_at_s ?? loadAt + 0.025 * durSec;
  const chars = Array.from(props.url_text);
  const typed = Math.floor(chars.length * cueProgress(tSec, typeAt, loadAt - typeAt));
  const load = easeInOutCubic(cueProgress(tSec, loadAt, 0.3 * durSec));
  const reveal = easeOutCubic(cueProgress(tSec, revealAt, 0.37 * durSec));
  const dark = c.tokens.isDark;
  return <ScreenStage frame={frame} style={style} headline={props.headline}>
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: dark ? "#1b1d21" : "#dedbd6" }}>
      <div style={{ ...centered, position: "relative", height: 78, flexShrink: 0,
        background: dark ? "linear-gradient(#424449,#27292d)" : "linear-gradient(#f1f1ee,#d5d4d0)",
        borderBottom: "1px solid #15161750" }}>
        <div style={{ position: "absolute", left: 34, display: "flex", gap: 10 }}>
          {[0, 1, 2].map(i => <i key={i} style={{ width: 12, height: 12, borderRadius: "50%",
            background: dark ? "#909195" : "#888886", boxShadow: "inset 0 1px 1px #fff5" }} />)}
        </div>
        <div style={{ ...centered, width: "64%", height: 43, borderRadius: 13, color: dark ? "#eeefeb" : "#272a2b",
          background: dark ? "#202226" : "#f8f8f5", boxShadow: "inset 0 1px 4px #14141444, 0 1px 0 #fff4",
          fontFamily: frame.fontFamily, fontWeight: 500, letterSpacing: ".02em",
          fontSize: typeSize(props.url_text, 24, 880), whiteSpace: "pre" }}>
          {chars.slice(0, typed).join("")}
          <i style={{ height: "1em", width: 2, marginLeft: 2, background: "currentColor",
            opacity: tSec < loadAt + 0.075 * durSec && Math.floor(frame.tSec * 3.5) % 2 === 0 ? 1 : 0 }} />
        </div>
      </div>
      <div style={{ position: "relative", flex: 1, overflow: "hidden", background: dark ? "#25272a" : "#eae8e3" }}>
        <Image src={frame.resources[0]} style={{ width: "100%", height: "100%", objectFit: "contain",
          opacity: reveal, filter: `blur(${(1 - reveal) * 9}px)`, transform: `scale(${1.025 - 0.025 * reveal})` }} />
        {props.badge && <div style={{ position: "absolute", right: 28, bottom: 28, opacity: reveal,
          background: "#18191ce8", border: "1px solid #ffffff45", color: "#faf7f1",
          fontSize: 25, borderRadius: 45, padding: "9px 22px" }}>{props.badge}</div>}
        <div style={{ position: "absolute", top: 0, left: 0, height: 4, width: `${100 * load}%`,
          background: c.accent, opacity: 1 - cueProgress(tSec, loadAt + 0.315 * durSec, 0.13 * durSec), boxShadow: `0 0 12px ${c.accent}` }} />
      </div>
    </div>
  </ScreenStage>;
}

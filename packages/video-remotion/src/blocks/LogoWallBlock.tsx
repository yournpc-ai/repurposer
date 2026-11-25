import React from "react";
import {
  Stage,
  palette,
  appear,
  typeSize,
  type Frame,
  type StudioStyle,
  PinnedImage,
} from "./Stage";

interface Props extends StudioStyle {
  mode: "marquee_strip" | "grid_stagger" | "spotlight_lockup";
  eyebrow?: string;
  headline?: string;
  items: { text: string; resource_index?: number | null }[];
}
export function LogoWallBlock({
  props,
  frame,
}: {
  props: Props;
  frame: Frame;
}): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const marquee = props.mode === "marquee_strip";
  const spotlight = props.mode === "spotlight_lockup";
  const active = Math.min(
    props.items.length - 1,
    Math.floor((frame.tSec / frame.durSec) * props.items.length),
  );
  const count = props.items.length;
  const repeated = marquee
    ? Array.from({ length: count + 6 }, (_, i) => props.items[i % count])
    : spotlight
      ? [props.items[active]]
      : props.items;
  return (
    <Stage style={props} frame={frame}>
      <div style={{ position: "absolute", top: 140, left: 148, right: 148 }}>
        <div
          style={{
            fontSize: 24,
            letterSpacing: ".13em",
            textTransform: "uppercase",
            color: c.accentText,
          }}
        >
          {props.eyebrow}
        </div>
        <div
          style={{
            fontSize: typeSize(props.headline ?? "", 96, 1600, 2),
            fontWeight: 700,
            letterSpacing: "-.05em",
            lineHeight: 1.1,
            marginTop: 22,
          }}
        >
          {props.headline}
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 148,
          right: 148,
          top: 430,
          bottom: 110,
          overflow: "hidden",
          borderTop: `1px solid ${c.line}`,
          borderBottom: `1px solid ${c.line}`,
          maskImage: marquee
            ? "linear-gradient(90deg,transparent,black 6%,black 94%,transparent)"
            : undefined,
        }}
      >
        <div
          style={{
            display: marquee ? "flex" : "grid",
            height: "100%",
            alignItems: "center",
            gridTemplateColumns: spotlight
              ? "1fr"
              : `repeat(${Math.min(4, count)},1fr)`,
            transform: marquee
              ? `translateX(-${(frame.tSec * 116) % (count * 380)}px)`
              : undefined,
          }}
        >
          {repeated.map((item, i) => (
            <div
              key={i}
              style={{
                ...(props.mode === "grid_stagger"
                  ? appear(frame.tSec, i * 0.075)
                  : {}),
                flex: "0 0 380px",
                textAlign: "center",
                padding: "0 20px",
                boxSizing: "border-box",
                fontSize: typeSize(
                  item.text,
                  spotlight ? 108 : 62,
                  spotlight ? 1200 : 336,
                ),
                fontFamily:
                  (i % count) % 2 ? "Georgia, serif" : frame.fontFamily,
                fontWeight: (i % count) % 2 ? 500 : 750,
                letterSpacing: "-.055em",
              }}
            >
              {item.resource_index != null ? (
                <div style={{ height: spotlight ? 220 : 92 }}>
                  <PinnedImage src={frame.resources[item.resource_index]} />
                </div>
              ) : (
                item.text
              )}
            </div>
          ))}
        </div>
      </div>
    </Stage>
  );
}

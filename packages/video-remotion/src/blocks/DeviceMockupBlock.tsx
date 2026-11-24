import React from "react";
import { evaluateCamera } from "../engine/camera";
import {
  PinnedImage,
  appear,
  Heading,
  palette,
  Stage,
  typeSize,
  type Frame,
  type StudioStyle,
} from "./Stage";

interface DeviceProps extends StudioStyle {
  layout?: "dual" | "desktop" | "mobile";
  eyebrow?: string;
  headline?: string;
  caption?: string;
  reveal_at_s?: number | null;
}

export function DeviceMockupBlock({ props, frame }: { props: DeviceProps; frame: Frame }): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const mobileOnly = props.layout === "mobile";
  const dual = (props.layout ?? "dual") === "dual" && frame.resources.length > 1;
  const phone = mobileOnly || dual;
  const cue = props.reveal_at_s ?? (dual ? frame.durSec * 0.38 : 0.2);
  const camera = evaluateCamera("tilt_left", frame.tSec - (dual ? 0 : cue), frame.durSec, 0.5, 0.5, 1, 0, 1);
  const chrome = !c.tokens.isDark ? "#DAE1E3" : "#35414A";
  return (
    <Stage style={props} frame={frame}>
      <Heading title={props.headline} eyebrow={props.eyebrow} colors={c} />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: props.headline || props.eyebrow ? 322 : 172,
          height: 590,
          perspective: camera.perspective,
        }}
      >
        {!mobileOnly && (
          <div
            style={{
              width: 1030,
              height: 580,
              margin: "0 auto",
              position: "relative",
              left: dual ? -100 : 0,
              opacity: camera.opacity,
              transform: camera.stage,
              transformStyle: "preserve-3d",
              borderRadius: 22,
              padding: "0 8px 8px",
              boxSizing: "border-box",
              background: chrome,
              boxShadow: "0 22px 45px rgba(3,10,16,.23)",
              border: `1px solid ${c.line}`,
            }}
          >
            <div style={{ height: 34, display: "flex", alignItems: "center", gap: 7, paddingLeft: 12 }}>
              {[0, 1, 2].map((i) => (
                <i key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: c.line }} />
              ))}
              <i style={{ margin: "auto", width: "34%", height: 9, borderRadius: 8, background: c.line }} />
            </div>
            <div
              style={{
                height: "calc(100% - 34px)",
                borderRadius: 12,
                background: c.surface,
                overflow: "hidden",
              }}
            >
              <PinnedImage src={frame.resources[0]} />
            </div>
          </div>
        )}
        {phone && (
          <div
            style={{
              ...appear(frame.tSec, cue),
              position: "absolute",
              left: dual ? 1256 : 824,
              top: dual ? 46 : -20,
              width: 272,
              height: 580,
              boxSizing: "border-box",
              padding: 8,
              background: "#222C33",
              border: "2px solid #72808A",
              borderRadius: 38,
              boxShadow: "0 18px 42px rgba(5,11,18,.27)",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                overflow: "hidden",
                borderRadius: 28,
                background: c.surface,
              }}
            >
              <PinnedImage src={frame.resources[1] ?? frame.resources[0]} />
            </div>
          </div>
        )}
      </div>
      {props.caption && (
        <div
          style={{
            ...appear(frame.tSec, Math.max(cue, frame.durSec * 0.59)),
            position: "absolute",
            left: 180,
            right: 180,
            bottom: 65,
            textAlign: "center",
            color: c.secondary,
            fontSize: typeSize(props.caption, 29, 1520, 2),
          }}
        >
          {props.caption}
        </div>
      )}
    </Stage>
  );
}

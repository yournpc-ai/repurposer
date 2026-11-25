import React from "react";
import { DeviceFrame } from "../engine/DeviceFrame";
import { evaluateCamera } from "../engine/camera";
import { cueProgress, easeOutCubic } from "../engine/math";
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
  layout?: "dual" | "desktop" | "mobile" | "split_focus" | "hero_bleed";
  eyebrow?: string;
  headline?: string;
  caption?: string;
  reveal_at_s?: number | null;
}

export function DeviceMockupBlock({
  props,
  frame,
}: {
  props: DeviceProps;
  frame: Frame;
}): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const layout = props.layout ?? "dual";
  const split = layout === "split_focus";
  const bleed = layout === "hero_bleed";
  const dual = layout === "dual" && frame.resources.length > 1;
  const cue = props.reveal_at_s ?? (dual ? frame.durSec * 0.38 : 0.2);
  const camera = evaluateCamera(
    "tilt_left",
    frame.tSec - (dual ? 0 : cue),
    frame.durSec,
    0.5,
    0.5,
    1,
    0,
    1,
  );
  const focus = easeOutCubic(cueProgress(frame.tSec, cue, 0.8));
  const screen = frame.resources[0] ? (
    <PinnedImage src={frame.resources[0]} />
  ) : (
    <div
      style={{
        height: "100%",
        background:
          "radial-gradient(ellipse at 36% 84%,#a6abc0,transparent 36%),linear-gradient(138deg,#191f32,#5f687a 58%,#282c3a)",
      }}
    />
  );
  return (
    <Stage style={props} frame={frame}>
      {split && (
        <div
          style={{
            position: "absolute",
            left: 890,
            top: 178,
            width: 940,
            height: 530,
            opacity: 0.38,
            transform: "perspective(1600px) rotateY(-16deg)",
            filter: `blur(${3 + focus * 15}px)`,
          }}
        >
          {screen}
        </div>
      )}
      {split ? (
        <div style={{ position: "absolute", left: 132, top: 310, width: 790 }}>
          <div
            style={{
              fontSize: 23,
              letterSpacing: "0.13em",
              textTransform: "uppercase",
              color: c.accentText,
            }}
          >
            {props.eyebrow}
          </div>
          <div
            style={{
              marginTop: 28,
              fontSize: typeSize(props.headline ?? "", 120, 790, 3),
              letterSpacing: "-.065em",
              fontWeight: 700,
              lineHeight: 1.02,
            }}
          >
            {props.headline}
          </div>
          <div style={{ marginTop: 30, fontSize: 31, color: c.secondary }}>
            {props.caption}
          </div>
        </div>
      ) : (
        <Heading title={props.headline} eyebrow={props.eyebrow} colors={c} />
      )}
      {bleed && (
        <div
          style={{
            position: "absolute",
            inset: "56% 0 0",
            background:
              "radial-gradient(ellipse at center, #bbb9ac55, transparent 65%)",
          }}
        />
      )}
      <div
        style={{
          position: "absolute",
          inset: 0,
          perspective: camera.perspective,
        }}
      >
        {layout !== "mobile" && (
          <DeviceFrame
            variant={split || bleed ? "laptop" : "browser"}
            style={{
              position: "absolute",
              width: bleed ? 1660 : split ? 798 : 1030,
              height: bleed ? 934 : split ? 452 : 580,
              left: split ? 950 : bleed ? 438 : dual ? 345 : 445,
              top: split
                ? 294
                : bleed
                  ? 365
                  : props.headline || props.eyebrow
                    ? 322
                    : 172,
              opacity: camera.opacity,
              transform: split
                ? `rotateY(-18deg) rotateX(5deg) rotateZ(-3deg) translateY(${20 * (1 - focus)}px)`
                : camera.stage,
              filter: split ? `blur(${(1 - focus) * 9}px)` : undefined,
            }}
          >
            {screen}
          </DeviceFrame>
        )}
        {(dual || layout === "mobile") && (
          <DeviceFrame
            variant="phone"
            style={{
              ...appear(frame.tSec, cue),
              position: "absolute",
              width: 272,
              height: 580,
              left: dual ? 1256 : 824,
              top:
                (props.headline || props.eyebrow ? 322 : 172) +
                (dual ? 46 : -20),
            }}
          >
            <PinnedImage src={frame.resources[1] ?? frame.resources[0]} />
          </DeviceFrame>
        )}
      </div>
      {!split && props.caption && (
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

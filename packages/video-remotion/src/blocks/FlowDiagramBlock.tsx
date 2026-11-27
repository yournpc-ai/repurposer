import React from "react";
import { cueProgress, easeInOutCubic } from "../engine/math";
import {
  activeFocusStyle,
  appear,
  cardFace,
  Heading,
  itemTime,
  palette,
  Stage,
  typeSize,
  type Frame,
  type StudioStyle,
} from "./Stage";

interface Node {
  step_label?: string;
  title: string;
  detail?: string;
  badge?: string;
  reveal_at_s?: number;
}
interface FlowProps extends StudioStyle {
  eyebrow?: string;
  title?: string;
  nodes: Node[];
}

export function FlowDiagramBlock({ props, frame }: { props: FlowProps; frame: Frame }): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const { nodes } = props;
  const gap = 64;
  const width = (1660 - (nodes.length - 1) * gap) / nodes.length;
  const cardTop = props.title || props.eyebrow ? 378 : 296;
  const height = 396;
  const times = props.nodes.map((item, i) => itemTime(item.reveal_at_s, i, props.nodes.length, frame.durSec));
  return (
    <Stage style={props} frame={frame}>
      <Heading title={props.title} eyebrow={props.eyebrow} colors={c} />
      <div style={{ position: "absolute", top: cardTop, left: 130 }}>
        {nodes.map((node, i) => {
          const start = times[i];
          const travel = easeInOutCubic(cueProgress(frame.tSec, start, 0.42));
          const left = i * (width + gap);
          const inner = width - 48;
          return (
            <React.Fragment key={i}>
              {i > 0 && (
                <svg
                  width={gap}
                  height="28"
                  viewBox={`0 0 ${gap} 28`}
                  style={{
                    position: "absolute",
                    left: left - gap,
                    top: height / 2 - 14,
                    overflow: "visible",
                  }}
                >
                  <path d={`M0 14H${gap}`} stroke={c.line} strokeWidth="1.5" />
                  <path
                    d={`M0 14H${gap}`}
                    stroke={c.accent}
                    strokeWidth="3"
                    pathLength="1"
                    strokeDasharray="1"
                    strokeDashoffset={1 - travel}
                  />
                  {travel > 0 && <circle cx={gap * travel} cy="14" r="5" fill={c.accent} />}
                </svg>
              )}
              <article
                style={{
                  ...cardFace(c),
                  ...appear(frame.tSec, start, activeFocusStyle(frame.tSec, times, i, frame.durSec)),
                  position: "absolute",
                  left,
                  width,
                  height,
                  padding: "30px 24px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  gap: 18,
                }}
              >
                <div
                  style={{
                    color: c.secondary,
                    letterSpacing: ".04em",
                    fontSize: typeSize(node.step_label ?? "", 22, inner, 2),
                  }}
                >
                  {node.step_label ?? String(i + 1).padStart(2, "0")}
                </div>
                <div style={{ height: 3, background: c.accent, width: 46 * travel }} />
                <strong style={{ fontWeight: c.headingWeight, lineHeight: 1.14, fontSize: typeSize(node.title, 43, inner, 3) }}>
                  {node.title}
                </strong>
                {node.detail && (
                  <div style={{ color: c.secondary, fontSize: typeSize(node.detail, 26, inner, 4) }}>
                    {node.detail}
                  </div>
                )}
                {node.badge && (
                  <span
                    style={{
                      alignSelf: "flex-start",
                      borderRadius: c.cardTreatment === "brutal_offset" ? 2 : 8,
                      background: c.tint,
                      color: c.cardTreatment === "editorial_rule" ? c.ink : c.accentText,
                      fontWeight: 700,
                      padding: "5px 10px",
                      fontSize: typeSize(node.badge, 20, inner - 20, 2),
                    }}
                  >
                    {node.badge}
                  </span>
                )}
              </article>
            </React.Fragment>
          );
        })}
      </div>
    </Stage>
  );
}

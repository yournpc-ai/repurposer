import React from "react";
import { cueProgress, easeInOutCubic } from "../engine/math";
import { appear, Heading, itemTime, palette, Stage, typeSize, type Frame, type StudioStyle } from "./Stage";

interface Step {
  number?: number | string;
  title: string;
  detail?: string;
  reveal_at_s?: number;
}
interface TimelineProps extends StudioStyle {
  eyebrow?: string;
  title?: string;
  steps: Step[];
  active_step?: number;
}

export function StepTimelineBlock({
  props,
  frame,
}: {
  props: TimelineProps;
  frame: Frame;
}): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const { steps } = props;
  const width = 1656 / steps.length;
  const times = steps.map((s, i) => itemTime(s.reveal_at_s, i, steps.length, frame.durSec));
  const current = times.reduce((active, start, i) => (frame.tSec >= start ? i : active), -1);
  const focus = props.active_step == null ? current : props.active_step - 1;
  return (
    <Stage style={props} frame={frame}>
      <Heading title={props.title} eyebrow={props.eyebrow} colors={c} />
      <div style={{ position: "absolute", left: 132, top: 424, width: 1656, display: "flex" }}>
        <div
          style={{
            position: "absolute",
            left: 32,
            width: width * (steps.length - 1),
            top: 31,
            height: 2,
            background: c.line,
          }}
        />
        {steps.map((step, i) => {
          const selected = i === focus;
          const progress = easeInOutCubic(cueProgress(frame.tSec, times[i], 0.55));
          const badge = String(step.number ?? String(i + 1).padStart(2, "0"));
          return (
            <div key={i} style={{ width, position: "relative", boxSizing: "border-box", paddingRight: 45 }}>
              {i > 0 && (
                <i
                  style={{
                    position: "absolute",
                    height: 4,
                    left: 64 - width,
                    top: 30,
                    width: (width - 64) * progress,
                    background: c.accent,
                  }}
                />
              )}
              <div style={{ position: "relative", height: 64, display: "flex", alignItems: "center" }}>
                <div
                  style={{
                    width: 64,
                    height: 64,
                    borderRadius:
                      c.cardTreatment === "editorial_rule"
                        ? 4
                        : c.cardTreatment === "brutal_offset"
                          ? 2
                          : "50%",
                    background: selected ? c.accent : c.surface,
                    color: selected ? c.accentInk : c.ink,
                    boxSizing: "border-box",
                    border: `${selected ? 3 : 2}px solid ${
                      c.cardTreatment === "editorial_rule"
                        ? c.line
                        : selected
                          ? c.accent
                          : c.line
                    }`,
                    boxShadow:
                      selected && c.cardTreatment === "editorial_rule"
                        ? `3px 3px 0px ${c.line}`
                        : selected && c.cardTreatment === "brutal_offset"
                          ? `4px 4px 0px ${c.accentSecondary}`
                          : undefined,
                    display: "grid",
                    placeContent: "center",
                    textAlign: "center",
                  }}
                >
                  <span
                    style={{
                      opacity: progress,
                      maxWidth: 53,
                      fontWeight: c.headingWeight,
                      fontSize: typeSize(badge, 25, 53, 2),
                    }}
                  >
                    {badge}
                  </span>
                </div>
              </div>
              <div
                style={{
                  ...appear(frame.tSec, times[i]),
                  marginTop: 34,
                  borderTop: `3px solid ${selected ? c.accent : c.line}`,
                  paddingTop: 24,
                }}
              >
                <strong
                  style={{
                    display: "block",
                    fontWeight: c.headingWeight,
                    fontSize: typeSize(step.title, 52, width - 50, 3),
                    lineHeight: 1.12,
                  }}
                >
                  {step.title}
                </strong>
                {step.detail && (
                  <div
                    style={{
                      marginTop: 19,
                      color: c.secondary,
                      fontSize: typeSize(step.detail, 30, width - 50, 4),
                    }}
                  >
                    {step.detail}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Stage>
  );
}

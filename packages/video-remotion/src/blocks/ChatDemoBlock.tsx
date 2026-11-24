import React from "react";
import { cueProgress, easeOutCubic } from "../engine/math";
import {
  PinnedImage,
  appear,
  cardFace,
  palette,
  Stage,
  typeSize,
  type Frame,
  type StudioStyle,
} from "./Stage";

interface Message {
  role: "user" | "assistant";
  text: string;
  at_s?: number | null;
}
interface ChatProps extends StudioStyle {
  title?: string;
  messages: Message[];
  work_steps?: { label: string; at_s?: number | null }[];
  result_card?: { title: string; subtitle?: string; badge?: string };
}

export function ChatDemoBlock({ props, frame }: { props: ChatProps; frame: Frame }): React.JSX.Element {
  const { tSec, durSec } = frame;
  const c = palette(props, frame.compositionStyle);
  const steps = props.work_steps ?? [];
  const compact = props.messages.length > 2;
  const span = durSec * 0.72;
  const messageTimes = props.messages.map(
    (m, i) =>
      m.at_s ??
      (i === 0
        ? 0.12
        : (span * (i + (steps.length ? 0.8 : 0))) / (props.messages.length - 1 + (steps.length ? 0.8 : 0))),
  );
  const stepTimes = steps.map(
    (step, i) =>
      step.at_s ??
      messageTimes[0] +
        (messageTimes[1] - messageTimes[0]) * (0.35 + (0.55 * i) / Math.max(1, steps.length - 1)),
  );
  const resultTime = Math.max(...messageTimes, ...stepTimes) + 0.34;
  const result = props.result_card;
  return (
    <Stage style={props} frame={frame}>
      <div style={{ position: "absolute", inset: "78px 232px 106px", display: "flex", alignItems: "center" }}>
        <section
          style={{
            ...cardFace(c, { elevated: true }),
            width: "100%",
            padding: "34px 52px",
            ...(c.tokens.hasCompositionStyle
              ? {}
              : { borderRadius: 30, boxShadow: "0 25px 60px rgba(5,14,21,.13)" }),
          }}
        >
          {props.title && (
            <header
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                borderBottom: `1px solid ${c.line}`,
                paddingBottom: 20,
                marginBottom: 22,
                fontWeight: 700,
                fontSize: typeSize(props.title, 38, 1230, 2),
              }}
            >
              <span style={{ width: 15, height: 15, background: c.accent, borderRadius: 4, flexShrink: 0 }} />
              {props.title}
            </header>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: compact ? 14 : 24 }}>
            {props.messages.map((message, i) => {
              const user = message.role === "user";
              const start = messageTimes[i];
              const chars = Array.from(message.text);
              const next = i === 0 && stepTimes.length ? stepTimes[0] : messageTimes[i + 1];
              const typing = Math.max(0.15, Math.min(0.85, (next ?? start + 1) - start));
              const typed = user ? Math.floor(chars.length * cueProgress(tSec, start, typing)) : chars.length;
              return (
                <React.Fragment key={i}>
                  <div
                    style={{
                      ...appear(tSec, start),
                      boxSizing: "border-box",
                      width: "83%",
                      alignSelf: user ? "flex-end" : "flex-start",
                      padding: user ? "15px 30px" : "8px 24px",
                      borderRadius: user ? "21px 21px 4px 21px" : 0,
                      background: user ? c.tint : undefined,
                      borderLeft: user ? undefined : `4px solid ${c.accent}`,
                      fontSize: typeSize(message.text, compact ? 34 : 42, 1050, 2),
                      fontWeight: user ? 400 : 700,
                    }}
                  >
                    {chars.slice(0, typed).join("")}
                    <span style={{ visibility: "hidden" }}>{chars.slice(typed).join("")}</span>
                  </div>
                  {i === 0 && steps.length > 0 && (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: "10px 28px",
                        padding: "8px 24px",
                      }}
                    >
                      {steps.map((step, j) => {
                        const progress = easeOutCubic(cueProgress(tSec, stepTimes[j], 0.32));
                        return (
                          <div
                            key={j}
                            style={{
                              display: "flex",
                              gap: 14,
                              alignItems: "center",
                              opacity: progress,
                              color: c.secondary,
                              fontSize: typeSize(step.label, 25, 555, 2),
                            }}
                          >
                            <svg width="23" height="23" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
                              <path
                                d="M3 12l6 6L21 5"
                                fill="none"
                                stroke={c.accent}
                                strokeWidth="3"
                                pathLength="1"
                                strokeDasharray="1"
                                strokeDashoffset={1 - progress}
                              />
                            </svg>
                            {step.label}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </React.Fragment>
              );
            })}
            {result && (
              <div
                style={{
                  ...appear(tSec, resultTime),
                  borderTop: `1px solid ${c.line}`,
                  paddingTop: 18,
                  display: "flex",
                  alignItems: "center",
                  gap: 20,
                }}
              >
                {frame.resources[0] && (
                  <div style={{ width: 155, height: 86, flexShrink: 0 }}>
                    <PinnedImage src={frame.resources[0]} />
                  </div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: typeSize(result.title, 32, 780, 2) }}>
                    {result.title}
                  </div>
                  {result.subtitle && (
                    <div style={{ color: c.secondary, fontSize: typeSize(result.subtitle, 24, 780, 2) }}>
                      {result.subtitle}
                    </div>
                  )}
                </div>
                {result.badge && (
                  <span
                    style={{
                      ...cardFace(c),
                      background: c.tint,
                      maxWidth: 310,
                      padding: "8px 16px",
                      fontSize: typeSize(result.badge, 23, 270, 2),
                    }}
                  >
                    {result.badge}
                  </span>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </Stage>
  );
}

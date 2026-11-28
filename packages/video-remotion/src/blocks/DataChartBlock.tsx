import React from "react";
import { cueProgress, easeInOutCubic, springOut } from "../engine/math";
import { appear, Heading, itemTime, palette, Stage, typeSize, type Frame, type StudioStyle } from "./Stage";

interface Point {
  label: string;
  value: number;
  display_value?: string;
  reveal_at_s?: number;
}
interface ChartProps extends StudioStyle {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  chart_type: "line" | "bar";
  unit?: string;
  points: Point[];
  highlight_index?: number;
}

export function DataChartBlock({ props, frame }: { props: ChartProps; frame: Frame }): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const { points } = props;
  // Normalize first so that opposite-sign finite values cannot overflow the domain.
  const magnitude = Math.max(...points.map((p) => Math.abs(p.value))) || 1;
  const values = points.map((p) => p.value / magnitude);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const width = 1640;
  const plotHeight = 348;
  const column = width / points.length;
  const y = (v: number) => ((hi - v) * plotHeight) / (hi - lo || 1) + 100;
  const zero = y(0);
  const x = (i: number) => column * (i + 0.5);
  const times = points.map((p, i) => itemTime(p.reveal_at_s, i, points.length, frame.durSec));
  const bar = props.chart_type === "bar";
  const barRadius =
    c.cardTreatment === "brutal_offset"
      ? 0
      : c.cardTreatment === "editorial_rule" || c.cardTreatment === "minimal_hairline"
        ? 2
        : 5;
  const barStroke =
    c.cardTreatment === "editorial_rule"
      ? c.line
      : c.cardTreatment === "brutal_offset"
        ? c.accentSecondary
        : undefined;
  return (
    <Stage style={props} frame={frame}>
      <Heading title={props.title} eyebrow={props.eyebrow} colors={c} />
      {props.subtitle && (
        <div
          style={{
            position: "absolute",
            top: 306,
            left: 138,
            width: width,
            color: c.secondary,
            fontSize: typeSize(props.subtitle, 29, width, 1),
          }}
        >
          {props.subtitle}
        </div>
      )}
      <div style={{ position: "absolute", left: 140, top: 358, width, height: 580 }}>
        <svg width={width} height="475" style={{ position: "absolute", overflow: "visible" }}>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <path
              key={t}
              d={`M0 ${100 + t * plotHeight}h${width}`}
              fill="none"
              stroke={c.line}
              strokeWidth="1"
              opacity={c.cardTreatment === "editorial_rule" ? ".24" : ".46"}
            />
          ))}
          <path d={`M0 ${zero}h${width}`} stroke={c.line} strokeWidth="2" />
          {points.map((p, i) => {
            const start = times[i];
            const grow = springOut(frame.tSec - start);
            const valueY = y(values[i]);
            const height = Math.abs(valueY - zero) * grow;
            const selected = i === props.highlight_index;
            const color = selected || props.highlight_index == null ? c.accent : c.line;
            if (bar)
              return (
                <g key={i}>
                  {c.cardTreatment === "editorial_rule" && height > 2 && (
                    <rect
                      x={x(i) - column * 0.26 + 5}
                      width={column * 0.52}
                      rx={barRadius}
                      y={(p.value >= 0 ? zero - height : zero) + 5}
                      height={height}
                      fill={c.line}
                      opacity={selected ? 0.9 : 0.35}
                    />
                  )}
                  {c.cardTreatment === "brutal_offset" && selected && height > 2 && (
                    <rect
                      x={x(i) - column * 0.26 + 6}
                      width={column * 0.52}
                      y={(p.value >= 0 ? zero - height : zero) + 6}
                      height={height}
                      fill={c.accentSecondary}
                    />
                  )}
                  <rect
                    x={x(i) - column * 0.26}
                    width={column * 0.52}
                    rx={barRadius}
                    y={p.value >= 0 ? zero - height : zero}
                    height={height}
                    fill={selected ? c.accent : props.highlight_index == null ? c.accent : c.cardTreatment === "editorial_rule" ? "#D6CFC0" : c.line}
                    stroke={selected ? barStroke : c.cardTreatment === "editorial_rule" ? c.line : undefined}
                    strokeWidth={barStroke ? 2 : undefined}
                  />
                </g>
              );
            const draw = easeInOutCubic(cueProgress(frame.tSec, start, 0.44));
            return (
              <g key={i}>
                {i > 0 && (
                  <path
                    d={`M${x(i - 1)} ${y(values[i - 1])}L${x(i)} ${valueY}`}
                    stroke={c.cardTreatment === "editorial_rule" ? c.accentSecondary : c.accent}
                    strokeWidth="5"
                    fill="none"
                    pathLength="1"
                    strokeDasharray="1"
                    strokeDashoffset={1 - draw}
                  />
                )}
                <circle
                  cx={x(i)}
                  cy={valueY}
                  r={(selected ? 13 : 8) * grow}
                  fill={selected ? c.accent : c.surface}
                  stroke={selected && c.cardTreatment === "editorial_rule" ? c.line : color}
                  strokeWidth={grow * 4}
                />
              </g>
            );
          })}
        </svg>
        {points.map((point, i) => {
          const value = point.display_value ?? `${point.value}${props.unit ?? ""}`;
          const selected = i === props.highlight_index;
          return (
            <React.Fragment key={i}>
              <div
                style={{
                  ...appear(frame.tSec, times[i] + 0.18),
                  position: "absolute",
                  left: i * column + 5,
                  width: column - 10,
                  bottom: 580 - y(values[i]) + 24,
                  textAlign: "center",
                  lineHeight: 1.1,
                  fontWeight: c.headingWeight,
                  fontSize: typeSize(value, 37, column - 16, 2),
                }}
              >
                <span
                  style={{
                    background: selected && c.cardTreatment === "editorial_rule" ? c.accent : c.surface,
                    color: selected
                      ? c.cardTreatment === "editorial_rule"
                        ? c.accentInk
                        : c.accentText
                      : c.ink,
                    border:
                      c.cardTreatment === "editorial_rule"
                        ? `1.5px solid ${c.line}`
                        : c.cardTreatment === "brutal_offset" && selected
                          ? `1.5px solid ${c.accent}`
                          : undefined,
                    borderRadius: c.cardTreatment === "brutal_offset" ? 2 : 6,
                    padding: "2px 8px",
                  }}
                >
                  {value}
                </span>
              </div>
              <div
                style={{
                  ...appear(frame.tSec, times[i]),
                  position: "absolute",
                  left: i * column + 5,
                  width: column - 10,
                  top: 463,
                  textAlign: "center",
                  lineHeight: 1.18,
                  fontWeight: selected ? 700 : 500,
                  color: selected ? c.ink : c.secondary,
                  fontSize: typeSize(point.label, 28, column - 12, 3),
                }}
              >
                {point.label}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </Stage>
  );
}

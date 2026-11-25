import React from "react";
import { DeviceFrame } from "../engine/DeviceFrame";
import {
  Stage,
  palette,
  type Frame,
  type StudioStyle,
  typeSize,
} from "./Stage";

interface Props extends StudioStyle {
  mode: "typing_cli" | "diff_highlight" | "command_palette";
  title?: string;
  lines: string[];
  prompt_prefix?: string;
  highlight_line?: number;
}

export function CodeTerminalBlock({
  props,
  frame,
}: {
  props: Props;
  frame: Frame;
}): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const light = c.tokens.theme === "light";
  const chars = props.lines.map((line) => Array.from(line));
  let remaining = Math.floor(
    chars.reduce((n, line) => n + line.length, 0) *
      Math.min(1, frame.tSec / (frame.durSec * 0.74)),
  );
  const paletteMode = props.mode === "command_palette";
  const fg = light ? "#202c35" : "#e9edf2";
  return (
    <Stage style={props} frame={frame}>
      <DeviceFrame
        variant="tablet"
        style={{
          position: "absolute",
          left: 280,
          top: 194,
          width: 1360,
          height: 692,
          padding: 3,
          borderRadius: 30,
        }}
      >
        <div
          style={{
            height: "100%",
            padding: "52px 70px",
            boxSizing: "border-box",
            background: light
              ? "#fafaf8"
              : "linear-gradient(135deg,#22262b,#111519)",
            color: fg,
          }}
        >
          <div
            style={{
              fontSize: 26,
              letterSpacing: ".05em",
              borderBottom: `1px solid ${light ? "#ddd" : "#484b50"}`,
              paddingBottom: 25,
              marginBottom: 30,
            }}
          >
            {props.title}
          </div>
          {chars.map((line, i) => {
            const visible =
              props.mode === "typing_cli"
                ? Math.max(0, Math.min(remaining, line.length))
                : line.length;
            const cursor =
              props.mode === "typing_cli" &&
              remaining >= 0 &&
              remaining < line.length;
            remaining -= line.length;
            const raw = props.lines[i];
            const selected =
              (props.highlight_line ?? (paletteMode ? 1 : 0)) === i + 1;
            const color = raw.startsWith("+")
              ? light
                ? "#236148"
                : "#a8ebc5"
              : raw.startsWith("-")
                ? light
                  ? "#972d42"
                  : "#ffabb6"
                : fg;
            return (
              <div
                key={i}
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: typeSize(raw, 39, 1150),
                  lineHeight: "56px",
                  color,
                  background: selected
                    ? light
                      ? "#dce7ed"
                      : "#36424d"
                    : undefined,
                  padding: "0 16px",
                  borderRadius: 7,
                  whiteSpace: "pre",
                }}
              >
                {visible > 0 &&
                  (paletteMode
                    ? "› "
                    : i === 0 && !raw.startsWith(props.prompt_prefix ?? "$")
                      ? (props.prompt_prefix ?? "$") + " "
                      : "") + line.slice(0, visible).join("")}
                {cursor && <span style={{ color: c.accent }}>▍</span>}
              </div>
            );
          })}
        </div>
      </DeviceFrame>
    </Stage>
  );
}

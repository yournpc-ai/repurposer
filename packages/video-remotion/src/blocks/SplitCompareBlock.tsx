import React from "react";
import { cueProgress, easeInOutCubic } from "../engine/math";
import {
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

interface Argument {
  text: string;
  reveal_at_s?: number;
}
interface CompareProps extends StudioStyle {
  eyebrow?: string;
  title?: string;
  left_heading: string;
  right_heading: string;
  left_items: Argument[];
  right_items: Argument[];
  dim_left?: boolean;
}

export function SplitCompareBlock({
  props,
  frame,
}: {
  props: CompareProps;
  frame: Frame;
}): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const sides = [
    { heading: props.left_heading, items: props.left_items },
    { heading: props.right_heading, items: props.right_items },
  ];
  return (
    <Stage style={props} frame={frame}>
      <Heading title={props.title} eyebrow={props.eyebrow} colors={c} />
      <div style={{ position: "absolute", inset: "340px 132px 138px", display: "flex", gap: 76 }}>
        <i
          style={{
            position: "absolute",
            left: "50%",
            top: 0,
            width: 2,
            height: `${100 * easeInOutCubic(cueProgress(frame.tSec, 0, 0.75))}%`,
            background: c.line,
          }}
        />
        {sides.map(({ heading, items }, side) => (
          <article
            key={side}
            style={{
              ...cardFace(c, { selected: Boolean(side) }),
              padding: "34px 40px",
              flex: 1,
              minWidth: 0,
              display: "flex",
              flexDirection: "column",
              borderTop: `4px solid ${side ? c.accent : c.line}`,
            }}
          >
            <strong
              style={{
                fontWeight: c.headingWeight,
                color: side ? c.accentText : c.ink,
                lineHeight: 1.12,
                fontSize: typeSize(heading, 46, 692, 2),
                marginBottom: 22,
              }}
            >
              {heading}
            </strong>
            {items.map((item, i) => {
              const start = itemTime(item.reveal_at_s, i, items.length, frame.durSec);
              const opposed = props.right_items[i];
              const strike =
                opposed && !side && props.dim_left !== false
                  ? easeInOutCubic(
                      cueProgress(
                        frame.tSec,
                        itemTime(opposed.reveal_at_s, i, props.right_items.length, frame.durSec) + 0.25,
                        0.45,
                      ),
                    )
                  : 0;
              const strikeColor = `color-mix(in srgb, ${c.line} 45%, ${c.surface})`;
              return (
                <div
                  key={i}
                  style={{
                    ...appear(frame.tSec, start),
                    borderTop: `1px solid ${c.line}`,
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                  }}
                >
                  <i
                    style={{
                      width: side ? 10 : 16,
                      height: side ? 10 : 2,
                      flexShrink: 0,
                      borderRadius: side ? 3 : 0,
                      background: side ? c.accent : c.line,
                    }}
                  />
                  <span
                    style={{
                      fontSize: typeSize(item.text, 33, 640, 2),
                      lineHeight: 1.25,
                      color: side ? c.ink : c.secondary,
                      backgroundImage: `linear-gradient(${strikeColor}, ${strikeColor})`,
                      backgroundRepeat: "no-repeat",
                      backgroundPosition: "left center",
                      backgroundSize: `${strike * 100}% 1px`,
                    }}
                  >
                    {item.text}
                  </span>
                </div>
              );
            })}
          </article>
        ))}
      </div>
    </Stage>
  );
}

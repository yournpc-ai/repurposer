import React from "react";
import {
  Heading,
  activeFocusStyle,
  appear,
  cardFace,
  itemTime,
  palette,
  Stage,
  typeSize,
  type Frame,
  type StudioStyle,
} from "./Stage";

interface Card {
  tag?: string;
  title: string;
  detail: string;
  reveal_at_s?: number;
}
interface BentoProps extends StudioStyle {
  eyebrow?: string;
  title?: string;
  cards: Card[];
  highlight_index?: number;
}

export function BentoFeaturesBlock({ props, frame }: { props: BentoProps; frame: Frame }): React.JSX.Element {
  const c = palette(props, frame.compositionStyle);
  const three = props.cards.length === 3;
  const times = props.cards.map((item, i) => itemTime(item.reveal_at_s, i, props.cards.length, frame.durSec));
  return (
    <Stage style={props} frame={frame}>
      <Heading eyebrow={props.eyebrow} title={props.title} colors={c} />
      <div
        style={{
          position: "absolute",
          inset: "322px 132px 164px",
          display: "grid",
          gap: 22,
          gridTemplateColumns: three ? "1.12fr 1fr" : "1fr 1fr",
          gridTemplateRows: "1fr 1fr",
        }}
      >
        {props.cards.map((card, i) => {
          const lead = three && i === 0;
          const selected = props.highlight_index === i;
          return (
            <article
              key={i}
              style={{
                ...cardFace(c, { selected }),
                ...appear(frame.tSec, times[i], activeFocusStyle(frame.tSec, times, i, frame.durSec)),
                gridRow: lead ? "span 2" : undefined,
                padding: lead ? 48 : "24px 38px",
                display: "flex",
                flexDirection: "column",
                justifyContent: lead ? "space-between" : "center",
                gap: 12,
              }}
            >
              {(card.tag || lead) && (
                <div
                  style={{
                    display: "flex",
                    gap: 14,
                    alignItems: "center",
                    color: selected ? c.accentText : c.secondary,
                    fontWeight: selected ? 700 : 600,
                    fontSize: 22,
                    letterSpacing: ".035em",
                  }}
                >
                  <i style={{ width: 19, height: 5, background: c.accent }} />
                  {card.tag}
                </div>
              )}
              <div>
                <strong
                  style={{
                    display: "block",
                    fontWeight: c.headingWeight,
                    letterSpacing: "-.025em",
                    lineHeight: 1.13,
                    fontSize: typeSize(card.title, lead ? 70 : 43, 685, lead ? 3 : 2),
                  }}
                >
                  {card.title}
                </strong>
                <div
                  style={{
                    color: c.secondary,
                    marginTop: 13,
                    fontSize: typeSize(card.detail, lead ? 32 : 27, 685, lead ? 4 : 2),
                  }}
                >
                  {card.detail}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </Stage>
  );
}

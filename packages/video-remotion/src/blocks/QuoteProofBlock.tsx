import React from "react";
import { cueProgress, easeInOutCubic, easeOutCubic } from "../engine/math";
import { appear, palette, Stage, typeSize, type Frame, type StudioStyle } from "./Stage";

interface QuoteProps extends StudioStyle {
  quote: string;
  author: string;
  role_or_source?: string;
  verification_badge?: string;
  highlight_phrase?: string;
  highlight_at_s?: number;
}

// Break at the marked phrase first so a replacement can highlight part of a word.
// Preserve original whitespace; CJK glyphs get their own reveal beats.
function runs(text: string): string[] {
  return (
    text.match(
      /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]|[^\s\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]+|\s+/gu,
    ) ?? []
  );
}

export function QuoteProofBlock({ props, frame }: { props: QuoteProps; frame: Frame }): React.JSX.Element {
  const c = palette(props);
  const phrase = props.highlight_phrase ?? "";
  const at = phrase ? props.quote.indexOf(phrase) : -1;
  const pieces =
    at < 0 ? [props.quote] : [props.quote.slice(0, at), phrase, props.quote.slice(at + phrase.length)];
  const tokens = pieces.flatMap((part, i) =>
    runs(part).map((text) => ({ text, marked: at >= 0 && i === 1 })),
  );
  const length = tokens.filter((token) => token.text.trim()).length;
  const sweep = easeInOutCubic(cueProgress(frame.tSec, props.highlight_at_s ?? frame.durSec * 0.5, 0.55));
  const creditAt = frame.durSec * 0.62;
  let word = 0;
  return (
    <Stage style={props} frame={frame}>
      <div
        style={{
          position: "absolute",
          inset: "102px 206px 132px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <svg width="92" height="69" viewBox="0 0 92 69" fill={c.accent} aria-hidden>
          <path d="M0 69V42Q0 15 30 1l6 9Q16 22 16 37h18v32ZM48 69V42Q48 15 78 1l6 9Q64 22 64 37h18v32Z" />
        </svg>
        <blockquote
          style={{
            margin: "38px 0 40px",
            fontSize: typeSize(props.quote, 85, 1470, 5),
            fontWeight: 700,
            lineHeight: 1.2,
            letterSpacing: "-.026em",
            whiteSpace: "normal",
            textWrap: "balance",
          }}
        >
          {tokens.map(({ text, marked }, i) => {
            if (!text.trim()) return text;
            const start = 0.12 + frame.durSec * 0.42 * (word++ / Math.max(1, length - 1));
            const p = easeOutCubic(cueProgress(frame.tSec, start, 0.34));
            return (
              <span
                key={i}
                style={{
                  display: "inline-block",
                  maxWidth: "100%",
                  verticalAlign: "bottom",
                  clipPath: `inset(${100 * (1 - p)}% 0 0 0)`,
                  transform: `translateY(${8 * (1 - p)}px)`,
                  backgroundImage: marked ? `linear-gradient(${c.accent},${c.accent})` : undefined,
                  backgroundPosition: "left bottom",
                  backgroundRepeat: "no-repeat",
                  backgroundSize: `${100 * sweep}% 3px`,
                }}
              >
                {text}
              </span>
            );
          })}
        </blockquote>
        <div
          style={{
            width: `${100 * easeInOutCubic(cueProgress(frame.tSec, creditAt - 0.24, 0.6))}%`,
            height: 2,
            background: c.line,
          }}
        />
        <footer
          style={{
            ...appear(frame.tSec, creditAt),
            display: "flex",
            gap: 28,
            alignItems: "center",
            marginTop: 26,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong style={{ fontSize: typeSize(props.author, 38, 980, 2) }}>{props.author}</strong>
            {props.role_or_source && (
              <div
                style={{
                  marginTop: 7,
                  color: c.secondary,
                  fontSize: typeSize(props.role_or_source, 26, 980, 2),
                }}
              >
                {props.role_or_source}
              </div>
            )}
          </div>
          {props.verification_badge && (
            <div
              style={{
                background: c.tint,
                border: `1px solid ${c.line}`,
                borderRadius: 30,
                maxWidth: 380,
                padding: "10px 22px",
                fontSize: typeSize(props.verification_badge, 23, 370, 2),
              }}
            >
              {props.verification_badge}
            </div>
          )}
        </footer>
      </div>
    </Stage>
  );
}

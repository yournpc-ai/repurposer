import React from "react";
import { AbsoluteFill, OffthreadVideo, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionCue, ClipSpec } from "./types";
import { COMPOSITION_FPS, keptSegments } from "./types";

/**
 * The single source of truth for how a clip looks — consumed by BOTH the
 * editor's <Player> (preview) and the render service (export). Rendering both
 * from this one component is what makes "preview == final video" structural
 * rather than something we have to keep in sync by hand.
 *
 * MVP scope: renders the FIRST kept segment (generation currently emits one).
 * Multi-segment concat (after transcript "delete sentence" creates gaps) is a
 * documented extension — see docs/VIDEO_EDITOR.md.
 */

const WORDS_PER_LINE = 7;

function groupLines(cues: CaptionCue[]): CaptionCue[][] {
  const lines: CaptionCue[][] = [];
  for (let i = 0; i < cues.length; i += WORDS_PER_LINE) {
    lines.push(cues.slice(i, i + WORDS_PER_LINE));
  }
  return lines;
}

export const Clip: React.FC<{ spec: ClipSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seg = keptSegments(spec)[0];

  const segStart = seg?.start ?? 0;
  const segEnd = seg?.end ?? 0;
  const sourceTime = segStart + frame / (fps || COMPOSITION_FPS);
  // Render the source only when present — keeps the composition valid for
  // text/audio-only or preview-before-source cases (renders captions on black).
  const hasSource = Boolean(seg && spec.source.url);

  const lines = groupLines(spec.caption_track);
  const activeLine =
    lines.find((line) => sourceTime >= line[0].start && sourceTime <= line[line.length - 1].end) ??
    lines.find((line) => sourceTime < line[0].start) ??
    [];

  const accent = spec.caption_style_preset === "karaoke-highlight" ? "#facc15" : "#ffffff";

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {hasSource ? (
        <AbsoluteFill
          style={{
            // Reframe via transform (object-position is unsupported on the
            // future client-render path — keep to the CSS ∩ libass subset).
            transform: `scale(${spec.crop.scale}) translate(${(0.5 - spec.crop.x) * 100}%, ${(0.5 - spec.crop.y) * 100}%)`,
          }}
        >
          <OffthreadVideo
            src={spec.source.url}
            startFrom={Math.round(segStart * (fps || COMPOSITION_FPS))}
            endAt={Math.round(segEnd * (fps || COMPOSITION_FPS))}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </AbsoluteFill>
      ) : null}

      {spec.title.enabled && spec.title.text ? (
        <div
          style={{
            position: "absolute",
            top: 80,
            left: 48,
            right: 48,
            textAlign: "center",
            color: "#ffffff",
            fontFamily: "sans-serif",
            fontSize: 58,
            fontWeight: 800,
            lineHeight: 1.15,
            textShadow: "0 2px 12px rgba(0,0,0,0.7)",
          }}
        >
          {spec.title.text}
        </div>
      ) : null}

      {activeLine.length > 0 ? (
        <div
          style={{
            position: "absolute",
            bottom: 220,
            left: 60,
            right: 60,
            textAlign: "center",
            fontFamily: "sans-serif",
            fontSize: 56,
            fontWeight: 700,
            lineHeight: 1.25,
            color: "#ffffff",
            WebkitTextStroke: "2px rgba(0,0,0,0.55)",
            textShadow: "0 2px 10px rgba(0,0,0,0.6)",
          }}
        >
          {activeLine.map((cue, i) => {
            const isActive = sourceTime >= cue.start && sourceTime < cue.end;
            return (
              <span key={i} style={{ color: isActive ? accent : "#ffffff" }}>
                {cue.text}
                {i < activeLine.length - 1 ? " " : ""}
              </span>
            );
          })}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

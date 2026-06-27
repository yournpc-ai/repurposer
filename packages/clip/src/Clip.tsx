import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Series,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CaptionCue, ClipSpec } from "./types";
import { COMPOSITION_FPS, keptSegments } from "./types";
import { fontFamilyFor } from "./fonts";

/**
 * The single source of truth for how a clip looks — consumed by BOTH the
 * editor's <Player> (preview) and the render service (export). Rendering both
 * from this one component is what makes "preview == final video" structural.
 *
 * Multi-segment: kept (non-hidden) segments are concatenated via <Series>
 * (transcript "delete sentence" splits a segment into kept + hidden + kept).
 * Captions are looked up by SOURCE time, which is remapped from the cut output
 * timeline; the editor removes a deleted range's cues from caption_track too.
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
  const fpsv = fps || COMPOSITION_FPS;

  // Concatenated output timeline of kept segments (gaps for deleted ranges cut).
  const kept = keptSegments(spec);
  let acc = 0;
  const timeline = kept.map((seg) => {
    const dur = Math.max(0, seg.end - seg.start);
    const entry = { seg, outStart: acc, dur };
    acc += dur;
    return entry;
  });

  const outputTime = frame / fpsv;
  const current =
    timeline.find((t) => outputTime >= t.outStart && outputTime < t.outStart + t.dur) ??
    timeline[timeline.length - 1];
  const sourceTime = current ? current.seg.start + (outputTime - current.outStart) : 0;
  const hasSource = Boolean(spec.source.url && timeline.length > 0);

  const lines = groupLines(spec.caption_track);
  const activeLine =
    lines.find((line) => sourceTime >= line[0].start && sourceTime <= line[line.length - 1].end) ??
    lines.find((line) => sourceTime < line[0].start) ??
    [];

  // Brand (baked into the spec by the API; absent -> default look).
  const brand = spec.brand ?? undefined;
  const captionColor = brand?.caption_color || "#ffffff";
  const captionSize = brand?.caption_size || 56;
  const captionFont = fontFamilyFor(brand?.caption_font);
  const objectFit = brand?.fill_mode === "fit" ? "contain" : "cover";
  const accent =
    spec.caption_style_preset === "karaoke-highlight" ? "#facc15" : captionColor;

  // Background music: play the baked track when enabled, looped to fill the clip.
  const music = spec.music;
  const musicUrl = music?.enabled ? music.url ?? null : null;
  const musicVolume = Math.min(1, Math.pow(10, (music?.gain_db ?? -18) / 20));

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {musicUrl ? <Audio src={musicUrl} volume={musicVolume} loop /> : null}

      {hasSource ? (
        <AbsoluteFill
          style={{
            // Reframe via transform (object-position is unsupported on the
            // future client-render path — keep to the CSS ∩ libass subset).
            transform: `scale(${spec.crop.scale}) translate(${(0.5 - spec.crop.x) * 100}%, ${(0.5 - spec.crop.y) * 100}%)`,
          }}
        >
          <Series>
            {timeline.map((t, i) => (
              <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                <OffthreadVideo
                  src={spec.source.url}
                  startFrom={Math.round(t.seg.start * fpsv)}
                  endAt={Math.round(t.seg.end * fpsv)}
                  style={{ width: "100%", height: "100%", objectFit }}
                />
              </Series.Sequence>
            ))}
          </Series>
        </AbsoluteFill>
      ) : null}

      {brand?.logo_url ? (
        <Img
          src={brand.logo_url}
          style={{
            position: "absolute",
            top: 40,
            right: 40,
            height: 72,
            width: "auto",
            objectFit: "contain",
            filter: "drop-shadow(0 2px 8px rgba(0,0,0,0.5))",
          }}
        />
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
            fontFamily: captionFont,
            fontSize: captionSize,
            fontWeight: 700,
            lineHeight: 1.25,
            color: captionColor,
            WebkitTextStroke: "2px rgba(0,0,0,0.55)",
            textShadow: "0 2px 10px rgba(0,0,0,0.6)",
          }}
        >
          {activeLine.map((cue, i) => {
            const isActive = sourceTime >= cue.start && sourceTime < cue.end;
            return (
              <span key={i} style={{ color: isActive ? accent : captionColor }}>
                {cue.text}
                {i < activeLine.length - 1 ? " " : ""}
              </span>
            );
          })}
        </div>
      ) : null}

      {brand?.cta ? (
        <div
          style={{
            position: "absolute",
            bottom: 96,
            left: 60,
            right: 60,
            textAlign: "center",
            fontFamily: "sans-serif",
            fontSize: 34,
            fontWeight: 700,
            color: "#ffffff",
            textShadow: "0 2px 10px rgba(0,0,0,0.7)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              padding: "10px 28px",
              borderRadius: 9999,
              backgroundColor: "rgba(0,0,0,0.55)",
            }}
          >
            {brand.cta}
          </span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

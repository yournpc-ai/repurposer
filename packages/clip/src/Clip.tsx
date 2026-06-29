import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  Series,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CaptionCue, ClipSpec, Point } from "./types";
import {
  COMPOSITION_FPS,
  introSeconds,
  keptSegments,
  outroSeconds,
  videoDurationSeconds,
} from "./types";
import { fontFamilyFor } from "./fonts";

/** Normalized center point -> absolute-position style (CSS translate / libass \pos). */
function pointStyle(p: Point | null | undefined, fallback: Point): React.CSSProperties {
  const pt = p ?? fallback;
  return {
    position: "absolute",
    left: `${pt.x * 100}%`,
    top: `${pt.y * 100}%`,
    transform: "translate(-50%, -50%)",
    width: "84%",
  };
}

const DEFAULT_TITLE_POS: Point = { x: 0.5, y: 0.12 };
const DEFAULT_CAPTION_POS: Point = { x: 0.5, y: 0.84 };
const DEFAULT_CTA_POS: Point = { x: 0.5, y: 0.92 };

/**
 * The single source of truth for how a clip looks — consumed by BOTH the
 * editor's <Player> (preview) and the render service (export). Rendering both
 * from this one component is what makes "preview == final video" structural.
 *
 * Output timeline: [brand intro card] [kept video segments] [brand outro card].
 * Kept (non-hidden) segments are concatenated via <Series> (transcript "delete
 * sentence" splits a segment into kept + hidden + kept) and offset past the
 * intro by a <Sequence>. Captions are looked up by SOURCE time, remapped from
 * the cut output timeline (minus the intro offset); the editor removes a deleted
 * range's cues from caption_track too. No brand intro/outro -> zero offset.
 */

const WORDS_PER_LINE = 7;

function groupLines(cues: CaptionCue[]): CaptionCue[][] {
  const lines: CaptionCue[][] = [];
  for (let i = 0; i < cues.length; i += WORDS_PER_LINE) {
    lines.push(cues.slice(i, i + WORDS_PER_LINE));
  }
  return lines;
}

/** Split `total` frames into `count` even chunks (last chunk absorbs remainder). */
function splitFrames(count: number, total: number): number[] {
  const base = Math.max(1, Math.floor(total / count));
  return Array.from({ length: count }, (_, i) =>
    i === count - 1 ? Math.max(1, total - base * (count - 1)) : base,
  );
}

export const Clip: React.FC<{ spec: ClipSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fpsv = fps || COMPOSITION_FPS;

  // Brand (baked into the spec by the API; absent -> default look).
  const brand = spec.brand ?? undefined;
  const captionColor = brand?.caption_color || "#ffffff";
  const captionSize = brand?.caption_size || 56;
  const captionFont = fontFamilyFor(brand?.caption_font);
  const objectFit = brand?.fill_mode === "fit" ? "contain" : "cover";
  const accent =
    spec.caption_style_preset === "karaoke-highlight" ? "#facc15" : captionColor;

  // Output timeline windows: intro card | video | outro card.
  const introDur = introSeconds(spec);
  const videoTotal = videoDurationSeconds(spec);
  const outroDur = outroSeconds(spec);
  const introFrames = Math.round(introDur * fpsv);
  const videoFrames = Math.max(1, Math.round(videoTotal * fpsv));

  const outputTime = frame / fpsv;
  const localOutput = outputTime - introDur; // time within the video portion
  const inVideo = localOutput >= 0 && localOutput < videoTotal;
  const inIntro = introDur > 0 && outputTime < introDur;
  const inOutro = outroDur > 0 && outputTime >= introDur + videoTotal;

  // Concatenated video timeline of kept segments (local time; gaps for cuts).
  const kept = keptSegments(spec);
  let acc = 0;
  const timeline = kept.map((seg) => {
    const dur = Math.max(0, seg.end - seg.start);
    const entry = { seg, outStart: acc, dur };
    acc += dur;
    return entry;
  });

  const current =
    timeline.find((t) => localOutput >= t.outStart && localOutput < t.outStart + t.dur) ??
    timeline[timeline.length - 1];
  const sourceTime = current ? current.seg.start + (localOutput - current.outStart) : 0;
  const hasSource = Boolean(spec.source.url && timeline.length > 0);

  // "stills" audiogram: image[s] backing + optional speech audio. The visual is
  // an even hard-cut slideshow of the images (1 -> full-frame); empty -> the
  // outer black fill shows through. Audio (when present) is sliced to the kept
  // segments exactly like video, so caption mapping is unchanged.
  const isStills = spec.source.kind === "stills";
  const images = spec.source.image_urls ?? [];
  const audioUrl = spec.source.url || null;
  const imageDurs = images.length > 0 ? splitFrames(images.length, videoFrames) : [];

  const lines = groupLines(spec.caption_track);
  const activeLine =
    lines.find((line) => sourceTime >= line[0].start && sourceTime <= line[line.length - 1].end) ??
    lines.find((line) => sourceTime < line[0].start) ??
    [];

  // Background music: play the baked track when enabled, looped to fill the clip.
  const music = spec.music;
  const musicUrl = music?.enabled ? music.url ?? null : null;
  const musicVolume = Math.min(1, Math.pow(10, (music?.gain_db ?? -18) / 20));

  // Cloned-voice dub: when enabled, it REPLACES the source's original audio
  // (the video is muted / the stills speech track is skipped) and plays across
  // the video portion. Rough overlay — no lip-sync (see docs/VIDEO_EDITOR.md).
  const dubUrl = spec.dub?.enabled ? spec.dub.url ?? null : null;
  const dubVolume = Math.min(1, Math.pow(10, (spec.dub?.gain_db ?? 0) / 20));

  const cardText = inIntro ? brand?.intro_text : inOutro ? brand?.outro_text : null;

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {musicUrl ? <Audio src={musicUrl} volume={musicVolume} loop /> : null}
      {dubUrl ? (
        <Sequence from={introFrames} durationInFrames={videoFrames} layout="none">
          <Audio src={dubUrl} volume={dubVolume} />
        </Sequence>
      ) : null}

      {isStills ? (
        <Sequence from={introFrames} durationInFrames={videoFrames} layout="none">
          {images.length > 0 ? (
            <AbsoluteFill>
              <Series>
                {images.map((src, i) => (
                  <Series.Sequence key={i} durationInFrames={imageDurs[i]}>
                    <Img src={src} style={{ width: "100%", height: "100%", objectFit }} />
                  </Series.Sequence>
                ))}
              </Series>
            </AbsoluteFill>
          ) : null}
          {!dubUrl && audioUrl && timeline.length > 0 ? (
            <Series>
              {timeline.map((t, i) => (
                <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                  <Audio
                    src={audioUrl}
                    startFrom={Math.round(t.seg.start * fpsv)}
                    endAt={Math.round(t.seg.end * fpsv)}
                  />
                </Series.Sequence>
              ))}
            </Series>
          ) : null}
        </Sequence>
      ) : hasSource ? (
        <Sequence from={introFrames} durationInFrames={videoFrames} layout="none">
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
                    muted={Boolean(dubUrl)}
                    startFrom={Math.round(t.seg.start * fpsv)}
                    endAt={Math.round(t.seg.end * fpsv)}
                    style={{ width: "100%", height: "100%", objectFit }}
                  />
                </Series.Sequence>
              ))}
            </Series>
          </AbsoluteFill>
        </Sequence>
      ) : null}

      {cardText ? (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 96 }}>
          <div
            style={{
              textAlign: "center",
              color: "#ffffff",
              fontFamily: captionFont,
              fontSize: 68,
              fontWeight: 700,
              lineHeight: 1.2,
              textShadow: "0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {cardText}
          </div>
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

      {inVideo && spec.title.enabled && spec.title.text ? (
        <div
          style={{
            textAlign: "center",
            color: "#ffffff",
            fontFamily: "sans-serif",
            fontSize: spec.title.size || 58,
            fontWeight: 800,
            lineHeight: 1.15,
            textShadow: "0 2px 12px rgba(0,0,0,0.7)",
            // Fade in over ~0.4s once the video portion starts (libass \fad).
            opacity: interpolate(frame, [introFrames, introFrames + 12], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            ...pointStyle(spec.title.position, DEFAULT_TITLE_POS),
          }}
        >
          {spec.title.text}
        </div>
      ) : null}

      {inVideo && activeLine.length > 0 ? (
        <div
          style={{
            textAlign: "center",
            fontFamily: captionFont,
            fontSize: captionSize,
            fontWeight: 700,
            lineHeight: 1.25,
            color: captionColor,
            WebkitTextStroke: "2px rgba(0,0,0,0.55)",
            textShadow: "0 2px 10px rgba(0,0,0,0.6)",
            ...pointStyle(spec.caption_position, DEFAULT_CAPTION_POS),
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

      {inVideo && brand?.cta ? (
        <div
          style={{
            textAlign: "center",
            fontFamily: "sans-serif",
            fontSize: 34,
            fontWeight: 700,
            color: "#ffffff",
            textShadow: "0 2px 10px rgba(0,0,0,0.7)",
            ...pointStyle(brand.cta_position, DEFAULT_CTA_POS),
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

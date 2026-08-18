import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  continueRender,
  delayRender,
  Easing,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  Series,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { getVideoMetadata } from "@remotion/media-utils";
import type { CaptionCue, ClipLayer, ClipSpec, IntroOutroCard, Point, SegmentTransition } from "./types";
import {
  COMPOSITION_FPS,
  introSeconds,
  outputTimeAtSourceTime,
  outroSeconds,
  projectLayers,
  sampleCrop,
  sourceTimeAtOutputTime,
  videoDurationSeconds,
  videoTimeline,
} from "./types";
import { captionPreset, type CaptionEntrance } from "./captions";
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
/** stack layout default: the container's TOP edge anchors here and lines
 * flow downward (caption_position overrides the anchor the same way). */
const DEFAULT_STACK_POS: Point = { x: 0.5, y: 0.14 };

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

/**
 * Per-line caption entrance animation — the `entrance` primitive from the
 * caption catalog (captions.ts); `none` renders statically. Returns a
 * transform *suffix* rather than a full `transform` because the caller
 * already centers the box via `pointStyle()`'s `translate(-50%, -50%)`; the
 * two compose into one `transform` string. Every value maps onto a single
 * opacity/transform pair a future libass renderer can express with `\fad` +
 * `\t(\fscx,\fscy)` or `\move` (the catalog's libass mapping gate).
 */
function captionEntrance(
  entrance: CaptionEntrance,
  frame: number,
  revealFrame: number,
): { opacity: number; transformSuffix: string } {
  if (entrance === "fade-in") {
    const opacity = interpolate(frame, [revealFrame, revealFrame + 6], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return { opacity, transformSuffix: "" };
  }
  if (entrance === "pop-in") {
    const t = interpolate(frame, [revealFrame, revealFrame + 8], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.back(1.7)),
    });
    return { opacity: Math.min(1, t + 0.4), transformSuffix: `scale(${0.85 + 0.15 * t})` };
  }
  if (entrance === "slide-up") {
    const t = interpolate(frame, [revealFrame, revealFrame + 7], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.quad),
    });
    return { opacity: t, transformSuffix: `translateY(${(1 - t) * 14}px)` };
  }
  return { opacity: 1, transformSuffix: "" };
}

/**
 * An intro/outro brand card: text, image, or a short video, filling the fixed
 * INTRO_SECONDS/OUTRO_SECONDS window. Image/video are simply cut at the
 * window edge if longer — no per-card duration editing (see docs/VIDEO_EDITOR.md).
 */
function IntroOutroCardView({
  card,
  fontFamily,
}: {
  card: IntroOutroCard;
  fontFamily: string;
}) {
  // Same height-scaling rule as captions/title: 68 is the reference size on
  // the 1920-tall vertical canvas, not a fixed px on every frame.
  const { height } = useVideoConfig();
  if (card.kind === "image" && card.media_url) {
    return (
      <AbsoluteFill>
        <Img
          src={card.media_url}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </AbsoluteFill>
    );
  }
  if (card.kind === "video" && card.media_url) {
    return (
      <AbsoluteFill>
        <OffthreadVideo
          src={card.media_url}
          muted
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 96 }}>
      <div
        style={{
          textAlign: "center",
          color: "#ffffff",
          fontFamily,
          fontSize: Math.round(68 * (height / 1920)),
          fontWeight: 700,
          lineHeight: 1.2,
          textShadow: "0 2px 12px rgba(0,0,0,0.6)",
        }}
      >
        {card.text}
      </div>
    </AbsoluteFill>
  );
}

/**
 * A layer-track item (ADR-044): one render branch by MEDIA type
 * (video/image/text) — the layer `kind` is authoring/check metadata, the
 * renderer never branches on it. Position comes from the layer's rect;
 * the output window was projected from its anchor (projectLayers).
 */
function LayerView({ layer, fontFamily }: { layer: ClipLayer; fontFamily: string }) {
  const { height } = useVideoConfig();
  const media = layer.media;
  const style: React.CSSProperties = {
    position: "absolute",
    left: `${layer.rect.x * 100}%`,
    top: `${layer.rect.y * 100}%`,
    width: `${layer.rect.w * 100}%`,
    height: `${layer.rect.h * 100}%`,
  };
  if (media?.kind === "video" && media.url) {
    return <OffthreadVideo src={media.url} style={{ ...style, objectFit: "cover" }} />;
  }
  if (media?.kind === "image" && media.url) {
    return <Img src={media.url} style={{ ...style, objectFit: "cover" }} />;
  }
  if (media?.kind === "text" && media.text) {
    return (
      <div
        style={{
          ...style,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
          color: "#ffffff",
          fontFamily,
          fontSize: Math.round(52 * (height / 1920)),
          fontWeight: 700,
          lineHeight: 1.25,
          WebkitTextStroke: "2px rgba(0,0,0,0.55)",
          textShadow: "0 2px 10px rgba(0,0,0,0.6)",
        }}
      >
        {media.text}
      </div>
    );
  }
  return null;
}

/**
 * Entry-edge transition veil (fade = from black, dip = white flash): a
 * single-sided overlay on the incoming segment's first frames — no timeline
 * time is consumed (two-sided xfade mechanics are the L3 gallery, banned).
 * Sits above the main media, below layers/title/captions.
 */
const TRANSITION_FRAMES: Record<Exclude<SegmentTransition, "none">, number> = {
  fade: 12, // ~0.4s @30fps
  dip: 8, // ~0.27s white flash
};

function TransitionVeil({ kind }: { kind: Exclude<SegmentTransition, "none"> }) {
  const local = useCurrentFrame(); // Sequence-relative
  const frames = TRANSITION_FRAMES[kind];
  const opacity = interpolate(local, [0, frames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: kind === "dip" ? "#ffffff" : "#000000", opacity }} />
  );
}

export const Clip: React.FC<{ spec: ClipSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const fpsv = fps || COMPOSITION_FPS;

  // Crop data track rendering needs the SOURCE pixel dims (the window math
  // positions the video explicitly). The track can ARRIVE without a remount
  // (a reframe morph updates the Player's inputProps in place), so the delay
  // handle is armed at render time the moment a track is present and dims
  // are unresolved — never frozen in an initial useState.
  const hasCropTrack = Boolean(spec.crop_track?.length);
  const [srcDims, setSrcDims] = useState<{ width: number; height: number } | null>(null);
  const [dimsHandle, setDimsHandle] = useState<number | null>(null);
  if (hasCropTrack && srcDims === null && dimsHandle === null) {
    setDimsHandle(delayRender("crop_track: resolving source dims"));
  }
  useEffect(() => {
    if (dimsHandle === null || srcDims !== null) return;
    let cancelled = false;
    getVideoMetadata(spec.source.url)
      .then((m) => {
        if (!cancelled) setSrcDims({ width: m.width, height: m.height });
      })
      .catch(() => undefined) // fall through to the static-crop path
      .finally(() => continueRender(dimsHandle));
    return () => {
      cancelled = true;
    };
  }, [dimsHandle, srcDims, spec.source.url]);

  // Brand (baked into the spec by the API; absent -> default look).
  const brand = spec.brand ?? undefined;
  const captionColor = brand?.caption_color || "#ffffff";
  // Dimension-derived, never a fixed px (2026-08-14 ruling): brand
  // caption_size is the REFERENCE size on the 1080×1920 vertical canvas and
  // scales with frame height — 68 default → 9:16 keeps 68, 1:1/16:9 get 38
  // (≈3.5% of height, the TikTok/CapCut/YouTube caption norm across aspects).
  // The 84% caption width is the same rule horizontally: 8% side margins
  // scale with frame width by construction.
  const captionSize = Math.round((brand?.caption_size || 68) * (height / 1920));
  const captionFont = fontFamilyFor(brand?.caption_font);
  const objectFit = brand?.fill_mode === "fit" ? "contain" : "cover";
  // Caption style = catalog lookup (captions.ts), never a per-id branch.
  const preset = captionPreset(spec.caption_style_preset);
  const accent = preset.wordHighlight ? "#facc15" : captionColor;

  // Output timeline windows: intro card | video | outro card.
  const introDur = introSeconds(spec);
  const videoTotal = videoDurationSeconds(spec);
  const outroDur = outroSeconds(spec);
  const introFrames = Math.round(introDur * fpsv);
  const videoFrames = Math.max(1, Math.round(videoTotal * fpsv));
  const outroFrames = Math.round(outroDur * fpsv);

  const outputTime = frame / fpsv;
  const localOutput = outputTime - introDur; // time within the video portion
  const inVideo = localOutput >= 0 && localOutput < videoTotal;

  // Concatenated video timeline of kept segments (video-local output clock) —
  // the lane projection is a compile artifact (存法 C), computed by the single
  // home in types.ts, never persisted.
  const timeline = videoTimeline(spec);

  const current =
    timeline.find((t) => localOutput >= t.outStart && localOutput < t.outStart + t.dur) ??
    timeline[timeline.length - 1];
  const mappedSource = sourceTimeAtOutputTime(spec, outputTime);
  const sourceTime =
    mappedSource ??
    (current
      ? current.seg.start + Math.min(Math.max(0, localOutput - current.outStart), current.dur)
      : 0);
  // Crop data track (ADR-045): the framing sampled at this source second.
  // Outside the video portion the video is hidden anyway — hold the static crop.
  const cropNow = mappedSource === null ? spec.crop : sampleCrop(spec, mappedSource);
  // Hetero main-track splice (切 op, ADR-044): a segment carrying its own
  // asset_id/url plays from its donor source — its [start,end] offsets live in
  // the DONOR's timeline, so the main source's captions must not match it.
  const onMainSource = Boolean(current && !current.seg.asset_id && !current.seg.url);
  const hasSource = Boolean(
    timeline.length > 0 && (spec.source.url || timeline.some((t) => t.seg.url)),
  );

  // "stills" audiogram: image[s] backing + optional speech audio. The visual is
  // an even hard-cut slideshow of the images (1 -> full-frame); empty -> the
  // outer black fill shows through. Audio (when present) is sliced to the kept
  // segments exactly like video, so caption mapping is unchanged.
  const isStills = spec.source.kind === "stills";
  const images = spec.source.image_urls ?? [];
  const audioUrl = spec.source.url || null;
  const imageDurs = images.length > 0 ? splitFrames(images.length, videoFrames) : [];

  const lines = groupLines(spec.caption_track);
  const activeLine = !onMainSource
    ? []
    : (lines.find(
          (line) => sourceTime >= line[0].start && sourceTime <= line[line.length - 1].end,
        ) ??
      lines.find((line) => sourceTime < line[0].start) ??
      []);

  // 双语对照轨 (translation_track): unit-level translation cues paired with
  // the active original line by time overlap. Rendered as the PRIMARY line
  // (full caption style) with the original words smaller beneath — the
  // translated version's viewer reads the translation. Single layout only:
  // a stacked bilingual wall doubles every line and reads as noise, so the
  // stack layout keeps the original track alone.
  const translationTrack = spec.translation_track ?? [];
  const activeTranslation = !onMainSource
    ? null
    : (translationTrack.find((c) => sourceTime >= c.start && sourceTime <= c.end) ?? null);

  const captionsEnabled = spec.caption_enabled !== false;
  // Frame at which a line's first cue becomes visible in OUTPUT time — the
  // inverse remap's single home (types.ts outputTimeAtSourceTime). Per-line so
  // both layouts can drive entrance animations: `single` animates the active
  // line, `stack` animates each revealed line by its own reveal frame.
  const lineRevealFrame = (line: CaptionCue[]): number => {
    if (line.length === 0) return 0;
    const out = outputTimeAtSourceTime(spec, line[0].start);
    return out === null ? 0 : Math.round(out * fpsv);
  };
  const revealFrame = lineRevealFrame(activeLine);

  // stack layout (堆叠): every line revealed so far stays on screen, newest
  // at the bottom, sliding window of the last `maxLines` lines (the oldest
  // leave without animation in v1 — no dim, no exit animation).
  const stackMaxLines = preset.maxLines ?? 5;
  const visibleStack =
    preset.layout === "stack"
      ? lines.filter((line) => lineRevealFrame(line) <= frame).slice(-stackMaxLines)
      : [];

  // Background music: play the baked track when enabled, looped to fill the clip.
  const music = spec.music;
  const musicUrl = music?.enabled ? music.url ?? null : null;
  const musicVolume = Math.min(1, Math.pow(10, (music?.gain_db ?? -18) / 20));

  // Cloned-voice dub: when enabled, it REPLACES the source's original audio
  // (the video is muted / the stills speech track is skipped) and plays across
  // the video portion. Rough overlay — no lip-sync (see docs/VIDEO_EDITOR.md).
  const dubUrl = spec.dub?.enabled ? spec.dub.url ?? null : null;
  const dubVolume = Math.min(1, Math.pow(10, (spec.dub?.gain_db ?? 0) / 20));

  const captionPosStyle = pointStyle(spec.caption_position, DEFAULT_CAPTION_POS);
  // stack container: anchored by the edge nearer the anchor point so the block
  // never grows off-canvas — a top-half anchor pins the TOP edge (lines grow
  // downward); a bottom-half anchor (e.g. a single-layout caption_position at
  // 0.84) pins the BOTTOM edge and lines grow upward, newest at the bottom,
  // the sliding window exiting at the top (chat-scroll style).
  const stackAnchor = spec.caption_position ?? DEFAULT_STACK_POS;
  const stackPosStyle: React.CSSProperties = {
    position: "absolute",
    left: `${stackAnchor.x * 100}%`,
    top: `${stackAnchor.y * 100}%`,
    transform: stackAnchor.y > 0.5 ? "translate(-50%, -100%)" : "translate(-50%, 0)",
    width: "84%",
  };
  const entrance = captionEntrance(preset.entrance, frame, revealFrame);

  // stack + title: the title is a ~3s intro card (it fades out below); the
  // caption wall waits for it, so the two never share the top area. Lines
  // revealed during the intro stay revealed — the wall appears with them.
  const titleShown = Boolean(inVideo && spec.title.enabled && spec.title.text);
  const stackHiddenForIntro =
    preset.layout === "stack" && titleShown && frame <= introFrames + 105;

  // One line's cue spans — the active word takes the accent color (visible
  // only for wordHighlight presets; otherwise accent == captionColor).
  const renderCueSpans = (line: CaptionCue[]) =>
    line.map((cue, i) => {
      const isActive = sourceTime >= cue.start && sourceTime < cue.end;
      return (
        <span key={i} style={{ color: isActive ? accent : captionColor }}>
          {cue.text}
          {i < line.length - 1 ? " " : ""}
        </span>
      );
    });

  const captionTextStyle: React.CSSProperties = {
    textAlign: "center",
    fontFamily: captionFont,
    fontSize: captionSize,
    fontWeight: 700,
    lineHeight: 1.25,
    color: captionColor,
    WebkitTextStroke: "2px rgba(0,0,0,0.55)",
    textShadow: "0 2px 10px rgba(0,0,0,0.6)",
  };

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
          {!dubUrl && timeline.length > 0 ? (
            <Series>
              {timeline.map((t, i) => {
                // Hetero splice: the segment's own url is its donor's audio.
                const segAudio = t.seg.url ?? audioUrl;
                return segAudio ? (
                  <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                    <Audio
                      src={segAudio}
                      startFrom={Math.round(t.seg.start * fpsv)}
                      endAt={Math.round(t.seg.end * fpsv)}
                    />
                  </Series.Sequence>
                ) : null;
              })}
            </Series>
          ) : null}
        </Sequence>
      ) : hasSource ? (
        <Sequence from={introFrames} durationInFrames={videoFrames} layout="none">
          {srcDims ? (
            // Source-window crop (crop_track present): the video is sized to
            // the scaled source and positioned so the sampled window center
            // sits at the composition center — this is what lets a 16:9
            // interview reframe into per-speaker 9:16 shots (objectFit's
            // pre-crop would have destroyed the sides before any transform).
            // Empty-track specs never reach here (hasCropTrack gate above).
            <AbsoluteFill style={{ overflow: "hidden" }}>
              <Series>
                {timeline.map((t, i) => {
                  if (t.seg.url) {
                    // Hetero donor segment: crop keyframes are MAIN-SOURCE
                    // coordinates — never reframe donor pixels with the main
                    // source's dims. Plain cover, the pre-reframe behavior.
                    return (
                      <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                        <OffthreadVideo
                          src={t.seg.url}
                          muted={Boolean(dubUrl)}
                          startFrom={Math.round(t.seg.start * fpsv)}
                          endAt={Math.round(t.seg.end * fpsv)}
                          style={{ width: "100%", height: "100%", objectFit }}
                        />
                      </Series.Sequence>
                    );
                  }
                  const zoom =
                    (objectFit === "cover"
                      ? Math.max(width / srcDims.width, height / srcDims.height)
                      : Math.min(width / srcDims.width, height / srcDims.height)) * cropNow.scale;
                  return (
                    <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                      <OffthreadVideo
                        src={spec.source.url}
                        muted={Boolean(dubUrl)}
                        startFrom={Math.round(t.seg.start * fpsv)}
                        endAt={Math.round(t.seg.end * fpsv)}
                        style={{
                          position: "absolute",
                          width: srcDims.width * zoom,
                          height: srcDims.height * zoom,
                          left: width / 2 - cropNow.x * srcDims.width * zoom,
                          top: height / 2 - cropNow.y * srcDims.height * zoom,
                        }}
                      />
                    </Series.Sequence>
                  );
                })}
              </Series>
            </AbsoluteFill>
          ) : (
            <AbsoluteFill
              style={{
                // Reframe via transform (object-position is unsupported on the
                // future client-render path — keep to the CSS ∩ libass subset).
                // Per-frame value: the crop data track sampled at the current
                // source second (empty track = the static crop, 语义不变).
                transform: `scale(${cropNow.scale}) translate(${(0.5 - cropNow.x) * 100}%, ${(0.5 - cropNow.y) * 100}%)`,
              }}
            >
              <Series>
                {timeline.map((t, i) => (
                  <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(t.dur * fpsv))}>
                    <OffthreadVideo
                      // Hetero splice: the segment's own url is its donor's video.
                      src={t.seg.url ?? spec.source.url}
                      muted={Boolean(dubUrl)}
                      startFrom={Math.round(t.seg.start * fpsv)}
                      endAt={Math.round(t.seg.end * fpsv)}
                      style={{ width: "100%", height: "100%", objectFit }}
                    />
                  </Series.Sequence>
                ))}
              </Series>
            </AbsoluteFill>
          )}
        </Sequence>
      ) : null}

      {/* Entry-edge transition veils: above the main media, below layers/text. */}
      {timeline
        .filter((t) => t.seg.transition !== "none")
        .map((t) => (
          <Sequence
            key={t.seg.id}
            from={introFrames + Math.round(t.outStart * fpsv)}
            durationInFrames={TRANSITION_FRAMES[t.seg.transition as Exclude<SegmentTransition, "none">]}
            layout="none"
          >
            <TransitionVeil kind={t.seg.transition as Exclude<SegmentTransition, "none">} />
          </Sequence>
        ))}

      {/* Layer track: anchor-projected windows (compile artifact), one render
          branch by media type inside LayerView. */}
      {projectLayers(spec).resolved.map(({ layer, window }) => (
        <Sequence
          key={layer.id}
          from={Math.round(window.start * fpsv)}
          durationInFrames={Math.max(1, Math.round((window.end - window.start) * fpsv))}
          style={{ zIndex: layer.z }}
        >
          <LayerView layer={layer} fontFamily={captionFont} />
        </Sequence>
      ))}

      {brand?.intro ? (
        <Sequence from={0} durationInFrames={introFrames} layout="none">
          <IntroOutroCardView card={brand.intro} fontFamily={captionFont} />
        </Sequence>
      ) : null}
      {brand?.outro ? (
        <Sequence from={introFrames + videoFrames} durationInFrames={outroFrames} layout="none">
          <IntroOutroCardView card={brand.outro} fontFamily={captionFont} />
        </Sequence>
      ) : null}

      {inVideo && spec.title.enabled && spec.title.text ? (
        <div
          style={{
            textAlign: "center",
            color: "#ffffff",
            fontFamily: "sans-serif",
            fontSize: Math.round((spec.title.size || 58) * (height / 1920)),
            fontWeight: 800,
            lineHeight: 1.15,
            textShadow: "0 2px 12px rgba(0,0,0,0.7)",
            // Fade in over ~0.4s once the video portion starts (libass \fad).
            // stack layout: the accumulating caption wall owns the top area,
            // so the title is a ~3s intro card and fades out (libass \fad
            // out) — a permanent title collides with the stacked lines.
            opacity:
              preset.layout === "stack"
                ? interpolate(
                    frame,
                    [introFrames, introFrames + 12, introFrames + 90, introFrames + 105],
                    [0, 1, 1, 0],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  )
                : interpolate(frame, [introFrames, introFrames + 12], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
            ...pointStyle(spec.title.position, DEFAULT_TITLE_POS),
          }}
        >
          {spec.title.text}
        </div>
      ) : null}

      {inVideo && captionsEnabled && preset.layout === "stack" && visibleStack.length > 0 && !stackHiddenForIntro ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
            ...stackPosStyle,
          }}
        >
          {visibleStack.map((line, i) => {
            const lineEntrance = captionEntrance(
              preset.entrance,
              frame,
              lineRevealFrame(line),
            );
            return (
              <div
                key={line[0]?.start ?? i}
                style={{
                  ...captionTextStyle,
                  opacity: lineEntrance.opacity,
                  transform: lineEntrance.transformSuffix || undefined,
                }}
              >
                {renderCueSpans(line)}
              </div>
            );
          })}
        </div>
      ) : null}

      {inVideo && captionsEnabled && preset.layout === "single" && (activeLine.length > 0 || activeTranslation) ? (
        <div
          style={{
            ...captionPosStyle,
            transform: [captionPosStyle.transform, entrance.transformSuffix]
              .filter(Boolean)
              .join(" "),
            opacity: entrance.opacity,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: Math.round(captionSize * 0.3),
          }}
        >
          {activeTranslation ? (
            // 双语对照: the primary translation line takes a 0.82 discount —
            // two stacked lines need the air (2026-08-14 ruling).
            <div
              style={{
                ...captionTextStyle,
                fontSize: Math.round(captionSize * 0.82),
              }}
            >
              {activeTranslation.text}
            </div>
          ) : null}
          {activeLine.length > 0 ? (
            <div
              style={
                activeTranslation
                  ? {
                      ...captionTextStyle,
                      fontSize: Math.round(captionSize * 0.55),
                      fontWeight: 500,
                      opacity: 0.85,
                    }
                  : captionTextStyle
              }
            >
              {renderCueSpans(activeLine)}
            </div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

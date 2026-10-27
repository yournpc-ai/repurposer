// The video composition: tracks → clips → objects over the output timeline.
// TextPart identity/timing and all frame quantization arrive compiled; this
// adapter only evaluates values and paints the explicit inline layout.
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  cancelRender,
  continueRender,
  delayRender,
  useCurrentFrame,
} from "remotion";

import {
  evaluateProperty,
  type AnimValue,
  type VideoClip,
  type VideoSpec,
  type VideoTextObject,
  type VideoTextPart,
} from "@repurposer/video-spec";

function scalar(v: AnimValue | undefined, fallback: number): number {
  return typeof v === "number" ? v : fallback;
}

function vec2(v: AnimValue | undefined): [number, number] | undefined {
  return Array.isArray(v) ? [v[0], v[1]] : undefined;
}

const gainLinear = (db: number) => Math.pow(10, db / 20);
const originCss = (origin: "center" | "top_left") =>
  origin === "top_left" ? "0% 0%" : "50% 50%";

const FontResources: React.FC<{ fonts: VideoSpec["fonts"] }> = ({ fonts }) => {
  const [handle] = React.useState(() => delayRender("video: loading pinned font resources"));
  React.useEffect(() => {
    let active = true;
    Promise.all(
      fonts.map(async (resource) => {
        const face = new FontFace(
          resource.family,
          `url(${JSON.stringify(resource.url)}) format("${resource.format}")`,
          { style: "normal", weight: String(resource.weight) },
        );
        await face.load();
        if (active) {
          (document.fonts as FontFaceSet & { add(font: FontFace): void }).add(face);
        }
      }),
    )
      .then(() => {
        if (active) continueRender(handle);
      })
      .catch((error) => {
        if (active) cancelRender(error);
      });
    return () => {
      active = false;
    };
  }, [fonts, handle]);
  return null;
};

function wholeObjectStyle(clip: VideoClip, frame: number): React.CSSProperties {
  const obj = clip.object;
  if (obj.kind === "audio") throw new Error("audio object has no visual layout");
  const { animations } = clip;
  const position =
    vec2(evaluateProperty(animations, obj.object_id, "transform.position", frame)) ??
    ([0, 0] as [number, number]);
  const scale = scalar(
    evaluateProperty(animations, obj.object_id, "transform.scale", frame),
    obj.transform.scale,
  );
  const rotation = scalar(
    evaluateProperty(animations, obj.object_id, "transform.rotation", frame),
    obj.transform.rotation,
  );
  const opacity = scalar(
    evaluateProperty(animations, obj.object_id, "opacity", frame),
    obj.opacity,
  );
  return {
    position: "absolute",
    left: obj.layout.x,
    top: obj.layout.y,
    width: obj.layout.width,
    height: obj.layout.height,
    opacity,
    transformOrigin: originCss(obj.transform.origin),
    transform: `translate(${obj.transform.x + position[0]}px, ${
      obj.transform.y + position[1]
    }px) scale(${scale}) rotate(${rotation}deg)`,
  };
}

function textPartStyle(
  clip: VideoClip,
  part: VideoTextPart,
  frame: number,
  line: boolean,
): React.CSSProperties {
  const objectId = clip.object.object_id;
  const position =
    vec2(evaluateProperty(clip.animations, objectId, "transform.position", frame, part.part_id)) ??
    ([0, 0] as [number, number]);
  const scale = scalar(
    evaluateProperty(clip.animations, objectId, "transform.scale", frame, part.part_id),
    1,
  );
  const rotation = scalar(
    evaluateProperty(clip.animations, objectId, "transform.rotation", frame, part.part_id),
    0,
  );
  const opacity = scalar(
    evaluateProperty(clip.animations, objectId, "opacity", frame, part.part_id),
    1,
  );
  return {
    display: line ? "block" : "inline-block",
    whiteSpace: line ? "pre-wrap" : "pre",
    opacity,
    transformOrigin: "50% 50%",
    transform: `translate(${position[0]}px, ${position[1]}px) scale(${scale}) rotate(${rotation}deg)`,
  };
}

function targetedParts(
  object: VideoTextObject,
  kind: "word" | "grapheme",
  line: VideoTextPart,
): VideoTextPart[] {
  return object.parts
    .filter(
      (part) =>
        part.kind === kind &&
        part.layout_range.start === line.text_range.start &&
        part.layout_range.end === line.text_range.end,
    )
    .sort((a, b) => a.text_range.start - b.text_range.start);
}

const TextLine: React.FC<{
  clip: VideoClip & { object: VideoTextObject };
  line: VideoTextPart;
  granular: "word" | "grapheme" | null;
  frame: number;
}> = ({ clip, line, granular, frame }) => {
  const object = clip.object;
  if (!granular) {
    return <div style={textPartStyle(clip, line, frame, true)}>{line.text || "​"}</div>;
  }
  const parts = targetedParts(object, granular, line);
  const chars = Array.from(object.text);
  const children: React.ReactNode[] = [];
  let cursor = line.text_range.start;
  for (const part of parts) {
    if (part.text_range.start < cursor) {
      throw new Error(`overlapping TextParts in ${object.object_id}`);
    }
    if (part.text_range.start > cursor) {
      children.push(chars.slice(cursor, part.text_range.start).join(""));
    }
    children.push(
      <span key={part.part_id} style={textPartStyle(clip, part, frame, false)}>
        {part.text}
      </span>,
    );
    cursor = part.text_range.end;
  }
  if (cursor < line.text_range.end) children.push(chars.slice(cursor, line.text_range.end).join(""));
  if (children.length === 0) children.push("​");
  return <div style={textPartStyle(clip, line, frame, true)}>{children}</div>;
};

const TextObjectView: React.FC<{
  clip: VideoClip & { object: VideoTextObject };
  fonts: VideoSpec["fonts"];
  frame: number;
}> = ({ clip, fonts, frame }) => {
  const object = clip.object;
  const families = fonts.filter(
    (resource) =>
      resource.font_id === object.style.font.font_id &&
      resource.font_set_digest === object.style.font.digest,
  );
  if (families.length === 0) throw new Error(`no pinned font for ${object.object_id}`);
  const partKinds = new Set(
    object.parts
      .filter((part) =>
        clip.animations.some((animation) => animation.target_text_part_id === part.part_id),
      )
      .map((part) => part.kind),
  );
  const granular = partKinds.has("grapheme") ? "grapheme" : partKinds.has("word") ? "word" : null;
  const lines = object.parts.filter((part) => part.kind === "line");
  return (
    <div
      style={{
        ...wholeObjectStyle(clip, frame),
        color: object.style.color,
        background: object.style.background ?? "transparent",
        fontFamily: families.map((resource) => resource.family).join(", "),
        fontSynthesis: "none",
        fontSize: object.style.font_size,
        fontWeight: object.style.weight,
        textAlign: object.style.align,
        lineHeight: object.style.line_height,
        whiteSpace: "pre-wrap",
      }}
    >
      {lines.map((line) => (
        <TextLine
          key={line.part_id}
          clip={clip}
          line={line}
          granular={granular}
          frame={frame}
        />
      ))}
    </div>
  );
};

const VisualObjectView: React.FC<{ clip: VideoClip; fonts: VideoSpec["fonts"] }> = ({
  clip,
  fonts,
}) => {
  const frame = useCurrentFrame();
  const obj = clip.object;
  if (obj.kind === "audio") return null;
  if (obj.kind === "text") {
    return <TextObjectView clip={clip as VideoClip & { object: VideoTextObject }} fonts={fonts} frame={frame} />;
  }
  if (!clip.source) throw new Error(`${obj.kind} clip ${clip.clip_id} carries no source`);
  return (
    <div style={wholeObjectStyle(clip, frame)}>
      <Img
        src={clip.source.url}
        style={{ width: "100%", height: "100%", objectFit: obj.fit }}
      />
    </div>
  );
};

const AudioClipView: React.FC<{ clip: VideoClip }> = ({ clip }) => {
  if (clip.object.kind !== "audio" || !clip.source) return null;
  const src = clip.source;
  const base = gainLinear(clip.object.gain_db);
  const gainAnim = clip.animations.find(
    (animation) =>
      animation.target_object_id === clip.object.object_id &&
      animation.target_text_part_id === null &&
      animation.property === "audio.gain",
  );
  return (
    <Audio
      src={src.url}
      startFrom={src.start_frame ?? 0}
      endAt={src.end_frame}
      volume={
        gainAnim
          ? (frame) =>
              base *
              scalar(
                evaluateProperty(clip.animations, clip.object.object_id, "audio.gain", frame),
                1,
              )
          : base
      }
    />
  );
};

export const Video: React.FC<{ spec: VideoSpec }> = ({ spec }) => {
  const visualTracks = spec.tracks
    .filter((track) => track.kind === "visual")
    .sort((a, b) => a.order - b.order);
  const audioTracks = spec.tracks.filter((track) => track.kind === "audio");
  return (
    <AbsoluteFill style={{ background: spec.background }}>
      <FontResources fonts={spec.fonts} />
      {visualTracks.flatMap((track) =>
        track.clips.map((clip) => (
          <Sequence
            key={clip.clip_id}
            from={clip.start_frame}
            durationInFrames={clip.end_frame - clip.start_frame}
          >
            <VisualObjectView clip={clip} fonts={spec.fonts} />
          </Sequence>
        )),
      )}
      {audioTracks.flatMap((track) =>
        track.clips.map((clip) => (
          <Sequence
            key={clip.clip_id}
            from={clip.start_frame}
            durationInFrames={clip.end_frame - clip.start_frame}
          >
            <AudioClipView clip={clip} />
          </Sequence>
        )),
      )}
    </AbsoluteFill>
  );
};

import {
  LAYOUT_VERSION,
  transitionKinds,
  SEGMENTATION_VERSION,
  type VideoSpec,
} from "@repurposer/video-spec";

/** Explicit capability court: schema-valid but unimplemented input fails. */
export const VIDEO_CAPABILITIES = {
  objects: ["text", "shape", "image", "web", "video", "motion_block", "audio"],
  motion_blocks: [
    "kinetic_title",
    "product_showcase",
    "statement_hook",
    "metric_grid",
    "closing_cta",
    "chat_demo",
    "device_mockup",
    "flow_diagram",
    "split_compare",
    "step_timeline",
    "bento_features",
    "data_chart",
    "quote_proof",
  ] as readonly string[],
  text_parts: ["line", "word", "grapheme"],
  segmentation_versions: [SEGMENTATION_VERSION] as readonly string[],
  layout_versions: [LAYOUT_VERSION] as readonly string[],
  properties: [
    "opacity",
    "transform.position",
    "transform.scale",
    "transform.rotation",
    "filter.blur",
    "text.letter_spacing",
    "text.color",
    "text.stroke_color",
    "text.weight",
    "text.stroke_width",
    "path.reveal",
    "audio.gain",
  ],
  easings: ["linear", "hold", "cubic_bezier"],
  transitions: transitionKinds,
  fractional_fps: false,
} as const;

export class VideoCapabilityError extends Error {}

export function assertVideoSupported(spec: VideoSpec): void {
  if (spec.fps.den !== 1) {
    throw new VideoCapabilityError(
      `fractional fps ${spec.fps.num}/${spec.fps.den} is not supported by this adapter`,
    );
  }
  for (const transition of spec.transitions ?? []) {
    if (!VIDEO_CAPABILITIES.transitions.includes(transition.kind)) {
      throw new VideoCapabilityError(`transition kind ${transition.kind} unsupported`);
    }
  }
  const fontKeys = new Set<string>();
  for (const font of spec.fonts) {
    const key = `${font.font_id}:${font.family}:${font.weight}:${font.digest}`;
    if (fontKeys.has(key)) throw new VideoCapabilityError(`duplicate font resource ${key}`);
    fontKeys.add(key);
  }
  for (const track of spec.tracks) {
    for (const clip of track.clips) {
      const object = clip.object;
      if (!(VIDEO_CAPABILITIES.objects as readonly string[]).includes(object.kind)) {
        throw new VideoCapabilityError(`object kind ${object.kind} unsupported`);
      }
      if (object.kind === "motion_block") {
        if (!VIDEO_CAPABILITIES.motion_blocks.includes(object.block_id) || object.block_version !== 1) {
          throw new VideoCapabilityError(
            `motion_block ${object.block_id}@v${object.block_version} unsupported`,
          );
        }
      }
      if (object.kind === "text") {
        if (!VIDEO_CAPABILITIES.segmentation_versions.includes(object.segmentation_version)) {
          throw new VideoCapabilityError("text segmentation version unsupported");
        }
        if (!VIDEO_CAPABILITIES.layout_versions.includes(object.layout_version)) {
          throw new VideoCapabilityError("text layout version unsupported");
        }
        if (
          !spec.fonts.some(
            (font) =>
              font.font_id === object.style.font.font_id &&
              font.font_set_digest === object.style.font.digest,
          )
        ) {
          throw new VideoCapabilityError(`text object ${object.object_id} lacks its font set`);
        }
      }
      const partIds = new Set(object.kind === "text" ? object.parts.map((part) => part.part_id) : []);
      if (object.kind === "text" && partIds.size !== object.parts.length) {
        throw new VideoCapabilityError(`duplicate TextPart ids in ${object.object_id}`);
      }
      const animatedPartKinds = new Set<string>();
      for (const anim of clip.animations) {
        if (!(VIDEO_CAPABILITIES.properties as readonly string[]).includes(anim.property)) {
          throw new VideoCapabilityError(`property ${anim.property} unsupported`);
        }
        if (anim.property === "path.reveal") {
          if (object.kind !== "shape" || object.shape !== "path" || !object.path) {
            throw new VideoCapabilityError("path.reveal requires a path shape with path data");
          }
          if (anim.target_text_part_id !== null) {
            throw new VideoCapabilityError("path.reveal does not accept TextPart targets");
          }
        }
        if (anim.target_text_part_id !== null) {
          if (object.kind !== "text" || !partIds.has(anim.target_text_part_id)) {
            throw new VideoCapabilityError(`unknown TextPart target ${anim.target_text_part_id}`);
          }
          const part = object.parts.find((item) => item.part_id === anim.target_text_part_id)!;
          animatedPartKinds.add(part.kind);
        }
        const seenFrames = new Set<number>();
        for (const kf of anim.keyframes) {
          if (seenFrames.has(kf.at)) {
            throw new VideoCapabilityError(
              `animation ${anim.animation_id} has duplicate frame ${kf.at}`,
            );
          }
          seenFrames.add(kf.at);
          if (!(VIDEO_CAPABILITIES.easings as readonly string[]).includes(kf.easing.kind)) {
            throw new VideoCapabilityError(`easing ${kf.easing.kind} unsupported`);
          }
        }
      }
      if (animatedPartKinds.has("word") && animatedPartKinds.has("grapheme")) {
        throw new VideoCapabilityError("mixed word + grapheme part hierarchy is not supported");
      }
    }
  }
}

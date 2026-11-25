import { z } from "zod";

/**
 * video-spec — renderer-neutral compiled CompositionVersion. Every time is
 * already an integer frame; source/font bytes carry independently verifiable
 * digests. No React, Remotion, DOM, callback or arbitrary CSS enters the wire.
 */

const fpsSchema = z
  .object({ num: z.number().int().positive(), den: z.number().int().positive() })
  .strict();

const hexColor = z.string().regex(/^#[0-9a-fA-F]{6}$/);

const layoutBoxSchema = z
  .object({
    x: z.number().finite(),
    y: z.number().finite(),
    width: z.number().finite().positive(),
    height: z.number().finite().positive(),
  })
  .strict();

const transformSchema = z
  .object({
    x: z.number().finite(),
    y: z.number().finite(),
    scale: z.number().finite().positive(),
    rotation: z.number().finite(),
    origin: z.enum(["center", "top_left"]),
  })
  .strict();

const fontRefSchema = z
  .object({ font_id: z.string().min(1), digest: z.string().length(64) })
  .strict();

const fontResourceSchema = z
  .object({
    font_id: z.string().min(1),
    font_set_digest: z.string().length(64),
    family: z.string().min(1),
    weight: z.union([z.literal(400), z.literal(700), z.literal(900)]),
    format: z.enum(["opentype", "truetype"]),
    url: z.string().min(1),
    digest: z.string().length(64),
    unicode_range: z.string().min(1).optional(),
  })
  .strict();

const textBorderSchema = z
  .object({
    color: hexColor,
    width: z.number().finite().min(0).max(16),
  })
  .strict();

const textStrokeSchema = z
  .object({
    color: hexColor,
    width: z.number().finite().min(0).max(64),
  })
  .strict();

const textShadowSchema = z
  .object({
    color: hexColor,
    offset: z.tuple([z.number().finite(), z.number().finite()]),
    blur: z.number().finite().min(0).max(100),
  })
  .strict();

export const textBackgroundModes = ["box", "pill", "line"] as const;
export const textTransforms = ["none", "uppercase"] as const;

const textStyleSchema = z
  .object({
    finish: z.enum(["chrome","outline","gradient_pill","split_ink","neon"]).optional(),
    font_size: z.number().int().positive().max(400),
    color: hexColor,
    background: hexColor.nullable(),
    background_mode: z.enum(textBackgroundModes).default("box"),
    background_opacity: z.number().finite().min(0).max(1).default(1),
    background_padding: z
      .tuple([z.number().finite().min(0).max(120), z.number().finite().min(0).max(120)])
      .default([0, 0]),
    background_radius: z.number().finite().min(0).max(999).default(0),
    border: textBorderSchema.nullable().default(null),
    weight: z.union([
      z.literal(400),
      z.literal(500),
      z.literal(600),
      z.literal(700),
      z.literal(800),
      z.literal(900),
    ]),
    align: z.enum(["left", "center", "right"]),
    line_height: z.number().finite().positive(),
    letter_spacing: z.number().finite().min(-0.2).max(0.5).default(0),
    text_transform: z.enum(textTransforms).default("none"),
    secondary_line_scale: z.number().finite().min(0.4).max(1).default(1),
    secondary_line_opacity: z.number().finite().min(0.2).max(1).default(1),
    stroke: textStrokeSchema.nullable().default(null),
    shadow: textShadowSchema.nullable().default(null),
    font: fontRefSchema,
  })
  .strict();

const textRangeSchema = z
  .object({
    start: z.number().int().nonnegative(),
    end: z.number().int().nonnegative(),
  })
  .strict()
  .superRefine((range, ctx) => {
    if (range.end < range.start) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "text range is reversed" });
    }
  });

const textPartSchema = z
  .object({
    part_id: z.string().min(1),
    kind: z.enum(["line", "word", "grapheme"]),
    text: z.string(),
    text_range: textRangeSchema,
    layout_range: textRangeSchema,
  })
  .strict();

const textObjectSchema = z
  .object({
    kind: z.literal("text"),
    object_id: z.string().min(1),
    text: z.string().min(1),
    layout: layoutBoxSchema,
    style: textStyleSchema,
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
    segmentation_version: z.string().min(1),
    layout_version: z.string().min(1),
    parts: z.array(textPartSchema),
  })
  .strict();

const imageObjectSchema = z
  .object({
    kind: z.literal("image"),
    object_id: z.string().min(1),
    layout: layoutBoxSchema,
    fit: z.enum(["cover", "contain"]),
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
  })
  .strict();

const webObjectSchema = z
  .object({
    kind: z.literal("web"),
    object_id: z.string().min(1),
    view_id: z.string().min(1),
    layout: layoutBoxSchema,
    fit: z.enum(["cover", "contain"]),
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
  })
  .strict();

const videoObjectSchema = z
  .object({
    kind: z.literal("video"),
    object_id: z.string().min(1),
    layout: layoutBoxSchema,
    fit: z.enum(["cover", "contain"]),
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
    gain_db: z.number().finite().min(-60).max(12),
    muted: z.boolean(),
  })
  .strict();

const shapeObjectSchema = z
  .object({
    kind: z.literal("shape"),
    object_id: z.string().min(1),
    shape: z.enum(["rect", "ellipse", "path"]),
    layout: layoutBoxSchema,
    fill: hexColor.nullable(),
    stroke: hexColor.nullable(),
    stroke_width: z.number().finite().min(0).max(200),
    corner_radius: z.number().finite().min(0).max(1000),
    path: z.string().min(1).max(4096).nullable(),
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
  })
  .strict();

const motionBlockResourceSchema = z
  .object({
    path: z.string().min(1).max(120),
    url: z.string().min(1),
    digest: z.string().length(64),
    content_type: z.enum(["image/png", "image/jpeg", "image/webp"]),
  })
  .strict();

export const backdropStyles = [
  "ambient_mesh",
  "architectural_grid",
  "editorial_paper",
  "kinetic_diagonal",
  "studio_spotlight",
  "warm_obsidian",
  "editorial_studio",
  "clean",
] as const;

const studioProps = {
  theme: z.enum(["light","dark"]).nullish(), backdrop_style: z.enum(backdropStyles).nullish(),
  accent_color: hexColor.nullish(), show_backdrop: z.boolean().optional(),
};
const shortLabel = z.string().trim().min(1).max(32);
const heading = z.string().trim().min(1).max(80).nullish();
const terminalProps = z.object({
  ...studioProps, mode:z.enum(["typing_cli","diff_highlight","command_palette"]).optional(),
  title:heading, lines:z.array(z.string().trim().min(1).max(120)).min(1).max(8),
  prompt_prefix:shortLabel.optional(), highlight_line:z.number().int().positive().nullish(),
}).strict().refine(p=>p.highlight_line==null || p.highlight_line <= p.lines.length, "highlight_line exceeds line count");
const logoProps = z.object({
  ...studioProps, mode:z.enum(["marquee_strip","grid_stagger","spotlight_lockup"]).optional(),
  eyebrow:shortLabel.nullish(), headline:heading,
  items:z.array(z.object({text:shortLabel, resource_index:z.number().int().min(0).max(15).nullish()}).strict()).min(1).max(12),
}).strict();

const motionBlockObjectSchema = z
  .object({
    kind: z.literal("motion_block"),
    object_id: z.string().min(1),
    block_id: z.enum([
      "kinetic_title",
      "product_showcase",
      "statement_hook",
      "metric_grid",
      "closing_cta",
      "chat_demo",
      "code_terminal", "logo_wall",
      "device_mockup",
      "flow_diagram",
      "split_compare",
      "step_timeline",
      "bento_features",
      "data_chart",
      "quote_proof",
      "kinetic_beat",
      "ui_montage",
    ]),
    block_version: z.literal(1),
    props: z.record(z.string(), z.unknown()),
    resources: z.array(motionBlockResourceSchema).max(16),
    layout: layoutBoxSchema,
    fit: z.enum(["cover", "contain"]),
    transform: transformSchema,
    opacity: z.number().min(0).max(1),
  })
  .strict();

const audioObjectSchema = z
  .object({
    kind: z.literal("audio"),
    object_id: z.string().min(1),
    gain_db: z.number().finite().min(-60).max(12),
  })
  .strict();

const objectSchema = z.discriminatedUnion("kind", [
  textObjectSchema,
  imageObjectSchema,
  webObjectSchema,
  videoObjectSchema,
  shapeObjectSchema,
  motionBlockObjectSchema,
  audioObjectSchema,
]);

const easingSchema = z
  .object({
    kind: z.enum(["linear", "hold", "cubic_bezier"]),
    params: z.tuple([
      z.number().finite(),
      z.number().finite(),
      z.number().finite(),
      z.number().finite(),
    ]).optional(),
  })
  .strict()
  .superRefine((easing, ctx) => {
    if (easing.kind === "cubic_bezier" && !easing.params) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "cubic_bezier requires params" });
    }
    if (easing.kind !== "cubic_bezier" && easing.params) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${easing.kind} takes no params` });
    }
    if (easing.params && (easing.params[0] < 0 || easing.params[0] > 1 || easing.params[2] < 0 || easing.params[2] > 1)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "bezier x controls must stay in [0, 1]" });
    }
  });

const keyframeSchema = z
  .object({
    at: z.number().int().nonnegative(),
    value: z.union([
      z.number().finite(),
      z.tuple([z.number().finite(), z.number().finite()]),
      hexColor,
    ]),
    easing: easingSchema,
  })
  .strict();

const holdOnlyTextProperties = new Set([
  "text.color",
  "text.stroke_color",
  "text.weight",
  "text.stroke_width",
]);
const stringTextProperties = new Set(["text.color", "text.stroke_color"]);

const animationSchema = z
  .object({
    animation_id: z.string().min(1),
    target_object_id: z.string().min(1),
    target_text_part_id: z.string().min(1).nullable(),
    property: z.enum([
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
    ]),
    keyframes: z.array(keyframeSchema).min(1),
  })
  .strict()
  .superRefine((animation, ctx) => {
    const holdOnly = holdOnlyTextProperties.has(animation.property);
    const expectsString = stringTextProperties.has(animation.property);
    animation.keyframes.forEach((keyframe, index) => {
      const validShape = expectsString
        ? typeof keyframe.value === "string"
        : animation.property === "transform.position"
          ? Array.isArray(keyframe.value)
          : typeof keyframe.value === "number";
      if (!validShape) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: expectsString
            ? `${animation.property} requires color string values`
            : `${animation.property} does not accept string values`,
          path: ["keyframes", index, "value"],
        });
      }
      if (animation.property === "path.reveal" &&
          (typeof keyframe.value !== "number" || keyframe.value < 0 || keyframe.value > 1)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "path.reveal must stay in [0, 1]",
          path: ["keyframes", index, "value"],
        });
      }
      if (animation.property === "text.weight" &&
          (typeof keyframe.value !== "number" || ![400, 500, 600, 700, 800, 900].includes(keyframe.value))) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "text.weight has an unsupported font weight",
          path: ["keyframes", index, "value"],
        });
      }
      if (animation.property === "text.stroke_width" &&
          (typeof keyframe.value !== "number" || keyframe.value < 0 || keyframe.value > 64)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "text.stroke_width must stay in [0, 64]",
          path: ["keyframes", index, "value"],
        });
      }
      if (holdOnly && index < animation.keyframes.length - 1 && keyframe.easing.kind !== "hold") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `${animation.property} supports hold segments only`,
          path: ["keyframes", index, "easing", "kind"],
        });
      }
    });
  });

const clipSourceSchema = z
  .object({
    url: z.string().min(1),
    digest: z.string().length(64),
    start_frame: z.number().int().nonnegative().optional(),
    end_frame: z.number().int().positive().optional(),
  })
  .strict();

const clipSchema = z
  .object({
    clip_id: z.string().min(1),
    start_frame: z.number().int().nonnegative(),
    end_frame: z.number().int().positive(),
    scene_id: z.string().min(1).nullable(),
    source: clipSourceSchema.nullable(),
    object: objectSchema,
    animations: z.array(animationSchema),
  })
  .strict()
  .superRefine((clip, ctx) => {
    if (clip.end_frame <= clip.start_frame) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "end_frame must exceed start_frame" });
    }
    if (clip.object.kind === "motion_block") {
      const block = clip.object;
      if (block.block_id === "code_terminal" && !terminalProps.safeParse(block.props).success) {
        ctx.addIssue({code:z.ZodIssueCode.custom, message:"Invalid code_terminal props"});
      }
      if (block.block_id === "logo_wall") {
        const result = logoProps.safeParse(block.props);
        if (!result.success || result.data.items.some(i=>i.resource_index!=null && i.resource_index>=block.resources.length)) {
          ctx.addIssue({code:z.ZodIssueCode.custom, message:"Invalid logo_wall items or pinned image references"});
        }
      }
    }
    if (clip.object.kind === "motion_block" && clip.object.block_id === "device_mockup" &&
        ((!clip.object.resources.length && clip.object.props.layout !== "split_focus") || clip.object.resources.length > 2)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "device_mockup requires one or two pinned images" });
    }
    if (clip.object.kind === "motion_block" && clip.object.block_id === "ui_montage" && !clip.object.resources.length) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "ui_montage requires pinned images" });
    }
    const hasWindow = clip.source?.start_frame !== undefined || clip.source?.end_frame !== undefined;
    if (["audio", "video"].includes(clip.object.kind) && !hasWindow) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "time-based clips need a source window" });
    }
    if (["image", "web", "motion_block"].includes(clip.object.kind) && hasWindow) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "static sources carry no source window" });
    }
    if (["text", "shape"].includes(clip.object.kind) && clip.source) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "native objects take no media source" });
    }
    clip.animations.forEach((animation, index) => {
      if (animation.property !== "path.reveal") return;
      if (clip.object.kind !== "shape" || clip.object.shape !== "path" || !clip.object.path) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "path.reveal requires a path shape with non-empty path data",
          path: ["animations", index, "property"],
        });
      }
      if (animation.target_text_part_id !== null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "path.reveal does not accept TextPart targets",
          path: ["animations", index, "target_text_part_id"],
        });
      }
    });
  });

const trackSchema = z
  .object({
    track_id: z.string().min(1),
    kind: z.enum(["visual", "audio"]),
    role: z.enum(["main", "title", "caption", "dialogue", "music", "effect"]),
    order: z.number().int().nonnegative(),
    clips: z.array(clipSchema),
  })
  .strict();

export const transitionKinds = ["crossfade", "whip_pan", "wipe_reveal", "zoom_through", "iris_focus"] as const;

export const stylePresetIds = [
  "institutional_dark",
  "swiss_paper",
  "vox_editorial",
  "kinetic_anime",
] as const;



export const cardTreatments = [
  "glass_soft",
  "minimal_hairline",
  "editorial_rule",
  "brutal_offset",
] as const;

export const headlineTreatments = [
  "clean",
  "swiss_rule",
  "highlight_tape",
  "outlined_impact",
] as const;

const videoCaptionStyleSchema = z
  .object({
    color: hexColor,
    weight: z.union([
      z.literal(400),
      z.literal(500),
      z.literal(600),
      z.literal(700),
      z.literal(800),
      z.literal(900),
    ]),
    background: hexColor.nullable(),
    background_mode: z.enum(textBackgroundModes).default("box"),
    background_opacity: z.number().finite().min(0).max(1).default(1),
    background_padding: z
      .tuple([z.number().finite().min(0).max(120), z.number().finite().min(0).max(120)])
      .default([0, 0]),
    background_radius: z.number().finite().min(0).max(999).default(0),
    border: textBorderSchema.nullable().default(null),
    stroke: textStrokeSchema.nullable(),
    shadow: textShadowSchema.nullable(),
    text_transform: z.enum(textTransforms).default("none"),
    secondary_line_scale: z.number().finite().min(0.4).max(1).default(1),
    secondary_line_opacity: z.number().finite().min(0.2).max(1).default(1),
  })
  .strict();

export const videoStyleSchema = z
  .object({
    preset_id: z.enum(stylePresetIds),
    theme: z.enum(["dark", "light"]),
    backdrop_style: z.enum(backdropStyles),
    canvas_bg: hexColor,
    surface_bg: hexColor,
    ink: hexColor,
    secondary_ink: hexColor,
    line_color: hexColor,
    accent: hexColor,
    accent_secondary: hexColor,
    accent_ink: hexColor,
    accent_text: hexColor,
    card_treatment: z.enum(cardTreatments),
    headline_treatment: z.enum(headlineTreatments),
    heading_weight: z.union([z.literal(700), z.literal(900)]),
    default_transition: z.enum(transitionKinds),
    caption_style: videoCaptionStyleSchema,
  })
  .strict();

export const videoSpecSchema = z
  .object({
    family: z.literal("video"),
    format: z.literal(1),
    fps: fpsSchema,
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    background: hexColor,
    style: videoStyleSchema.optional(),
    sample_rate: z.number().int().positive(),
    duration_frames: z.number().int().positive(),
    fonts: z.array(fontResourceSchema),
    tracks: z.array(trackSchema).min(1),
    transitions: z.array(z.object({
      transition_id: z.string().min(1),
      kind: z.enum(transitionKinds).default("crossfade"),
      from_clip_id: z.string().min(1),
      to_clip_id: z.string().min(1),
      start_frame: z.number().int().nonnegative(),
      end_frame: z.number().int().positive(),
      cut_frame: z.number().int().positive(),
    }).strict().refine(t => t.start_frame < t.cut_frame && t.cut_frame < t.end_frame, {
      message: "A centered transition needs frames on both sides of its cut",
    })).optional(),
    provenance: z
      .object({
        composition_id: z.string().min(1),
        composition_version_id: z.string().min(1),
        content_digest: z.string().length(64),
      })
      .strict(),
  })
  .strict();

export type VideoStyle = z.infer<typeof videoStyleSchema>;
export type VideoSpec = z.infer<typeof videoSpecSchema>;
export type VideoClip = VideoSpec["tracks"][number]["clips"][number];
export type VideoAnimation = VideoClip["animations"][number];
export type VideoKeyframe = VideoAnimation["keyframes"][number];
export type VideoTextObject = Extract<VideoClip["object"], { kind: "text" }>;
export type VideoTextPart = VideoTextObject["parts"][number];
export type VideoMotionBlockObject = Extract<VideoClip["object"], { kind: "motion_block" }>;

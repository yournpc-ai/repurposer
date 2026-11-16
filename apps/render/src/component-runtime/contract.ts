import { z } from "zod";

// Keep this lock in sync with editing.schemas.COMPONENT_DEPENDENCIES. The
// request carries it across the API/runner boundary and the digest covers it.
export const COMPONENT_DEPENDENCIES = {
  react: "19.2.7",
  "react-dom": "19.2.7",
  remotion: "4.0.484",
  "@remotion/bundler": "4.0.484",
  "@remotion/renderer": "4.0.484",
} as const;

// Mirrored by app.tools.video.components on the API side. The HTTP route allows
// 64 MiB because the 32 MiB aggregate expands to about 42.7 MiB in base64.
export const MAX_FIXED_RESOURCE_BYTES = 16 * 1024 * 1024;
export const MAX_TOTAL_FIXED_RESOURCE_BYTES = 32 * 1024 * 1024;
const MAX_FIXED_RESOURCES = 64;
export const MAX_FIXED_RESOURCE_BASE64_CHARS = 4 * Math.ceil(MAX_FIXED_RESOURCE_BYTES / 3);

const scalarParameter = z.union([
  z.string().max(128),
  z.number().finite(),
  z.boolean(),
]);

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
const jsonValue: z.ZodType<JsonValue> = z.lazy(() => z.union([
  z.string(), z.number().finite(), z.boolean(), z.null(),
  z.array(jsonValue), z.record(jsonValue),
]));

const projectPath = z.string().max(120).regex(/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/).refine(
  (value) => !value.startsWith(".") && !value.includes("//") &&
    !value.split("/").includes("..") && !value.endsWith("/"),
  "project paths are relative and cannot traverse",
);
const sourcePath = projectPath.refine(
  (value) => value.endsWith(".ts") || value.endsWith(".tsx"),
  "the entry must be a .ts or .tsx source file",
);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);

export const projectFileSchema = z.object({
  path: projectPath.refine(
    (value) => value.endsWith(".ts") || value.endsWith(".tsx") || value.endsWith(".json"),
    "project files must be .ts, .tsx or .json",
  ),
  content: z.string().min(1).max(24000),
  digest: sha256,
}).strict();

export const remotionProjectSchema = z.object({
  schema_version: z.literal(1),
  entry: sourcePath,
  composition_id: z.string().regex(/^[A-Za-z][A-Za-z0-9_-]{0,63}$/),
  files: z.array(projectFileSchema).min(2).max(24),
  props: z.record(jsonValue),
  props_schema: z.object({
    type: z.literal("object"),
    additionalProperties: z.literal(false),
    properties: z.record(z.object({ type: z.enum([
      "string", "number", "integer", "boolean", "array", "object", "null",
    ]) }).strict()),
    required: z.array(z.string()).optional(),
  }).strict(),
}).strict().superRefine((project, ctx) => {
  const paths = project.files.map(({ path }) => path);
  if (new Set(paths).size !== paths.length || !paths.includes(project.entry)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "project files need unique paths and the declared entry" });
  }
  if (project.files.reduce((sum, file) => sum + Buffer.byteLength(file.content, "utf8"), 0) > 96000) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "project source exceeds its byte budget" });
  }
  if (Object.keys(project.props).length > 32 || JSON.stringify(project.props).length > 8192) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "project props exceed their budget" });
  }
  const properties = Object.keys(project.props_schema.properties);
  if (properties.length !== Object.keys(project.props).length ||
      properties.some((key) => !(key in project.props))) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "props_schema must describe exactly the supplied props" });
  }
});

export const fixedResourceSchema = z.object({
  path: projectPath,
  digest: sha256,
  content_type: z.enum(["image/png", "image/jpeg", "image/webp"]),
  data_base64: z.string().min(4).max(MAX_FIXED_RESOURCE_BASE64_CHARS),
}).strict().superRefine((resource, ctx) => {
  const suffix = { "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp" }[resource.content_type];
  if (!resource.path.toLowerCase().endsWith(suffix)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "resource suffix differs from content_type" });
  }
});

export const componentOutputSchema = z.object({
  width: z.number().int().min(16).max(1920),
  height: z.number().int().min(16).max(1920),
  fps: z.number().int().positive().max(60),
  duration_frames: z.number().int().positive().max(3600),
  background: z.string().regex(/^#[0-9a-fA-F]{6}$/),
}).strict().superRefine((output, ctx) => {
  if (output.width % 2 || output.height % 2) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "raster dimensions must be even" });
  }
});

export const componentBakeRequestSchema = z.object({
  producer: z.literal("remotion-project"),
  program_digest: sha256,
  dependencies: z.object({
    react: z.literal(COMPONENT_DEPENDENCIES.react),
    "react-dom": z.literal(COMPONENT_DEPENDENCIES["react-dom"]),
    remotion: z.literal(COMPONENT_DEPENDENCIES.remotion),
    "@remotion/bundler": z.literal(COMPONENT_DEPENDENCIES["@remotion/bundler"]),
    "@remotion/renderer": z.literal(COMPONENT_DEPENDENCIES["@remotion/renderer"]),
  }).strict(),
  code: z.string().min(1).max(24000).optional(),
  project: remotionProjectSchema.optional(),
  parameters: z.record(scalarParameter).superRefine((parameters, ctx) => {
    const entries = Object.entries(parameters);
    if (entries.length > 24) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "at most 24 parameters" });
    }
    for (const [key, value] of entries) {
      if (!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(key)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `invalid parameter key: ${key}` });
      }
      if (typeof value === "string" && /https?:\/\/|\bdata:/i.test(value)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${key} is not a fixed resource` });
      }
    }
  }),
  resources: z.array(fixedResourceSchema).max(MAX_FIXED_RESOURCES),
  output: componentOutputSchema,
}).strict().superRefine((request, ctx) => {
  if ((request.code === undefined) === (request.project === undefined)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "exactly one complete project or historical code source is required" });
  }
  if (request.project && Object.keys(request.parameters).length > 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "complete projects carry values in project.props" });
  }
  const paths = request.resources.map(({ path }) => path);
  if (new Set(paths).size !== paths.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "resource paths must be unique" });
  }
});

export type ComponentBakeRequest = z.infer<typeof componentBakeRequestSchema>;
export type RemotionProject = z.infer<typeof remotionProjectSchema>;
export type ProjectFile = z.infer<typeof projectFileSchema>;

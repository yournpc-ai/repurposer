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

const scalarParameter = z.union([
  z.string().max(128),
  z.number().finite(),
  z.boolean(),
]);

export const componentOutputSchema = z.object({
  width: z.number().int().min(16).max(1920),
  height: z.number().int().min(16).max(1920),
  fps: z.number().int().positive().max(60),
  duration_frames: z.number().int().positive().max(180),
  background: z.string().regex(/^#[0-9a-fA-F]{6}$/),
}).strict().superRefine((output, ctx) => {
  if (output.width % 2 || output.height % 2) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "raster dimensions must be even" });
  }
});

export const componentBakeRequestSchema = z.object({
  runtime: z.literal("component-v1"),
  program_digest: z.string().regex(/^[0-9a-f]{64}$/),
  dependencies: z.object({
    react: z.literal(COMPONENT_DEPENDENCIES.react),
    "react-dom": z.literal(COMPONENT_DEPENDENCIES["react-dom"]),
    remotion: z.literal(COMPONENT_DEPENDENCIES.remotion),
    "@remotion/bundler": z.literal(COMPONENT_DEPENDENCIES["@remotion/bundler"]),
    "@remotion/renderer": z.literal(COMPONENT_DEPENDENCIES["@remotion/renderer"]),
  }).strict(),
  code: z.string().min(1).max(24000),
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
  output: componentOutputSchema,
}).strict();

export type ComponentBakeRequest = z.infer<typeof componentBakeRequestSchema>;

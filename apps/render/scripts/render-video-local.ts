/**
 * Render one video-spec JSON to MP4 locally — the same `renderVideo` code
 * path the HTTP service (/render, family="video" fork) uses, minus the
 * queue / presigned-URL dance. For render debugging and the phase-A
 * vertical-slice verification.
 *
 *   pnpm tsx scripts/render-video-local.ts <spec.json> <outDir> [basename]
 *
 * The spec's source URLs must be fetchable by this machine. For fully local
 * fixtures, pass file paths via a tiny static server: prefix the JSON's
 * storage keys with a served base URL before writing the spec.
 */
import fs from "node:fs/promises";
import path from "node:path";

import { videoSpecSchema } from "@repurposer/video-spec";

import { renderVideo } from "../src/video";

const [specPath, outDir, basename = "video"] = process.argv.slice(2);
if (!specPath || !outDir) {
  console.error("usage: pnpm tsx scripts/render-video-local.ts <spec.json> <outDir> [basename]");
  process.exit(1);
}

const raw = JSON.parse(await fs.readFile(specPath, "utf8"));
const parsed = videoSpecSchema.safeParse(raw);
if (!parsed.success) {
  console.error("invalid video spec:", parsed.error.issues);
  process.exit(1);
}

const { videoPath } = await renderVideo(parsed.data, path.resolve(outDir), basename);
console.log(`video: ${videoPath}`);

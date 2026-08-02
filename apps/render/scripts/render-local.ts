/**
 * Render one clip-spec JSON to MP4+SRT locally — same `renderClip` code path
 * the HTTP service (/render) uses, minus the queue / presigned-URL dance.
 * For asset authoring (e.g. landing demo videos) and render debugging.
 *
 *   pnpm tsx scripts/render-local.ts <spec.json> <outDir> [basename]
 */
import fs from "node:fs/promises";
import path from "node:path";

import type { ClipSpec } from "@repurposer/clip";

import { renderClip } from "../src/render";

const [specPath, outDir, basename = "clip"] = process.argv.slice(2);
if (!specPath || !outDir) {
  console.error("usage: pnpm tsx scripts/render-local.ts <spec.json> <outDir> [basename]");
  process.exit(1);
}

const spec = JSON.parse(await fs.readFile(specPath, "utf8")) as ClipSpec;
const { videoPath, srtPath } = await renderClip(spec, path.resolve(outDir), basename);
console.log(`video: ${videoPath}`);
console.log(`srt: ${srtPath}`);

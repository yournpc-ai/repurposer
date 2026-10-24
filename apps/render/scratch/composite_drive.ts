/**
 * Composite-acceptance render driver (scratch — not shipped): serves the
 * fixture dir + the staging cache over ONE loopback port (RENDER_PORT must
 * be set to the same port from the shell, so stage.ts's toLoopbackUrl points
 * here), then renders every spec in the manifest through the REAL
 * renderFilm (own bundle — the running 3001 service is never touched).
 *
 * Usage: RENDER_PORT=8799 npx tsx scratch/composite_drive.ts <specsDir> <outDir> [name ...]
 */
import fs from "node:fs";
import path from "node:path";

import express from "express";

import { renderFilm } from "../src/film/render";
import { filmSpecSchema } from "../src/film/schema";
import { CACHE_DIR } from "../src/stage";

const PORT = Number(process.env.RENDER_PORT ?? 8799);
const specsDir = path.resolve(process.argv[2]);
const outDir = path.resolve(process.argv[3]);
const only = new Set(process.argv.slice(4));

async function main() {
  const app = express();
  // The staging loopback (stage.ts /cache/*) + the fixture sources.
  app.use("/cache", express.static(CACHE_DIR));
  app.use("/fixture", express.static(path.dirname(specsDir)));
  await new Promise<void>((resolve) => {
    app.listen(PORT, "127.0.0.1", () => resolve());
  });
  console.log(`fixture+cache server on 127.0.0.1:${PORT}`);

  const names = fs
    .readdirSync(specsDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .filter((n) => only.size === 0 || only.has(n));

  for (const name of names) {
    const raw = JSON.parse(fs.readFileSync(path.join(specsDir, `${name}.json`), "utf8"));
    // Mirror server.ts's seat: parse through the schema so defaults
    // materialize (raw JSON props carry no zod defaults).
    const spec = filmSpecSchema.parse(raw);
    const started = Date.now();
    const result = await renderFilm(spec, outDir, name);
    console.log(`rendered ${name} → ${result.videoPath} (${((Date.now() - started) / 1000).toFixed(1)}s)`);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

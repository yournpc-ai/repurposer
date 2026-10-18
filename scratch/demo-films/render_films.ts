// Offline demo film renderer (ADR-120 E3 货架片): reads the absolutized
// film-specs from ./specs/ and renders each with the REAL renderer
// (renderFilm — same seat the render service uses) into ./out/.
import path from "node:path";
import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { renderFilm } from "../../apps/render/src/film/render";
import { filmSpecSchema } from "../../apps/render/src/film/schema";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, "out");

async function main() {
  for (const aspect of ["16x9", "1x1", "9x16"]) {
    const spec = filmSpecSchema.parse(
      JSON.parse(await fs.readFile(path.join(here, "specs", `film-${aspect}.json`), "utf8")),
    );
    console.log(`rendering ${aspect} (${spec.scenes.length} scenes)…`);
    const t0 = Date.now();
    const { videoPath } = await renderFilm(spec, outDir, `film-${aspect}`);
    console.log(`  → ${videoPath} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

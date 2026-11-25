import { writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";

const root = new URL("../", import.meta.url);
const require = createRequire(new URL("packages/sound-engine/package.json", root));
const { tsImport } = require("tsx/esm/api");
const { SOUND_RECIPES, SOUND_ENGINE_VERSION, TUNE_SCHEMA, synthesizeWav } =
  await tsImport(new URL("packages/sound-engine/src/index.ts", root).href, import.meta.url);
const audit = new URL("scratch/sound-engine-v3-audit/", root);
const withAudit = process.argv.includes("--audit");
if (withAudit) await mkdir(audit, { recursive: true });
const examples = new Set(["tap_glass", "tap_wood", "stinger_tech", "stinger_marimba", "impact_metal_cold",
  "riser_snap_half", "trans_tape_stop", "trans_vinyl_pull", "glitch_data", "whoosh_micro"]);
const recipes = {};
const acoustics = {};
const report = {};
for (const recipe of SOUND_RECIPES) {
  const input = { recipeId: recipe.id };
  const normal = synthesizeWav(input);
  recipes[recipe.id] = recipe;
  acoustics[recipe.id] = normal.acoustics;
  if (!withAudit) continue;
  if (examples.has(recipe.id)) await writeFile(new URL(recipe.id + ".wav", audit), normal.wav);
  const stretch = {};
  for (const scale of [0.5, 1, 2]) {
    const take = scale === 1 ? normal : synthesizeWav({ ...input, tune: { length_scale: scale } });
    const { duration_ms, peak_offset_ms, lufs, spectral_centroid_hz, peak_dbfs } = take.acoustics;
    stretch[scale] = { duration_ms, peak_offset_ms, lufs, spectral_centroid_hz, peak_dbfs };
    if (scale !== 1 && recipe.id === "whoosh_micro")
      await writeFile(new URL("whoosh_micro_" + scale + "x.wav", audit), take.wav);
  }
  report[recipe.id] = { domain: recipe.domain, category: recipe.category, ...stretch[1], stretch };
}
const json = data => JSON.stringify(data, null, 2) + "\n";
await writeFile(new URL("apps/api/app/catalog/sound_engine_catalog.json", root),
  json({ engine_version: SOUND_ENGINE_VERSION, tune_schema: TUNE_SCHEMA, recipes, acoustics }));
if (withAudit) await writeFile(new URL("catalog_acoustics_report.json", audit), json(report));

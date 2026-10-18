import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
import fs from "node:fs/promises";
import { renderFilm } from "../../apps/render/src/film/render";
import { filmSpecSchema } from "../../apps/render/src/film/schema";

async function main() {
  const spec = filmSpecSchema.parse(
    JSON.parse(await fs.readFile(path.join(here, "specs", "smoke-plate.json"), "utf8")),
  );
  const { videoPath } = await renderFilm(spec, path.join(here, "out"), "smoke-plate");
  console.log("→", videoPath);
}
main().catch((e) => { console.error(e); process.exit(1); });

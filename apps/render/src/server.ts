import path from "node:path";

import type { ClipSpec } from "@repurposer/clip";
import express from "express";

import { renderClip } from "./render";

const app = express();
app.use(express.json({ limit: "8mb" }));

const PORT = Number(process.env.RENDER_PORT ?? 3001);
// Shared output dir — the api serves these files via its Range endpoint.
// Defaults to the repo's assets (relative to apps/render cwd) so rendered
// outputs share the user-scoped layout with the API.
const OUTPUT_DIR =
  process.env.RENDER_OUTPUT_DIR ?? path.resolve(process.cwd(), "../../assets");

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

/**
 * Black-box render endpoint: clip-spec in -> MP4 + SRT out.
 * Body: { spec, out_subdir?, basename? }. Returns paths relative to OUTPUT_DIR
 * so the api can map them onto its stream URL (storage seam).
 */
app.post("/render", async (req, res) => {
  const { spec, out_subdir, basename } = req.body as {
    spec?: ClipSpec;
    out_subdir?: string;
    basename?: string;
  };

  const src = spec?.source;
  // Renderable if: video/stills with a media URL, or stills with backing images
  // (a no-audio slideshow has url="" and relies on image_urls).
  const renderable =
    src && (src.kind === "stills" ? (src.image_urls?.length ?? 0) > 0 || !!src.url : !!src.url);
  if (!renderable) {
    res.status(400).json({ error: "spec.source needs a url (video/audio) or image_urls (stills)" });
    return;
  }

  try {
    const outDir = path.join(OUTPUT_DIR, out_subdir ?? "clips");
    const name = basename ?? `clip-${Date.now()}`;
    const { videoPath, srtPath } = await renderClip(spec, outDir, name);
    res.json({
      video: path.relative(OUTPUT_DIR, videoPath),
      srt: path.relative(OUTPUT_DIR, srtPath),
    });
  } catch (err) {
    console.error("render_failed", err);
    res.status(500).json({ error: String(err) });
  }
});

app.listen(PORT, () => {
  console.log(`[render] Remotion render service on http://localhost:${PORT}`);
});

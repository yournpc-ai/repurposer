import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

import type { ClipSpec } from "@repurposer/clip";
import express from "express";

import { renderClip } from "./render";

const app = express();
app.use(express.json({ limit: "8mb" }));

const PORT = Number(process.env.RENDER_PORT ?? 3001);

async function uploadFile(url: string, filePath: string, contentType?: string) {
  const buffer = await fs.readFile(filePath);
  const headers: Record<string, string> = {};
  if (contentType) headers["Content-Type"] = contentType;
  const resp = await fetch(url, { method: "PUT", body: buffer, headers });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`Upload failed: ${resp.status} ${body}`);
  }
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

/**
 * Black-box render endpoint: clip-spec in -> MP4 + SRT out.
 * Body: { spec, out_subdir?, basename?, outputs: { video: { key, put_url, content_type? }, srt: { key, put_url, content_type? } } }.
 *
 * The render service renders to a temp dir, PUTs the rendered files to the
 * supplied presigned URLs, and returns the object keys.
 */
app.post("/render", async (req, res) => {
  const { spec, basename, outputs } = req.body as {
    spec?: ClipSpec;
    basename?: string;
    outputs?: {
      video?: { key: string; put_url: string; content_type?: string };
      srt?: { key: string; put_url: string; content_type?: string };
    };
  };

  const src = spec?.source;
  const renderable =
    src && (src.kind === "stills" ? (src.image_urls?.length ?? 0) > 0 || !!src.url : !!src.url);
  if (!renderable) {
    res.status(400).json({ error: "spec.source needs a url (video/audio) or image_urls (stills)" });
    return;
  }

  if (!outputs?.video?.put_url || !outputs?.srt?.put_url) {
    res.status(400).json({ error: "outputs.video.put_url and outputs.srt.put_url are required" });
    return;
  }

  try {
    const outDir = await fs.mkdtemp(path.join(os.tmpdir(), "repurposer-render-"));
    const name = basename ?? `clip-${Date.now()}`;
    const { videoPath, srtPath } = await renderClip(spec, outDir, name);

    await uploadFile(outputs.video.put_url, videoPath, outputs.video.content_type);
    await uploadFile(outputs.srt.put_url, srtPath, outputs.srt.content_type);
    await fs.rm(outDir, { recursive: true, force: true }).catch(() => {});

    res.json({
      ok: true,
      video: outputs.video.key,
      srt: outputs.srt.key,
    });
  } catch (err) {
    console.error("render_failed", err);
    res.status(500).json({ error: String(err) });
  }
});

app.listen(PORT, () => {
  console.log(`[render] Remotion render service on http://localhost:${PORT}`);
});

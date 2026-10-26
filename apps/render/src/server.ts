import type { ClipSpec } from "@repurposer/clip";
import express from "express";

import { renderFilm } from "./film/render";
import { filmSpecSchema, filmTotalFrames } from "./film/schema";
import { renderClip } from "./render";
import { CACHE_DIR } from "./stage";
import { renderArtifacts, cachedArtifacts, ArtifactCacheMiss } from "./artifacts";
import type { Artifacts } from "./artifacts";
import { uploadFile, UploadError } from "./upload";

const app = express();
app.use(express.json({ limit: "8mb" }));

// Locally staged sources (see stage.ts), served back to Remotion over
// loopback. CORS "*" because the composition's <Audio> fetches the staged URL
// from the bundle-server origin.
app.use(
  "/cache",
  (_req, res, next) => {
    res.setHeader("access-control-allow-origin", "*");
    next();
  },
  express.static(CACHE_DIR),
);

const PORT = Number(process.env.RENDER_PORT ?? 3001);

// Film family resource cap (config): total storyboard frames allowed per
// render. fps is fixed at 30, so this is also the duration cap — the default
// 3600 = 120 s @ 30 fps.
const FILM_MAX_FRAMES = Number(process.env.FILM_MAX_FRAMES ?? 3600);

async function artifactsForRequest(
  identity: unknown,
  uploadOnly: boolean,
  render: (directory: string) => Promise<Artifacts>,
): Promise<Artifacts> {
  if (!uploadOnly) return renderArtifacts(identity, render);
  const cached = await cachedArtifacts(identity);
  if (!cached) throw new ArtifactCacheMiss();
  return cached;
}

function failureBody(err: unknown) {
  if (err instanceof ArtifactCacheMiss) {
    return {
      status: 409,
      body: {
        error: "Rendered files are no longer cached; render again before uploading",
        stage: "recovery",
        code: "ARTIFACT_CACHE_MISS",
      },
    };
  }
  return {
    status: 500,
    body: {
      error: err instanceof UploadError ? err.message : "Video rendering failed",
      stage: err instanceof UploadError ? "upload" : "render",
      code: err instanceof UploadError ? err.code : "RENDER_FAILED",
    },
  };
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

/**
 * Black-box render endpoint: spec in -> rendered artifacts out.
 * Body: { spec, out_subdir?, basename?, outputs: { video: { key, put_url, content_type? }, srt: { key, put_url, content_type? } } }.
 *
 * The envelope is the shared minimal envelope for both spec families; the
 * `spec` payload is per-family (clip-spec vs film-spec, each with its own
 * schema). Dispatch reads only `spec.family` ("film" -> film path; absent ->
 * clip path) — never node type/name or any out-of-spec field. Every
 * lifecycle event (first render / preview / retry / revision / recovery)
 * arrives as this same POST, so this single fork covers the whole lifecycle.
 *
 * The render service renders to a temp dir, PUTs the rendered files to the
 * supplied presigned URLs, and returns the object keys.
 */
app.post("/render", async (req, res) => {
  const { spec, outputs, source_key, render_id, upload_only } = req.body as {
    render_id?: string;
    upload_only?: boolean;
    spec?: ClipSpec;
    basename?: string;
    outputs?: {
      video?: { key: string; put_url: string; content_type?: string };
      srt?: { key: string; put_url: string; content_type?: string };
    };
    // Optional object-store key of spec.source.url (envelope field, never
    // clip-spec) — indexes the shared source cache (see stage.ts).
    source_key?: string;
  };

  // --- film family fork ---------------------------------------------------
  if ((spec as unknown as { family?: unknown } | undefined)?.family === "film") {
    const parsed = filmSpecSchema.safeParse(spec);
    if (!parsed.success) {
      const issues = parsed.error.issues
        .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
        .join("; ");
      res.status(400).json({ error: `invalid film spec: ${issues}` });
      return;
    }

    // A film renders to video alone (no caption track -> no SRT artifact).
    if (!outputs?.video?.put_url) {
      res.status(400).json({ error: "outputs.video.put_url is required" });
      return;
    }

    const totalFrames = filmTotalFrames(parsed.data);
    if (totalFrames > FILM_MAX_FRAMES) {
      res
        .status(400)
        .json({ error: `film spec total frames ${totalFrames} exceeds cap ${FILM_MAX_FRAMES}` });
      return;
    }

    try {
      const { videoPath } = await artifactsForRequest(
        { id: render_id ?? outputs.video.key, spec: parsed.data },
        upload_only === true,
        (outDir) => renderFilm(parsed.data, outDir, "video"),
      );

      await uploadFile(outputs.video.put_url, videoPath, outputs.video.content_type);

      res.json({ ok: true, video: outputs.video.key });
    } catch (err) {
      console.error("film_render_failed", { render_id, error: err });
      const failure = failureBody(err);
      res.status(failure.status).json(failure.body);
    }
    return;
  }

  // --- clip family (existing path, unchanged) -----------------------------
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
    const { videoPath, srtPath } = await artifactsForRequest(
      { id: render_id ?? outputs.video.key, spec, source_key },
      upload_only === true,
      (outDir) => renderClip(spec, outDir, "video", source_key),
    );

    await uploadFile(outputs.video.put_url, videoPath, outputs.video.content_type);
    if (srtPath && outputs.srt?.put_url) {
      await uploadFile(outputs.srt.put_url, srtPath, outputs.srt.content_type);
    }

    res.json({
      ok: true,
      video: outputs.video.key,
      ...(srtPath && outputs.srt ? { srt: outputs.srt.key } : {}),
    });
  } catch (err) {
    console.error("render_failed", { render_id, error: err });
    const failure = failureBody(err);
    res.status(failure.status).json(failure.body);
  }
});

app.listen(PORT, () => {
  console.log(`[render] Remotion render service on http://localhost:${PORT}`);
});

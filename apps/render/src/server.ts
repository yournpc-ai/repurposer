import { videoSpecSchema, type VideoSpec } from "@repurposer/video-spec";
import express from "express";

import { CACHE_DIR } from "./stage";
import { renderArtifacts, cachedArtifacts, ArtifactCacheMiss } from "./artifacts";
import type { Artifacts } from "./artifacts";
import { uploadFile, UploadError } from "./upload";
import { renderVideo } from "./video";
import {
  bakeComponent,
  componentBakeEnabled,
  componentIsolation,
  ComponentBakeError,
} from "./component-runtime/bake";
import { componentBakeRequestSchema } from "./component-runtime/contract";

const app = express();

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

// Video family resource cap (same role, separate dial): the spec carries its
// own fps, so this is a pure frame budget, not a seconds claim.
const VIDEO_MAX_FRAMES = Number(process.env.VIDEO_MAX_FRAMES ?? 3600);

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
  res.json({
    status: "ok",
    component_bake: {
      enabled: componentBakeEnabled(),
      isolation: componentIsolation(),
      max_concurrency: 1,
    },
  });
});

// Upstream controlled Generator bake. This is deliberately separate from the
// renderer-neutral /render endpoint: authored TSX never enters a video-spec.
// Static source diagnostics are not a security boundary, so the route is
// fail-closed until a deployment supplies actual runner isolation.
app.post("/component-bake", express.json({ limit: "64mb" }), async (req, res) => {
  if (!componentBakeEnabled()) {
    res.status(503).json({
      error: "remotion-project bake is unavailable: no verified isolated component runner",
      code: "COMPONENT_RUNNER_UNAVAILABLE",
    });
    return;
  }
  const parsed = componentBakeRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; "),
      code: "INVALID_COMPONENT_REQUEST",
    });
    return;
  }
  try {
    const result = await bakeComponent(parsed.data);
    res.json(result);
  } catch (error) {
    console.error("component_bake_failed", { program_digest: parsed.data.program_digest, error });
    const message = error instanceof Error ? error.message.slice(-4000) : "Component bake failed";
    res.status(error instanceof ComponentBakeError ? 422 : 500).json({
      error: message,
      code: "COMPONENT_BAKE_FAILED",
      source_repairable: error instanceof ComponentBakeError ? error.sourceRepairable : false,
    });
  }
});

app.use(express.json({ limit: "8mb" }));

// Bounded working-draft evidence only: the API has already sliced and pinned
// the spec. This path neither uploads nor creates an Output or saved version.
app.post("/preview", async (req, res) => {
  const parsed = videoSpecSchema.safeParse(req.body?.spec);
  if (!parsed.success) {
    res.status(400).json({ error: "invalid preview video spec" });
    return;
  }
  if (parsed.data.family !== "video" || parsed.data.duration_frames > 720) {
    res.status(422).json({ error: "a working-draft preview is limited to 720 frames" });
    return;
  }
  try {
    const { videoPath } = await renderArtifacts(
      { preview: parsed.data },
      (outDir) => renderVideo(parsed.data, outDir, "video"),
    );
    res.type("video/mp4").sendFile(videoPath);
  } catch (err) {
    console.error("video_preview_failed", { error: err });
    res.status(500).json({ error: "Working-draft preview rendering failed" });
  }
});

// The only render contract is video-spec. Upload-only recovery never renders on cache miss.
app.post(["/render", "/prepare-export", "/upload"], async (req, res) => {
  if (req.path === "/upload") req.body.upload_only = true;
  const { spec, outputs, render_id, upload_only } = req.body as {
    render_id?: string;
    upload_only?: boolean;
    spec?: VideoSpec;
    outputs?: { video?: { key: string; put_url: string; content_type?: string; create_only?: boolean; upload_id?: string } };
  };
  const parsed = videoSpecSchema.safeParse(spec);
  if (!parsed.success || parsed.data.family !== "video") {
    res.status(400).json({ error: "a valid video-spec is required" });
    return;
  }
  const prepareOnly = req.path === "/prepare-export";
  if (prepareOnly && !render_id) {
    res.status(400).json({ error: "A render identity is required" });
    return;
  }
  if (!prepareOnly && !outputs?.video?.put_url) {
    res.status(400).json({ error: "outputs.video.put_url is required" });
    return;
  }
  if (parsed.data.duration_frames > VIDEO_MAX_FRAMES) {
    res.status(400).json({ error: `video spec ${parsed.data.duration_frames} frames exceeds cap ${VIDEO_MAX_FRAMES}` });
    return;
  }
  try {
    const { videoPath } = await artifactsForRequest(
      { id: render_id ?? outputs!.video!.key, spec: parsed.data },
      upload_only === true,
      (outDir) => renderVideo(parsed.data, outDir, "video"),
    );
    if (prepareOnly) {
      res.json({ ready: true, single_put: true, upload_identity: true });
      return;
    }
    const video = outputs!.video!;
    await uploadFile(video.put_url, videoPath, video.content_type, video.create_only, video.upload_id);
    res.json({ ok: true, video: video.key });
  } catch (err) {
    console.error("video_render_failed", { render_id, error: err });
    const failure = failureBody(err);
    res.status(failure.status).json(failure.body);
  }
});

app.listen(PORT, () => {
  console.log(`[render] Remotion render service on http://localhost:${PORT}`);
});

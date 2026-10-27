// Video family render driver — the video-spec peer of film/render.ts.
// Reuses the shared staging cache (../stage) and the clip path's loudnorm
// post-pass (../render), bundles its own entry (./remotion/entry.tsx).
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import type { VideoSpec } from "@repurposer/video-spec";

import { normalizeLoudness } from "../render";
import { stageRemoteSource } from "../stage";
import { assertVideoSupported } from "./capabilities";

let videoBundlePromise: Promise<string> | null = null;
function getVideoBundle(): Promise<string> {
  if (!videoBundlePromise) {
    const entryPoint = fileURLToPath(new URL("./remotion/entry.tsx", import.meta.url));
    videoBundlePromise = bundle({ entryPoint });
  }
  return videoBundlePromise;
}

export interface VideoRenderResult {
  videoPath: string;
}

/**
 * Render one video-spec to MP4. Every source URL must already be absolute
 * (the API dispatch seam absolutizes storage keys) — the renderer never
 * resolves relative keys.
 */
export async function renderVideo(
  spec: VideoSpec,
  outDir: string,
  basename: string,
): Promise<VideoRenderResult> {
  assertVideoSupported(spec);
  await fs.mkdir(outDir, { recursive: true });

  // Stage remote sources into the shared local cache first (the film path's
  // law: Remotion's internal asset fetch ignores HTTPS_PROXY and downloads
  // inside the delayRender budget). Dedup per URL is stageRemoteSource's.
  const stagedSpec: VideoSpec = {
    ...spec,
    fonts: await Promise.all(
      spec.fonts.map(async (font) => ({
        ...font,
        url: await stageRemoteSource(font.url, undefined, font.digest),
      })),
    ),
    tracks: await Promise.all(
      spec.tracks.map(async (track) => ({
        ...track,
        clips: await Promise.all(
          track.clips.map(async (clip) =>
            clip.source
              ? {
                  ...clip,
                  source: {
                    ...clip.source,
                    url: await stageRemoteSource(clip.source.url, undefined, clip.source.digest),
                  },
                }
              : clip,
          ),
        ),
      })),
    ),
  };

  const serveUrl = await getVideoBundle();
  const inputProps = { spec: stagedSpec };
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });

  const videoPath = path.join(outDir, `${basename}.mp4`);
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
    timeoutInMilliseconds: 180_000,
  });

  // Loudness is an enhancement, not correctness — never fail a finished
  // render over the post-pass (the clip path's law).
  try {
    await normalizeLoudness(videoPath);
  } catch (err) {
    console.error("video loudnorm post-pass failed, keeping original audio:", err);
  }

  return { videoPath };
}

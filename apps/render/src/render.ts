import { createRequire } from "node:module";
import fs from "node:fs/promises";
import path from "node:path";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { type ClipSpec, keptSegments } from "@repurposer/clip";

import { captionTrackToSrt } from "./srt";

const require = createRequire(import.meta.url);

// Bundle the Remotion project once and reuse it across renders.
let bundlePromise: Promise<string> | null = null;
function getBundle(): Promise<string> {
  if (!bundlePromise) {
    const entryPoint = require.resolve("@repurposer/clip/remotion-entry");
    bundlePromise = bundle({ entryPoint });
  }
  return bundlePromise;
}

export interface RenderResult {
  videoPath: string;
  srtPath: string;
}

/**
 * Render one clip-spec to MP4 + SRT. The spec's `source.url` must be an absolute
 * URL the render process can fetch (the api worker absolutizes the stored
 * relative stream URL before calling — see docs/VIDEO_EDITOR.md storage seam).
 */
export async function renderClip(
  spec: ClipSpec,
  outDir: string,
  basename: string,
): Promise<RenderResult> {
  await fs.mkdir(outDir, { recursive: true });

  const serveUrl = await getBundle();
  const inputProps = { spec };
  const composition = await selectComposition({ serveUrl, id: "Clip", inputProps });

  const videoPath = path.join(outDir, `${basename}.mp4`);
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
    // OffthreadVideo extracts frames by fetching the remote source through
    // Remotion's internal asset proxy; slow origin range responses (observed
    // 3-6 s/MB from TOS) can exceed the 28 s delayRender default and abort
    // the whole render. Give slow origins room; the HTTP client timeout
    // upstream (900 s) still bounds the real failure case.
    timeoutInMilliseconds: 180_000,
  });

  const clipStart = keptSegments(spec)[0]?.start ?? 0;
  const srtPath = path.join(outDir, `${basename}.srt`);
  await fs.writeFile(srtPath, captionTrackToSrt(spec.caption_track, clipStart), "utf8");

  return { videoPath, srtPath };
}

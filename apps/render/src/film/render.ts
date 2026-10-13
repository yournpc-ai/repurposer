// Film family render driver — the film-spec peer of render.ts's clip path.
// render.ts / srt.ts / stage.ts are untouched; this module REUSES the shared
// staging cache (stage.ts) and bundles its own entry (film/entry.tsx).
//
// A film has no caption track and no audio bed, so there is no SRT artifact
// and no loudness pass — the output of a film render is the MP4 alone.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

import { stageRemoteSource } from "../stage";
import type { FilmSpec } from "./schema";

// Bundle the film entry once and reuse it across renders (same law as the
// clip bundle in render.ts).
let filmBundlePromise: Promise<string> | null = null;
function getFilmBundle(): Promise<string> {
  if (!filmBundlePromise) {
    const entryPoint = fileURLToPath(new URL("./entry.tsx", import.meta.url));
    filmBundlePromise = bundle({ entryPoint });
  }
  return filmBundlePromise;
}

export interface FilmRenderResult {
  videoPath: string;
}

/**
 * Render one film-spec to MP4. Every remote reference (`ui.image` screenshots,
 * `end.logo_url`) must already be an absolute URL — the renderer never
 * resolves relative keys (the baking seam upstream absolutizes them).
 */
export async function renderFilm(
  spec: FilmSpec,
  outDir: string,
  basename: string,
): Promise<FilmRenderResult> {
  await fs.mkdir(outDir, { recursive: true });

  // Stage scene imagery into the shared local cache first — Remotion's
  // internal asset fetch ignores HTTPS_PROXY and downloads inside the
  // delayRender budget (the exact trap stage.ts was written for). Dedup per
  // URL is inherited from stageRemoteSource.
  const stagedScenes = await Promise.all(
    spec.scenes.map(async (s) => {
      if (s.type === "ui") {
        return { ...s, image: await stageRemoteSource(s.image) };
      }
      if (s.type === "end" && s.logo_url) {
        return { ...s, logo_url: await stageRemoteSource(s.logo_url) };
      }
      return s;
    }),
  );
  const stagedSpec: FilmSpec = { ...spec, scenes: stagedScenes };

  const serveUrl = await getFilmBundle();
  const inputProps = { spec: stagedSpec };
  const composition = await selectComposition({ serveUrl, id: "Film", inputProps });

  const videoPath = path.join(outDir, `${basename}.mp4`);
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
    // All remote imagery is staged locally by now, so Remotion only fetches
    // loopback URLs — but keep the same headroom as the clip path for slow
    // compositor startups.
    timeoutInMilliseconds: 180_000,
  });

  return { videoPath };
}

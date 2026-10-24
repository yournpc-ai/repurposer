// Film family render driver — the film-spec peer of render.ts's clip path.
// render.ts / srt.ts / stage.ts are untouched; this module REUSES the shared
// staging cache (stage.ts) and bundles its own entry (film/entry.tsx).
//
// A film's captions are burned into the picture from the narration cue list,
// so there is no SRT artifact — but it DOES carry audio (the narration
// voiceover + the music bed, ADR-130), so the clip path's loudnorm
// post-pass applies verbatim (shared seat, exported from ../render).
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

import { normalizeLoudness } from "../render";
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

  // Stage scene imagery + audio into the shared local cache first —
  // Remotion's internal asset fetch ignores HTTPS_PROXY and downloads inside
  // the delayRender budget (the exact trap stage.ts was written for). Dedup
  // per URL is inherited from stageRemoteSource.
  const stagedScenes = await Promise.all(
    spec.scenes.map(async (s) => {
      const audio = s.audio ? await stageRemoteSource(s.audio) : s.audio;
      if (s.type === "ui") {
        return { ...s, image: await stageRemoteSource(s.image), audio };
      }
      if (s.type === "composite") {
        // ADR-140: stage each media element's src (text elements carry no
        // bytes); dedup per URL is inherited from stageRemoteSource.
        const elements = await Promise.all(
          s.elements.map(async (el) =>
            el.kind === "text" ? el : { ...el, src: await stageRemoteSource(el.src) },
          ),
        );
        return { ...s, elements, audio };
      }
      if (s.type === "end") {
        const logo_url = s.logo_url ? await stageRemoteSource(s.logo_url) : s.logo_url;
        return { ...s, logo_url, audio };
      }
      return audio === s.audio ? s : { ...s, audio };
    }),
  );
  const stagedSpec: FilmSpec = {
    ...spec,
    scenes: stagedScenes,
    ...(spec.music
      ? { music: { ...spec.music, url: await stageRemoteSource(spec.music.url) } }
      : {}),
  };

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

  // Loudness is an enhancement, not correctness (the clip path's law) —
  // never fail a finished render over the post-pass.
  try {
    await normalizeLoudness(videoPath);
  } catch (err) {
    console.error("film loudnorm post-pass failed, keeping original audio:", err);
  }

  return { videoPath };
}

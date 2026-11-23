// Video family render driver for video-spec.
// Reuses the shared staging cache and audio post-pass, with its own video-spec entry.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import type { VideoSpec } from "@repurposer/video-spec";

import { encodeBaselineMp4, InvalidAudioClock, normalizeLoudness } from "../audio";
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

export type StageSourceFn = (
  url: string,
  cacheKey?: string,
  expectedSha256?: string,
) => Promise<string>;

/**
 * Stage all remote fonts, clip sources, and MotionBlock resources into the
 * shared local loopback cache so Chromium/Remotion never hits external URLs
 * directly inside delayRender.
 */
export async function stageVideoSpecSources(
  spec: VideoSpec,
  stageFn: StageSourceFn = stageRemoteSource,
): Promise<VideoSpec> {
  return {
    ...spec,
    fonts: await Promise.all(
      spec.fonts.map(async (font) => ({
        ...font,
        url: await stageFn(font.url, undefined, font.digest),
      })),
    ),
    tracks: await Promise.all(
      spec.tracks.map(async (track) => ({
        ...track,
        clips: await Promise.all(
          track.clips.map(async (clip) => {
            const stagedSource = clip.source
              ? {
                  ...clip.source,
                  url: await stageFn(clip.source.url, undefined, clip.source.digest),
                }
              : clip.source;
            if (clip.object.kind === "motion_block" && clip.object.resources.length > 0) {
              const stagedResources = await Promise.all(
                clip.object.resources.map(async (resource) => ({
                  ...resource,
                  url: await stageFn(resource.url, undefined, resource.digest),
                })),
              );
              return {
                ...clip,
                source: stagedSource,
                object: {
                  ...clip.object,
                  resources: stagedResources,
                },
              };
            }
            return stagedSource !== clip.source ? { ...clip, source: stagedSource } : clip;
          }),
        ),
      })),
    ),
  };
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

  // Stage remote sources into the shared local cache first (the renderer's
  // law: Remotion's internal asset fetch ignores HTTPS_PROXY and downloads
  // inside the delayRender budget). Dedup per URL is stageRemoteSource's.
  const stagedSpec = await stageVideoSpecSources(spec);

  const serveUrl = await getVideoBundle();
  const inputProps = { spec: stagedSpec };
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });

  const videoPath = path.join(outDir, `${basename}.mp4`);
  const hasSoundSource = stagedSpec.tracks.some((track) =>
    track.clips.some(({ object }) =>
      object.kind === "audio" || (object.kind === "video" && !object.muted),
    ),
  );
  const work = await fs.mkdtemp(path.join(outDir, ".encode-"));
  const baseline = path.join(work, "baseline.mp4");
  const intermediate = path.join(work, "mix.mov");
  try {
    // Keep Remotion's PCM mix intact until the MP4 muxer can record AAC priming.
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      ...(hasSoundSource ? { audioCodec: "pcm-16" as const } : { muted: true }),
      // The parallel pre-stitcher writes video only. Preserve its frame clock until MOV stitching.
      ffmpegOverride: ({ type, args }) => type === "pre-stitcher" && hasSoundSource
        ? [...args.slice(0, -1), "-f", "mp4", args[args.length - 1]]
        : args,
      outputLocation: hasSoundSource ? intermediate : baseline,
      inputProps,
      timeoutInMilliseconds: 180_000,
    });
    if (hasSoundSource) {
      await encodeBaselineMp4(intermediate, baseline);
      await fs.unlink(intermediate);
    }
    // Optional loudness processing may fall back only to a completed MP4.
    try {
      const expectedSamples = Math.round(composition.durationInFrames * 48000 / composition.fps);
      await normalizeLoudness(baseline, expectedSamples, { requireAudio: hasSoundSource });
    } catch (err) {
      if (err instanceof InvalidAudioClock) throw err;
      console.error("video loudnorm post-pass failed, keeping original audio:", err);
    }
    await fs.rename(baseline, videoPath);
  } finally {
    await fs.rm(work, { recursive: true, force: true });
  }

  return { videoPath };
}

import { createRequire } from "node:module";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import path from "node:path";

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { type ClipSpec, keptSegments } from "@repurposer/clip";

import { captionTrackToSrt } from "./srt";
import { stageRemoteSource } from "./stage";

const require = createRequire(import.meta.url);
const execFileAsync = promisify(execFile);

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

  // Stage the remote source into the local cache first — Remotion's internal
  // asset fetch is a raw node:https GET (ignores HTTPS_PROXY, whole-file
  // download inside the frame-extraction budget), so a slow origin surfaces
  // as an opaque delayRender timeout. Our staging fetch is proxy-aware,
  // dedupes per URL across this run's clips, and hands Remotion a loopback
  // URL (see stage.ts).
  const stagedUrl = await stageRemoteSource(spec.source.url);
  const stagedSpec =
    stagedUrl === spec.source.url
      ? spec
      : { ...spec, source: { ...spec.source, url: stagedUrl } };

  const serveUrl = await getBundle();
  const inputProps = { spec: stagedSpec };
  const composition = await selectComposition({ serveUrl, id: "Clip", inputProps });

  const videoPath = path.join(outDir, `${basename}.mp4`);
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
    // The source itself is staged locally before we get here; the remaining
    // remote assets (music / dub / stills images) are MB-scale and still
    // fetched through Remotion's internal proxy, so keep headroom over the
    // 28 s delayRender default for slow origins.
    timeoutInMilliseconds: 180_000,
  });

  const clipStart = keptSegments(spec)[0]?.start ?? 0;
  const srtPath = path.join(outDir, `${basename}.srt`);
  await fs.writeFile(srtPath, captionTrackToSrt(spec.caption_track, clipStart), "utf8");

  try {
    await normalizeLoudness(videoPath);
  } catch (err) {
    // Loudness is an enhancement, not correctness — never fail a finished
    // render over it. Ship the original audio and log.
    console.error("loudnorm post-pass failed, keeping original audio:", err);
  }

  return { videoPath, srtPath };
}

// --- Loudness normalization (EBU R128, -16 LUFS) -------------------------
//
// renderMedia has no loudness API (its audio model is browser mixing, not
// measurement), so the final mix — source voice + background music — is
// normalized here, post-render, with the ffmpeg binary that ships inside
// Remotion's own platform compositor package. Two-pass loudnorm: measure,
// then apply linear gain; the video stream is copied untouched.

const LOUDNORM_TARGET = "I=-16:TP=-1.5:LRA=11";

/** Resolve ffmpeg/ffprobe from Remotion's compositor package, PATH as fallback. */
function resolveFfBinary(bin: "ffmpeg" | "ffprobe"): string {
  const candidates: string[] = [];
  if (process.platform === "darwin") {
    candidates.push(`@remotion/compositor-darwin-${process.arch}`);
  } else if (process.platform === "linux") {
    candidates.push(
      `@remotion/compositor-linux-${process.arch}-gnu`,
      `@remotion/compositor-linux-${process.arch}-musl`,
    );
  } else if (process.platform === "win32") {
    candidates.push("@remotion/compositor-win32-x64-msvc");
  }
  for (const pkg of candidates) {
    try {
      // Only the package matching the host platform is installed (optional
      // deps of @remotion/renderer); the rest fail to resolve.
      const { dir } = require(pkg) as { dir: string };
      return path.join(dir, process.platform === "win32" ? `${bin}.exe` : bin);
    } catch {
      // try the next candidate
    }
  }
  return bin; // PATH fallback
}

/** Spawn options matching Remotion's own callFf: dylibs sit next to the binary. */
function ffSpawnOpts(binPath: string): { cwd: string; env: NodeJS.ProcessEnv } {
  const cwd = path.dirname(binPath);
  const env = { ...process.env };
  if (process.platform === "darwin") {
    env.DYLD_LIBRARY_PATH = cwd;
  }
  return { cwd, env };
}

interface LoudnormMeasure {
  input_i: string;
  input_tp: string;
  input_lra: string;
  input_thresh: string;
  target_offset: string;
}

async function normalizeLoudness(videoPath: string): Promise<void> {
  const ffmpeg = resolveFfBinary("ffmpeg");
  const ffprobe = resolveFfBinary("ffprobe");

  const { stdout: streamType } = await execFileAsync(
    ffprobe,
    [
      "-v", "error",
      "-select_streams", "a:0",
      "-show_entries", "stream=codec_type",
      "-of", "csv=p=0",
      videoPath,
    ],
    ffSpawnOpts(ffprobe),
  );
  if (streamType.trim() !== "audio") {
    return; // silent render (e.g. stills slideshow) — nothing to normalize
  }

  const measure = await execFileAsync(
    ffmpeg,
    [
      "-hide_banner", "-nostats",
      "-i", videoPath,
      "-vn",
      "-af", `loudnorm=${LOUDNORM_TARGET}:print_format=json`,
      "-f", "null", "-",
    ],
    { ...ffSpawnOpts(ffmpeg), maxBuffer: 16 * 1024 * 1024 },
  );
  const jsonStart = measure.stderr.lastIndexOf("{");
  const jsonEnd = measure.stderr.lastIndexOf("}");
  if (jsonStart < 0 || jsonEnd <= jsonStart) {
    throw new Error("loudnorm measure: no JSON block in ffmpeg output");
  }
  const m = JSON.parse(measure.stderr.slice(jsonStart, jsonEnd + 1)) as LoudnormMeasure;
  if (m.input_i === "-inf") {
    return; // effectively silent audio — gain is meaningless
  }

  const filter =
    `loudnorm=${LOUDNORM_TARGET}` +
    `:measured_I=${m.input_i}:measured_TP=${m.input_tp}` +
    `:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}` +
    `:offset=${m.target_offset}:linear=true:print_format=summary`;
  const tmpPath = videoPath.replace(/\.mp4$/, "") + ".loudnorm.mp4";
  await execFileAsync(
    ffmpeg,
    [
      "-y", "-hide_banner", "-nostats",
      "-i", videoPath,
      "-c:v", "copy",
      "-af", filter,
      // loudnorm internally upsamples (AAC caps at 96 kHz); >48 kHz AAC
      // fails to decode in some browsers — pin the universal video rate.
      "-ar", "48000",
      "-c:a", "aac", "-b:a", "192k",
      tmpPath,
    ],
    ffSpawnOpts(ffmpeg),
  );
  await fs.rename(tmpPath, videoPath);
}

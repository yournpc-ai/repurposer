import { createRequire } from "node:module";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import path from "node:path";

const require = createRequire(import.meta.url);
const execFileAsync = promisify(execFile);
const LOUDNORM_TARGET = "I=-16:TP=-1.5:LRA=11";

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
      const { dir } = require(pkg) as { dir: string };
      return path.join(dir, process.platform === "win32" ? `${bin}.exe` : bin);
    } catch {
      // The host's PATH is the fallback for platforms without a compositor package.
    }
  }
  return bin;
}

function ffSpawnOpts(binPath: string): { cwd: string; env: NodeJS.ProcessEnv } {
  const cwd = path.dirname(binPath);
  const env = { ...process.env };
  if (process.platform === "darwin") env.DYLD_LIBRARY_PATH = cwd;
  return { cwd, env };
}

export async function encodeBaselineMp4(input: string, output: string): Promise<void> {
  const ffmpeg = resolveFfBinary("ffmpeg");
  await execFileAsync(
    ffmpeg,
    ["-v", "error", "-i", input, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy",
      "-c:a", "libfdk_aac", "-b:a", "320k", "-cutoff", "18000",
      "-movie_timescale", "48000", "-movflags", "+faststart", output],
    ffSpawnOpts(ffmpeg),
  );
}

interface LoudnormMeasure {
  input_i: string;
  input_tp: string;
  input_lra: string;
  input_thresh: string;
  target_offset: string;
}

export class InvalidAudioClock extends Error {}

export interface VerifyAudioOptions {
  requireAudio?: boolean;
  probe?: (videoPath: string) => Promise<string>;
}

async function defaultProbeAudio(videoPath: string): Promise<string> {
  const ffprobe = resolveFfBinary("ffprobe");
  const { stdout } = await execFileAsync(
    ffprobe,
    ["-v", "error", "-select_streams", "a:0", "-show_entries",
      "stream=sample_rate,time_base,start_pts,duration_ts", "-of", "json", videoPath],
    ffSpawnOpts(ffprobe),
  );
  return stdout;
}

export async function verifyAudioWindow(
  videoPath: string,
  expectedSamples: number,
  stage: "baseline" | "loudnorm",
  options: VerifyAudioOptions = {},
): Promise<boolean> {
  const clockError = (message: string, cause?: unknown): Error =>
    stage === "baseline"
      ? new InvalidAudioClock(message, cause ? { cause } : undefined)
      : new Error(message, cause ? { cause } : undefined);
  const probe = options.probe ?? defaultProbeAudio;
  let timing: string;
  try {
    timing = await probe(videoPath);
  } catch (err) {
    throw clockError(`${stage}: ffprobe failed while verifying audio clock: ${err instanceof Error ? err.message : String(err)}`, err);
  }
  let parsed: { streams?: unknown };
  try {
    parsed = JSON.parse(timing) as { streams?: unknown };
  } catch (err) {
    throw clockError(`${stage}: malformed ffprobe JSON while verifying audio clock`, err);
  }
  if (!parsed || !Array.isArray(parsed.streams)) {
    throw clockError(`${stage}: ffprobe output missing streams array: ${timing.trim()}`);
  }
  const [track] = parsed.streams as Array<Record<string, unknown> | undefined>;
  if (!track && stage === "baseline") {
    if (options.requireAudio) {
      throw clockError(`baseline: expected a zero-based 48 kHz track of ${expectedSamples} samples; got no audio stream`);
    }
    return false;
  }
  if (track?.sample_rate !== "48000" || track.time_base !== "1/48000" || track.start_pts !== 0 ||
      !Number.isSafeInteger(track.duration_ts) || (track.duration_ts as number) <= 0 || track.duration_ts !== expectedSamples) {
    throw clockError(`${stage}: expected a zero-based 48 kHz track of ${expectedSamples} samples; got ${timing.trim()}`);
  }
  return true;
}

export async function normalizeLoudness(
  videoPath: string,
  expectedSamples: number,
  options: { requireAudio?: boolean } = {},
): Promise<void> {
  if (!await verifyAudioWindow(videoPath, expectedSamples, "baseline", options)) return;
  const ffmpeg = resolveFfBinary("ffmpeg");
  const measure = await execFileAsync(
    ffmpeg,
    ["-hide_banner", "-nostats", "-i", videoPath, "-vn", "-af", `loudnorm=${LOUDNORM_TARGET}:print_format=json`, "-f", "null", "-"],
    { ...ffSpawnOpts(ffmpeg), maxBuffer: 16 * 1024 * 1024 },
  );
  const jsonStart = measure.stderr.lastIndexOf("{");
  const jsonEnd = measure.stderr.lastIndexOf("}");
  if (jsonStart < 0 || jsonEnd <= jsonStart) throw new Error("loudnorm measure: no JSON block in ffmpeg output");
  const m = JSON.parse(measure.stderr.slice(jsonStart, jsonEnd + 1)) as LoudnormMeasure;
  if (m.input_i === "-inf") return;
  // Give dynamic loudnorm lookahead past the cut, then keep only the presentation window.
  const trim = `atrim=end_sample=${expectedSamples}`;
  const filter =
    `${trim},apad,loudnorm=${LOUDNORM_TARGET}` +
    `:measured_I=${m.input_i}:measured_TP=${m.input_tp}` +
    `:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}` +
    `:offset=${m.target_offset}:linear=true:print_format=summary,aresample=48000,${trim}`;
  const tmpPath = videoPath.replace(/\.mp4$/, "") + ".loudnorm.mp4";
  await execFileAsync(
    ffmpeg,
    ["-y", "-hide_banner", "-nostats", "-i", videoPath, "-c:v", "copy", "-af", filter,
      "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movie_timescale", "48000", tmpPath],
    ffSpawnOpts(ffmpeg),
  );
  await verifyAudioWindow(tmpPath, expectedSamples, "loudnorm");
  await fs.rename(tmpPath, videoPath);
}

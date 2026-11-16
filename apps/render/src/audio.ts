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

interface LoudnormMeasure {
  input_i: string;
  input_tp: string;
  input_lra: string;
  input_thresh: string;
  target_offset: string;
}

export async function normalizeLoudness(videoPath: string): Promise<void> {
  const ffmpeg = resolveFfBinary("ffmpeg");
  const ffprobe = resolveFfBinary("ffprobe");
  const { stdout: streamType } = await execFileAsync(
    ffprobe,
    ["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", videoPath],
    ffSpawnOpts(ffprobe),
  );
  if (streamType.trim() !== "audio") return;
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
  const filter =
    `loudnorm=${LOUDNORM_TARGET}` +
    `:measured_I=${m.input_i}:measured_TP=${m.input_tp}` +
    `:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}` +
    `:offset=${m.target_offset}:linear=true:print_format=summary`;
  const tmpPath = videoPath.replace(/\.mp4$/, "") + ".loudnorm.mp4";
  await execFileAsync(
    ffmpeg,
    ["-y", "-hide_banner", "-nostats", "-i", videoPath, "-c:v", "copy", "-af", filter,
      "-ar", "48000", "-c:a", "aac", "-b:a", "192k", tmpPath],
    ffSpawnOpts(ffmpeg),
  );
  await fs.rename(tmpPath, videoPath);
}

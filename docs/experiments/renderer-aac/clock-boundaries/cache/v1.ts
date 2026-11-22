import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export type Artifacts = { videoPath: string; srtPath?: string | null };
const root = path.join(os.tmpdir(), "repurposer-render-artifacts");
const active = new Map<string, Promise<Artifacts>>();
const retentionMs = 24 * 60 * 60 * 1000;

export class ArtifactCacheMiss extends Error {
  constructor() { super("Rendered artifact cache miss"); }
}

// Stable across JSON key order and fresh upload signatures. Version the cache
// when renderer semantics change; output identity isolates users/projects.
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

function artifactDirectory(identity: unknown, cacheRoot: string): string {
  const key = createHash("sha256").update(canonical({ version: 1, identity })).digest("hex");
  return path.join(cacheRoot, key);
}

async function readReadyArtifacts(directory: string): Promise<Artifacts> {
  if (Date.now() - (await fs.stat(directory)).mtimeMs > retentionMs) {
    throw new Error("Expired artifact");
  }
  const marker = path.join(directory, "ready.json");
  const saved: { srt: boolean } = JSON.parse(await fs.readFile(marker, "utf8"));
  const result = {
    videoPath: path.join(directory, "video.mp4"),
    ...(saved.srt ? { srtPath: path.join(directory, "video.srt") } : {}),
  };
  if ((await fs.stat(result.videoPath)).size === 0) throw new Error("Empty video");
  if (result.srtPath) await fs.stat(result.srtPath); // empty SRT is valid
  const now = new Date();
  await fs.utimes(directory, now, now);
  return result;
}

/** Upload-only recovery reads finished bytes but never generates replacements.
 * A missing, expired, or incomplete entry is an honest cache miss. */
export async function cachedArtifacts(
  identity: unknown, cacheRoot = root,
): Promise<Artifacts | null> {
  const directory = artifactDirectory(identity, cacheRoot);
  try { return await readReadyArtifacts(directory); } catch { return null; }
}

/** Keep finished bytes across upload failures and process restarts. A new
 * spec gets a new entry; incomplete renders never publish a ready marker. */
export async function renderArtifacts(
  identity: unknown,
  render: (directory: string) => Promise<Artifacts>,
  cacheRoot = root,
): Promise<Artifacts> {
  const directory = artifactDirectory(identity, cacheRoot);
  const running = active.get(directory);
  if (running) return running;
  const task = (async () => {
    await fs.mkdir(cacheRoot, { recursive: true });
    // Bounded retention, excluding jobs currently generating bytes.
    for (const entry of await fs.readdir(cacheRoot, { withFileTypes: true })) {
      const candidate = path.join(cacheRoot, entry.name);
      if (!entry.isDirectory() || candidate === directory || active.has(candidate)) continue;
      const stat = await fs.stat(candidate).catch(() => null);
      if (stat && Date.now() - stat.mtimeMs > retentionMs) {
        await fs.rm(candidate, { recursive: true, force: true });
      }
    }
    try {
      return await readReadyArtifacts(directory);
    } catch { /* missing/incomplete entry: regenerate */ }
    // A stale ready marker must not bless partially overwritten bytes when
    // regeneration crashes. Publish a new marker only after full success.
    await fs.rm(directory, { recursive: true, force: true });
    await fs.mkdir(directory, { recursive: true });
    const result = await render(directory);
    const marker = path.join(directory, "ready.json");
    await fs.writeFile(`${marker}.tmp`, JSON.stringify({ srt: Boolean(result.srtPath) }));
    await fs.rename(`${marker}.tmp`, marker);
    return result;
  })();
  active.set(directory, task);
  try { return await task; } finally { active.delete(directory); }
}

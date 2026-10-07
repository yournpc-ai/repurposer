import { createHash } from "node:crypto";
import { createWriteStream } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { ReadableStream as WebReadableStream } from "node:stream/web";

import { Agent, fetch, ProxyAgent } from "undici";

/**
 * Source staging: a clip-spec's remote `source.url` is downloaded once into a
 * local cache and served back to Remotion over loopback (`/cache/*` in
 * server.ts).
 *
 * Why: Remotion's internal asset fetch is a raw `node:https` GET — it ignores
 * HTTPS_PROXY, has no usable timeout of ours, and downloads the WHOLE source
 * inside the frame-extraction delayRender budget. A slow origin (observed
 * ~300 KB/s from TOS, 63 MB source ≈ 200 s) then surfaces as an opaque 178 s
 * delayRender timeout and a 500. Staging decouples download from rendering:
 * our own proxy-aware fetch with our own timeouts, deduped per URL so the N
 * clips of one run share a single download.
 *
 * 素材源缓存 (2026-10-07): this dir is SHARED with the api side
 * (providers/storage.download_to_cache) — the render payload's optional
 * `source_key` envelope field names the object key, and both sides hash it
 * with the same sha1 law, so a source the processing chain already pulled
 * (ASR / speaker_map / reframe) is a zero-network hit here. Without the key
 * the cache falls back to URL hashing (legacy payloads, non-asset sources).
 */

export const CACHE_DIR = path.join(os.tmpdir(), "repurposer-source-cache");
const CACHE_MAX_BYTES = 4 * 1024 * 1024 * 1024;
/** Hard cap for one source download; stalls die much earlier via bodyTimeout. */
const HARD_TIMEOUT_MS = 15 * 60 * 1000;

const RENDER_PORT = Number(process.env.RENDER_PORT ?? 3001);

/** In-flight dedup: concurrent renders of clips sharing one source download it once. */
const inflight = new Map<string, Promise<string>>();

const SAFE_EXT = /^\.[a-z0-9]{1,8}$/i;
const LOOPBACK_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/i;

function proxyEnv(): string | undefined {
  const raw =
    process.env.HTTPS_PROXY ??
    process.env.https_proxy ??
    process.env.HTTP_PROXY ??
    process.env.http_proxy;
  if (!raw) return undefined;
  // ProxyAgent's uri must be absolute — a bare host:port gets http://.
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `http://${raw}`;
}

/** Proxy-aware dispatcher shared by source staging AND result upload —
 * loopback skips the proxy; a remote host rides HTTPS_PROXY when present
 * (the direct TOS link from this network is throttled to ~300 KB/s). */
export function dispatcherFor(url: string): Agent | ProxyAgent {
  // bodyTimeout is an idle (between-chunks) timeout, not a total one — slow
  // but flowing downloads survive; the AbortSignal above bounds the total.
  const opts = { headersTimeout: 60_000, bodyTimeout: 300_000 };
  const host = new URL(url).hostname;
  const proxy = LOOPBACK_HOST.test(host) ? undefined : proxyEnv();
  return proxy ? new ProxyAgent({ uri: proxy, ...opts }) : new Agent(opts);
}

function cachePathFor(url: string, cacheKey?: string): string {
  // One hashing law with the api side (providers/storage.source_cache_path):
  // sha1 of the object key when the envelope names one, sha1 of the URL
  // otherwise — so an api-side download and a render-side staging of the
  // same source land on the SAME path.
  const hash = createHash("sha1")
    .update(cacheKey ?? url)
    .digest("hex");
  let ext = "";
  try {
    ext = path.extname(cacheKey ?? new URL(url).pathname);
  } catch {
    // keep "" — content-type comes from the extension, so a bogus one is worse
  }
  if (!SAFE_EXT.test(ext)) ext = "";
  return path.join(CACHE_DIR, hash + ext);
}

function toLoopbackUrl(filePath: string): string {
  return `http://127.0.0.1:${RENDER_PORT}/cache/${path.basename(filePath)}`;
}

/**
 * Stage a remote source URL into the local cache; returns its loopback URL.
 * Non-http(s) inputs are returned unchanged (already local). `cacheKey` is
 * the object-store key when the caller knows it (render payload's
 * `source_key`) — the api side's shared source cache is indexed by it, so a
 * hit costs zero network.
 */
export async function stageRemoteSource(
  url: string,
  cacheKey?: string,
): Promise<string> {
  if (!/^https?:\/\//i.test(url)) return url;
  const pending = inflight.get(cacheKey ?? url);
  if (pending) return pending;
  const p = doStage(url, cacheKey).finally(() => inflight.delete(cacheKey ?? url));
  inflight.set(cacheKey ?? url, p);
  return p;
}

async function doStage(url: string, cacheKey?: string): Promise<string> {
  await fs.mkdir(CACHE_DIR, { recursive: true });
  const dest = cachePathFor(url, cacheKey);
  const existing = await fs.stat(dest).catch(() => null);
  if (existing && existing.size > 0) {
    // LRU touch — eviction sorts by mtime.
    await fs.utimes(dest, new Date(), new Date()).catch(() => {});
    return toLoopbackUrl(dest);
  }

  const tmp = `${dest}.part-${process.pid}`;
  try {
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(HARD_TIMEOUT_MS),
      dispatcher: dispatcherFor(url),
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`source staging got HTTP ${resp.status} for ${url}`);
    }
    await pipeline(
      Readable.fromWeb(resp.body as unknown as WebReadableStream),
      createWriteStream(tmp),
    );
    await fs.rename(tmp, dest);
  } catch (err) {
    await fs.rm(tmp, { force: true }).catch(() => {});
    throw err;
  }

  evictCache().catch((err) => console.error("render cache eviction failed:", err));
  return toLoopbackUrl(dest);
}

/** Oldest-mtime-first eviction once the cache exceeds CACHE_MAX_BYTES. */
async function evictCache(): Promise<void> {
  const names = await fs.readdir(CACHE_DIR).catch(() => [] as string[]);
  const entries = (
    await Promise.all(
      names
        .filter((n) => !n.includes(".part"))
        .map(async (name) => {
          const s = await fs.stat(path.join(CACHE_DIR, name)).catch(() => null);
          return s ? { name, size: s.size, mtimeMs: s.mtimeMs } : null;
        }),
    )
  ).filter((e): e is { name: string; size: number; mtimeMs: number } => e !== null);

  let total = entries.reduce((acc, e) => acc + e.size, 0);
  entries.sort((a, b) => a.mtimeMs - b.mtimeMs);
  for (const e of entries) {
    if (total <= CACHE_MAX_BYTES) break;
    await fs.rm(path.join(CACHE_DIR, e.name), { force: true }).catch(() => {});
    total -= e.size;
  }
}

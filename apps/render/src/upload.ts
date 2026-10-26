import fs from "node:fs/promises";
import { fetch } from "undici";
import { dispatcherFor } from "./stage";

export class UploadError extends Error {
  readonly stage = "upload";
  constructor(readonly code: string, options?: ErrorOptions) {
    super(`Video upload failed (${code})`, options);
  }
}

const MAX_ATTEMPTS = 4;
const ATTEMPT_TIMEOUT_MS = 10 * 60 * 1000;
const TOTAL_TIMEOUT_MS = 12 * 60 * 1000;
const TRANSIENT_CODES = new Set([
  "ECONNRESET", "EPIPE", "ECONNREFUSED", "ETIMEDOUT", "EAI_AGAIN",
  "ENETUNREACH", "EHOSTUNREACH", "UND_ERR_SOCKET", "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_HEADERS_TIMEOUT", "UND_ERR_BODY_TIMEOUT", "UPLOAD_TIMEOUT",
]);

export function uploadErrorCode(error: unknown): string {
  const seen = new Set<unknown>();
  let current = error;
  while (current && typeof current === "object" && !seen.has(current)) {
    seen.add(current);
    const item = current as { name?: string; code?: unknown; cause?: unknown };
    if (item.name === "TimeoutError") return "UPLOAD_TIMEOUT";
    if (typeof item.code === "string") return item.code;
    current = item.cause;
  }
  return "UPLOAD_TRANSPORT_ERROR";
}

export function uploadRetryDelay(attempt: number, retryAfter: string | null,
  now = Date.now(), random = Math.random()): number {
  const backoff = Math.round(1000 * 2 ** (attempt - 1) * (0.5 + random));
  if (!retryAfter) return backoff;
  const seconds = Number(retryAfter);
  const serverDelay = Number.isFinite(seconds)
    ? seconds * 1000 : Date.parse(retryAfter) - now;
  return Number.isFinite(serverDelay) ? Math.max(backoff, serverDelay) : backoff;
}

/** Idempotent PUTs reuse the finished bytes, but never a failed connection
 * pool. Four attempts share a 12-minute budget (including backoff); auth,
 * certificate/configuration failures and unknown errors fail immediately. */
export async function uploadFile(url: string, filePath: string, contentType?: string) {
  const buffer = await fs.readFile(filePath);
  const deadline = performance.now() + TOTAL_TIMEOUT_MS;
  let lastError: UploadError | undefined;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const remaining = Math.floor(deadline - performance.now());
    if (remaining <= 0) break;
    const dispatcher = dispatcherFor(url, ATTEMPT_TIMEOUT_MS);
    let retryAfter: string | null = null;
    let retryable = false;
    try {
      const resp = await fetch(url, {
        method: "PUT", body: buffer,
        headers: contentType ? { "Content-Type": contentType } : {},
        dispatcher,
        signal: AbortSignal.timeout(Math.min(ATTEMPT_TIMEOUT_MS, remaining)),
      });
      retryAfter = resp.headers.get("retry-after");
      await resp.body?.cancel().catch(() => {});
      if (resp.ok) return;
      retryable = resp.status >= 500 || resp.status === 408 || resp.status === 429;
      throw new UploadError(`HTTP_${resp.status}`);
    } catch (error) {
      const code = uploadErrorCode(error);
      lastError = error instanceof UploadError ? error : new UploadError(code, { cause: error });
      if (!(retryable || TRANSIENT_CODES.has(code)) || attempt === MAX_ATTEMPTS) {
        throw lastError;
      }
    } finally {
      // Tear down the failed socket/tunnel before the next attempt. Cleanup
      // must not mask the upload result or wait for a broken pool to drain.
      await dispatcher.destroy().catch(() => {});
    }
    const delayMs = uploadRetryDelay(attempt, retryAfter);
    if (delayMs >= deadline - performance.now()) break;
    console.warn("upload_retry", { attempt, next_attempt: attempt + 1,
      code: lastError?.code, delay_ms: delayMs });
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw lastError ?? new UploadError("UPLOAD_TIMEOUT");
}

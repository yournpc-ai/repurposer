import fs from "node:fs/promises";
import { fetch } from "undici";
import { dispatcherFor } from "./stage";

export class UploadError extends Error {
  readonly stage = "upload";
  constructor(readonly code: string, options?: ErrorOptions) {
    super(`Video upload failed (${code})`, options);
  }
}

/** PUT to the same object is idempotent. Retry transient transport/5xx errors
 * once; auth/expired signatures need a fresh request, never a blind loop. */
export async function uploadFile(url: string, filePath: string, contentType?: string) {
  const buffer = await fs.readFile(filePath);
  const dispatcher = dispatcherFor(url);
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      let retryable = true;
      try {
        const resp = await fetch(url, {
          method: "PUT", body: buffer,
          headers: contentType ? { "Content-Type": contentType } : {},
          dispatcher,
          signal: AbortSignal.timeout(6 * 60 * 1000),
        });
        await resp.body?.cancel();
        if (resp.ok) return;
        retryable = resp.status >= 500 || resp.status === 408 || resp.status === 429;
        throw new UploadError(`HTTP_${resp.status}`);
      } catch (error) {
        const cause = error as { code?: string; cause?: { code?: string } };
        const code = cause.cause?.code ?? cause.code ?? "UPLOAD_TRANSPORT_ERROR";
        if (!retryable || attempt === 1) {
          throw error instanceof UploadError ? error : new UploadError(code, { cause: error });
        }
        console.warn("upload_retry", { attempt: attempt + 1, code });
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }
  } finally { await dispatcher.close(); }
}

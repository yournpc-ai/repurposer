import assert from "node:assert/strict";
import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { uploadFile, UploadError, uploadErrorCode, uploadRetryDelay } from "./upload";

test("PUT retries a transient failure with the same bytes, but not an expired signature", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "upload-test-"));
  const file = path.join(root, "video.mp4");
  await fs.writeFile(file, "finished video");
  let attempts = 0;
  const bodies: string[] = [];
  const server = http.createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    bodies.push(body);
    attempts++;
    res.statusCode = req.url === "/expired" ? 403 : attempts === 1 ? 503 : 200;
    res.end();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  try {
    await uploadFile(`http://127.0.0.1:${port}/video`, file, "video/mp4");
    assert.equal(attempts, 2);
    assert.deepEqual(bodies, ["finished video", "finished video"]);
    await assert.rejects(uploadFile(`http://127.0.0.1:${port}/expired`, file),
      (error) => error instanceof UploadError && error.code === "HTTP_403");
    assert.equal(attempts, 3);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await fs.rm(root, { recursive: true, force: true });
  }
});

async function uploadServer(
  handler: (req: http.IncomingMessage, res: http.ServerResponse) => void,
  run: (url: string, file: string) => Promise<void>,
) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "upload-retry-test-"));
  const file = path.join(root, "video.mp4");
  await fs.writeFile(file, "finished video");
  const server = http.createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await run(`http://127.0.0.1:${(server.address() as { port: number }).port}/video`, file);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await fs.rm(root, { recursive: true, force: true });
  }
}

test("socket reset then service failure recover with fresh connections and identical bytes", async () => {
  const bodies: string[] = [];
  const sockets = new Set();
  await uploadServer(async (req, res) => {
    sockets.add(req.socket);
    let body = "";
    for await (const chunk of req) body += chunk;
    bodies.push(body);
    if (bodies.length === 1) { req.socket.destroy(); return; }
    res.statusCode = bodies.length === 2 ? 503 : 200;
    res.end();
  }, async (url, file) => {
    await uploadFile(url, file);
    assert.deepEqual(bodies, Array(3).fill("finished video"));
    assert.equal(sockets.size, 3);
  });
});

test("persistent service failures stop after four attempts and preserve the file", async () => {
  let attempts = 0;
  await uploadServer((req, res) => {
    req.resume();
    attempts++;
    res.writeHead(503).end();
  }, async (url, file) => {
    await assert.rejects(uploadFile(url, file),
      (err) => err instanceof UploadError && err.code === "HTTP_503");
    assert.equal(attempts, 4);
    assert.equal(await fs.readFile(file, "utf8"), "finished video");
  });
});

test("Retry-After beyond the total budget stops instead of retrying early", async () => {
  let attempts = 0;
  await uploadServer((req, res) => {
    req.resume();
    attempts++;
    res.writeHead(429, { "Retry-After": "3600" }).end();
  }, async (url, file) => {
    await assert.rejects(uploadFile(url, file),
      (err) => err instanceof UploadError && err.code === "HTTP_429");
    assert.equal(attempts, 1);
  });
});

test("elapsed upload budget prevents another attempt", async (t) => {
  let attempts = 0;
  let now = 0;
  t.mock.method(performance, "now", () => now);
  await uploadServer((req, res) => {
    req.resume();
    attempts++;
    now = 12 * 60 * 1000;
    res.writeHead(503).end();
  }, async (url, file) => {
    await assert.rejects(uploadFile(url, file),
      (err) => err instanceof UploadError && err.code === "HTTP_503");
    assert.equal(attempts, 1);
  });
});

test("classifies nested transport errors and timeout names", () => {
  for (const code of ["EPIPE", "ECONNRESET", "CERT_HAS_EXPIRED"]) {
    assert.equal(uploadErrorCode(new TypeError("fetch failed", { cause: { code } })), code);
  }
  assert.equal(uploadErrorCode(new DOMException("expired", "TimeoutError")), "UPLOAD_TIMEOUT");
  assert.equal(uploadErrorCode(new Error("unknown")), "UPLOAD_TRANSPORT_ERROR");
});

test("backoff grows with jitter and respects Retry-After seconds and dates", () => {
  assert.equal(uploadRetryDelay(1, null, 0, 0.5), 1000);
  assert.equal(uploadRetryDelay(3, null, 0, 0.5), 4000);
  assert.equal(uploadRetryDelay(1, "10", 0, 0.5), 10000);
  assert.equal(uploadRetryDelay(1, "Thu, 01 Jan 1970 00:00:10 GMT", 0, 0.5), 10000);
  assert.equal(uploadRetryDelay(1, "invalid", 0, 0.5), 1000);
});

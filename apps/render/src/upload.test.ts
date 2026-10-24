import assert from "node:assert/strict";
import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { uploadFile, UploadError } from "./upload";

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

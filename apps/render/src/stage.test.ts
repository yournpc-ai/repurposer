import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import http from "node:http";
import test from "node:test";
import { stageRemoteSource } from "./stage";

async function sourceServer(
  handler: (req: http.IncomingMessage, res: http.ServerResponse, count: number) => void,
) {
  let requests = 0;
  const server = http.createServer((req, res) => handler(req, res, ++requests));
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  return {
    url: `http://127.0.0.1:${address.port}/source-${randomUUID()}.png`,
    requests: () => requests,
    close: () => new Promise<void>((resolve, reject) => {
      server.closeAllConnections();
      server.close((error) => error ? reject(error) : resolve());
    }),
  };
}

test("source staging retries a transient dropped connection once in place", async () => {
  const server = await sourceServer((_req, res, count) => {
    if (count === 1) res.socket?.destroy();
    else res.end("real source bytes");
  });
  try {
    const staged = await stageRemoteSource(server.url);
    assert.match(staged, /^http:\/\/127\.0\.0\.1:\d+\/cache\//);
    assert.equal(server.requests(), 2);
  } finally { await server.close(); }
});

test("source staging does not blind-retry an HTTP rejection", async () => {
  const server = await sourceServer((_req, res) => {
    res.statusCode = 404;
    res.end("missing");
  });
  try {
    await assert.rejects(stageRemoteSource(server.url), /HTTP 404/);
    assert.equal(server.requests(), 1);
  } finally { await server.close(); }
});

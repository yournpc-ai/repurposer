import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { InvalidAudioClock, verifyAudioWindow } from "./audio";

test("verifyAudioWindow fails closed with InvalidAudioClock on baseline probe/parse/clock faults", async () => {
  const expected = 48000 * 3;
  // 1. Real ffprobe failure against missing or corrupt file fails closed on baseline
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "audio-clock-test-"));
  const corrupt = path.join(dir, "corrupt.mp4");
  try {
    await fs.writeFile(corrupt, "not a valid mp4 container");
    await assert.rejects(
      verifyAudioWindow(corrupt, expected, "baseline"),
      (err: unknown) => err instanceof InvalidAudioClock,
    );
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }

  // 2. Injected probe crash, malformed JSON, missing streams, clock drift all throw InvalidAudioClock
  await assert.rejects(
    verifyAudioWindow("x.mp4", expected, "baseline", {
      probe: async () => { throw new Error("ENOENT ffprobe"); },
    }),
    (err: unknown) => err instanceof InvalidAudioClock,
  );
  await assert.rejects(
    verifyAudioWindow("x.mp4", expected, "baseline", { probe: async () => "{not-json" }),
    (err: unknown) => err instanceof InvalidAudioClock,
  );
  await assert.rejects(
    verifyAudioWindow("x.mp4", expected, "baseline", { probe: async () => "{}" }),
    (err: unknown) => err instanceof InvalidAudioClock,
  );
  await assert.rejects(
    verifyAudioWindow("x.mp4", expected, "baseline", {
      probe: async () => JSON.stringify({
        streams: [{ sample_rate: "48000", time_base: "1/48000", start_pts: 0, duration_ts: expected + 2048 }],
      }),
    }),
    (err: unknown) => err instanceof InvalidAudioClock,
  );

  // 3. Silent baseline is allowed unless requireAudio is true
  const silent = await verifyAudioWindow("x.mp4", expected, "baseline", {
    probe: async () => JSON.stringify({ streams: [] }),
  });
  assert.equal(silent, false);
  await assert.rejects(
    verifyAudioWindow("x.mp4", expected, "baseline", {
      requireAudio: true,
      probe: async () => JSON.stringify({ streams: [] }),
    }),
    (err: unknown) => err instanceof InvalidAudioClock,
  );

  // 4. Valid 48 kHz zero-based exact duration passes
  const ok = await verifyAudioWindow("x.mp4", expected, "baseline", {
    probe: async () => JSON.stringify({
      streams: [{ sample_rate: "48000", time_base: "1/48000", start_pts: 0, duration_ts: expected }],
    }),
  });
  assert.equal(ok, true);
});

test("verifyAudioWindow throws recoverable Error (not InvalidAudioClock) on loudnorm faults", async () => {
  const expected = 48000 * 3;
  for (const probe of [
    async () => { throw new Error("ffprobe crashed"); },
    async () => "bad-json",
    async () => JSON.stringify({ streams: [] }),
    async () => JSON.stringify({
      streams: [{ sample_rate: "48000", time_base: "1/48000", start_pts: 1024, duration_ts: expected }],
    }),
  ]) {
    await assert.rejects(
      verifyAudioWindow("x.mp4", expected, "loudnorm", { probe }),
      (err: unknown) => err instanceof Error && !(err instanceof InvalidAudioClock),
    );
  }
});

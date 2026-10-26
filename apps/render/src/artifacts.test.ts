import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { cachedArtifacts, renderArtifacts } from "./artifacts";

test("upload recovery reuses finished bytes; changes and users cannot reuse them", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "render-recovery-test-"));
  let renders = 0;
  const render = async (directory: string) => {
    renders++;
    const videoPath = path.join(directory, "video.mp4");
    const srtPath = path.join(directory, "video.srt");
    await fs.writeFile(videoPath, "rendered bytes");
    await fs.writeFile(srtPath, "");
    return { videoPath, srtPath };
  };
  try {
    const first = await renderArtifacts({ id: "a", spec: { fps: 30, scenes: [1] } }, render, root);
    // Simulate upload failure/restart: no in-memory active promise survives.
    const retry = await renderArtifacts({ spec: { scenes: [1], fps: 30 }, id: "a" }, render, root);
    assert.equal(retry.videoPath, first.videoPath);
    assert.equal(renders, 1);
    await renderArtifacts({ id: "a", spec: { fps: 30, scenes: [2] } }, render, root);
    await renderArtifacts({ id: "b", spec: { fps: 30, scenes: [1] } }, render, root);
    assert.equal(renders, 3);
    await fs.unlink(first.videoPath);
    await renderArtifacts({ id: "a", spec: { fps: 30, scenes: [1] } }, render, root);
    assert.equal(renders, 4);
    await fs.unlink(first.srtPath!);
    await assert.rejects(renderArtifacts({ id: "a", spec: { fps: 30, scenes: [1] } }, async (dir) => {
      await fs.writeFile(path.join(dir, "video.mp4"), "partial output");
      throw new Error("crash during recovery");
    }, root), /crash during recovery/);
    const recovered = await renderArtifacts({ id: "a", spec: { fps: 30, scenes: [1] } }, render, root);
    assert.equal(renders, 5);
    assert.equal(await fs.readFile(recovered.videoPath, "utf8"), "rendered bytes");
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test("upload-only cache reads never regenerate missing bytes", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "render-upload-only-test-"));
  const identity = { id: "a", spec: { fps: 30, scenes: [1] } };
  let renders = 0;
  const render = async (directory: string) => {
    renders++;
    const videoPath = path.join(directory, "video.mp4");
    await fs.writeFile(videoPath, "rendered bytes");
    return { videoPath };
  };
  try {
    const first = await renderArtifacts(identity, render, root);
    assert.deepEqual(await cachedArtifacts(identity, root), first);
    assert.equal(renders, 1);
    await fs.unlink(first.videoPath);
    assert.equal(await cachedArtifacts(identity, root), null);
    assert.equal(renders, 1);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test("concurrent retries render once, failed renders publish no ready marker", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "render-recovery-test-"));
  let renders = 0;
  const render = async (directory: string) => {
    renders++;
    if (renders === 1) throw new Error("renderer died");
    const videoPath = path.join(directory, "video.mp4");
    await fs.writeFile(videoPath, "finished");
    return { videoPath };
  };
  try {
    await assert.rejects(renderArtifacts("a", render, root), /renderer died/);
    const [a, b] = await Promise.all([
      renderArtifacts("a", render, root), renderArtifacts("a", render, root),
    ]);
    assert.equal(a.videoPath, b.videoPath);
    assert.equal(renders, 2);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

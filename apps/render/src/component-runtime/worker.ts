import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { makeCancelSignal, renderMedia, renderStill, selectComposition } from "@remotion/renderer";

import {
  componentBakeRequestSchema,
  COMPONENT_DEPENDENCIES,
  MAX_FIXED_RESOURCE_BYTES,
  MAX_TOTAL_FIXED_RESOURCE_BYTES,
} from "./contract";
import { assertDynamicComponentFrames, type ComponentFrameSample } from "./dynamics";
import { assertComponentSource, assertRemotionProject, guardStaticFileResources } from "./policy";

const MAX_MEDIA_BYTES = 24 * 1024 * 1024;
const MAX_PREVIEW_BYTES = 4 * 1024 * 1024;
const require = createRequire(import.meta.url);
const RENDER_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const BROWSER_EXECUTABLE = process.env.COMPONENT_BROWSER_EXECUTABLE ?? path.join(
  RENDER_ROOT,
  "node_modules",
  ".remotion",
  "chrome-headless-shell",
  `mac-${os.arch() === "arm64" ? "arm64" : "x64"}`,
  `chrome-headless-shell-mac-${os.arch() === "arm64" ? "arm64" : "x64"}`,
  "chrome-headless-shell",
);

function assertInstalledDependencyLock() {
  for (const [name, expected] of Object.entries(COMPONENT_DEPENDENCIES)) {
    const actual = (require(`${name}/package.json`) as { version?: string }).version;
    if (actual !== expected) {
      throw new Error(`component dependency ${name} is ${actual ?? "unknown"}, expected ${expected}`);
    }
  }
}

const ALLOWED_PRELUDE = `import React from "react";
import { AbsoluteFill, Sequence, Series, useCurrentFrame, useVideoConfig, interpolate, spring, Easing, random } from "remotion";
`;

function digest(data: string | Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

async function writeProject(work: string, request: ReturnType<typeof componentBakeRequestSchema.parse>) {
  if (!request.project) return { entryPath: path.join(work, "entry.tsx"), publicDir: null };
  for (const file of request.project.files) {
    const destination = path.join(work, file.path);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.writeFile(destination, guardStaticFileResources(file, request.resources), "utf8");
  }
  const publicDir = path.join(work, "public");
  await fs.mkdir(publicDir, { recursive: true });
  let total = 0;
  for (const resource of request.resources) {
    const data = Buffer.from(resource.data_base64, "base64");
    total += data.length;
    if (!data.length || data.length > MAX_FIXED_RESOURCE_BYTES || total > MAX_TOTAL_FIXED_RESOURCE_BYTES) {
      throw new Error("component fixed resources exceed their byte budget");
    }
    if (digest(data) !== resource.digest) throw new Error(`${resource.path}: fixed resource digest mismatch`);
    if (resource.content_type === "image/png" && !data.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
      throw new Error(`${resource.path}: declared PNG bytes are malformed`);
    }
    if (resource.content_type === "image/jpeg" && (data.length < 3 || data[0] !== 0xff || data[1] !== 0xd8 || data[2] !== 0xff)) {
      throw new Error(`${resource.path}: declared JPEG bytes are malformed`);
    }
    if (resource.content_type === "image/webp" && (data.length < 12 || data.toString("ascii", 0, 4) !== "RIFF" || data.toString("ascii", 8, 12) !== "WEBP")) {
      throw new Error(`${resource.path}: declared WebP bytes are malformed`);
    }
    const destination = path.join(publicDir, resource.path);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.writeFile(destination, data);
  }
  return { entryPath: path.join(work, request.project.entry), publicDir };
}

async function main() {
  assertInstalledDependencyLock();
  const [requestPath, resultPath] = process.argv.slice(2);
  const request = componentBakeRequestSchema.parse(JSON.parse(await fs.readFile(requestPath, "utf8")));
  const work = path.dirname(requestPath);
  const output = request.output;
  let entryPath: string;
  let publicDir: string | null;
  let compositionId: string;
  let inputProps: Record<string, unknown>;

  if (request.project) {
    assertRemotionProject(request.project, request.resources);
    ({ entryPath, publicDir } = await writeProject(work, request));
    compositionId = request.project.composition_id;
    inputProps = request.project.props;
  } else {
    assertComponentSource(request.code!);
    const generatedPath = path.join(work, "generated.tsx");
    entryPath = path.join(work, "entry.tsx");
    publicDir = null;
    compositionId = "Component";
    inputProps = { parameters: request.parameters };
    await fs.writeFile(generatedPath, ALLOWED_PRELUDE + request.code, "utf8");
    await fs.writeFile(entryPath, `import React from "react";
import { AbsoluteFill, Composition, registerRoot } from "remotion";
import GeneratedComponent from "./generated";
const Baked = (props: { parameters: Record<string, string | number | boolean> }) => (
  <AbsoluteFill style={{ background: "${output.background}" }}>
    <GeneratedComponent {...props} />
  </AbsoluteFill>
);
const Root = () => <Composition
  id="Component"
  component={Baked}
  fps={${output.fps}}
  width={${output.width}}
  height={${output.height}}
  durationInFrames={${output.duration_frames}}
  defaultProps={{ parameters: {} }}
/>;
registerRoot(Root);
`, "utf8");
  }

  console.error("component-bake: bundling");
  const serveUrl = await bundle({
    entryPoint: entryPath,
    rootDir: RENDER_ROOT,
    outDir: path.join(work, "bundle"),
    publicDir,
    enableCaching: false,
  });
  console.error("component-bake: selecting composition");
  const composition = await selectComposition({ serveUrl, id: compositionId, inputProps, browserExecutable: BROWSER_EXECUTABLE, chromeMode: "headless-shell" });
  if (composition.durationInFrames !== output.duration_frames || composition.fps !== output.fps ||
      composition.width !== output.width || composition.height !== output.height) {
    throw new Error("registered Composition does not match the declared output constraints");
  }
  const { cancelSignal } = makeCancelSignal();
  const previewFrame = Math.floor(output.duration_frames / 2);
  const sampleFrames = [...new Set([
    0,
    previewFrame,
    output.duration_frames - 1,
  ])].sort((a, b) => a - b);
  const samples: ComponentFrameSample[] = [];
  for (const frame of sampleFrames) {
    console.error(`component-bake: rendering still ${frame}`);
    const rendered = await renderStill({
      composition,
      serveUrl,
      frame,
      inputProps,
      browserExecutable: BROWSER_EXECUTABLE,
      chromeMode: "headless-shell",
      imageFormat: "png",
      envVariables: {},
      timeoutInMilliseconds: 30_000,
      cancelSignal,
    });
    if (!rendered.buffer || !rendered.buffer.length || rendered.buffer.length > MAX_PREVIEW_BYTES) {
      throw new Error("component PNG preview exceeds its byte budget");
    }
    samples.push({ frame, png: rendered.buffer });
  }
  assertDynamicComponentFrames(samples);
  const preview = samples.find(({ frame }) => frame === previewFrame)?.png;
  if (!preview) throw new Error("component bake produced no representative frame");

  const videoPath = path.join(work, "component.mp4");
  console.error("component-bake: rendering media");
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
    browserExecutable: BROWSER_EXECUTABLE,
    muted: true,
    concurrency: 2,
    envVariables: {},
    timeoutInMilliseconds: 30_000,
    cancelSignal,
  });
  const videoStat = await fs.stat(videoPath);
  if (!videoStat.size || videoStat.size > MAX_MEDIA_BYTES) {
    throw new Error("component MP4 exceeds its byte budget");
  }
  const video = await fs.readFile(videoPath);
  await fs.writeFile(resultPath, JSON.stringify({
    producer: request.producer,
    program_digest: request.program_digest,
    dependencies: COMPONENT_DEPENDENCIES,
    output: request.output,
    video_base64: video.toString("base64"),
    preview_base64: preview.toString("base64"),
    diagnostics: {
      frames: output.duration_frames,
      preview_frame: previewFrame,
      dynamic_sample_frames: sampleFrames,
      dependency_lock: COMPONENT_DEPENDENCIES,
      entry: request.project?.entry ?? "entry.tsx",
      composition_id: compositionId,
      files: request.project?.files.map(({ path: filePath, digest: fileDigest }) => ({ path: filePath, digest: fileDigest })) ?? [],
      resources: request.resources.map(({ path: resourcePath, digest: resourceDigest, content_type }) => ({
        path: resourcePath, digest: resourceDigest, content_type,
      })),
      process_budget_seconds: 240,
      network: "loopback-only-macos-seatbelt; postgres/mysql/redis-denied",
      filesystem: "declared-dependencies-and-workdir-only-macos-seatbelt",
      resource_limits: {
        max_active_bakes: 1,
        cpu_seconds: 220,
        memory_group_kb: 8 * 1024 * 1024,
        temporary_storage_kb: 512 * 1024,
        max_open_files: 256,
      },
      cleanup: "descendant-process-groups-sigkill-and-temp-tree-removal",
    },
  }));
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});

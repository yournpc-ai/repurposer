import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { makeCancelSignal, renderMedia, renderStill, selectComposition } from "@remotion/renderer";

import { componentBakeRequestSchema, COMPONENT_DEPENDENCIES } from "./contract";
import { assertDynamicComponentFrames, type ComponentFrameSample } from "./dynamics";
import { assertComponentSource } from "./policy";

const MAX_MEDIA_BYTES = 24 * 1024 * 1024;
const MAX_PREVIEW_BYTES = 4 * 1024 * 1024;
const require = createRequire(import.meta.url);
const RENDER_ROOT = fileURLToPath(new URL("../..", import.meta.url));

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

async function main() {
  assertInstalledDependencyLock();
  const [requestPath, resultPath] = process.argv.slice(2);
  const request = componentBakeRequestSchema.parse(JSON.parse(await fs.readFile(requestPath, "utf8")));
  assertComponentSource(request.code);
  const work = path.dirname(requestPath);
  const generatedPath = path.join(work, "generated.tsx");
  const entryPath = path.join(work, "entry.tsx");
  const output = request.output;
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

  const serveUrl = await bundle({
    entryPoint: entryPath,
    rootDir: RENDER_ROOT,
    outDir: path.join(work, "bundle"),
    publicDir: null,
    enableCaching: false,
  });
  const inputProps = { parameters: request.parameters };
  const composition = await selectComposition({ serveUrl, id: "Component", inputProps });
  const { cancelSignal } = makeCancelSignal();
  const previewFrame = Math.floor(output.duration_frames / 2);
  const sampleFrames = [...new Set([
    0,
    previewFrame,
    output.duration_frames - 1,
  ])].sort((a, b) => a - b);
  const samples: ComponentFrameSample[] = [];
  for (const frame of sampleFrames) {
    const rendered = await renderStill({
      composition,
      serveUrl,
      frame,
      inputProps,
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
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: videoPath,
    inputProps,
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
    runtime: request.runtime,
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
      process_budget_seconds: 240,
    },
  }));
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});

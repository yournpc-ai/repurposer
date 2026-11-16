/** One-shot D5 native-preset still/MP4 diagnostic; not a second preview adapter. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import type { VideoSpec } from "@repurposer/video-spec";

import { stageRemoteSource } from "../src/stage";
import { assertVideoSupported } from "../src/video/capabilities";

type Manifest = {
  cases: {
    name: string;
    spec: string;
    mp4: string;
    samples: Record<string, { frames: number[] }>;
  }[];
};

const manifestPath = process.argv[2];
if (!manifestPath) throw new Error("usage: tsx d5_native_presets.ts MANIFEST.json [--stills-only]");
const stillsOnly = process.argv.includes("--stills-only");
const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8")) as Manifest;
const entryPoint = fileURLToPath(new URL("../src/video/remotion/entry.tsx", import.meta.url));
const serveUrl = await bundle({ entryPoint });
const results: unknown[] = [];

for (const item of manifest.cases) {
  const spec = JSON.parse(await fs.readFile(item.spec, "utf8")) as VideoSpec;
  assertVideoSupported(spec);
  const stagedSpec: VideoSpec = {
    ...spec,
    fonts: await Promise.all(spec.fonts.map(async (font) => ({
      ...font,
      url: await stageRemoteSource(font.url, undefined, font.digest),
    }))),
    tracks: await Promise.all(spec.tracks.map(async (track) => ({
      ...track,
      clips: await Promise.all(track.clips.map(async (clip) => clip.source ? {
        ...clip,
        source: {
          ...clip.source,
          url: await stageRemoteSource(clip.source.url, undefined, clip.source.digest),
        },
      } : clip)),
    }))),
  };
  const inputProps = { spec: stagedSpec };
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });
  await fs.mkdir(path.dirname(item.mp4), { recursive: true });
  if (!stillsOnly) {
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation: item.mp4,
      inputProps,
      timeoutInMilliseconds: 180_000,
    });
  }
  for (const [preset, sample] of Object.entries(item.samples)) {
    const directory = path.join(path.dirname(item.mp4), "stills", item.name);
    await fs.mkdir(directory, { recursive: true });
    for (const frame of sample.frames) {
      const outputLocation = path.join(directory, `${preset}-${String(frame).padStart(4, "0")}.png`);
      const rendered = await renderStill({
        composition,
        serveUrl,
        inputProps,
        frame,
        imageFormat: "png",
        timeoutInMilliseconds: 180_000,
      });
      if (!rendered.buffer?.length) throw new Error(`empty still for ${preset} frame ${frame}`);
      await fs.writeFile(outputLocation, rendered.buffer);
    }
  }
  results.push({ name: item.name, mp4: stillsOnly ? null : item.mp4, presets: Object.keys(item.samples) });
  console.log(JSON.stringify(results.at(-1)));
}

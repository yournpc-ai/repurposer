// Video-scene spike driver — renders a HAND-WRITTEN film spec (dev test, not
// product acceptance) through the REAL film entry (src/film/entry.tsx) to
// prove the minimal film extension: OffthreadVideo footage + trim ranges +
// text overlay, with consecutive scenes advancing the source range (never
// replaying from 0). Stills at mid-scene frames make the trim verdict
// visible. Usage: node render.mjs
import { bundle } from '@remotion/bundler';
import { renderMedia, renderStill, selectComposition } from '@remotion/renderer';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const t0 = Date.now();

const browserExecutable =
  '/Users/sylas/.cache/puppeteer/chrome/mac_arm-145.0.7632.46/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';

const spec = {
  family: 'film',
  theme: { canvas: '#F7F6F2', ink: '#141414' },
  aspect: '16:9',
  fps: 30,
  scenes: [
    {
      type: 'words',
      frames: 60,
      dark: false,
      lines: ['录屏配文字', 'video scene spike'],
      captions: [],
    },
    {
      // Footage 10s→14s of the source, text overlay segment 1.
      type: 'video',
      frames: 120,
      video: 'public/source.mp4',
      start: 10,
      end: 14,
      fit: 'cover',
      keep_audio: false,
      lines: ['第一段文字贴在画面上'],
      captions: [],
    },
    {
      // SAME source continuing 14s→18s — must NOT replay from 0.
      type: 'video',
      frames: 120,
      video: 'public/source.mp4',
      start: 14,
      end: 18,
      fit: 'cover',
      keep_audio: false,
      lines: ['第二段 — 画面接续不回退'],
      captions: [],
    },
    {
      type: 'end',
      frames: 90,
      name: 'Spike',
      tagline: 'video scene over footage',
      url: 'repurposer.local',
      captions: [],
    },
  ],
};

const serveUrl = await bundle({
  entryPoint: path.join(dir, '..', '..', 'src', 'film', 'entry.tsx'),
  publicDir: path.join(dir, 'public'),
});
console.log(`bundled in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

const composition = await selectComposition({
  serveUrl,
  id: 'Film',
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
console.log(
  `composition: ${composition.width}x${composition.height}@${composition.fps} ` +
    `${composition.durationInFrames} frames (${(composition.durationInFrames / composition.fps).toFixed(1)}s)`,
);

// Trim verdict stills: mid video-scene-1 (source ~11.5s) vs mid video-scene-2
// (source ~16s) — identical frames would mean an uninvited replay from 0.
for (const [name, frame] of [
  ['still-video1', 150],
  ['still-video2', 300],
]) {
  await renderStill({
    composition,
    serveUrl,
    inputProps: { spec },
    frame,
    output: path.join(dir, 'out', `${name}.png`),
    browserExecutable,
    chromeMode: 'chrome-for-testing',
  });
  console.log(`still ${name} (frame ${frame}) done`);
}

const t1 = Date.now();
let lastLog = 0;
await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: path.join(dir, 'out', 'video-scene-spike.mp4'),
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
  onProgress: ({ progress }) => {
    if (Date.now() - lastLog > 5000) {
      lastLog = Date.now();
      console.log(`render ${(progress * 100).toFixed(0)}%  ${((Date.now() - t1) / 1000).toFixed(0)}s`);
    }
  },
});
console.log(`RENDER DONE in ${((Date.now() - t1) / 1000).toFixed(1)}s → out/video-scene-spike.mp4`);

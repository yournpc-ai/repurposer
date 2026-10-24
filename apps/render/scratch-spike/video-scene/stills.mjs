// Still-strip probe: render one frame per scene window to map actual content
// to the timeline. Usage: node stills.mjs
import { bundle } from '@remotion/bundler';
import { renderStill, selectComposition } from '@remotion/renderer';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const browserExecutable =
  '/Users/sylas/.cache/puppeteer/chrome/mac_arm-145.0.7632.46/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';

const spec = {
  family: 'film',
  theme: { canvas: '#F7F6F2', ink: '#141414' },
  aspect: '16:9',
  fps: 30,
  scenes: [
    { type: 'words', frames: 60, dark: false, lines: ['录屏配文字', 'video scene spike'], captions: [] },
    { type: 'video', frames: 120, video: 'public/source.mp4', start: 10, end: 14, fit: 'cover', keep_audio: false, lines: ['第一段文字贴在画面上'], captions: [] },
    { type: 'video', frames: 120, video: 'public/source.mp4', start: 14, end: 18, fit: 'cover', keep_audio: false, lines: ['第二段 — 画面接续不回退'], captions: [] },
    { type: 'end', frames: 90, name: 'Spike', tagline: 'video scene over footage', url: 'repurposer.local', captions: [] },
  ],
};

const serveUrl = await bundle({
  entryPoint: path.join(dir, '..', '..', 'src', 'film', 'entry.tsx'),
  publicDir: path.join(dir, 'public'),
});
const composition = await selectComposition({
  serveUrl,
  id: 'Film',
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
for (const frame of [30, 90, 120, 150, 200, 250, 280, 320, 350]) {
  await renderStill({
    composition,
    serveUrl,
    inputProps: { spec },
    frame,
    output: path.join(dir, 'out', `f${frame}.png`),
    browserExecutable,
    chromeMode: 'chrome-for-testing',
  });
  console.log(`f${frame} done`);
}

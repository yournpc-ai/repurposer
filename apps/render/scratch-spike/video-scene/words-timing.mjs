// Batch B precise-timing spike: the user's named example rendered for real —
// scene 1 carries enter_start 0.3 / enter_interval 0.12 / enter_duration 0.25
// (expected token starts f9/f13/f17/f21/f25/f29, 8-frame entrances), scene 2
// is the legacy cadence control (no timing keys), scene 3 bounds a push to
// the 1.5s–3.5s window (f45–f105 — clear of the lines entrance's settle).
// No music, no voiceover. Decode frames with
// PyAV afterwards (words-timing-probe.py). Usage: node words-timing.mjs
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
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
    {
      type: 'words',
      frames: 120,
      dark: false,
      enter: 'words',
      enter_start: 0.3,
      enter_interval: 0.12,
      enter_duration: 0.25,
      lines: ['文字依次入场'],
      captions: [],
    },
    {
      type: 'words',
      frames: 120,
      dark: true,
      enter: 'words',
      lines: ['对照组整行 legacy cadence'],
      captions: [],
    },
    {
      type: 'words',
      frames: 120,
      dark: false,
      motion: 'push',
      motion_start: 1.5,
      motion_end: 3.5,
      lines: ['推镜窗口'],
      captions: [],
    },
  ],
};

const serveUrl = await bundle({
  entryPoint: path.join(dir, '..', '..', 'src', 'film', 'entry.tsx'),
});
const composition = await selectComposition({
  serveUrl,
  id: 'Film',
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
console.log(`composition: ${composition.durationInFrames} frames`);
await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: path.join(dir, 'out', 'words-timing-spike.mp4'),
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
console.log('RENDER DONE → out/words-timing-spike.mp4');

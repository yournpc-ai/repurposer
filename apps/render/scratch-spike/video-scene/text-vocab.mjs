// Text-vocabulary spike: words scene enter="words" + motion="push" vs the
// lines/static default — real render, pts-probed. Usage: node text-vocab.mjs
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
      frames: 90,
      dark: false,
      motion: 'push',
      enter: 'words',
      lines: ['关键词 *逐字* 出现', 'word by word reveal'],
      captions: [],
    },
    {
      type: 'words',
      frames: 90,
      dark: true,
      lines: ['对照组 — 整行入场', 'static plane, lines enter'],
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
  outputLocation: path.join(dir, 'out', 'text-vocab-spike.mp4'),
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
console.log('RENDER DONE → out/text-vocab-spike.mp4');

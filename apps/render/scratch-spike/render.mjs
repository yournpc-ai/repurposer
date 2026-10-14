// Spike render driver — bundle the spike entry and render it through our
// Remotion stack (apps/render deps), timed. Usage: node render.mjs
import { bundle } from '@remotion/bundler';
import { getCompositions, renderMedia } from '@remotion/renderer';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const t0 = Date.now();

// Chrome for Testing binary from the puppeteer cache — avoids any download.
const browserExecutable =
  '/Users/sylas/.cache/puppeteer/chrome/mac_arm-145.0.7632.46/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';

const serveUrl = await bundle({
  entryPoint: path.join(dir, 'film.tsx'),
  publicDir: path.join(dir, 'public'),
});
console.log(`bundled in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

const comps = await getCompositions(serveUrl, { browserExecutable, chromeMode: 'chrome-for-testing' });
const comp = comps.find((c) => c.id === 'LaunchFilm');
console.log(`composition: ${comp.width}x${comp.height}@${comp.fps} ${comp.durationInFrames} frames (${(comp.durationInFrames / comp.fps).toFixed(1)}s)`);

const t1 = Date.now();
let lastLog = 0;
await renderMedia({
  composition: comp,
  serveUrl,
  codec: 'h264',
  outputLocation: path.join(dir, 'out', 'launch-film-spike.mp4'),
  browserExecutable,
  chromeMode: 'chrome-for-testing',
  onProgress: ({ progress }) => {
    if (Date.now() - lastLog > 5000) {
      lastLog = Date.now();
      console.log(`render ${(progress * 100).toFixed(0)}%  ${((Date.now() - t1) / 1000).toFixed(0)}s`);
    }
  },
});
console.log(`RENDER DONE in ${((Date.now() - t1) / 1000).toFixed(1)}s → out/launch-film-spike.mp4`);

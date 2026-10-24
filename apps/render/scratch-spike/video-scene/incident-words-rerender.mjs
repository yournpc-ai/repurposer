// A4 incident re-render: replay the d08af2af final spec (9:16 words scenes)
// against the CURRENT renderer — before/after the Words right-edge fix.
// Local only, zero provider calls. Usage: node incident-words-rerender.mjs
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const browserExecutable =
  '/Users/sylas/.cache/puppeteer/chrome/mac_arm-145.0.7632.46/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';

const spec = JSON.parse(readFileSync('/tmp/d08af2af_incident_spec.json', 'utf8'));
// The baked spec omits empty caption tracks (backend attaches only non-empty);
// the harness bypasses the zod default, so fill it here.
for (const s of spec.scenes) s.captions ??= [];
const tag = process.argv[2] || 'before';

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
console.log(`composition: ${composition.durationInFrames} frames @ ${composition.width}x${composition.height}`);
await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: path.join(dir, 'out', `incident-words-${tag}.mp4`),
  inputProps: { spec },
  browserExecutable,
  chromeMode: 'chrome-for-testing',
});
console.log(`RENDER DONE → out/incident-words-${tag}.mp4`);

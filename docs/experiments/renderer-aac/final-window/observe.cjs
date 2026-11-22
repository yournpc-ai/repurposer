// Test-only preload for the archived 24 fps drive.mts. Preserve the real probe and rename.
const assert = require('node:assert/strict');
const { ChildProcess } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const hash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const record = data => fs.appendFileSync(path.join(process.env.LAB, 'events.jsonl'), JSON.stringify(data) + '\n');
const spawn = ChildProcess.prototype.spawn;
ChildProcess.prototype.spawn = function(options) {
  const args = options.args;
  if (path.basename(options.file) === 'ffprobe' && args.includes('stream=sample_rate,time_base,start_pts,duration_ts')) {
    const target = args.at(-1);
    const final = target.endsWith('.loudnorm.mp4');
    const before = hash(target);
    if (final) {
      assert.equal(before, hash(path.join(process.env.CONTROLS, '24-loudnorm.mp4')));
      if (process.env.CONTROL === 'negative') {
        fs.copyFileSync(path.join(process.env.CONTROLS, '24-default-timescale.mp4'), target);
      }
    }
    record({stage:final ? 'final-probe' : 'baseline-probe', file:options.file, args, before, presented:hash(target)});
  }
  return spawn.call(this, options);
};
const rename = fs.promises.rename;
fs.promises.rename = async function(from, to) {
  const watched = from.endsWith('.loudnorm.mp4') || to.endsWith('/video.mp4');
  const sha = watched && hash(from);
  const value = await rename.call(this, from, to);
  if (watched) record({stage:'renamed', from, to, sha});
  return value;
};

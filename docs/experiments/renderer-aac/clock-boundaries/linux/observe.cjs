const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const original = cp.ChildProcess.prototype.spawn;
cp.ChildProcess.prototype.spawn = function(options) {
  if (['ffmpeg', 'ffprobe'].includes(path.basename(options.file))) {
    const args = options.args.map(String);
    fs.appendFileSync('/lab/commands.jsonl', JSON.stringify({file:options.file,args:args.slice(1)})+'\n');
    for(let i=1;i<args.length;i++) {
      if(args[i-1] !== '-i' && !args.includes('stream=codec_type')) continue;
      if(['pre-encode.mp4','mix.mov','baseline.mp4','audio.wav'].includes(path.basename(args[i])) && fs.existsSync(args[i])) {
        fs.copyFileSync(args[i], '/lab/'+path.basename(args[i]));
      }
    }
  }
  return original.call(this, options);
}

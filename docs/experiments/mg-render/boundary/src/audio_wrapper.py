"""Wrap the pinned binary, retaining the exact pre/post-codec intermediates."""
import os,subprocess,sys,shutil,json
from pathlib import Path
cfg=json.loads(Path(__file__).with_name('probe.json').read_text())
args=sys.argv[1:];dst=Path(args[-1]);cap=Path(cfg['capture'])
if cfg['m4a'] and '-f' in args and 'adts' in args:
    # MP4 stores codec priming in an edit list. FFmpeg sniffs the intermediate on read.
    args[args.index('adts')]='mp4'
with (cap/'commands.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
result=subprocess.run([cfg['ffmpeg'],*args],env={**os.environ,'DYLD_LIBRARY_PATH':str(Path(cfg['ffmpeg']).parent)})
if result.returncode==0 and dst.name in {'merged.wav','audio.aac'} and dst.exists():shutil.copyfile(dst,cap/dst.name)
sys.exit(result.returncode)

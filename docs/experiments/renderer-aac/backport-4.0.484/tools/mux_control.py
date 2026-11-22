"""Replay the recorded 24 fps loudnorm command, with the default movie timescale."""
import json, os, subprocess, sys
from pathlib import Path

commands, baseline, output, receipt = map(Path,sys.argv[1:])
rows = map(json.loads, commands.read_text().splitlines())
call, = [row for row in rows if row['mode']=='boundary' and '-af' in row.get('args',[]) and '-movie_timescale' in row['args']]
args = call['args'].copy()
args[args.index('-i')+1] = str(baseline)
args[-1] = str(output)
index = args.index('-movie_timescale')
assert args[index+1]=='48000'
del args[index:index+2]
env = {**os.environ, 'DYLD_LIBRARY_PATH':call['cwd']}
result = subprocess.run(args,cwd=call['cwd'],env=env,capture_output=True,text=True)
receipt.write_text(json.dumps(dict(args=args,exit=result.returncode,stderr=result.stderr),indent=2)+'\n')
result.check_returncode()

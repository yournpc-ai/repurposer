import os, subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from bench import server
from c import CHECK
route,v,tag=sys.argv[1:]
server()
cmd=['node','src/b.cjs'] if route=='B' else [sys.executable,'src/c.py']
subprocess.run(cmd+[v,tag]+([str(k) for k in CHECK] if tag=='still' and route=='B' else []),check=True)
if tag!='still':
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-i','cache/silent.mp4','-i','cache/audio.m4a','-map','0:v','-map','1:a','-c','copy','-movflags','+faststart',f'cache/{route}{v}-{tag}.mp4'],check=True)

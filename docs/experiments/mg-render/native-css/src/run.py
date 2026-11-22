import json, os, subprocess, sys, wave
from pathlib import Path
import imageio_ffmpeg, numpy as np
from bench import measure
from audio_oracle import pcm

spec=json.loads(Path('cache/data5.json').read_text())
with wave.open('cache/ref.wav','wb') as f:
    f.setparams((2,2,48000,0,'NONE',''))
    f.writeframes(np.round(pcm(spec)*32767).astype('<i2').tobytes())
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-i','cache/ref.wav','-c:a','aac','-b:a','192k','cache/audio.m4a'],check=True)
for v,tags in [(5,['cold','warm','still']),(6,['edit']),(7,['edit'])]:
    for tag in tags:
        for route in 'BC':
            name=f'{route}{v}-{tag}'
            if measure([sys.executable,'src/job.py',route,str(v),tag],name):
                raise RuntimeError(Path(f'logs/{name}.log').read_text()[-4000:])

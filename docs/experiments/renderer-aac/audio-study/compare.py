from pathlib import Path
import numpy as np
from inspect_audio import wav
from render import RATE,pcm_wave

items=[]
for recipe in ("whoosh","impact","click"):
    for version in ("default","rev"):
        items.extend((np.zeros((RATE//3,2)),wav(recipe+"-"+version+".wav")))
    items.append(np.zeros((RATE//2,2)))
Path("comparison.wav").write_bytes(pcm_wave(np.vstack(items)))

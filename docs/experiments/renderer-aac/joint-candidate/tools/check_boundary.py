"""Verify the retained pre-mux PCM and per-track delay values against the 24 fps spec."""
import hashlib, importlib.util, json, re, sys, wave
from fractions import Fraction
from pathlib import Path
import numpy as np
stage, spec_file, assets, measure = map(Path, sys.argv[1:])
loader = importlib.util.spec_from_file_location('clock_measure', measure)
m=importlib.util.module_from_spec(loader)
loader.loader.exec_module(m)
spec=json.loads(spec_file.read_text())
ref,stems=m.audio_reference(spec, assets)
with wave.open(str(stage/'audio.wav')) as w:
    pcm=np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,w.getnchannels())[:,0]/32768.
filters=(stage/'merged.wav-filter.txt').read_text()
starts=[c['start_frame'] for t in spec['tracks'] if t['kind']=='audio' for c in t['clips']]
fps=Fraction(spec['fps']['num'],spec['fps']['den'])
ends=[int(x) for x in re.findall(r'pad_len=(\d+)',filters)]
delays=[int(x) for x in re.findall(r'adelay=(\d+)\|',filters)]
tracks={}
for i,(name,stem) in enumerate(stems.items()):
    with wave.open(str(stage/f'{i}.wav')) as w:
        n=w.getnframes()
    expect=starts[i]*48000/fps
    actual=delays[i]*48
    tracks[name]=dict(expected_start=int(expect),delay_ms=delays[i],actual_start=actual,lag=m.lag(stem,pcm),stem_samples=n,pad_samples=ends[i],padded_end=actual+n+ends[i])
print(json.dumps(dict(expected_samples=len(ref),actual_samples=len(pcm),tracks=tracks,filter_graph=filters,sha256=m.digest(stage/'audio.wav')),indent=2))

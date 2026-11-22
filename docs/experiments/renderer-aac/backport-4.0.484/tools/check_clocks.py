"""Check the captured run using the pre-existing independent clocks and original frame records."""
import hashlib
import importlib.util
import json
import os
import re
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from boxes import inspect as inspect_boxes

lab, archive = map(Path, sys.argv[1:])
research = archive.parent
module = importlib.util.spec_from_file_location('measure', research/'clock-boundaries/measure.py')
measure = importlib.util.module_from_spec(module)
module.loader.exec_module(measure)
current = json.loads(Path(os.environ.get('CURRENT_METRICS', archive/'evidence/mac.json')).read_text())
old = json.loads((research/'joint-candidate/mac/mac.json').read_text())
results = {}
for case, expected in [('boundary',382000), ('edge',382080), ('success',384000), ('encodeFail',384000)]:
    row = current['cases'][case]
    stage = lab/'mac/run'/case
    original = old['media'][old['cases'][case]['files']['raw.mp4']]['video']
    assert not row['temporary_encode_dirs']
    files = {}
    for name, digest in row['files'].items():
        measured = current['media'][digest]
        audio, video = measured['audio'], measured['video']
        assert video['frames'] == original['frames'] and len(video['frames']) == row['frames']
        assert video['packetSHA'] == original['packetSHA'] and video['ptsErrors'] == video['idErrors'] == 0
        assert audio['valid'] == expected and not audio['gaps']
        assert audio['lag'] == audio['tail'] == 0 and not any(audio['stems'].values())
        if name.endswith('mp4'):
            skip = 2048 if name=='raw.mp4' or case=='encodeFail' else 1024
            assert audio['pts'] == audio['dts'] == -skip and audio['timebase'] == '1/48000'
            assert int.from_bytes(bytes.fromhex(dict(audio['side'])['skip_samples'])[:4],'little')==skip
            boxes = inspect_boxes(stage/name)
            assert boxes['movie_scale_duration'] == [48000,expected]
            assert boxes['soun']['edits'] == [[expected,skip,1,0]]
            files[name] = dict(sha256=digest,boxes=boxes,skip=skip,decoded=audio['decoded'])
    results[case] = dict(media=files,video_payload=original['packetSHA'],matched_frames=row['frames'])
fallback = current['cases']['encodeFail']['files']
assert fallback['raw.mp4']==fallback['video.mp4']==current['cases']['success']['files']['raw.mp4']

stage = lab/'mac/run/boundary'
spec = json.loads((lab/'mac/boundary.json').read_text())
ref, stems = measure.audio_reference(spec, lab/'mac/assets')
with wave.open(str(stage/'audio.wav')) as w:
    assert (w.getsampwidth(), w.getframerate())==(2,48000)
    pcm = np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,w.getnchannels())[:,0]
assert len(ref)==len(pcm)==382000
delays = re.findall(r'adelay=(\d+)S\|(\d+)S', (stage/'merged.wav-filter.txt').read_text())
clips = [c for t in spec['tracks'] if t['kind']=='audio' for c in t['clips']]
assert len(delays)==len(clips)==3
onsets = {}
for (left,right), clip in zip(delays,clips):
    start = Fraction(clip['start_frame']*48000*spec['fps']['den'],spec['fps']['num'])
    lag = measure.lag(stems[clip['clip_id']],pcm)
    assert start==int(left)==int(right) and lag==0
    onsets[clip['clip_id']]={'start':int(start),'mix_lag':lag}
results['pcm_24'] = dict(samples=len(pcm), tracks=onsets, sha256=measure.digest(stage/'audio.wav'))

def payload(path,kind):
    h = hashlib.sha256()
    with av.open(str(path)) as f:
        for p in f.demux(getattr(f.streams,kind)[0]):
            if p.size: h.update(p.size.to_bytes(4,'big')+bytes(p))
    return h.hexdigest()

negative = lab/'mux-1000.mp4'
positive = stage/'video.mp4'
boxes = inspect_boxes(negative)
bad = measure.inspect(negative,spec,lab/'mac/assets')['audio']
assert boxes['soun']['edits']==[[7958,1024,1,0]]
assert bad['valid']==381984 and bad['decoded']==382976
pair = {kind:payload(negative,kind) for kind in ('audio','video')}
assert all(h==payload(positive,kind) for kind,h in pair.items())
results['negative_24'] = dict(boxes=boxes, audio=bad,sha256=measure.digest(negative),same_payload_as_positive=pair)
receipts = {}
for row in map(json.loads,(lab/'skip-results.jsonl').read_text().splitlines()):
    name = row['mode']
    file = lab/'skips/run'/name/'probe.mp4'
    assert row['before']==row['after']==measure.digest(file)
    assert payload(file,'video')==results['success']['video_payload']
    with av.open(str(file)) as f:
        assert bool(f.streams.audio) == (name=='silent')
        assert not list(file.parent.glob('*.loudnorm.mp4'))
    data = measure.inspect(file,json.loads((lab/'mac/mix.json').read_text()),lab/'mac/assets')
    v = data['video']
    assert len(v['frames'])==240 and v['ptsErrors']==v['idErrors']==0
    if name=='silent':
        assert data['audio']['peak']==0 and data['audio']['valid']==384000 and not data['audio']['gaps']
    receipts[name]=dict(hash=row['after'],frames=len(v['frames']),audio_samples=data.get('audio',{}).get('valid'),peak=data.get('audio',{}).get('peak'))
results['postpass_skips'] = receipts
print(json.dumps(results,indent=2))

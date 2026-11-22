"""Measure a directory of actual Renderer outputs against the archived fixtures."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

platform, measure_script, output = map(Path, sys.argv[1:])
loader = importlib.util.spec_from_file_location('clock_measure', measure_script)
m = importlib.util.module_from_spec(loader)
loader.loader.exec_module(m)
results = {}
media = {}
for case in sorted((platform/'run').iterdir()):
    spec_name = case.name if case.name in ('boundary','edge','silence','shape') else 'mix'
    spec = json.loads((platform/(spec_name+'.json')).read_text())
    item = {'spec': spec_name, 'fps': spec['fps'], 'frames': spec['duration_frames'],
            'temporary_encode_dirs': [p.name for p in case.glob('.encode-*')], 'files': {}}
    results[case.name] = item
    for f in sorted(case.iterdir()):
        if f.suffix not in ('.mp4','.mov','.mkv'): continue
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        if digest not in media:
            media[digest] = m.inspect(f, spec, platform/'assets')
        item['files'][f.name] = digest
output.write_text(json.dumps({'cases':results, 'media':media},indent=2)+'\n')
for mode,data in results.items():
    print(mode,[(k,h[:12],media[h]['video']['ptsErrors'], media[h]['video']['idErrors'],media[h].get('audio',{}).get('valid'),media[h].get('audio',{}).get('tail')) for k,h in data['files'].items()])

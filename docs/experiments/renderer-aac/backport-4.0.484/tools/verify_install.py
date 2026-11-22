"""Compare the installed backport with an unmodified locked Renderer installation."""
import hashlib
import json
import sys
from pathlib import Path

old, new = [Path(n).resolve() for n in sys.argv[1:]]
files = ('dist/esm/index.mjs', 'dist/stringify-ffmpeg-filter.js')
old_expr = '(padStart * 1000).toFixed(0)'
new_expr = chr(96) + '$' + '{Math.round(padStart * sampleRate)}S' + chr(96)

def digest(b):
    return hashlib.sha256(b).hexdigest()

def entries(root):
    return {f.relative_to(root).as_posix(): digest(f.read_bytes())
            for f in root.rglob('*') if f.is_file() and 'node_modules' not in f.relative_to(root).parts}

for root in (old, new):
    meta = json.loads((root / 'package.json').read_text())
    assert (meta['name'], meta['version']) == ('@remotion/renderer', '4.0.484')
a, b = entries(old), entries(new)
assert a.keys() == b.keys()
assert sorted(k for k in a if a[k] != b[k]) == sorted(files)
for f in files:
    source = (old / f).read_text()
    assert source.count(old_expr) == 1 and source.replace(old_expr, new_expr) == (new / f).read_text()
print(json.dumps({'package_files': len(b), 'version': '4.0.484',
                  'changed': {f: {'original': a[f], 'patched': b[f]} for f in files}},
                 indent=2))

"""Compile the additional legal 24 fps Composition from the archived fixed sources."""
import json
import sys
import uuid
from pathlib import Path

from app.editing.schemas import CompositionContent
from app.editing.store import content_digest_of
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec

fixtures, dest = map(Path, sys.argv[1:])
obj = json.loads((fixtures / 'mix.version.json').read_text())
obj['settings']['fps']['num'] = 24
end = 191 * 3750  # 90 kHz Composition ticks
obj['scenes'][0]['range']['end'] = end
visual = obj['timeline']['tracks'][0]['clips'][0]
visual['range']['end'] = end
source_range = visual['source']['source_range']
source_range['end'] = source_range['start'] + end
content = CompositionContent(**obj)
snapshot_ids = {s.snapshot_id for s in content.sources}
facts = {uuid.UUID(k): v for k, v in json.loads((fixtures / 'sources3.json').read_text()).items()
         if uuid.UUID(k) in snapshot_ids}
validate_content(content, facts)
digest = content_digest_of(content)
spec = compile_video_spec(content, facts, composition_id=uuid.uuid5(uuid.NAMESPACE_URL, 'joint-clock-24'),
                          version_id=uuid.uuid5(uuid.NAMESPACE_URL, digest), content_digest=digest)
for track in spec['tracks']:
    for clip in track['clips']:
        clip['source']['url'] = 'http://127.0.0.1:49873/' + clip['source']['url']
dest.write_text(json.dumps(spec))

import wave,json,uuid,hashlib
from pathlib import Path
from app.editing.schemas import CompositionContent
from app.editing.store import content_digest_of
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
v=json.load(open('v3.json')); s=json.load(open('sources3.json'))
with wave.open('assets/silence.wav','wb') as f:
 f.setparams((1,2,48000,0,'NONE',''));f.writeframes(bytes(48000*5*2))
for mode in ['mix','noaudio','silence']:
 tracks=[t for t in v['timeline']['tracks'] if t['track_id'] in (['track-main'] if mode=='noaudio' else ['track-main','track-voice'] if mode=='silence' else ['track-main','track-voice','track-impact','track-whoosh'])]
 import copy
 tracks=copy.deepcopy(tracks);sources={}
 for t in tracks:
  c=t['clips'][0]['source'];k=c['snapshot_id'];src=s[k].copy()
  if mode=='silence' and t['kind']=='audio':
   src.update(storage_key='silence.wav',digest=sha('assets/silence.wav'),duration_ticks=450000);k=str(uuid.uuid5(uuid.NAMESPACE_URL,'silence'));c.update(snapshot_id=k,snapshot_digest=src['digest'])
  assert sha('assets/'+src['storage_key'])==src['digest'];sources[uuid.UUID(k)]=src
 obj=CompositionContent(settings=v['settings'],scenes=v['scenes'],timeline={'tracks':tracks},sources=[dict(snapshot_id=k,snapshot_digest=i['digest']) for k,i in sources.items()])
 validate_content(obj,sources);dig=content_digest_of(obj);vid=uuid.uuid5(uuid.NAMESPACE_URL,dig)
 Path(mode+'.version.json').write_text(obj.model_dump_json())
 spec=compile_video_spec(obj,sources,composition_id=uuid.UUID(v['composition_id']),version_id=vid,content_digest=dig)
 for t in spec['tracks']:
  for c in t['clips']:c['source']['url']='http://127.0.0.1:49873/'+c['source']['url']
 Path(mode+'.json').write_text(json.dumps(spec,indent=2))

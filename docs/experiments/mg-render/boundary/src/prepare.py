import json,os,hashlib,uuid
from pathlib import Path
from app.editing.schemas import CompositionContent
from app.editing.store import content_digest_of
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,default=str))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=read('fixture/v3.json');meta={k:b.pop(k) for k in ('id','composition_id','base_version_id','content_digest','version')}
t=next(c for tr in b['timeline']['tracks'] for c in tr['clips'] if c['clip_id']=='title')
g=t['object'];g['layout'].update(x=1250,y=68,width=580,height=310);g['output'].update(width=580,height=310)
p=g['project'];p['entry']='Boundary.tsx';p['files']=[dict(path=name,content=Path('src/'+name).read_text(),digest=sha('src/'+name)) for name in ('Boundary.tsx','scene.tsx')]
p['props']['targetObjectId']='sensor-film';p['props_schema']['properties']['targetObjectId']={'type':'string'}
c=CompositionContent.model_validate(b);sources={uuid.UUID(k):v for k,v in read('fixture/sources3.json').items()}
for snap in sources.values():assert sha('assets/'+snap['storage_key'])==snap['digest']
validate_content(c,sources);dg=content_digest_of(c);vid=uuid.uuid5(uuid.NAMESPACE_URL,dg)
save('evidence/version.json',dict(**c.model_dump(mode='json'),id=vid,version=4,base_version_id=meta['id'],composition_id=meta['composition_id'],content_digest=dg))
ordinary=c.model_copy(deep=True);ordinary.timeline.tracks=[tr for tr in ordinary.timeline.tracks if tr.role!='title']
spec=compile_video_spec(ordinary,sources,composition_id=uuid.UUID(meta['composition_id']),version_id=vid,content_digest=dg)
pip=next(k for tr in spec['tracks'] for k in tr['clips'] if k['object']['object_id']==p['props']['targetObjectId'])
spec['tracks']=[tr for tr in spec['tracks'] if pip not in tr['clips']]
save('evidence/data.json',dict(spec=spec,pip=pip,mg=dict(start=t['range']['start']//3000,end=t['range']['end']//3000,layout=g['layout'],props=p['props'])))

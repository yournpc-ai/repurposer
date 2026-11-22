import copy, hashlib, json, os, uuid
from pathlib import Path
from app.editing.schemas import CompositionContent
from app.editing.store import content_digest_of
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec, _quantize_frames

def read(path):
    return json.loads(Path(path).read_text())

def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, default=str)+'\n')

mg=Path(os.environ['MG'])
base=read(mg/'boundary/evidence/version.json')
meta={k:base.pop(k) for k in ('composition_id','id','version','base_version_id','content_digest')}
sources={uuid.UUID(k):v for k,v in read(mg/'baseline/fixture/sources3.json').items()}
for s in sources.values():
    assert hashlib.sha256(Path('assets',s['storage_key']).read_bytes()).hexdigest()==s['digest']
tracks=base['timeline']['tracks']
title=next(t for t in tracks if t['track_id']=='track-title')
pip=next(t for t in tracks if t['track_id']=='track-pip')
rear=copy.deepcopy(title)
tracks.append(rear)
rear.update(order=1,track_id='track-sweep')
rear['clips'][0]['clip_id']='sweep'
rear['clips'][0]['object']['object_id']='signal-sweep'
pip['order']=2
title['order']=3
for t,entry in [(rear,'Sweep'),(title,'Readout')]:
    project=t['clips'][0]['object']['project']
    files=[]
    for name in ['Blocks.tsx','aperture.ts']:
        code=Path('src',name).read_text()
        files.append(dict(path=name,content=code,digest=hashlib.sha256(code.encode()).hexdigest()))
    project.update(entry='Blocks.tsx',composition_id=entry,files=files)
parent=meta['id']
for n in [5,6,7]:
    if n==6: title['clips'][0]['object']['project']['props']['ink']='#ffc152'
    if n==7: pip['order']=4
    c=CompositionContent.model_validate(base)
    validate_content(c,sources)
    digest=content_digest_of(c)
    vid=uuid.uuid5(uuid.NAMESPACE_URL,digest)
    save(f'evidence/v{n}.json',dict(**c.model_dump(mode='json'),id=vid,version=n,composition_id=meta['composition_id'],content_digest=digest,base_version_id=parent))
    parent=vid
    ordinary=c.model_copy(deep=True)
    generators=[tr for tr in ordinary.timeline.tracks if tr.role=='title']
    ordinary.timeline.tracks=[tr for tr in ordinary.timeline.tracks if tr.role!='title']
    spec=compile_video_spec(ordinary,sources,composition_id=uuid.UUID(meta['composition_id']),version_id=vid,content_digest=digest)
    for tr in generators:
        clip=tr.clips[0]
        g=clip.object
        spec['tracks'].append(dict(track_id=tr.track_id,kind='visual',order=tr.order,clips=[dict(start_frame=_quantize_frames(clip.range.start,c),end_frame=_quantize_frames(clip.range.end,c),object=dict(kind='generator',object_id=g.object_id,layout=g.layout.model_dump(),entry=g.project.composition_id,props=g.project.props))]))
    spec['target']=title['clips'][0]['object']['project']['props']['targetObjectId']
    save(f'cache/data{n}.json',spec)

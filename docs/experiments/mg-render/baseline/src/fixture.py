import hashlib,json,uuid,wave,os,sys
from pathlib import Path
from app.editing.schemas import CompositionContent
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec
from app.editing.store import content_digest_of
from app.editing.timing import SOURCE_TIMEBASE
import av
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def uid(s):return uuid.uuid5(uuid.NAMESPACE_URL,'urn:abc:'+s)
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,default=str))
def version(v):
    sources={};tracks=[]
    def track(name,role,start,end,obj,file=None,offset=0):
        visual=role in ('main','title');clip=dict(clip_id=name,object=obj,scene_id='survey',range=dict(start=start*3000,end=end*3000))
        if file:
            path=Path('assets')/file;key=uid(sha(path));kind=obj['kind']
            with av.open(str(path)) as c:duration=int(c.duration*SOURCE_TIMEBASE/1000000)
            sources[key]=dict(kind=kind,digest=sha(path),storage_key=file,duration_ticks=duration)
            clip['source']=dict(snapshot_id=key,snapshot_digest=sha(path),source_range=dict(start=offset*3000,end=(offset+end-start)*3000))
        tracks.append(dict(track_id='track-'+name,kind='visual' if visual else 'audio',role=role,order=len(tracks),clips=[clip]))
    def box(x,y,w,h):return dict(x=x,y=y,width=w,height=h)
    track('main','main',0,240,dict(kind='video',object_id='main-film',layout=box(0,0,1920,1080),muted=True),'main.mp4',15)
    track('pip','main',15,210,dict(kind='video',object_id='sensor-film',layout=box(1330,88,480,270),muted=True),'pip.mp4',12)
    props=dict(headline='Parallel signals',ink='#e5d392',rate=1) if v==1 else dict(headline='Signals in sync',ink='#8acdf5',rate=.72)
    files=[dict(path='Generator.tsx',content=Path('src/Generator.tsx').read_text()),dict(path='Title.tsx',content=Path('src/Title.tsx' if v==1 else 'src/TitleV2.tsx').read_text())]
    proj=dict(entry='Generator.tsx',composition_id='SignalTitle',files=files,props=props,props_schema=dict(type='object',additionalProperties=False,properties={k:dict(type='number' if k=='rate' else 'string') for k in props}))
    track('title','title',30,180,dict(kind='generator',producer='remotion-project',object_id='signal-title',project=proj,layout=box(112,720,900,210),output=dict(width=900,height=210,fps=30,duration_frames=150,background='#142b30')))
    for name,file,start,n,db,role in [('voice','voice.wav',9,150,-4,'dialogue'),('whoosh','whoosh.wav',42,36,-3,'effect'),('impact','impact1.wav' if v<3 else 'impact2.wav',60,24,-3,'effect')]:
        track(name,role,start,start+n,dict(kind='audio',object_id=name+'-audio',gain_db=db),file)
    c=CompositionContent(settings=dict(width=1920,height=1080,timebase=90000),sources=[dict(snapshot_id=k,snapshot_digest=i['digest']) for k,i in sources.items()],scenes=[dict(scene_id='survey',range=dict(start=0,end=720000))],timeline=dict(tracks=tracks))
    validate_content(c,sources)
    content=c.model_dump(mode='json'); dig=content_digest_of(c); common=dict(composition_id=uid('work'),version_id=uid('v'+str(v)),content_digest=dig)
    save(f'fixture/v{v}.json',dict(id=common['version_id'],composition_id=common['composition_id'],base_version_id=uid('v'+str(v-1)) if v>1 else None,version=v,content_digest=dig,**content))
    gen=c.timeline.tracks[2].clips[0].object; gd=gen.program_digest(); pr=gen.project
    save(f'fixture/request{v}.json',dict(producer=gen.producer,program_digest=gd,dependencies=pr.dependencies,project=pr.model_dump(exclude={'dependencies','resources'}),parameters={},resources=[],output=gen.output.model_dump()))
    save(f'fixture/sources{v}.json',{str(k):i for k,i in sources.items()})
    # Compile ordinary tracks through the current compiler. Direct paths lower the title separately.
    ordinary=c.model_copy(deep=True);ordinary.timeline.tracks.pop(2)
    spec=compile_video_spec(ordinary,sources,**common)
    save(f'fixture/direct{v}.json',dict(spec=spec,mg=dict(start=c.timeline.tracks[2].clips[0].range.start//3000,end=c.timeline.tracks[2].clips[0].range.end//3000,layout=gen.layout.model_dump(),props=pr.props,file_digest=pr.files[1].digest,program_digest=gd)))
    baked=Path('assets')/(gd+'.mp4')
    if baked.exists():
        a=compile_video_spec(c,sources,generator_media={'signal-title':dict(program_digest=gd,media=dict(storage_key=baked.name,digest=sha(baked)))},**common)
        save(f'fixture/baked{v}.json',dict(spec=a))
if __name__=='__main__':
    for v in range(1,4):version(v)

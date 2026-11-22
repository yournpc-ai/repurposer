exec(open('fixture.py').read().split("for mode in")[0])
import copy
t=copy.deepcopy(v['timeline']['tracks'][0]);c=t['clips'][0];c.pop('source');c['object']=dict(kind='shape',object_id='marker',shape='rect',layout=dict(x=50,y=50,width=100,height=100),fill='#ffffff');c['range']=dict(start=60000,end=720000)
obj=CompositionContent(settings=v['settings'],scenes=v['scenes'],timeline={'tracks':[t]},sources=[]);validate_content(obj,{});dig=content_digest_of(obj)
Path('shape.version.json').write_text(obj.model_dump_json())
spec=compile_video_spec(obj,{},composition_id=uuid.UUID(v['composition_id']),version_id=uuid.uuid5(uuid.NAMESPACE_URL,dig),content_digest=dig);Path('shape.json').write_text(json.dumps(spec))

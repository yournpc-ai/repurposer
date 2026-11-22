import os,sys,json,subprocess,time,hashlib,signal
from pathlib import Path
r,v,n=sys.argv[1:4];v=int(v);n=int(n)
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def call(cmd):
    start=time.perf_counter();print('COMMAND',*map(str,cmd),flush=True);subprocess.run(cmd,check=True);return time.perf_counter()-start
version=read(f'fixture/v{v}.json');req=read(f'fixture/request{v}.json')
for snap in read(f'fixture/sources{v}.json').values():assert digest('assets/'+snap['storage_key'])==snap['digest']
assert digest(os.environ['FONT'])==Path('fixture/font.sha256').read_text().split()[0]
stages={};key=req['program_digest'];sid=f'{r}-v{v}-r{n}';out=Path('results')/(sid+'.mp4')
partial=out.with_name(sid+'.partial.mp4')
if r=='A':
    baked=Path('assets')/(key+'.mp4')
    if not baked.exists():
        stages['source_bake_s']=call([os.environ['REP']+'/apps/render/node_modules/.bin/tsx','src/bake.ts',str(v)])
        stages['compile_baked_spec_s']=call([sys.executable,'src/fixture.py'])
    assert digest(baked)==next(t for t in read(f'fixture/baked{v}.json')['spec']['tracks'] if t['role']=='title')['clips'][0]['source']['digest']
cmd=['node','src/remotion.cjs',r,str(v),str(partial)] if r!='C' else [sys.executable,'src/chromium.py',str(v),str(partial)]
stages['final_s']=call(cmd)
with __import__('av').open(str(partial)) as c:
    s=c.streams.video[0];assert (s.frames,s.width,s.height)==(240,1920,1080);assert len(c.streams.audio)==1
os.replace(partial,out)
receipt=dict(route=r,version_id=version['id'],composition_id=version['composition_id'],content_digest=version['content_digest'],program_digest=key,run=n,sha256=digest(out),stages=stages)
tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(receipt,indent=2));tmp.replace(out.with_suffix('.json'))

from pathlib import Path
import json,hashlib,sys,subprocess,os,wave,importlib.metadata as md,statistics as st
import av,numpy as np,imageio_ffmpeg
from audio_oracle import pcm
from PIL import Image,ImageDraw,ImageFont
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False))
def wav(p,a):
    with wave.open(str(p),'wb') as f:
        f.setparams((2,2,48000,0,'NONE','not compressed'));f.writeframes(np.rint(a*32767).clip(-32768,32767).astype('<i2').tobytes())
perf=[json.loads(l) for l in Path('logs/bench.jsonl').read_text().splitlines()];con=read('logs/conform.json');cost={};repeat={}
for r in 'ABC':
    group={}
    for v in (1,2,3):
        rows=[row for row in perf if row['tag'].startswith(f'{r}-v{v}-') and row['exit']==0]
        t=[item['wall_s']+con[item['tag']]['corrected_s'] for item in rows];assert len(t)==3
        h=[sha('final/'+item['tag']+'.mp4') for item in rows];assert len(set(h))==1
        repeat[f'{r}-v{v}']=h;group[v]=dict(seconds=t,hot_median_s=st.median(t[1:]),peak_mib=max(row['peak_tree_rss_mib'] for row in rows))
    cost[r]=group
save('analysis/costs.json',cost);save('analysis/repeat.json',repeat)
control={}
for r in 'BC':
    for i in (1,2,3):
        p=Path('results')/f'control-{r}-{i}.mp4'
        with av.open(str(p)) as c:
            pkt=bytes(next(c.demux(video=0)));start=pkt.index(b'x264 - core')
            control[p.stem]=dict(x264=pkt[start:start+29].decode(),threads=next(x.decode() for x in pkt.split(b' ') if x.startswith(b'threads=')),video_frames=c.streams.video[0].frames,muxer=c.metadata['encoder'],sha256=sha(p))
save('analysis/encoder-control.json',control)
plot=Image.new('RGB',(960,460),'#10272e');d=ImageDraw.Draw(plot);font=ImageFont.truetype(os.environ['FONT'],17)
spec=read('fixture/direct3.json')['spec'];ref=pcm(spec);wav('analysis/reference-v3.wav',ref)
waves={'Reference PCM':ref}
for r in 'ABC':
    with av.open(f'final/{r}-v3-r1.mp4') as c:y=np.concatenate([f.to_ndarray().T for f in c.decode(audio=0)])[:384000]
    wav(f'analysis/decoded-{r}.wav',y);waves[r+' decoded AAC']=y
d.text((18,9),'Audio alignment   /   overlap at 2.000 s',fill='white',font=font)
for i,(label,a) in enumerate(waves.items()):
    top=55+i*93;x0=184;w=735;start=72000;end=129600
    d.text((14,top+17),label,fill='#c5d1ce',font=font)
    for j,b in enumerate(np.array_split(a[start:end,0],w)):
        d.line((x0+j,top+33-int(b.max()*78),x0+j,top+33-int(b.min()*78)),fill='#b7d8b8')
    x=x0+int(w*(96000-start)/(end-start));d.line((x,top,x,top+67),fill='#e9aa71')
d.text((184,424),'1.500 s',fill='white',font=font);d.text((455,424),'Impact / flash',fill='#e9aa71',font=font);d.text((852,424),'2.700 s',fill='white',font=font);plot.save('analysis/audio-alignment.png')
rep=Path(os.environ['REP']);chrome=os.environ['CHROME'];ff=imageio_ffmpeg.get_ffmpeg_exe()
versions={n:md.version(n) for n in ('playwright','opencv-python-headless','pillow','numpy','av','imageio-ffmpeg') if any(d.metadata['Name'].lower()==n for d in md.distributions())}
manifest=dict(commit=subprocess.check_output(['git','-C',str(rep),'rev-parse','HEAD'],text=True).strip(),workspace_status=subprocess.check_output(['git','-C',str(rep),'status','--porcelain'],text=True),environment=dict(os=subprocess.check_output(['sw_vers'],text=True),chip=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),node=subprocess.check_output(['node','-v'],text=True).strip(),python=sys.version,python_packages=versions,node_packages=json.loads(subprocess.check_output(['node','-e',"""console.log(JSON.stringify(Object.fromEntries(['remotion','@remotion/renderer','@remotion/bundler','@remotion/player','react','react-dom','esbuild'].map(n=>[n,require(n+'/package.json').version]))))"""],text=True)),system_files={p:sha(p) for p in (chrome,ff,os.environ['FFBIN']+'/ffmpeg',os.environ['FONT'])}),versions=[],inputs={},outputs={},encoder_control=control)
recipes=read('fixture/recipes.json')
for p in Path('assets').iterdir():manifest['inputs'][p.name]=dict(sha256=sha(p),bytes=p.stat().st_size)
for v in (1,2,3):
    cv=read(f'fixture/v{v}.json');g=read(f'fixture/request{v}.json');choice='impact1' if v<3 else 'impact2'
    manifest['versions'].append(dict(composition_id=cv['composition_id'],version=cv['version'],version_id=cv['id'],parent=cv['base_version_id'],content_digest=cv['content_digest'],program_digest=g['program_digest'],inputs=g['project']['props'],source_files={x['path']:x['digest'] for x in g['project']['files']},impact_recipe=recipes[choice],impact_sha256=sha('assets/'+recipes[choice]['file']),whoosh_recipe=recipes['whoosh'],recipe_implementation=sha('src/materials.py')))
for p in sorted(Path('final').glob('*.mp4')):manifest['outputs'][str(p)]=dict(sha256=sha(p),bytes=p.stat().st_size)
save('manifest.json',manifest)

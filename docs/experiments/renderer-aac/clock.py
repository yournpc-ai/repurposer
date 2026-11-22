import json,subprocess,os
from pathlib import Path
import av,numpy as np
cmds=[c for c in map(json.loads,open('commands.jsonl')) if c['mode']=='success' and 'args' in c and any('measured_I=' in a for a in c['args'])]
ff=Path(cmds[0]['file']);env=dict(os.environ,DYLD_LIBRARY_PATH=str(ff.parent))
filt=cmds[0]['args'][cmds[0]['args'].index('-af')+1]
out={}
for name,options in [('filter-pcm',['-af',filt,'-ar','48000','-c:a','pcm_s16le']),('aac-only',['-c:a','aac','-b:a','192k'])]:
 path=name+'.mov';cmd=[str(ff),'-y','-i','run/success/raw.mp4','-vn',*options,path]
 done=subprocess.run(cmd,stderr=subprocess.PIPE,env=env);Path(name+'.log').write_bytes(done.stderr);out[name]={'cmd':cmd,'exit':done.returncode}
for name,path in [('raw','run/success/raw.mp4'),('normalized','run/success/video.mp4'),('filter-pcm','filter-pcm.mov'),('aac-only','aac-only.mov')]:
 with av.open(path) as c:
  s=c.streams.audio[0];pts=[];pcm=[];r=av.AudioResampler(format='fltp',layout='stereo',rate=48000)
  for f in c.decode(audio=0):
   pts.append((int(f.pts*f.time_base*48000),f.samples));pcm.extend(g.to_ndarray()[0] for g in r.resample(f))
  gaps=[{'after':a+n,'resume':b,'size':b-a-n} for (a,n),(b,_) in zip(pts,pts[1:]) if b!=a+n]
  d=out.setdefault(name,{});d.update(duration=int(s.duration*s.time_base*48000),gaps=gaps,decoded=sum(x[1] for x in pts))
  x=np.concatenate(pcm);ref=np.fromfile('reference.stereo.f32le','<f4')[::2];timeline=np.zeros(max(a+n for a,n in pts));i=0
  for a,n in pts:timeline[a:a+n]=x[i:i+n];i+=n
  d['timeline_windows']=[]
  for a,b in [(14400,70000),(96000,120000),(246000,254400)]:
   t=ref[a:b]; d['timeline_windows'].append({'window':[a,b],'rms':float(np.mean(t*t)**.5),'lags_scores':[(sh,float(np.corrcoef(t,timeline[a+sh:b+sh])[0,1])) for sh in (2048,4800)]})
Path('clock.json').write_text(json.dumps(out,indent=2))

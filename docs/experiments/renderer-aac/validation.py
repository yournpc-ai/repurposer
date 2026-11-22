import subprocess,json,os
from pathlib import Path
import av,numpy as np
cmd=next(c['args'][:] for c in map(json.loads,open('commands.jsonl')) if c.get('mode')=='success' and any('measured_I=' in x for x in c.get('args',[])))
ff=cmd[0];env=dict(os.environ,DYLD_LIBRARY_PATH=str(Path(ff).parent));m=json.load(open('metrics.json'))['control.mp4']['audio']['measured']
argslog=[]
for reset in (False,True):
 p='aligned-normalized'+('-clock' if reset else '')+'.mp4';a=cmd.copy();a[a.index('-i')+1]='control.mp4';a[-1]=p;f='loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true:print_format=summary'.format(**m);a[a.index('-af')+1]=f+(',aresample=48000,asetpts=N/SR/TB' if reset else '')
 done=subprocess.run(a,capture_output=True,env=env);assert done.returncode==0
 with av.open(p) as c:
  st=c.streams.audio[0];pts=[(int(x.pts*x.time_base*48000),x.samples) for x in c.decode(audio=0)];gaps=[(u[0]+u[1],v[0]) for u,v in zip(pts,pts[1:]) if u[0]+u[1]!=v[0]]
  argslog.append(dict(command=a,exit=done.returncode,decoded=sum(n for _,n in pts),clock=round(st.duration*st.time_base*48000),gaps=gaps));print(p,argslog[-1]['decoded'],argslog[-1]['clock'],gaps)
Path('aligned-control.json').write_text(json.dumps(argslog,indent=2))

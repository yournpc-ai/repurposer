import json,os,subprocess,av
from pathlib import Path
c=[c['args'] for c in map(json.loads,open('commands.jsonl')) if c.get('mode')=='success' and 'args' in c]
enc=next(a[:] for a in c if 'adts' in a);mux=next(a for a in c if '-c:a' in a and 'copy' in a and '-crf' in a);env=dict(os.environ,DYLD_LIBRARY_PATH=str(Path(enc[0]).parent));enc[enc.index('adts')]='mp4';enc[enc.index('-i')+1]='run/success/merged.wav';enc[-1]='control.m4a';ff=enc[0]
steps=[enc,[ff,'-y','-i','run/success/raw.mp4','-i','control.m4a','-map','0:v','-map','1:a','-c','copy','control.mp4']]
a=next(a[:] for a in c if any('measured_I=' in x for x in a));a.insert(1,'-debug_ts');a[-1]='debug.mp4';steps.append(a)
for i,args in enumerate(steps):
 with open('control-'+str(i)+'.log','wb') as f:r=subprocess.run(args,stderr=f,env=env);assert r.returncode==0
Path('control-commands.json').write_text(json.dumps(steps,indent=2))

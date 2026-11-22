from pathlib import Path
import os,time,sys,subprocess,tempfile,json,hashlib
from materials import video,recipe
from fractions import Fraction
root=Path.cwd()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
recipes=json.loads((root/'fixture/recipes.json').read_text())
tasks=[('narration.aiff',lambda:subprocess.run(['say','-v','Samantha','-r','174','-o','assets/narration.aiff','Two clocks, one cut. Watch the signals meet, then follow the second pulse.'],check=True)),('voice.wav',lambda:subprocess.run(['afconvert','-f','WAVE','-d','LEI16@48000','assets/narration.aiff','assets/voice.wav'],check=True)),('main.mp4',lambda:video('main',Fraction(24000,1001),(960,540),213)),('pip.mp4',lambda:video('pip',Fraction(25),(480,270),184))]
tasks += [(d['file'],lambda k=k,d=d:recipe('whoosh' if k=='whoosh' else 'impact',d)) for k,d in recipes.items()]
out={}
with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp);Path('assets').mkdir()
    for n,fn in tasks:
        t=time.perf_counter();fn();out[n]=dict(seconds=time.perf_counter()-t,identical_to_fixture=sha(Path('assets')/n)==sha(root/'assets'/n))
    os.chdir(root)
Path('logs/shared-material-cost.json').write_text(json.dumps(out,indent=2))

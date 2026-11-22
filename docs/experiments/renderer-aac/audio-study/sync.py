"""Fixed three-second motion study. Re-run from the evidence directory."""
import math,json,os
from fractions import Fraction
from pathlib import Path
import av, numpy as np
from PIL import Image,ImageDraw
from inspect_audio import wav,decode,db
from render import RATE,dump,digest
FPS=30
SPF=RATE//FPS
N=90
root=Path(os.environ.get("REP_REPO","/Users/sylas/repurposer"))
fixtures=root/"docs/tasks/agent-editor-evidence/iteration-6"
mix=np.zeros((N*SPF,2))
refs={}
for asset,start,gain in [("sample-generate_music.wav",0,0.20),("sample-generate_voice.mp3",0.76,0.72)]:
    path=fixtures/asset
    refs[asset]=digest(path.read_bytes())
    _,x=decode(path)
    i=round(start*RATE)
    x=x[:len(mix)-i]
    mix[i:i+len(x)]+=gain*x
stats={}
stems={}
for key,frame,level in [("whoosh",36,0.58),("impact",42,0.55),("click",65,0.68)]:
    x=wav(key+"-default.wav")
    peak=int(abs(x).max(axis=1).argmax())
    start=math.floor(frame-peak/SPF+.5)
    i=start*SPF
    mix[i:i+len(x)]+=level*x
    stems[key]=x*level
    stats[key]=dict(action_frame=frame,start_frame=start,start_sample=i,source_peak_sample=peak,
                    clip_gain_db=db(level),peak_error_ms=(i+peak-frame*SPF)/48)
assert abs(mix).max()<1
def title_x(frame):
    u=max(0,min(1,(frame-30)/12))
    return round(20+300*(3*u*u-2*u**3))

def image(frame):
    im=Image.new("RGB",(640,240),(15,22,35))
    d=ImageDraw.Draw(im)
    x=title_x(frame)
    d.rounded_rectangle((x,47,x+214,112),10,fill=(30,195,180))
    d.text((x+16,70),"MOTION   /   AUDIO",fill=(10,28,38))
    d.rounded_rectangle((440,148,535,185),7,fill=(235,145,42) if 65<=frame<70 else (64,69,86))
    d.text((465,160),"SELECT",fill="white")
    return im

with av.open("sync.mp4","w") as c:
    v=c.add_stream("libx264",rate=FPS)
    v.width,v.height,v.pix_fmt=640,240,"yuv420p"
    a=c.add_stream("aac",rate=RATE)
    a.layout="stereo"
    a.bit_rate=192000
    for f in range(N):
        vf=av.VideoFrame.from_image(image(f));vf.pts=f;vf.time_base=Fraction(1,FPS)
        for packet in v.encode(vf):c.mux(packet)
        af=av.AudioFrame.from_ndarray(np.ascontiguousarray(mix[f*SPF:(f+1)*SPF].T,dtype="float32"),format="fltp",layout="stereo")
        af.sample_rate=RATE;af.pts=f*SPF;af.time_base=Fraction(1,RATE)
        for packet in a.encode(af):c.mux(packet)
    for codec in (a,v):
        for packet in codec.encode(None):c.mux(packet)

audio_start,encoded=decode("sync.mp4")
visual=[]
with av.open("sync.mp4") as c:
    for f in c.decode(video=0):
        rgb=f.to_ndarray(format="rgb24")
        green=rgb[58,:,1]>150
        visual.append((float(f.pts*f.time_base),int(np.flatnonzero(green)[0]),int(rgb[154,454,0])>180))
assert len(visual)==N and next(i for i,row in enumerate(visual) if row[2])==65
assert max(abs(title_x(i)-x) for i,(_,x,_) in enumerate(visual))<=2
for key,stat in stats.items():
    # Cross-correlate the known dry reference with the actual AAC mix around expected time.
    x=stems[key].mean(axis=1)
    start=stat["start_sample"];radius=2400
    region=encoded[start-radius:start+len(x)+radius].mean(axis=1)
    correlation=np.correlate(region,x,"valid")
    lag=int(correlation.argmax())-radius
    measured=(start+lag+stat["source_peak_sample"])/RATE+audio_start
    stat.update(matched_lag_samples=lag,correlation=round(float(correlation.max()/(np.linalg.norm(x)*np.linalg.norm(region[radius+lag:radius+lag+len(x)]))),4),
                matched_peak_vs_decoded_frame_ms=round((measured-visual[stat["action_frame"]][0])*1000,3))
dump("sync.json",dict(events=stats,frames=[dict(frame=i,pts_s=t,x=x,pressed=b) for i,(t,x,b) in enumerate(visual)],
                       voice_and_bgm=refs,mix_peak_dbfs=db(abs(mix).max()),aac_peak_dbfs=db(abs(encoded).max()),
                       decoded_audio_start=audio_start,sha256=digest(Path("sync.mp4").read_bytes())))
print(stats)

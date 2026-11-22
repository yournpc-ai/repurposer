import json,hashlib,wave,subprocess,os,sys
from pathlib import Path
from fractions import Fraction
import numpy as np,av
R=Path.cwd();ff=next((R/'repo/node_modules/.pnpm').glob('@remotion+compositor-darwin-arm64@*/node_modules/@remotion/compositor-darwin-arm64'));env=dict(os.environ,DYLD_LIBRARY_PATH=str(ff))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,indent=2))
mix=json.load(open('mix.json'));ref=np.zeros(384000);stems={}
for t in mix['tracks']:
 if t['kind']!='audio':continue
 c=t['clips'][0];a=c['start_frame']*1600;b=c['end_frame']*1600
 with wave.open('assets/'+c['source']['url'].split('/')[-1]) as w:
  w.setpos(c['source']['start_frame']*1600);x=np.frombuffer(w.readframes(b-a),'<i2')/32768*10**(c['object']['gain_db']/20)/np.sqrt(2)
 stem=ref*0;stem[a:b]=x;stems[c['clip_id']]=stem;ref[a:b]+=x
np.repeat(ref[:,None],2,axis=1).astype('<f4').tofile('reference.stereo.f32le')
def lag(x,y):
 n=1<<(len(x)+len(y)-1).bit_length();off=np.arange(-5000,5001)
 return int(off[np.argmax(np.fft.irfft(np.fft.rfft(x,n).conj()*np.fft.rfft(y,n),n)[off])])
with av.open('assets/main.mp4') as c:times=[f.pts*f.time_base for f in c.decode(video=0)]
def measure(p):
 h=sha(p);probe=subprocess.check_output([ff/'ffprobe','-v','error','-show_packets','-show_streams','-show_format','-of','json',p],env=env); (p.parent/(p.name+'.probe.json')).write_bytes(probe)
 info=json.loads(probe);d={'sha':h,'format':info['format']['format_name']}
 for s in info['streams']:
  k=s['codec_type'];pkt=next(q for q in info['packets'] if q['stream_index']==s['index']);d[k]={z:s.get(z) for z in ['codec_name','time_base','sample_rate','start_pts','duration_ts']};v=d[k];v.update(firstPTS=pkt.get('pts'),firstDTS=pkt.get('dts'),side=pkt.get('side_data_list'))
  with av.open(str(p)) as c:
   st=c.streams[s['index']];hh=hashlib.sha256()
   for pk in c.demux(st):
    if not pk.size:continue
    raw=bytes(pk)
    if info['format']['format_name']=='aac':raw=raw[7 if raw[1]&1 else 9:]
    hh.update(len(raw).to_bytes(4,'big'));hh.update(raw)
   v['packetSHA']=hh.hexdigest()
  if k=='video':
   if h in videoCache: v.update(videoCache[h]);continue
   with av.open(str(p)) as c:
    rows=[]
    for i,f in enumerate(c.decode(video=0)):
     pix=f.to_ndarray(format='gray')
     if 'shape' in str(p):
      rows.append([i,str(f.pts*f.time_base),int(pix[100,100]>127),int(i>=20)]);continue
     code=sum(int(pix[32,2*(16+j*12)]>127)<<j for j in range(10));target=Fraction(i+15,30);near=min(range(len(times)),key=lambda j:(abs(times[j]-target),-j))
     rows.append([i,str(f.pts*f.time_base),code,near])
   dump(p.parent/(p.name+'.frames.json'),rows);vt=dict(frames=len(rows),ptsErrors=sum(Fraction(r[1])!=Fraction(r[0],30) for r in rows),idErrors=sum(r[2]!=r[3] for r in rows));videoCache[h]=vt;v.update(vt)
  if k=='audio':
   with av.open(str(p)) as c:
    res=av.AudioResampler(format='fltp',layout='stereo',rate=48000);y=np.concatenate([g.to_ndarray().T for f in c.decode(audio=0) for g in res.resample(f)])
   v.update(decoded=len(y),peak=float(abs(y).max()),clips=int((abs(y)>=1).sum()),present=round(Fraction(s['time_base'])*s['duration_ts']*48000))
   if v['peak']:
    sig=y[:,0];shift=lag(ref,sig);i=max(0,-shift);j=min(len(ref),len(sig)-shift);v.update(lag=shift,corr=float(np.corrcoef(ref[i:j],sig[i+shift:j+shift])[0,1]),stemLag={n:lag(x,sig) for n,x in stems.items()})
   if p.suffix=='.mp4':
    rr=subprocess.run([ff/'ffmpeg','-hide_banner','-nostats','-i',p,'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,env=env,check=True);v['measured']=json.loads(rr.stderr[rr.stderr.rfind('{'):rr.stderr.rfind('}')+1])
 return d
videoCache={};res={};store={}
for file in sys.argv[1:]:
 p=Path(file);h=sha(p)
 if h not in store:store[h]=measure(p)
 res[file]=store[h]
 dump(Path('metrics.json'),res)
 print(file,json.dumps(res[file]),flush=True)

import bisect,csv,hashlib,itertools,json,math,os,subprocess,sys,wave
from fractions import Fraction
from pathlib import Path
import av,numpy as np,cv2,imageio_ffmpeg
from PIL import Image,ImageDraw
from audio_oracle import pcm
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):Path('analysis/'+p).write_text(json.dumps(d,indent=2))
def samples(p):
    with av.open(str(p)) as c:return np.concatenate([f.to_ndarray().T for f in c.decode(audio=0)])
def lag(x,y):
    N=1<<((len(x)+len(y)-2).bit_length());corr=np.fft.irfft(np.fft.rfft(y,N)*np.fft.rfft(x,N).conj(),N)
    inds=np.arange(-3500,3501);i=int(inds[np.argmax(corr[inds])]);return i
def audios():
    result={}
    for v in (1,2,3):
        spec=read(f'fixture/direct{v}.json')['spec'];ref=pcm(spec)
        stems={}
        for tr in spec['tracks']:
            if tr['kind']=='audio':stems[tr['role']+tr['track_id']]=pcm({**spec,'tracks':[tr]})[:,0]
        lo=96000;hi=124800;X=np.stack(list(stems.values()),axis=1)[lo:hi]
        for r in 'ABC':
            key=f'{r}-v{v}-r1';p='final/'+key+'.mp4';raw=samples('results/'+key+'.mp4')[:,0];full=samples(p);y=full[:384000,0]
            idx=lag(ref[:,0],raw);lag_final=lag(ref[:,0],y)
            cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',p,'-vn','-af','ebur128=peak=true','-f','null','-']
            log=subprocess.run(cmd,stderr=subprocess.PIPE,text=True,check=True).stderr;Path('logs/'+key+'-levels.log').write_text(log)
            peak=float(log.split('True peak:')[-1].split('Peak:')[1].split()[0])
            fit=np.linalg.lstsq(X,y[lo:hi],rcond=None)[0]
            impact=stems['effecttrack-impact']
            residual=y-(ref[:,0]-impact)
            ilag=lag(impact[lo-4800:hi],residual[lo-4800:hi])
            result[key]=dict(raw_lag_samples=idx,final_lag_samples=lag_final,impact_lag_samples=ilag,true_peak_dbtp=peak,clipped_samples=int(np.sum(np.abs(full)>=1)),decoded_samples=len(full),correlation=float(np.corrcoef(ref[:,0],y)[0,1]),overlap_coefficients=dict(zip(stems,map(float,fit))),stems_overlap_rms={k:float(np.sqrt(np.mean(a[lo:hi]**2))) for k,a in stems.items()},audio_sha256=hashlib.sha256(full.tobytes()).hexdigest())
    save('audio.json',result)
def getrgb(f):return f.to_ndarray(format='rgb24')
def source_times(p):
    with av.open(p) as c:return [f.pts*f.time_base for f in c.decode(video=0)]
def code(a,x,y,m):return sum((int(a[y,int(x+m*(16+j*12)),0])>127)<<j for j in range(10))
def error(x,y):
    count=x.size;mae=cv2.norm(x,y,cv2.NORM_L1)/count;mse=cv2.norm(x,y,cv2.NORM_L2SQR)/count
    return mae,mse
def video():
    times={key:source_times('assets/'+key+'.mp4') for key in ('main','pip')}
    data={};stats={};preview={};pts_stats={}
    fields=['version','route','frame','source','target_sec','actual_index','actual_pts','nearest_index','interval_index','actual_minus_target_ms']
    sheet=Image.new('RGB',(1200,3*245),'#102428');draw=ImageDraw.Draw(sheet)
    with open('analysis/source-pts.csv','w') as f,open('analysis/frame-errors.csv','w') as m:
        pt=csv.writer(f);pt.writerow(fields);errors=csv.writer(m);errors.writerow(['version','frame','pair','full_mae','full_mse','title_box_mae','outside_box_mae'])
        for v in (1,2,3):
            cs={r:av.open(f'final/{r}-v{v}-r1.mp4') for r in 'ABC'}
            streams=[cs[r].decode(video=0) for r in 'ABC']
            ids={r:hashlib.sha256() for r in 'ABC'};flash={r:[] for r in 'ABC'}
            for k,frames in enumerate(zip(*streams,strict=True)):
                pix={}
                for r,frame in zip('ABC',frames):
                    assert frame.pts*frame.time_base==Fraction(k,30)
                    pix[r]=a=getrgb(frame);ids[r].update(a.data)
                    if 30<=k<180 and np.mean(a[747:760,966:979])>235:flash[r].append(k)
                    for src,offset,x,y,scale in [('main',15,0,32,2),('pip',-3,1330,105,1)]:
                        if src=='pip' and not 15<=k<210:continue
                        target=Fraction(k+offset,30);ts=times[src];actual=code(a,x,y,scale);assert actual<len(ts)
                        left=bisect.bisect_right(ts,target)-1
                        near=left+int(left+1<len(ts) and ts[left+1]-target<=target-ts[left])
                        dist=float((ts[actual]-target)*1000)
                        pt.writerow([v,r,k,src,str(target),actual,str(ts[actual]),near,left,round(dist,5)])
                        bucket=pts_stats.setdefault(f'{v}-{r}-{src}',[0,0,0,0,0])
                        bucket[0]+=1;bucket[1]+=int(actual!=near);bucket[2]+=int(actual!=left);bucket[3]=max(bucket[3],abs(dist));bucket[4]+=int(abs(ts[actual]-target)>abs(ts[near]-target))
                    if v==3 and k in (15,60,170):
                        Image.fromarray(a).save(f'analysis/{r}-f{k:03}.png')
                        row='ABC'.index(r);col=(15,60,170).index(k);sheet.paste(Image.fromarray(a).resize((400,225)),(400*col,row*245+20));draw.text((400*col+5,row*245+3),f'{r}   frame {k}',fill='white')
                    if v==3:
                        for label,path in [('renderer',f'analysis/still-{r}.png')]+([('player',f'analysis/player-{r}-{k}.png')] if r!='C' else []):
                            if ((label=='renderer' and k==60) or (label=='player' and k in (45,60,100))) and Path(path).exists():
                                b=np.array(Image.open(path).convert('RGB'));preview[f'{label}-{r}-{k}']=dict(mae=error(a,b)[0],source_codes=[code(b,0,32,2),code(b,1330,105,1)],output_codes=[code(a,0,32,2),code(a,1330,105,1)])
                for p,q in [('A','B'),('B','C')]:
                    x,y=pix[p],pix[q];e,z=error(x,y);roi=(slice(720,930),slice(112,1012));te=error(x[roi],y[roi])[0]
                    oe=(e*x.size-te*x[roi].size)/(x.size-x[roi].size)
                    key=f'v{v}-{p}{q}';stats.setdefault(key,[]).append((e,z,te,oe));errors.writerow([v,k,p+q,e,z,te,oe])
            assert k==239
            for r,c in cs.items():
                st=c.streams.video[0];assert (st.width,st.height,st.average_rate,c.duration)==(1920,1080,30,8000000)
                data[f'{r}-v{v}']=dict(rgb24_sha256=ids[r].hexdigest(),flash_frames=flash[r],size=[1920,1080],frames=k+1,duration_s=8)
                c.close()
    sheet.save('analysis/frames.jpg',quality=94)
    save('video.json',data);save('preview.json',preview);save('source-pts-summary.json',pts_stats)
    save('quality.json',{k:dict(mean_mae=np.mean(a,axis=0)[0],psnr_db=10*math.log10(255**2/np.mean(a,axis=0)[1]),max_frame_mae=max(i[0] for i in a),title_box_mae=np.mean(a,axis=0)[2],other_mae=np.mean(a,axis=0)[3]) for k,a in stats.items()})
if __name__=='__main__':audios();video()

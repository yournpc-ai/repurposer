import csv, hashlib, json, shutil, subprocess, sys
from fractions import Fraction
from pathlib import Path
import av, cv2, numpy as np
from PIL import Image, ImageDraw
from c import CHECK
from verify import code, lag, samples, source_times
from audio_oracle import pcm

E=Path('evidence')
def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def img(path): return np.asarray(Image.open(path).convert('RGB'))
def mae(a,b): return round(cv2.norm(a,b,cv2.NORM_L1)/a.size,4)
def ids(x,k): return [int(code(x,0,32,2)),int(code(x,1330,104,1)) if 15<=k<210 else None]
def changes(x,y,path=''):
    if isinstance(x,dict):
        assert x.keys()==y.keys()
        return sum((changes(x[k],y[k],path+'/'+k) for k in x),[])
    if isinstance(x,list):
        assert len(x)==len(y)
        return sum((changes(a,b,path+'/'+str(k)) for k,(a,b) in enumerate(zip(x,y))),[])
    return [] if x==y else [[path,x,y]]

spec=read('cache/data5.json')
refs=[source_times('assets/'+name+'.mp4') for name in ['main','pip']]
result={'outputs':{},'repeat':{},'edits':{},'ablations':{}}
for v in [5,6,7]:
    subprocess.run([sys.executable,'src/c.py',str(v),'probe'],check=True)
for a,b in [(5,6),(6,7)]:
    u,v=[read(E/f'v{i}.json') for i in [a,b]]
    assert v['base_version_id']==u['id']
    diff=changes(u['timeline'],v['timeline'])
    assert len(diff)==1
    for key in u.keys()-{'timeline','id','version','base_version_id','content_digest'}:assert u[key]==v[key]
    areas={}
    for k in CHECK:
        before,after=[img(f'cache/v{i}-{k}.png') for i in [a,b]]
        mask=np.any(before!=after,axis=2)
        y,x=np.where(mask)
        areas[k]=[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if len(x) else None
        if len(x):assert 30<=k<180 and x.min()>=1250 and y.min()>=68 and x.max()<1830 and y.max()<378
    assert areas[72]
    result['edits'][b]=dict(changes=diff,changed_pixel_bounds=areas)
for name in ['blend','glass']:
    normal=img('cache/v5-72.png')
    off=img(f'cache/{name}-off-5.png')
    mask=(normal!=off).any(axis=2)
    assert mask.any()
    result['ablations'][name]=dict(changed_pixels=int(mask.sum()),changed_pixel_mae=mae(normal[mask],off[mask]))
rows=[]
still_hash=read('cache/C5-raster.json')
for route in 'BC':
    cold,warm=[sha(f'cache/{route}5-{tag}.mp4') for tag in ['cold','warm']]
    result['repeat'][route]=dict(cold=cold,warm=warm,byte_equal=cold==warm)
source_rows=[]
for v,tag in [(5,'warm'),(6,'edit'),(7,'edit')]:
    files=[Path(f'cache/{r}{v}-{tag}.mp4') for r in 'BC']
    for r,p in zip('BC',files):
        y=samples(p)
        with av.open(str(p)) as cont:
            audio=cont.streams.audio[0]
            presented=int(audio.duration*audio.time_base*audio.rate)
        drift=lag(pcm(spec)[:,0],y[:,0])
        assert drift==0 and presented==384000
        result['outputs'][r+str(v)]=dict(sha256=sha(p),pcm_digest=hashlib.sha256(y.tobytes()).hexdigest(),lag_samples=drift,presented_samples=presented)
    with av.open(str(files[0])) as b,av.open(str(files[1])) as c:
        for k,(bf,cf) in enumerate(zip(b.decode(video=0),c.decode(video=0),strict=True)):
            assert cf.pts*cf.time_base==bf.pts*bf.time_base==Fraction(k,30)
            B,C=[f.to_ndarray(format='rgb24') for f in (bf,cf)]
            targets=[Fraction(k+15,30),Fraction(k-3,30)]
            nearest=[min(range(len(ts)),key=lambda i:(abs(ts[i]-t),-i)) for ts,t in zip(refs,targets)]
            if not 15<=k<210:nearest[1]=None
            indexes=[ids(p,k) for p in [B,C]]
            assert indexes[1]==nearest,(k,indexes,nearest)
            source_rows.append([v,k,*nearest,*indexes[0],*indexes[1]])
            if k not in CHECK: continue
            row=dict(v=v,k=k,expected=nearest,B=ids(B,k),C=ids(C,k),BC_mae=mae(B,C),BC_roi_mae=mae(B[68:378,1250:1830],C[68:378,1250:1830]))
            assert row['C']==nearest,row
            if v==5:
                for route,pixels in [('B',B),('C',C)]:
                    png=f'cache/{route}-{k}.png'
                    raw=img(png)
                    row[route+'_seek_mae']=mae(raw,pixels)
                    row[route+'_seek_ids']=ids(raw,k)
                    assert ids(raw,k)==row[route],row
                row['C_seek_exact']=sha(f'cache/C-{k}.png')==still_hash[str(k)]
                assert row['C_seek_exact']
            rows.append(row)
        assert k==239
assert len(set(x['pcm_digest'] for x in result['outputs'].values()))==1
with (E/'source-ids.csv').open('w') as out:
    writer=csv.writer(out);writer.writerow(['version','frame','main_expected','pip_expected','B_main','B_pip','C_main','C_pip']);writer.writerows(source_rows)
result['checkpoints']=rows
result['temp_bytes']={d:sum(p.stat().st_size for p in Path('cache',d).rglob('*') if p.is_file()) for d in ['bundle','frames']}
for f in ['page.js','audio.m4a','ref.wav','silent.mp4']:result['temp_bytes'][f]=Path('cache',f).stat().st_size
(E/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
shutil.copy('logs/bench.jsonl',E)
for path in ['cache/B5-warm.mp4','cache/C5-warm.mp4']:shutil.copy(path,E)
sheet=Image.new('RGB',(1200,550),'#161e25')
draw=ImageDraw.Draw(sheet)
for i,(name,label) in enumerate([('B-72','B / frame 72'),('C-72','C / frame 72'),('blend-off-5','C / blend disabled'),('glass-off-5','C / backdrop filter disabled'),('v6-72','V6 / title ink'),('v7-72','V7 / PiP in front')]):
    tile=Image.open('cache/'+name+'.png').crop((1200,45,1860,425)).resize((400,230))
    x,y=i%3*400,i//3*275
    sheet.paste(tile,(x,y+25));draw.text((x+10,y+6),label)
sheet.save(E/'frame72.jpg',quality=94)

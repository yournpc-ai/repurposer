"""Identify inset frames even when the timecode is masked, using exposed moving curves."""
import csv,io,json
from fractions import Fraction
from pathlib import Path
import av,numpy as np
from PIL import Image
from c import Paint,data,sync_playwright

def channel(rgb):return rgb[70:235:2,::2,1].astype(np.int16)
def match(target,refs,mask,near):
    candidates=range(max(0,near-3),min(len(refs),near+4))
    # Score pixels where those candidates actually differ, away from text and feather.
    stack=np.stack([refs[i] for i in candidates]);usable=(np.ptp(stack,axis=0)>14)&mask
    if usable.sum()<50:raise ValueError('insufficient moving unmasked pixels')
    errors=np.mean(np.abs(stack[:,usable]-channel(target)[usable]),axis=1)
    ids=np.argsort(errors)
    return candidates[ids[0]],round(float(errors[ids[1]]-errors[ids[0]]),3),int(usable.sum())
def main():
    d=data();E=Path('evidence');rows=[]
    events=json.loads((E/'preview-events.json').read_text());checked={e['frame'] for e in events if 'frame' in e}
    with av.open('assets/pip.mp4') as c:
        frames=list(c.decode(video=0));pts=[f.pts*f.time_base for f in frames]
        refs=[channel(f.to_ndarray(format='rgb24')) for f in frames]
    with sync_playwright() as pw,av.open(str(E/'B-m4a.mp4')) as b,av.open(str(E/'C.mp4')) as c:
        painter=Paint(pw,d)
        for k,(bf,cf) in enumerate(zip(b.decode(video=0),c.decode(video=0),strict=True)):
            if not 15<=k<210:continue
            t=Fraction(k-3,30);near=min(range(len(pts)),key=lambda i:(abs(pts[i]-t),-i))
            mask=np.ones((270,480),bool)
            if 30<=k<180:
                rgba=np.asarray(Image.open(io.BytesIO(painter.frame(k))).convert('RGBA'))
                mask=(rgba[20:290,80:560,3]==255)&(rgba[20:290,660:1140,3]==0)
            mask=mask[70:235:2,::2]
            for route,f in [('B',bf),('C',cf)]:
                imgs={'output':f.to_ndarray(format='rgb24')}
                if k in checked:imgs['player']=np.asarray(Image.open(f'cache/ui-{route}-{k}.png').convert('RGB'))
                for kind,img in imgs.items():
                    index,margin,n=match(img[88:358,1330:1810],refs,mask,near)
                    rows.append([route,kind,k,str(t),near,index,str(pts[index]),margin,n])
    with (E/'pip-source-ids.csv').open('w') as out:
        w=csv.writer(out);w.writerow(['route','surface','frame','target_sec','nearest_tie_later','matched_id','matched_pts','runner_up_mae_gap','moving_pixels']);w.writerows(rows)
if __name__=='__main__':main()

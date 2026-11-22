"""Relate the new AAC trace and spatial differences to the original A/B/C outputs."""
import json,sys,hashlib
from pathlib import Path
import av,numpy as np
from analyze import diff
def audio_hash(p):
    with av.open(str(p)) as c:
        h=hashlib.sha256()
        for packet in c.demux(c.streams.audio[0]):
            if packet.size:h.update(packet.size.to_bytes(4,'big'));h.update(bytes(packet))
        return h.hexdigest()
def main():
    base=Path(sys.argv[1]);E=Path('evidence')
    hashes={k:audio_hash(base/'results'/f'{k}-v3-r1.mp4') for k in 'AB'}
    hashes['new_B_adts']=audio_hash(E/'B-adts.mp4')
    # Disjoint old-scene zones: old title, inset, rest. Global contribution is area weighted.
    mask=np.zeros((1080,1920),np.uint8);mask[720:930,112:1012]=1;mask[88:358,1330:1810]=2
    errors=np.zeros(3);counts=np.zeros(3)
    with av.open(str(base/'final/B-v3-r1.mp4')) as b,av.open(str(base/'final/C-v3-r1.mp4')) as c:
        for i,(bf,cf) in enumerate(zip(b.decode(video=0),c.decode(video=0),strict=True)):
            delta=diff(bf.to_ndarray(format='rgb24'),cf.to_ndarray(format='rgb24')).sum(axis=2)
            active=mask.copy()
            if not 30<=i<180:active[active==1]=0
            if not 15<=i<210:active[active==2]=0
            errors+=np.bincount(active.ravel(),weights=delta.ravel(),minlength=3)
            counts+=3*np.bincount(active.ravel(),minlength=3)
    (E/'baseline-crosscheck.json').write_text(json.dumps(dict(raw_audio_packet_digest=hashes,frames=i+1,old_global_mae=errors.sum()/counts.sum(),old_regions={key:dict(mae=e/n,pixel_share=n/counts.sum(),fraction_of_total_absolute_error=e/errors.sum()) for key,e,n in zip(['outside_active_title_and_pip','active_title','active_pip'],errors,counts)}),indent=2)+'\n')
if __name__=='__main__':main()

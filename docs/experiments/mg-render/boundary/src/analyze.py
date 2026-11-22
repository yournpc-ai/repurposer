"""Measure independently decoded media, source IDs, alpha regions and AAC priming."""
import csv,hashlib,io,json,math,os,subprocess
from pathlib import Path
from fractions import Fraction
import av,numpy as np
from PIL import Image,ImageDraw
from c import data,command,Paint,sync_playwright
from audio_oracle import pcm

E=Path('evidence')
def save(name,d):(E/name).write_text(json.dumps(d,indent=2)+'\n')
def read_rgb(p):return np.asarray(Image.open(p).convert('RGB'))
def codes(a):return sum((int(a[32,2*(16+j*12),0])>127)<<j for j in range(10))
def decoded_audio(path):
    with av.open(str(path)) as container:
        r=av.AudioResampler(format='fltp',layout='stereo',rate=48000)
        return np.concatenate([b.to_ndarray().T for f in container.decode(audio=0) for b in r.resample(f)])
def lag(ref,y):
    n=1<<(len(ref)+len(y)-2).bit_length()
    scores=np.fft.irfft(np.conj(np.fft.rfft(ref,n))*np.fft.rfft(y,n),n)
    offsets=np.arange(-4800,4801);return int(offsets[np.argmax(scores[offsets])])
def audio():
    spec=data()['spec'];ref=pcm(spec)[:,0];rows={}
    for name in ['adts/merged.wav','m4a/merged.wav','adts/audio.aac','m4a/audio.aac','B-adts.mp4','B-m4a.mp4','C.mp4','../cache/segment.mp4']:
        p=E/name;y=decoded_audio(p)
        oracle=ref[54*1600:84*1600] if 'segment' in name else ref
        shift=lag(oracle,y[:,0]);lo=max(0,-shift);hi=min(len(oracle),len(y)-shift)
        with av.open(str(p)) as c:
            s=c.streams.audio[0]; packets=[pk for pk in c.demux(s) if pk.size];first=packets[0]
            h=hashlib.sha256()
            for packet in packets:
                raw=bytes(packet)
                if c.format.name=='aac':raw=raw[7 if raw[1]&1 else 9:]
                h.update(len(raw).to_bytes(4,'big'));h.update(raw)
            rows[name]=dict(container=c.format.name,stream_timebase=str(s.time_base),presentation_samples=round(s.duration*s.time_base*48000) if s.duration else None,first_packet_pts=first.pts,first_side_data=[dict(kind=x.data_type,first_ten_bytes=bytes(x)[:10].hex()) for x in first.iter_sidedata()],packet_count=len(packets),packet_payload_sha256=h.hexdigest(),decoded_samples=len(y),lag_samples=shift,correlation=float(np.corrcoef(oracle[lo:hi],y[lo+shift:hi+shift,0])[0,1]),sample_peak=float(np.max(np.abs(y))),clipped_samples=int((np.abs(y)>=1).sum()))
    save('audio-stages.json',rows)
def diff(a,b):return np.abs(a.astype(np.int16)-b)
def video():
    d=data();rows={};preview=[];controls=[];events=json.loads((E/'preview-events.json').read_text())
    sampled={e['frame'] for e in events if 'frame' in e}
    with sync_playwright() as pw, av.open(str(E/'B-m4a.mp4')) as bc,av.open(str(E/'C.mp4')) as cc,av.open('cache/segment.mp4') as clip,open(E/'frame-regions.csv','w') as file:
        painter=Paint(pw,d);segment=clip.decode(video=0);writer=csv.writer(file);keys=['main_outside','main_flat','main_detail','pip_hidden','pip_soft','pip_opaque','caption_ink','glyph_bright']
        writer.writerow(['frame','B_main_id','C_main_id','full_mae','mse',*keys]);squared=0;total=0;segment_errors=[]
        for k,(bf,cf) in enumerate(zip(bc.decode(video=0),cc.decode(video=0),strict=True)):
            assert bf.pts*bf.time_base==cf.pts*cf.time_base==Fraction(k,30)
            b=bf.to_ndarray(format='rgb24');c=cf.to_ndarray(format='rgb24');assert b.shape==c.shape==(1080,1920,3)
            delta=diff(b,c);mae=delta.mean();mse=np.mean(np.square(delta,dtype=np.float32));total+=mae;squared+=mse
            # Fixed left half never intersects the effect; classify by local B-image contrast.
            sample=b[::2,:960:2].astype(np.int16);left=delta[::2,:960:2]
            contrast=np.maximum(np.max(np.abs(np.diff(sample,axis=0,prepend=sample[:1])),axis=2),np.max(np.abs(np.diff(sample,axis=1,prepend=sample[:,:1])),axis=2))
            subsets={'main_outside':delta[:,:1200], 'main_flat':left[contrast<=2],'main_detail':left[contrast>=16]}
            if d['mg']['start']<=k<d['mg']['end']:
                mask=np.asarray(Image.open(io.BytesIO(painter.frame(k))).convert('RGBA'))
                coverage=mask[20:290,80:560,3];ink=mask[:,580:,:];plain=ink[20:290,80:560,3]==0;pix=delta[88:358,1330:1810]
                for zone,select in [('pip_hidden',coverage==0),('pip_soft',(coverage>0)&(coverage<255)),('pip_opaque',coverage==255)]:subsets[zone]=pix[plain&select]
                subsets['caption_ink']=delta[68:378,1250:1830][ink[:,:,3]>0]
                subsets['glyph_bright']=delta[68:378,1250:1830][(ink[:,:,3]>245)&(ink[:,:,:3].max(axis=2)>190)]
            values={}
            for zone,arr in subsets.items():
                if not arr.size:continue
                v=rows.setdefault(zone,[0,0]);v[0]+=int(arr.sum());v[1]+=arr.size;values[zone]=round(float(arr.mean()),5)
            writer.writerow([k,codes(b),codes(c),float(mae),float(mse),*[values.get(key,'') for key in keys]])
            if 54<=k<84:
                sf=next(segment);assert sf.pts*sf.time_base==Fraction(k-54,30)
                seg=sf.to_ndarray(format='rgb24');segment_errors.append([k,codes(seg),codes(c),float(diff(seg,c).mean())])
            if k in sampled:
                for route,ex in [('B',b),('C',c)]:
                    ui=read_rgb(f'cache/ui-{route}-{k}.png');still=read_rgb(f'cache/B-{k}.png' if route=='B' else f'cache/C-source-{k}.png')
                    preview.append(dict(route=route,frame=k,output_main_id=codes(ex),ui_main_id=codes(ui),offline_still_main_id=codes(still),ui_output_mae=float(diff(ui,ex).mean()),ui_offline_still_mae=float(diff(ui,still).mean()),still_output_mae=float(diff(still,ex).mean()),ui_output_effect_area_mae=float(diff(ui[68:378,1250:1830],ex[68:378,1250:1830]).mean())))
            if k in (45,72,156):
                rect=(slice(62,386),slice(1230,1850));panel=Image.new('RGB',(620*3,350));pen=ImageDraw.Draw(panel)
                for i,(name,pic) in enumerate([('B',b),('C',c),('abs(B-C) x8',np.clip(delta*8,0,255).astype('uint8'))]):
                    panel.paste(Image.fromarray(pic[rect]),(620*i,24));pen.text((620*i+10,5),f'{name} / frame {k}',fill='white')
                panel.save(E/f'comparison-{k:03}.png')
            if k==72:
                target=read_rgb('cache/B-72.png')
                for name,source_matrix,scale in [('baseline','bt601','bilinear'),('source709','bt709','bilinear'),('bicubic','bt601','bicubic')]:
                    path='cache/control-'+name+'.png';cmd=command(d,k,k+1,path);index=cmd.index('-filter_complex')+1
                    cmd[index]=cmd[index].replace('in_color_matrix=bt601','in_color_matrix='+source_matrix).replace('flags=bilinear','flags='+scale)
                    subprocess.run(cmd,input=painter.frame(k),check=True);test=read_rgb(path)
                    controls.append(dict(control=name,B_still_vs_C_png_main_MAE=float(diff(target[:,:1200],test[:,:1200]).mean()),B_still_vs_C_png_effect_MAE=float(diff(target[68:378,1250:1830],test[68:378,1250:1830]).mean())))
        assert k==239;assert next(segment,None) is None
        save('quality.json',dict(frames=k+1,duration_seconds=8,full_mae=float(total/240),psnr_db=10*math.log10(255**2/(squared/240)),region_mae={key:v[0]/v[1] for key,v in rows.items()},single_frame_controls=controls))
        save('preview-comparison.json',preview);save('playback-window.json',segment_errors)
if __name__=='__main__':audio();video()

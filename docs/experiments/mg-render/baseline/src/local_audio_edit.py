"""Measured alternative for V2→V3 after proving the visual subgraph is identical."""
import os,sys,time,wave,subprocess,json,hashlib
from pathlib import Path
import imageio_ffmpeg,av,numpy as np
from audio_oracle import pcm
def read(p):return json.loads(Path(p).read_text())
def visual(v):
    data=read(f'fixture/direct{v}.json');s=data['spec']
    return dict(mg=data['mg'],**{k:val for k,val in s.items() if k not in ('provenance','tracks')},tracks=[t for t in s['tracks'] if t['kind']=='visual'])
def encoded_video_digest(p):
    h=hashlib.sha256()
    with av.open(str(p)) as c:
        for pkt in c.demux(video=0):h.update(bytes(pkt))
    return h.hexdigest()
if __name__=='__main__':
    result={}
    for r in 'ABC':
        t=time.perf_counter();assert visual(2)==visual(3) and visual(1)!=visual(2)
        s=read('fixture/direct3.json')['spec'];x=pcm(s);assert abs(x).max()<1
        wav=Path('cache/local-audio.wav')
        with wave.open(str(wav),'wb') as f:
            f.setparams((2,2,48000,0,'NONE','not compressed'));f.writeframes(np.rint(x*32767).astype('<i2').tobytes())
        prev=Path('final')/(r+'-v2-r1.mp4');out=Path('analysis')/('incremental-'+r+'.mp4')
        cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(prev),'-i',str(wav),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)]
        subprocess.run(cmd,check=True)
        took=time.perf_counter()-t;h=encoded_video_digest(out);assert h==encoded_video_digest(prev)==encoded_video_digest(f'final/{r}-v3-r1.mp4')
        with av.open(str(out)) as c:
            assert c.duration==8000000
            samples=np.concatenate([f.to_ndarray()[0] for f in c.decode(audio=0)])[:384000]
        result[r]=dict(seconds=took,copied_video_sha256=h,pcm_correlation=float(np.corrcoef(samples,x[:,0])[0,1]),duration_s=8,video_renders=0,cmd=cmd)
    Path('analysis/local-audio-edit.json').write_text(json.dumps(result,indent=2))

"""Repair only the measured AAC preroll of this pinned Remotion build. Keep raw results."""
from pathlib import Path
import json,os,sys,time,subprocess,hashlib,av
def conform(src,dst):
    with av.open(str(src)) as f:
        a=f.streams.audio[0];video=f.streams.video[0]
        assert (video.frames,video.width,video.height)==(240,1920,1080)
        n=round(a.duration*a.time_base*48000)
    t=time.perf_counter();dst.parent.mkdir(exist_ok=True,parents=True)
    if n==386048:
        cmd=[os.environ['FFBIN']+'/ffmpeg','-loglevel','error','-y','-i',str(src),'-ss','0.042667','-i',str(src),'-map','0:v:0','-map','1:a:0','-c','copy','-t','8','-movflags','+faststart',str(dst)]
        subprocess.run(cmd,check=True)
    elif n==384000:
        cmd=['link',str(src),str(dst)]
        if not dst.exists():os.link(src,dst)
    else:raise ValueError(f'Uncharacterized audio presentation duration {n}')
    seconds=time.perf_counter()-t
    with av.open(str(dst)) as f:
        assert f.duration==8000000 and f.streams.audio[0].duration*f.streams.audio[0].time_base==8
    return dict(raw_audio_samples=n,corrected_s=seconds,command=cmd,sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
if __name__=='__main__':
    from glob import glob
    results={}
    for s in sorted(glob('results/*-r[123].mp4')):
        path=Path(s);results[path.stem]=conform(path,Path('final')/path.name)
    Path('logs/conform.json').write_text(json.dumps(results,indent=2))

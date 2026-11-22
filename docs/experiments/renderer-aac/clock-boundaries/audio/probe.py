"""Run from this directory with the locked compositor FFmpeg in FFMPEG."""
import json,os,subprocess
from pathlib import Path
ff=os.environ['FFMPEG'];env=dict(os.environ,DYLD_LIBRARY_PATH=str(Path(ff).parent))
filt=Path('filter.txt').read_text().strip()
def run(name,filters,rate,codec,mp4=False):
    dest=name+('.mp4' if mp4 else '.mov')
    args=[ff,'-debug_ts','-y','-hide_banner','-nostats','-i','baseline.mp4']
    args+=['-c:v','copy'] if mp4 else ['-vn']
    args+=['-af',filters,'-ar',str(rate),'-c:a',codec]
    if codec=='aac':args+=['-b:a','192k']
    args+=['-stats_enc_pre:a',name+'.samples','-stats_enc_pre_fmt:a','{n} {pts} {tb} {samp} {sn}',dest]
    with open(name+'.log','wb') as log:r=subprocess.run(args,env=env,stderr=log)
    with open('commands.jsonl','a') as out:print(json.dumps({'cmd':args,'exit':r.returncode}),file=out)
    if r.returncode:raise RuntimeError(Path(name+'.log').read_text()[-600:])
run('decoded','acopy',48000,'pcm_s16le')
run('upsampled','aresample=192000',192000,'pcm_s24le')
run('filtered',filt,192000,'pcm_s24le')
run('downsampled',filt,48000,'pcm_s24le')
run('failed',filt,48000,'aac',True)
run('trim-input','atrim=end_sample=382080,'+filt,48000,'aac',True)
# Bound real input and output by the verified MP4 presentation length.
# Padding lets the dynamic filter see zeros beyond the cut without flushing a short analysis block.
run('bounded','atrim=end_sample=382080,apad,'+filt+',aresample=48000,atrim=end_sample=382080',48000,'aac',True)

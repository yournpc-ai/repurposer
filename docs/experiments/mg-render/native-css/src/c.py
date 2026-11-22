"""Decode fixed source rasters, address by PTS, let Chromium paint the entire frame."""
import base64, bisect, hashlib, json, os, subprocess, sys
from fractions import Fraction
from pathlib import Path
import av, imageio_ffmpeg
from playwright.sync_api import sync_playwright

CHECK=[72,239,30,179,0,45,180,15,209]

def source_index(clips):
    indexes={}
    for clip in clips:
        name=clip['source']['url']
        directory=Path('cache/frames',name)
        manifest=directory/'pts.json'
        if not manifest.exists():
            directory.mkdir(parents=True,exist_ok=True)
            with av.open('assets/'+name) as source:
                pts=[]
                for i, frame in enumerate(source.decode(video=0)):
                    frame.to_image().save(directory/f'{i}.png',compress_level=1)
                    pts.append(str(frame.pts*frame.time_base))
            manifest.write_text(json.dumps(pts))
        indexes[name]=[Fraction(t) for t in json.loads(manifest.read_text())]
    return indexes

def frame_url(clip,k,fps,index):
    name=clip['source']['url']
    target=(k-clip['start_frame']+clip['source']['start_frame'])/fps
    times=index[name]
    right=min(bisect.bisect_left(times,target),len(times)-1)
    left=max(0,right-1)
    i=left if target-times[left]<times[right]-target else right
    return 'frames/'+name+'/'+str(i)+'.png'

def run(version,mode):
    data=json.loads(Path(f'cache/data{version}.json').read_text())
    fps=Fraction(data['fps']['num'],data['fps']['den'])
    clips=[c for t in data['tracks'] for c in t['clips'] if c['object']['kind']=='video']
    index=source_index(clips)
    js=Path('cache/page.js')
    if not js.exists():
        subprocess.run(['node_modules/.bin/esbuild','src/C.tsx','--bundle','--define:process.env.NODE_ENV="production"','--outfile='+str(js)],check=True)
    pagefile=Path('cache/page.html')
    pagefile.write_text('<body style="margin:0"><script src="page.js"></script></body>')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ['CHROME'],chromium_sandbox=True)
        page=browser.new_page(viewport=dict(width=data['width'],height=data['height']),device_scale_factor=1)
        page.goto(pagefile.resolve().as_uri())
        cdp=page.context.new_cdp_session(page)
        def paint(k):
            urls={c['object']['object_id']:frame_url(c,k,fps,index) for c in clips if c['start_frame']<=k<c['end_frame']}
            page.evaluate('p=>window.paint(p)',dict(k=k,data=data,urls=urls))
            return base64.b64decode(cdp.send('Page.captureScreenshot',dict(format='png',optimizeForSpeed=True))['data'])
        if mode=='still':
            for k in CHECK: Path(f'cache/C-{k}.png').write_bytes(paint(k))
            # Negative control: an ordinary autonomous CSS animation runs on wall time.
            observation=page.evaluate("""async () => {
              const node=document.querySelector('img');
              const a=node.animate([{opacity:1},{opacity:0}],{duration:5000});
              await a.ready;
              const first=getComputedStyle(node).opacity;
              await new Promise(resolve=>setTimeout(resolve,160));
              return [first,getComputedStyle(node).opacity,a.currentTime];
            }""")
            Path('evidence/wall-clock.json').write_text(json.dumps(observation))
        elif mode=='probe':
            for k in CHECK:
                Path(f'cache/v{version}-{k}.png').write_bytes(paint(k))
            paint(72)
            for name,rule in [('blend','[data-object="signal-sweep"] {mix-blend-mode:normal!important}'),
                              ('glass','[data-object="signal-title"] > div {backdrop-filter:none!important}')]:
                style=page.add_style_tag(content=rule)
                png=base64.b64decode(cdp.send('Page.captureScreenshot',dict(format='png',optimizeForSpeed=True))['data'])
                Path(f'cache/{name}-off-{version}.png').write_bytes(png)
                style.evaluate('el=>el.remove()')
        else:
            cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','image2pipe','-framerate',str(fps),'-i','-','-vf','scale=out_color_matrix=bt709','-c:v','libx264','-threads','2','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','cache/silent.mp4']
            hashes={}
            with subprocess.Popen(cmd,stdin=subprocess.PIPE) as encoder:
                try:
                    for k in range(data['duration_frames']):
                        png=paint(k)
                        encoder.stdin.write(png)
                        if k in CHECK: hashes[k]=hashlib.sha256(png).hexdigest()
                finally:
                    encoder.stdin.close()
                if encoder.wait(): raise RuntimeError('encoder failed')
            Path(f'cache/C{version}-raster.json').write_text(json.dumps(hashes))
        browser.close()

if __name__=='__main__': run(*sys.argv[1:])

"""Stream the local React surface to FFmpeg; keep both source videos compressed until their final pass."""
import sys,os,subprocess,json,base64,hashlib
from fractions import Fraction
from pathlib import Path
import av,imageio_ffmpeg
from playwright.sync_api import sync_playwright
def read(path):return json.loads(Path(path).read_text())
def graph(spec,mg,dest,preview):
    fps=spec['fps']['num'];rate=spec['sample_rate']
    tracks=sorted(spec['tracks'],key=lambda t:t['order'])
    clips=[c for t in tracks for c in t['clips']]
    args=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-filter_complex_threads','2']
    filters=[];audio=[];visual=None
    for i,c in enumerate(clips):
        source=c['source'];url='assets/'+source['url'];args+=['-threads','2','-i',url]
        start=c['start_frame'];end=c['end_frame'];a=source['start_frame'];b=source['end_frame']
        if c['object']['kind']=='video':
            layout=c['object']['layout'];x,y,w,h=[int(layout[k]) for k in ('x','y','width','height')]
            with av.open(url) as f:frequency=f.streams.video[0].average_rate
            # Convert each input PTS to its nearest-sample decision boundary before CFR selection.
            clock=720000; half=Fraction(clock,2)/frequency;assert half.denominator==1
            filters.append(f'[{i}:v]settb=1/{clock},setpts=PTS-STARTPTS-{int(half)},fps={fps}:start_time=0:round=up,trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS+{start},scale={w}:{h}:flags=bilinear:in_color_matrix=bt601:out_color_matrix=bt709,setsar=1[v{i}]')
            if visual is None:visual=f'[v{i}]'
            else:
                filters.append(f'{visual}[v{i}]overlay={x}:{y}:eof_action=pass:repeatlast=0[vv{i}]');visual=f'[vv{i}]'
        elif not preview:
            gain=c['object']['gain_db'];begin=a*rate//fps;finish=b*rate//fps;delay=start*rate//fps
            filters.append(f'[{i}:a]atrim=start_sample={begin}:end_sample={finish},asetpts=PTS-STARTPTS,volume={gain}dB,aformat=sample_rates={rate}:channel_layouts=stereo,adelay={delay}S:all=1[a{i}]')
            audio.append(f'[a{i}]')
    args+=['-f','image2pipe','-framerate',str(fps),'-vcodec','png','-i','pipe:0']
    layout=mg['layout'];i=len(clips)
    filters+=[f"[{i}:v]scale=out_color_matrix=bt709,format=yuv420p,setpts=PTS-STARTPTS+{mg['start']}[ink]",f"{visual}[ink]overlay={int(layout['x'])}:{int(layout['y'])}:eof_action=pass:repeatlast=0[scene]"]
    if preview:filters.append("[scene]select=eq(n\\,60)[preview]")
    else:
        samples=spec['duration_frames']*rate//fps
        filters.append(''.join(audio)+f'amix=inputs={len(audio)}:normalize=0,apad,atrim=end_sample={samples}[audio]')
    args+=['-filter_complex',';'.join(filters)]
    if preview:args+=['-map','[preview]','-frames:v','1','-threads','1',dest]
    else:args+=['-map','[scene]','-map','[audio]','-c:v','libx264','-crf','18','-preset','veryfast','-threads','2','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-c:a','aac','-b:a','192k','-ar',str(rate),'-movflags','+faststart',dest]
    return args
def main():
    v,dest=sys.argv[1:3];preview=len(sys.argv)>3
    data=read('fixture/direct'+v+'.json');s,mg=data['spec'],data['mg']
    h=hashlib.sha256((mg['file_digest']+Path('src/Direct.tsx').read_text()+Path('src/build.cjs').read_text()).encode()).hexdigest()
    build=Path('cache')/('C'+h[:16]);js=build/'app.js'
    if not js.exists():subprocess.run(['node','src/build.cjs',str(build),v],check=True)
    cmd=graph(s,mg,dest,preview);print('FFMPEG',json.dumps(cmd),flush=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ['CHROME'],chromium_sandbox=True)
        page=browser.new_page(viewport={k:int(mg['layout'][k]) for k in ['width','height']},device_scale_factor=1)
        page.set_content('<body style="margin:0"><div id="root"></div></body>');page.add_script_tag(path=str(js))
        session=page.context.new_cdp_session(page);session.send('DOM.enable');session.send('CSS.enable')
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            for k in range(mg['end']-mg['start']):
                page.evaluate('args=>window.draw(args)',dict(frame=k,**mg['props']))
                if k==0:
                    node=session.send('DOM.getDocument')['root']['nodeId']
                    nid=session.send('DOM.querySelector',{'nodeId':node,'selector':'div[style*="font-size: 76px"]'})['nodeId']
                    fonts=session.send('CSS.getPlatformFontsForNode',{'nodeId':nid})
                    assert any(f['familyName']=='Arial' and f['glyphCount'] for f in fonts['fonts']),fonts
                    Path('logs/font-C-v'+v+'.json').write_text(json.dumps(fonts,indent=2))
                png=base64.b64decode(session.send('Page.captureScreenshot',{'format':'png','optimizeForSpeed':True})['data'])
                proc.stdin.write(png)
        except BrokenPipeError:
            if not preview:raise
        finally:
            try:proc.stdin.close()
            except BrokenPipeError:pass
            status=proc.wait();browser.close()
        if status:raise RuntimeError('FFmpeg exited '+str(status))
if __name__=='__main__':main()

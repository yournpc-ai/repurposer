"""A two-plane Chromium surface: coverage of the PiP, plus painted caption."""
import json,sys,os,subprocess,base64
from pathlib import Path
from fractions import Fraction
import av,imageio_ffmpeg
from playwright.sync_api import sync_playwright
def data():return json.loads(Path('evidence/data.json').read_text())
def command(d,start,end,out,matrix='bt709'):
    preview=end==start+1
    spec=d['spec'];mg=d['mg'];pip=d['pip'];main=spec['tracks'][0]['clips'][0]
    fps=spec['fps']['num'];rate=spec['sample_rate'];active=(max(start,mg['start']),min(end,mg['end']))
    args=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-filter_complex_threads','2'];filters=[]
    clips=[main,pip]+[c for t in spec['tracks'] if t['kind']=='audio' for c in t['clips']]
    for c in clips:args+=['-threads','2','-i','assets/'+c['source']['url']]
    def video(index,c,a,b,name):
        src=c['source'];layout=c['object']['layout'];w,h=[int(layout[k]) for k in ('width','height')]
        with av.open('assets/'+src['url']) as f:hz=f.streams.video[0].average_rate
        half=Fraction(720000,2)/hz;assert half.denominator==1
        trim=a-c['start_frame']+src['start_frame']
        filters.append(f'[{index}:v]settb=1/720000,setpts=PTS-STARTPTS-{int(half)},fps={fps}:start_time=0:round=up,trim=start_frame={trim}:end_frame={trim+b-a},setpts=PTS-STARTPTS,scale={w}:{h}:flags=bilinear:in_color_matrix=bt601:out_color_matrix={matrix},setsar=1[{name}]')
    video(0,main,start,end,'bg');base='bg'
    def overlay(layer,a,label,x,y):
        nonlocal base
        filters.append(f'[{layer}]settb=1/{fps},setpts=PTS-STARTPTS+{a-start}[{label}time]')
        filters.append(f'[{base}][{label}time]overlay={x}:{y}:repeatlast=0:eof_action=pass[{label}]');base=label
    px,py=[int(pip['object']['layout'][k]) for k in ('x','y')]
    mx,my,w,h=[int(mg['layout'][k]) for k in ('x','y','width','height')]
    for left,right,label in [(pip['start_frame'],mg['start'],'intro'),(mg['end'],pip['end_frame'],'outro')]:
        a,b=max(left,start),min(right,end)
        if a<b:video(1,pip,a,b,label+'src');overlay(label+'src',a,label,px,py)
    a,b=active
    if a<b:
        video(1,pip,a,b,'picture')
        args+=['-f','image2pipe','-framerate',str(fps),'-vcodec','png','-i','pipe:0']
        filters += [f'[{len(clips)}:v]format=rgba,split[mask][caption]',
                    f'[mask]crop=480:270:{px-mx}:{py-my},alphaextract[coverage]',
                    '[picture][coverage]alphamerge[cut]',
                    f'[caption]crop={w}:{h}:{w}:0,scale=out_color_matrix=bt709,format=yuva420p[paint]']
        overlay('cut',a,'masked',px,py);overlay('paint',a,'finish',mx,my)
    if not preview:
        for i,c in enumerate(clips[2:],2):
            a=c['source']['start_frame']*rate//fps;n=(c['end_frame']-c['start_frame'])*rate//fps
            filters.append(f"[{i}:a]atrim=start_sample={a}:end_sample={a+n},asetpts=PTS-STARTPTS,volume={c['object']['gain_db']}dB,aformat=sample_rates={rate}:channel_layouts=stereo,adelay={c['start_frame']*rate//fps}S:all=1[a{i}]")
        filters.append(''.join(f'[a{i}]' for i in range(2,len(clips)))+f'amix=inputs={len(clips)-2}:normalize=0,apad,atrim=start_sample={start*rate//fps}:end_sample={end*rate//fps},asetpts=PTS-STARTPTS[audio]')
    args+=['-filter_complex',';'.join(filters),'-map',f'[{base}]']
    return args+(['-frames:v','1','-threads','1',str(out)] if preview else ['-map','[audio]','-c:v','libx264','-threads','2','-crf','18','-preset','veryfast','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)])
class Paint:
    def __init__(self,pw,d):
        js=Path('cache/planes.js')
        if not js.exists():subprocess.run(['node_modules/.bin/esbuild','src/planes.tsx','--bundle','--define:process.env.NODE_ENV="production"','--outfile='+str(js)],check=True)
        self.mg=d['mg'];layout=self.mg['layout']
        self.browser=pw.chromium.launch(executable_path=os.environ['CHROME'],chromium_sandbox=True)
        self.page=self.browser.new_page(viewport={'width':int(2*layout['width']),'height':int(layout['height'])},device_scale_factor=1)
        self.page.set_content('<body style="margin:0">');self.page.add_script_tag(path=str(js))
        self.cdp=self.page.context.new_cdp_session(self.page)
        self.cdp.send('Emulation.setDefaultBackgroundColorOverride',{'color':{'r':0,'g':0,'b':0,'a':0}})
    def frame(self,k):
        self.page.evaluate('p=>window.paint(p)',{**self.mg['props'],'frame':k-self.mg['start']})
        return base64.b64decode(self.cdp.send('Page.captureScreenshot',{'format':'png','optimizeForSpeed':True})['data'])
def render(painter,d,start,end,path,matrix='bt709'):
    cmd=command(d,start,end,path,matrix)
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for k in range(max(start,d['mg']['start']),min(end,d['mg']['end'])):
            img=painter.frame(k);proc.stdin.write(img)
            if k==72:Path('evidence/planes-072.png').write_bytes(img)
    finally:
        proc.stdin.close();status=proc.wait()
    if status:raise RuntimeError('FFmpeg failed: '+str(status))
if __name__=='__main__':
    d=data()
    with sync_playwright() as pw:
        p=Paint(pw,d);render(p,d,0,240,sys.argv[1] if len(sys.argv)>1 else 'evidence/C.mp4')

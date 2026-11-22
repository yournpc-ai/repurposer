import functools,http.server,json,os,re,subprocess,sys,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from seek_server import Seekable
from c import data,Paint,render
frames=[72,179,0,30,156,180,239,45,60]
header='<!doctype html><meta charset="utf-8"><body style="margin:0"><div id="view" style="width:1920px;height:1080px"></div><input id="scrub" type="range" min="0" max="239" value="0">'
b_html=header+'<script src="/cache/player.js"></script>'
c_html=header+'''<video controls src="/cache/segment.mp4"></video><script>
const img=document.createElement('img');view.appendChild(img);
const slider=document.querySelector('input');let generation=0;
slider.oninput=async()=>{const key=++generation,k=slider.value;
const blob=await (await fetch('/frame/'+k)).blob();const url=URL.createObjectURL(blob);
const decoded=new Image();decoded.src=url;await decoded.decode();
if(generation===key){const old=img.src;img.src=url;await img.decode();if(old)URL.revokeObjectURL(old);img.dataset.frame=k;}
};</script>'''
class Handler(Seekable):
    def do_GET(self):
        if self.path in ('/B','/C'):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write((b_html if self.path=='/B' else c_html).encode());return
        if re.fullmatch(r'/frame/\d{1,3}',self.path):
            with self.server.worker_lock:
                self.server.worker.stdin.write(self.path[7:]+'\n');self.server.worker.stdin.flush()
                name=json.loads(self.server.worker.stdout.readline())
            if not isinstance(name,str):return self.send_error(500)
            self.path='/'+name
        super().do_GET()
    def copyfile(self,*args):
        try:super().copyfile(*args)
        except (BrokenPipeError,ConnectionResetError):pass
def main():
    subprocess.run(['node_modules/.bin/esbuild','src/player.tsx','--bundle','--define:process.env.NODE_ENV="production"','--outfile=cache/player.js'],check=True)
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory='.'))
    worker=subprocess.Popen([sys.executable,'src/frame_worker.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    srv.worker=worker;srv.worker_lock=threading.Lock();threading.Thread(target=srv.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{srv.server_port}';os.environ['ASSET_URL']=url+'/assets'
    d=data()
    records=[]
    try:
        with sync_playwright() as pw:
            p=Paint(pw,d);render(p,d,54,84,'cache/segment.mp4');p.browser.close()
            for route in 'BC':
                browser=pw.chromium.launch(executable_path=os.environ['CHROME'],chromium_sandbox=True)
                page=browser.new_page(viewport={'width':1920,'height':1160},device_scale_factor=1)
                page.goto(url+'/'+route)
                if route=='B':
                    for clip in [d['pip']]+[c for t in d['spec']['tracks'] for c in t['clips']]:clip['source']['url']=url+'/assets/'+clip['source']['url']
                    page.evaluate('(d)=>window.mount(d)',d);page.wait_for_function('window.current()!==undefined')
                else:
                    play=page.evaluate('async()=>{const v=document.querySelector("video");v.muted=true;await v.play();await new Promise(r=>setTimeout(r,460));v.pause();return {time:v.currentTime,duration:v.duration,frames:v.getVideoPlaybackQuality().totalVideoFrames}}')
                    records.append(dict(route='C',segment=[54,84],native_play=play))
                for k in frames:
                    t=time.monotonic()
                    page.evaluate('k=>{const r=document.querySelector("input");r.value=k;r.dispatchEvent(new Event("input"));}',k)
                    if route=='B':
                        page.wait_for_function('k=>window.current()===k',arg=k)
                        page.wait_for_function('k=>{const v=[...document.querySelectorAll("video")];return v.length===(k>=15&&k<210?2:1)&&v.every(x=>x.readyState>=2&&!x.seeking&&Math.abs(x.currentTime-(k+(x.currentSrc.includes("main")?15:-3))/30)<0.075)}',arg=k,timeout=12000)
                        page.evaluate('()=>document.fonts.ready');page.wait_for_timeout(200)
                    else:page.wait_for_function('k=>Number(document.querySelector("img").dataset.frame)===k',arg=k)
                    media=page.evaluate('()=>[...document.querySelectorAll("video")].map(v=>({name:v.currentSrc.split("/").pop(),time:v.currentTime}))')
                    record=dict(route=route,frame=k,source_media=media,settle_seconds=time.monotonic()-t)
                    records.append(record);page.screenshot(clip={'x':0,'y':0,'width':1920,'height':1080},path=f'cache/ui-{route}-{k}.png')
                browser.close()
        subprocess.run(['node','src/b.cjs','still',*map(str,frames)],check=True)
    finally:
        Path('evidence/preview-events.json').write_text(json.dumps(records,indent=2))
        worker.stdin.close();worker.wait();srv.shutdown()
if __name__=='__main__':main()

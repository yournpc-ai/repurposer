import os,subprocess,sys,threading,http.server,functools,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from seek_server import Seekable
def player(url,r):
    data=json.loads(Path(f'fixture/{"baked" if r=="A" else "direct"}3.json').read_text())
    for tr in data['spec']['tracks']:
        for c in tr['clips']:
            if c['source']:c['source']['url']=url+'/assets/'+c['source']['url']
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ['CHROME'],chromium_sandbox=True)
        page=browser.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url+'/commands/player.html');page.evaluate('(p)=>window.mount(p)',data)
        for k in (45,60,100):
            page.wait_for_function('window.current()!==undefined')
            page.evaluate('n=>window.move(n)',k);page.wait_for_function(f'window.current()==={k}')
            page.wait_for_function("document.querySelectorAll('video').length>=2 && [...document.querySelectorAll('video')].every(v=>v.readyState>=2&&!v.seeking)",timeout=15000)
            page.wait_for_function("target=>Math.abs(document.querySelector('video').currentTime-target)<0.075",arg=(k+15)/30,timeout=5000)
            page.evaluate('()=>document.fonts.ready');page.wait_for_timeout(250)
            media=page.evaluate("()=>[...document.querySelectorAll('video')].map(v=>({src:v.currentSrc.split('/').pop(),at:v.currentTime,ready:v.readyState}))")
            if r=='B':
                session=page.context.new_cdp_session(page);session.send('DOM.enable');session.send('CSS.enable');root=session.send('DOM.getDocument')['root']['nodeId']
                nid=session.send('DOM.querySelector',{'nodeId':root,'selector':'div[style*="font-size: 76px"]'})['nodeId']
                fonts=session.send('CSS.getPlatformFontsForNode',{'nodeId':nid});session.detach()
            else:fonts='pixels in pinned Generator media'
            page.screenshot(path=f'analysis/player-{r}-{k}.png')
            with open('logs/player.jsonl','a') as f:f.write(json.dumps(dict(route=r,frame=k,media=media,fonts=fonts,errors=errors))+'\n')
        browser.close()
if __name__=='__main__':
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Seekable,directory='.'));threading.Thread(target=srv.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{srv.server_port}';os.environ['ASSET_URL']=url+'/assets'
    subprocess.run(['node','src/player.cjs'],check=True)
    status={}
    for r in 'ABC':
        cmd=(['node','src/remotion.cjs',r,'3',f'analysis/still-{r}.png','preview'] if r!='C' else [sys.executable,'src/chromium.py','3','analysis/still-C.png','preview'])
        subprocess.run(cmd,check=True)
        if r!='C':
            try:player(url,r);status[r]='seeked'
            except Exception as e:status[r]=str(e)
        Path('analysis/preview-status.json').write_text(json.dumps(status,indent=2))

"""Record actual compositor binaries, version pins, input/implementation hashes and font use."""
from pathlib import Path
import hashlib,importlib.metadata as md,json,os,platform,subprocess,sys,threading,functools,http.server
import av,imageio_ffmpeg
from playwright.sync_api import sync_playwright
from c import Paint,data
from serve import Live
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fonts(page):
    page.evaluate('()=>document.fonts.ready')
    s=page.context.new_cdp_session(page);s.send('DOM.enable');s.send('CSS.enable')
    node=s.send('DOM.getDocument')['root']['nodeId']
    text=s.send('DOM.querySelector',{'nodeId':node,'selector':'svg text'})['nodeId']
    found=s.send('CSS.getPlatformFontsForNode',{'nodeId':text})['fonts'];s.detach()
    assert any(f['postScriptName']=='Arial-BoldMT' and f['glyphCount']>0 for f in found),found
    return found
def media(path):
    with av.open(str(path)) as c:
        s=c.streams.video[0];stream=c.streams.audio[0]
        payload=hashlib.sha256()
        for p in c.demux(s):
            if p.size:payload.update(bytes(p))
        return dict(bytes=path.stat().st_size,sha256=sha(path),frames=s.frames,rate=str(s.average_rate),size=[s.width,s.height],duration_microseconds=c.duration,video_payload_sha256=payload.hexdigest(),audio_presented_samples=int(stream.duration*stream.time_base*stream.rate))
def main():
    E=Path('evidence');d=data()
    font=Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    assert sha(font)==Path('fixture/font.sha256').read_text().split()[0]
    fs={}
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Live,directory='.')) as srv,sync_playwright() as pw:
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        painter=Paint(pw,d);painter.frame(72);fs['C']=fonts(painter.page)
        p=painter.browser.new_page();p.goto(f'http://127.0.0.1:{srv.server_port}/B')
        p.wait_for_function('window.current()!==undefined')
        p.evaluate('()=>{const s=document.querySelector("input");s.value=72;s.dispatchEvent(new Event("input"));}')
        p.wait_for_selector('svg text');fs['B']=fonts(p);painter.browser.close();srv.shutdown()
    media_info={p.name:media(p) for p in sorted(E.glob('*.mp4'))}
    versions=json.loads((E/'version.json').read_text())
    pins={'chromium':os.environ['CHROME'],'remotion_ffmpeg':Path(os.environ['FFBIN'])/'ffmpeg','ffmpeg9':imageio_ffmpeg.get_ffmpeg_exe(),'font':font}
    record=dict(commit=subprocess.check_output(['git','-C',os.environ['REP'],'rev-parse','HEAD'],text=True).strip(),composition_id=versions['composition_id'],version_id=versions['id'],parent_id=versions['base_version_id'],content_digest=versions['content_digest'],system=platform.platform(),python=sys.version,node=subprocess.check_output(['node','--version'],text=True).strip(),python_packages={p:md.version(p) for p in ('av','numpy','pillow','playwright','imageio-ffmpeg')},binary_sha256={k:sha(p) for k,p in pins.items()},font_use=fs,assets={p.name:sha(p) for p in sorted(Path('assets').glob('*')) if p.name in ('main.mp4','pip.mp4','whoosh.wav','impact2.wav','voice.wav')},source_and_inputs={str(p):sha(p) for p in [*sorted(Path('src').glob('*.*')),Path('package-lock.json'),E/'version.json',E/'data.json']},outputs=media_info)
    (E/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()

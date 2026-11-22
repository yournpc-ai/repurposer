"""Local crash tests only. No product job or billing calls."""
import hashlib,json,os,signal,subprocess,sys,time,fcntl
from pathlib import Path
from bench import server
from conform import conform
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(r):
    files=['fixture/v3.json','fixture/request3.json','fixture/recipes.json','fixture/font.sha256','src/job.py','src/conform.py',os.environ['CHROME'],os.environ['FONT']]
    if r=='C':
        import imageio_ffmpeg
        files+=['src/Direct.tsx','src/chromium.py','src/build.cjs',imageio_ffmpeg.get_ffmpeg_exe()]
    else:files+=['src/remotion.cjs','src/RemotionRoot.tsx','src/Video.tsx','package-lock.json',os.environ['FFBIN']+'/ffmpeg']
    for snap in json.loads(Path('fixture/sources3.json').read_text()).values():
        assert sha('assets/'+snap['storage_key'])==snap['digest']
    files+=['src/bake.ts','src/recovery.py']
    row=dict(route=r,version=json.loads(Path('fixture/v3.json').read_text())['content_digest'],dependencies={p:sha(p) for p in files})
    if r=='A':
        key=json.loads(Path('fixture/request3.json').read_text())['program_digest']
        row['fixed_mg']=sha('assets/'+key+'.mp4')
    return hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
def kill_tree(pid):
    rows=[list(map(int,line.split())) for line in subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()]
    owned={pid}
    while True:
        child={p for p,pp in rows if pp in owned}-owned
        if not child:break
        owned.update(child)
    for p in owned:
        try:os.kill(p,signal.SIGKILL)
        except ProcessLookupError:pass
def trial(r):
    key=identity(r);home=Path('recovery')/'two-boundaries'/r;home.mkdir(exist_ok=True,parents=True)
    staged=home/'incomplete.mp4';done=home/'ready.json';out=home/'restored.mp4'
    cmd=([sys.executable,'src/chromium.py','3',str(staged)] if r=='C' else ['node','src/remotion.cjs',r,'3',str(staged)])
    with (home/'run.log').open('w') as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
        wait=time.monotonic()+2.8
        while time.monotonic()<wait and proc.poll() is None:time.sleep(.1)
        assert proc.poll() is None
        kill_tree(proc.pid);code=proc.wait();assert code!=0 and not done.exists()
        partial_bytes=staged.stat().st_size if staged.exists() else 0
        if staged.exists():staged.replace(home/'interrupted.partial')
        assert key==identity(r)
        subprocess.run(cmd,stdout=log,stderr=log,check=True);conform(staged,out)
        # Crash after atomic artifact, before publish. Durable readiness includes its actual byte hash.
        expected=sha('final/'+r+'-v3-r1.mp4');assert sha(out)==expected
        code2=subprocess.run([sys.executable,__file__,'seal-and-stop',str(home),r]).returncode
        old=json.loads((home/'sealed.json').read_text());assert code2==73 and old['key']==identity(r) and sha(out)==old['digest']
        published=home/'ready.tmp';published.write_text(json.dumps(old));published.replace(done)
        assert json.loads(done.read_text())==old
    return dict(identity=key,interrupted_exit=code,unpublished_partial_bytes=partial_bytes,resumed_render_count=1,after_seal_exit=code2,second_resume_render_count=0,artifact_sha256=old['digest'],matches_uninterrupted=True)
if __name__=='__main__':
    if len(sys.argv)>1:
        assert sys.argv[1]=='seal-and-stop'
        home=Path(sys.argv[2]);route=sys.argv[3];out=home/'restored.mp4'
        sealed=dict(key=identity(route),artifact=out.name,digest=sha(out))
        tmp=home/'sealed.tmp';tmp.write_text(json.dumps(sealed));tmp.replace(home/'sealed.json')
        os._exit(73)
    server();result={}
    for r in 'ABC':
        result[r]=trial(r);Path('analysis/recovery.json').write_text(json.dumps(result,indent=2))

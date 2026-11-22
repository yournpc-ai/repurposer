import os,signal,sys,time,json,subprocess,threading,http.server,functools
from pathlib import Path
class Quiet(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):self.send_header('Access-Control-Allow-Origin','*');super().end_headers()
    def log_message(self,*args):pass
def server():
    srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory='assets'))
    threading.Thread(target=srv.serve_forever,daemon=True).start();os.environ['ASSET_URL']=f'http://127.0.0.1:{srv.server_port}';return srv
def measure(cmd,tag):
    t=time.perf_counter();peak=0;samples=0
    with open('logs/'+tag+'.log','w') as log:
        p=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
        while p.poll() is None:
            lines=subprocess.check_output(['/bin/ps','-axo','pid=,ppid=,rss='],text=True)
            rows=[list(map(int,x.split())) for x in lines.splitlines() if len(x.split())==3]
            ids={p.pid}
            while True:
                more={pid for pid,pp,_ in rows if pp in ids}-ids
                if not more:break
                ids.update(more)
            peak=max(peak,sum(mem for pid,pp,mem in rows if pid in ids));samples+=1;time.sleep(.20)
    result=dict(tag=tag,wall_s=time.perf_counter()-t,peak_tree_rss_mib=peak/1024,rss_samples=samples,exit=p.returncode)
    with open('logs/bench.jsonl','a') as f:f.write(json.dumps(result)+'\n')
    print(result,flush=True);return p.returncode
if __name__=='__main__':
    server()
    for r in sys.argv[1]:
        for v in (1,2,3):
            for n in (1,2,3):
                tag=f'{r}-v{v}-r{n}'
                if Path('results/'+tag+'.json').exists():continue
                if measure([sys.executable,'src/job.py',r,str(v),str(n)],tag):sys.exit(1)

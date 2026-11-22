"""Manual review in a local browser after preview.py has produced the one-second segment."""
from preview import Handler,b_html,c_html,data
import functools,http.server,json,subprocess,sys,threading,webbrowser
class Live(Handler):
    def do_GET(self):
        if self.path not in ('/','/B','/C'):return super().do_GET()
        if self.path=='/':
            page='<meta charset="utf-8"><a href="/B">B · Remotion Player</a> | <a href="/C">C · frame / segment</a>'
        elif self.path=='/B':
            d=data()
            for clip in [d['pip']]+[c for tr in d['spec']['tracks'] for c in tr['clips']]:clip['source']['url']='/assets/'+clip['source']['url']
            page=b_html+'<script>window.mount('+json.dumps(d)+')</script>'
        else:page=c_html+'<script>slider.dispatchEvent(new Event("input"));</script>'
        self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.end_headers();self.wfile.write(page.encode())
if __name__=='__main__':
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Live,directory='.')) as srv:
        worker=subprocess.Popen([sys.executable,'src/frame_worker.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        srv.worker=worker;srv.worker_lock=threading.Lock()
        try:print(f'http://127.0.0.1:{srv.server_port}',flush=True);srv.serve_forever()
        except KeyboardInterrupt:pass
        finally:worker.stdin.close();worker.wait()

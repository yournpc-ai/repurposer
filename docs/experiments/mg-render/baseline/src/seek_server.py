from pathlib import Path
import re
from bench import Quiet
class Seekable(Quiet):
    def do_GET(self):
        path=Path(self.translate_path(self.path))
        if not path.is_file() or path.suffix not in {'.mp4','.wav'}:return super().do_GET()
        size=path.stat().st_size;requested=self.headers.get('Range');lo=0;hi=size-1
        if requested:
            m=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
            if not m:return self.send_error(416)
            lo=int(m[1]);hi=min(int(m[2]) if m[2] else hi,hi)
            if lo>hi:return self.send_error(416)
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Accept-Ranges','bytes')
        if requested:self.send_header('Content-Range',f'bytes {lo}-{hi}/{size}')
        self.send_header('Content-Length',str(hi-lo+1));self.end_headers()
        with path.open('rb') as f:
            f.seek(lo);remaining=hi-lo+1
            while remaining:
                chunk=f.read(min(remaining,65536));self.wfile.write(chunk);remaining-=len(chunk)

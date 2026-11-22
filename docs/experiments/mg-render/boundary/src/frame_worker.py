import sys,json
from pathlib import Path
from c import Paint,render,data,sync_playwright
with sync_playwright() as pw:
    d=data()
    painter=Paint(pw,d)
    for line in sys.stdin:
        try:
            k=int(line);assert 0<=k<240
            path=Path(f'cache/C-source-{k}.png')
            render(painter,d,k,k+1,path)
            print(json.dumps(str(path)),flush=True)
        except Exception as err:print(json.dumps({'error':str(err)}),flush=True)

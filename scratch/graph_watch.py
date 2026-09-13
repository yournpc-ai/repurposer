"""High-frequency /graph poller: catch anomalous (empty/partial/error) frames
during a live run. Read-only — never mutates."""
import json
import time
import urllib.request
import urllib.error
import sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1MjAzNzYwNC05MzIxLTRiNzAtOTIxMi00NDVjY2Y1YWRlNjAiLCJleHAiOjE3ODkzMzAyNjQsImlhdCI6MTc4OTI0Mzg2NH0.-W3iyDaCtn0zpBhTjSwbLOzrbLiO8to1OGZvHG3W9CQ"
BASE = "http://localhost:8000/api/v1"
PID = sys.argv[1]
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 120

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, str(e).encode()

start = time.time()
last_sig = None
i = 0
while time.time() - start < DURATION:
    i += 1
    t = time.time() - start
    st, body = get(f"/projects/{PID}/graph")
    if st != 200:
        sig = f"HTTP {st}"
        detail = body[:200].decode(errors="replace")
    else:
        try:
            d = json.loads(body)
            nodes = d.get("nodes", [])
            edges = d.get("edges", [])
            kinds = ",".join(f"{n['kind']}:{n['state']}" for n in nodes)
            sig = f"nodes={len(nodes)} edges={len(edges)} [{kinds}]"
            detail = ""
        except Exception as e:
            sig = f"PARSE-ERROR {e}"
            detail = body[:200].decode(errors="replace")
    if sig != last_sig:
        print(f"[{t:7.2f}s] {sig} {detail}", flush=True)
        last_sig = sig
    # also sample /results run status every ~2s
    if i % 10 == 0:
        st2, body2 = get(f"/projects/{PID}/results")
        if st2 == 200:
            try:
                r = json.loads(body2)
                run = r.get("latest_run")
                if run:
                    steps = ",".join(f"{s['kind']}={s['status']}" for s in run.get("steps", []))
                    print(f"[{t:7.2f}s]   run {run['status']} p={run['progress']} steps: {steps}", flush=True)
            except Exception:
                pass
    time.sleep(0.2)
print("done")

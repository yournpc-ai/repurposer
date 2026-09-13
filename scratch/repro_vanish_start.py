"""Fire the Start answer on the scratch project's docked task_book question
(the run begins; the resident worker picks it up)."""
import json
import sys
import urllib.request

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1MjAzNzYwNC05MzIxLTRiNzAtOTIxMi00NDVjY2Y1YWRlNjAiLCJleHAiOjE3ODkzMzAyNjQsImlhdCI6MTc4OTI0Mzg2NH0.-W3iyDaCtn0zpBhTjSwbLOzrbLiO8to1OGZvHG3W9CQ"
BASE = "http://localhost:8000/api/v1"

qid = sys.argv[1]
r = urllib.request.Request(
    f"{BASE}/chat/messages/{qid}/answer",
    method="POST",
    data=json.dumps({"kind": "start"}).encode(),
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(r, timeout=120) as resp:
    body = json.loads(resp.read())
    print("answer status:", resp.status, "| keys:", sorted(body.keys()))
    run = body.get("run") or {}
    print("run:", run.get("id"), run.get("status"))

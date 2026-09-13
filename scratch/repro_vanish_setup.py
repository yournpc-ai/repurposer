"""Vanish-bug repro setup (read-then-mutate scratch driver):
creates a scratch project for dev@local, uploads /tmp/xy_2_15s.mp4 through
the real composer path (presigned PUT + create-with-dims), sends the
multilingual-subs prompt through one-shot /chat (book docks, draft graph
stamps), and prints the project id + the task_book question message id.

DOES NOT start the run — the Start answer fires separately
(repro_vanish_start.py) while the CDP watcher is already on the page.
"""
import json
import sys
import urllib.request

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1MjAzNzYwNC05MzIxLTRiNzAtOTIxMi00NDVjY2Y1YWRlNjAiLCJleHAiOjE3ODkzMzAyNjQsImlhdCI6MTc4OTI0Mzg2NH0.-W3iyDaCtn0zpBhTjSwbLOzrbLiO8to1OGZvHG3W9CQ"
BASE = "http://localhost:8000/api/v1"
VIDEO = "/tmp/xy_2_15s.mp4"
PROMPT = "Caption my video in Chinese and French — Chinese as bilingual subtitles."


def req(method, path, body=None, raw=None, headers=None, timeout=180):
    h = {"Authorization": f"Bearer {TOKEN}"}
    if body is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    r = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else raw,
        headers=h,
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def main():
    # 1. scratch project
    st, b = req("POST", "/projects", {"title": "scratch: vanish repro"})
    pid = json.loads(b)["id"]
    print("project:", pid)

    # 2. upload via the composer path (presign → PUT → create with dims)
    st, b = req(
        "POST",
        f"/projects/{pid}/assets/upload-url",
        {"filename": "xy_2_15s.mp4", "content_type": "video/mp4"},
    )
    up = json.loads(b)
    with open(VIDEO, "rb") as f:
        data = f.read()
    put = urllib.request.Request(
        up["upload_url"],
        method="PUT",
        data=data,
        headers={"Content-Type": "video/mp4"},
    )
    with urllib.request.urlopen(put, timeout=300) as resp:
        print("PUT:", resp.status)
    st, b = req(
        "POST",
        f"/projects/{pid}/assets",
        {
            "type": "video",
            "key": up["key"],
            "title": "xy_2_15s.mp4",
            "width": 960,
            "height": 960,
        },
    )
    asset = json.loads(b)
    print("asset:", asset["id"], asset.get("status"))

    # 3. the recipe prompt (one-shot, no SSE) — book docks, draft graph stamps
    st, b = req(
        "POST",
        "/chat",
        {"project_id": pid, "message": PROMPT},
        timeout=300,
    )
    resp = json.loads(b)
    print("chat status:", st)
    msg = resp.get("assistant_message") or {}
    print("assistant message:", msg.get("id"), "| keys:", sorted(resp.keys()))

    # 4. find the docked task_book question message id (for the start answer)
    st, b = req("GET", f"/chat/conversation?project_id={pid}")
    conv = json.loads(b)
    conv_id = conv.get("id") or conv.get("conversation", {}).get("id")
    st, b = req("GET", f"/chat/conversations/{conv_id}/messages")
    msgs = json.loads(b).get("messages", [])
    qid = None
    for m in msgs:
        q = m.get("question")
        if q and q.get("kind") == "task_book" and not m.get("answered_at"):
            qid = m.get("id")
    print("conversation:", conv_id, "| task_book question:", qid)
    print(json.dumps({"project_id": pid, "question_id": qid}))


if __name__ == "__main__":
    sys.exit(main())

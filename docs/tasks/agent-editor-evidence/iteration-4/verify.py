"""Check the captured Iteration 4 provider, database and browser receipts offline."""

import gzip
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent


def read(name):
    path = HERE / name
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        return json.load(source)


def check_home():
    for name, case in read("home.json").items():
        posts = case["posts"]
        assert sum(p["path"] == "projects" for p in posts) == 1, name
        chat, = [p["body"] for p in posts if p["path"] == "chat"]
        assert chat["first_message"] and bool(chat["attachments"]) == ("upload" in name)
        assert sum(event == "turn.started" for event, _ in case["events"]) == 1
    recovery = read("opening-recovery.json")
    assert recovery["race"]["replay"] == 409 and recovery["history"]["posts"] == 0
    opening = read("studio-browser.json")["structured_opening"]["request"]
    assert opening["mentions"] and opening["attachments"] and opening["skill"]["version"] == "1.0.0"


def check_groups():
    admission = read("batch-admission.json")
    decisions = read("batch-trace.json")["decisions"]
    assert len(decisions) == 13 and len(admission) == 28
    calls = [(d["response"], call["id"]) for d in decisions for call in d["native_calls"]]
    assert calls == [(a["group"], a["call"]) for a in admission]
    assert all(a["schema_valid"] for a in admission)
    assert sum(bool(a["started"]) for a in admission) == 23
    assert Counter(a["state"] for a in admission) == {
        "completed": 18, "failed": 3, "cancelled": 2, "not_executed": 3, "no_receipt": 2,
    }
    cases = read("batch-trace.json")["cases"]
    assert [row["index"] for row in cases["overlap"]] == [1, 0, 3, 2]
    recovery = read("batch-browser.json.gz")
    assert [row["state"] for row in recovery["group_stop"]["after"]] == ["cancelled", "not_executed"]
    for project in ("cas_reload", "proof_reload"):
        samples = recovery[project]
        first_ids = [row["id"] for row in samples[0]]
        assert len(samples) == 4 and all([row["id"] for row in s] == first_ids for s in samples)
    media_turn = next(d["opening"] for d in decisions if d["response"].startswith("e61dadfa"))
    media, = [d for d in read("batch-database.json.gz").values()
              if any(m["id"] == media_turn for m in d["messages"])]
    assert [(t["kind"], t["amount"]) for t in media["ledger"] if t["kind"] != "grant"] == [
        ("hold", -2), ("release", 2), ("capture", -2),
    ]


def check_versions():
    race = read("competition.json.gz")["competition-final"]
    versions = race["versions"]
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[2]["base"] == versions[1]["id"] and versions[2]["request"] == race["peer_write"]["request"]
    assert [f["call_state"] for f in race["states"]] == ["completed", "completed", "failed"]
    late = read("late-worker.json.gz")
    late_db = read("final-database.json.gz")[late["project"]]
    assert [t["amount"] for t in late_db["ledger"] if t["kind"] == "capture"] == [-2]
    assert len([m for m in late_db["messages"] if "media_result" in (m["intent"] or {})]) == 2
    assert all(rows == late["reloads"][0] for rows in late["reloads"])

    receipt = read("ack-recovery.json")
    boundary = receipt["before_sigkill"]
    assert boundary["pre_ack"]["call_state"] == "running"
    versions = read("final-database.json.gz")[boundary["project"]]["versions"]
    assert [v["number"] for v in versions] == [1, 2] and versions[1]["request"] == boundary["request"]
    for rows in receipt["reloads"]:
        group = [row["frame"] for row in rows if (row["frame"] or {}).get("group_id")]
        assert [f["call_state"] for f in group] == ["completed", "not_executed"]
        assert group[0]["call_id"] == boundary["native"]


def check_studio():
    studio = read("studio-browser.json")
    for width, viewport in studio["viewports"].items():
        assert int(width) == viewport["width"] and not viewport["errors"]
        assert viewport["headers"] == 1
    touch = studio["touch"]
    messages = [post["body"] for post in touch["posts"] if post["path"] == "chat"]
    assert len(messages) == 2 and messages[0]["attachments"] and messages[0]["message"] != messages[1]["message"]
    assert not touch["errors"] and touch["touch_target"]["width"] > 0
    live = studio["live"]
    assert live["live"] == live["restored"] and live["wallet_reads_after_turn"] == [200]
    assert [row["state"] for row in live["live"]] == ["completed", "completed", "failed", "completed"]
    wire = read("studio-wire.json.gz")
    response, = [r["response"] for r in wire if r["model_call_id"] == live["group"] and r["phase"] == "response"]
    calls = response.get("tool_calls") or response["choices"][0]["message"]["tool_calls"]
    assert [c["id"] for c in calls] == [row["id"] for row in live["live"]]
    assert studio["image"]["views"][0] == studio["image"]["views"][1]
    assert studio["image"]["views"][0]["w"] == 1920
    archive = studio["archive"]["video"]
    assert archive["ready"] == 4 and not archive["paused"] and archive["time"] > 0
    thread = read("thread-browser.json")
    for video in [thread["video"]["live"], thread["video"]["refresh"]]:
        assert video["ready"] == 4 and not video["paused"] and video["time"] > 0
    assert thread["audioAndStop"]["audio"]["t"] > 0 and thread["audioAndStop"]["http"] == 200


if __name__ == "__main__":
    for check in [check_home, check_groups, check_versions, check_studio]:
        check()
        print(check.__name__, "OK")

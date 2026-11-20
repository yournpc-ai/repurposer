"""Verify the published closure sample without a provider, database or storage account."""
import gzip
import hashlib
import json
from pathlib import Path

import av

ROOT = Path(__file__).resolve().parent


def evidence(name):
    with gzip.open(ROOT / f"{name}.json.gz", "rt") as stream:
        return json.load(stream)


def main():
    media = json.loads((ROOT / "media.json").read_text())
    metrics = json.loads((ROOT / "metrics.json").read_text())
    database = evidence("database")
    decoded = {}
    for record in media.values():
        path = ROOT / record["artifact"]
        if path not in decoded:
            with av.open(str(path)) as stream:
                frames = sum(1 for _ in stream.decode(video=0))
            with av.open(str(path)) as stream:
                samples = sum(frame.samples for frame in stream.decode(audio=0))
            decoded[path] = (hashlib.sha256(path.read_bytes()).hexdigest(), frames, samples)
        digest, frames, samples = decoded[path]
        assert digest == record["sha256"] and frames == record["video"]["frames"]
        if "audio" in record:
            assert samples == record["audio"]["samples"]

    for case in ("pool-left", "pool-right", "pool-card", "pool-sound", "pool-demo", "pool-play-revision",
                 "left-head", "right-head", "title-head", "sound-head", "observed-studio", "observed-revision"):
        wire = evidence("wire-" + case)
        assert sum(row["phase"] == "request" for row in wire) == metrics[case]["requests"]
        assert all(call["schema_valid"] for call in metrics[case]["calls"])
    playback = evidence("pool-play-browser")
    for key in ("live", "reload0", "reload1", "revision_live", "revision_reload", "historical"):
        assert playback[key]["time"] > 0 and playback[key]["ready"] >= 2
    assert playback["live"]["url"] == playback["historical"]["url"]
    assert playback["revision_live"]["url"] != playback["live"]["url"]
    project = database[metrics["pool-demo"]["project"]]
    assert {o["id"] for o in project["outputs"]} == {playback["output"], playback["revision_output"]}
    for case, output in [("pool-demo", playback["output"]), ("pool-play-revision", playback["revision_output"])]:
        cards = [r["intent"]["output_refs"] for r in project["messages"]
                 if r["turn_id"] == metrics[case]["opening"] and (r["intent"] or {}).get("reviewed_version")]
        assert cards == [[output]]

    recovery = evidence("worker-recovery")
    assert recovery["objects"] == [recovery["boundary"]["file"]]
    assert recovery["files"]["video"] == recovery["boundary"]["file"]
    assert recovery["sha256_after_restart"] == recovery["files"]["video_sha256"] == recovery["boundary"]["sha256"]
    assert [r["amount"] for r in recovery["ledger"] if r["kind"] == "capture"] == ["-9"]
    assert evidence("ack-restored-0") == evidence("ack-restored-1")
    second_run = evidence("release-recovery")
    assert second_run["unreferenced_objects"] == []
    assert set(second_run["objects"]) == {o["file"] for o in second_run["outputs"]}
    assert len(second_run["outputs"]) == 2
    assert sorted(t["amount"] for t in second_run["ledger"] if t["kind"] == "capture") == [-10, -9]
    boundary = evidence("race-boundary")
    versions = database[boundary["project"]]["versions"]
    assert [v["id"] for v in versions] == [boundary["before"], boundary["competing_version"]]
    for case in ("pool-card", "title-head", "goodbye"):
        draft = evidence(case + "-pixels")
        assert draft["replay_returns_original"] and draft["outputs"] == 0 and draft["sources"] == []
        assert draft["frames"] == 90 and draft["video_duration"] == 3
        assert draft["minimum_white_pixels"] > 0 and draft["max_mean_delta_vs_first"] < 0.01
        assert all(not clip["animations"] for clip in draft["shots"])
    print(f"{len(decoded)} distinct MP4 files decoded. Both deliveries, upload recovery and draft replay verified.")


if __name__ == "__main__":
    main()

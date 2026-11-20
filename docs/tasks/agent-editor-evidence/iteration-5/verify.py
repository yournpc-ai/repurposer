"""Cross-check the archived MP4s, provider decisions, version writes, Chat and ledger."""
import gzip
import hashlib
import json
from pathlib import Path

import av

ROOT = Path(__file__).parent


def read(name):
    path = ROOT / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


def without_range(item):
    return {k: v for k, v in item.items() if k != "range"}


def verify():
    db = read("database.json.gz")
    metrics = read("metrics.json")
    manifest = read("media.json")
    for filename, evidence in manifest.items():
        path = ROOT / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"], filename
        for kind in ("video", "audio"):
            if kind not in evidence:
                continue
            with av.open(str(path)) as container:
                stream = getattr(container.streams, kind)[0]
                assert stream.codec_context.name == evidence[kind]["codec"]
                assert sum(1 for _ in container.decode(stream)) == evidence[kind]["frames"]
        if "preview" in evidence:
            assert evidence["preview"]["audio_available_to_model"] is False
            assert evidence["sha256"] == evidence["preview"]["mp4_sha256"]

    for prefix in ("", "take2-"):
        project = db[metrics[prefix + "studio"]["project"]]
        versions = project["versions"]
        assert [v["version"] for v in versions] == [1, 2, 3]
        assert [v["base_version_id"] for v in versions[1:]] == [v["id"] for v in versions[:-1]]
        assert len({v["content_digest"] for v in versions}) == 3
        assert len({v["composition_id"] for v in versions}) == 1
        assert all(v["settings"] == versions[0]["settings"] for v in versions)
        snapshots = {s["id"]: s["digest"] for s in project["sources"]}
        fixture = ROOT.parents[3] / "apps/api/test/fixtures/video_project/media/pricing-talk-source.mp4"
        source_hashes = {hashlib.sha256(f.read_bytes()).hexdigest() for f in [fixture, ROOT / "source-interview.mp4"]}
        assert source_hashes == set(snapshots.values())
        for v in versions:
            assert v["sources"] == versions[0]["sources"]
            assert all(snapshots[s["snapshot_id"]] == s["snapshot_digest"] for s in v["sources"])
        clips = [v["timeline"]["tracks"][0]["clips"] for v in versions]
        assert clips[0][0] == clips[1][0] == clips[2][0]
        assert without_range(clips[0][1]) == without_range(clips[1][1]) == without_range(clips[2][1])
        assert [(cs[1]["range"]["start"], cs[1]["range"]["end"]) for cs in clips] == [
            (405000, 540000), (270000, 405000), (270000, 450000)]
        assert all(without_range(v["scenes"][0]) == without_range(versions[0]["scenes"][0]) for v in versions)
        assert len(project["outputs"]) == len(project["runs"]) == 2
        assert sorted(t["amount"] for t in project["credits"] if t["kind"] == "capture") == [-10, -9]
        assert sum(t["amount"] for t in project["credits"] if t["kind"] in ("release", "hold")) == 0
        browser = read(prefix + "browser.json.gz")
        for number, label, playback in [(2, "studio", "live"), (3, "revision", "revision_live")]:
            v = versions[number - 1]
            turn = metrics[prefix + label]
            oid = browser["output" if number == 2 else "revision_output"]
            output = next(o for o in project["outputs"] if o["id"] == oid)
            pin = output["render_spec"]["provenance"]
            assert pin == {"composition_id": v["composition_id"], "composition_version_id": v["id"],
                           "content_digest": v["content_digest"]}
            assert output["composition_version_id"] == v["id"]
            artifact = manifest[prefix + f"delivery-v{number}.mp4"]
            review = output["quality"]["content_review"]
            assert pin.items() <= review.items() and review["output_id"] == oid
            assert review["video_sha256"] == artifact["sha256"]
            cards = [r for r in project["messages"] if r["turn_id"] == turn["opening"]
                     and (r["intent"] or {}).get("output_refs")]
            assert len(cards) == 1 and cards[0]["intent"]["output_refs"] == [oid]
            assert cards[0]["intent"]["reviewed_version"] == pin
            assert cards[0]["intent"]["video_sha256"] == artifact["sha256"]
            exchange = next(x for x in project["exchanges"] if x["turn_id"] == turn["opening"]
                            and x["tool"] == "review_video" and x["ok"])
            reviewed = json.loads(exchange["text"].split("\n", 1)[1])
            assert reviewed["reviewed_at"] == cards[0]["intent"]["reviewed_at"]
            assert reviewed["video_sha256"] == artifact["sha256"]
            for frame in reviewed["frames"]:
                file = ROOT / ("frame-" + frame["digest"][:12] + ".jpg")
                assert hashlib.sha256(file.read_bytes()).hexdigest() == frame["digest"]
            assert browser[playback]["ready"] == 4 and browser[playback]["time"] > 0.2
            assert oid in browser[playback]["url"]
            assert not {"present_plan", "propose_tasks", "start_run"} & {c["tool"] for c in turn["calls"]}
            assert all(c["schema_valid"] for c in turn["calls"])
            assert any(c["tool"] == "review_video" and c["status"] == "completed" for c in turn["calls"])
        assert browser["live"]["url"] == browser["reload0"]["url"] == browser["reload1"]["url"] == browser["historical"]["url"]
        assert browser["revision_live"]["url"] == browser["revision_reload"]["url"]

    actions = [c["tool"] for c in metrics["studio"]["calls"]]
    cut = actions.index("move_clip")
    assert "preview_range" in actions[:cut] and "preview_range" in actions[cut + 1:actions.index("export_video")]
    first_preview = next(v["preview"] for v in manifest.values()
                         if v.get("preview", {}).get("version_id") == db[metrics["studio"]["project"]]["versions"][0]["id"])
    assert {"from": 3.0, "to": 4.5, "active_clips": []} in first_preview["visual_windows"]
    before = read("ack-boundary.json.gz")
    recovered = read("ack-restored.json.gz")
    assert before["signal"] == "SIGKILL" and before["pre_ack"]["status"] == "active"
    for messages in recovered:
        assert len([r for r in messages if (r["intent"] or {}).get("type") == "editor_recovery"]) == 1
    assert read("stop-first.json.gz")["stop"]["body"]["turn_state"] == "retracted"
    assert read("save-first.json.gz")["stop"]["body"]["turn_state"] == "cancelled"
    interrupted = read("export-interruption.json.gz")
    fault = db[interrupted["project"]]
    assert len(fault["outputs"]) == len(fault["runs"]) == 1
    assert [t["amount"] for t in fault["credits"] if t["kind"] == "capture"] == [-12]
    assert fault["outputs"][0]["id"] == read("worker-interruption.json.gz")["output"]
    race = read("review-race.json.gz")
    assert race["original_uploaded_sha256"] == race["retained_sha256"]
    assert race["version"] == race["report"]["composition_version_id"] != race["concurrent_new_head"]
    assert race["output_quality_unchanged"] and race["cached_reviewed_at"] == race["report"]["reviewed_at"]
    paid = db[metrics["approved-fixed"]["project"]]
    assert [t["amount"] for t in paid["credits"] if t["kind"] == "capture"] == [-12]
    assert len(paid["outputs"]) == len(paid["runs"]) == 1
    assert any((r["intent"] or {}).get("output_refs") == [paid["outputs"][0]["id"]] for r in paid["messages"])
    declined = metrics["decline"]
    rows = [r for r in db[declined["project"]]["messages"] if r["turn_id"] == declined["opening"]]
    assert any((r["intent"] or {}).get("media_result", {}).get("status") == "declined" for r in rows)
    assert not any(r["workflow_run_id"] for r in rows)
    reused = metrics["reuse"]
    expected = read("take2-browser.json.gz")["revision_output"]
    assert any((r["intent"] or {}).get("output_refs") == [expected]
               for r in db[reused["project"]]["messages"] if r["turn_id"] == reused["opening"])
    assert not db[metrics["new-scope"]["project"]]["outputs"]
    print(f"Verified {len(manifest)} MP4 samples, both Studio sessions, pinned deliveries and recovery evidence.")


if __name__ == "__main__":
    verify()

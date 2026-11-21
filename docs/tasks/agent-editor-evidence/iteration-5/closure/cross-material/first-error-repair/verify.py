import gzip
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load(name):
    with gzip.open(ROOT / name, "rt") as archive:
        return json.load(archive)


def transform(result, number=-1):
    version = result["database"]["versions"][number]
    return [clip["object"]["transform"] for track in version["timeline"]["tracks"] for clip in track["clips"] if clip["object"]["kind"] == "video"]


def clips(result, number=-1):
    version = result["database"]["versions"][number]
    return [clip for track in version["timeline"]["tracks"] for clip in track["clips"] if clip["object"]["kind"] == "video"]


def main():
    single = load("single-speaker-repair-original.json.gz")
    assert len(single["database"]["outputs"]) == 0
    assert transform(single) == [{"x": -29.1, "y": 46.2, "scale": 2.2, "origin": "center", "rotation": 0.0}]
    assert clips(single)[0]["range"] == {"start": 0, "end": 1080000}

    subtitle = load("subtitled-short-repair-original.json.gz")
    assert transform(subtitle) == [{"x": 0.0, "y": 0.0, "scale": 1.0, "origin": "center", "rotation": 0.0}]
    assert subtitle["database"]["outputs"][0]["composition_version_id"] == subtitle["database"]["versions"][-1]["id"]

    opened = load("open-speech-repair-original.json.gz")
    opened_clips = clips(opened)
    assert [[clip["range"]["start"] / 90000, clip["range"]["end"] / 90000] for clip in opened_clips] == [[0, 5], [5, 10], [10, 15]]
    assert [[clip["source"]["source_range"]["start"] / 90000, clip["source"]["source_range"]["end"] / 90000] for clip in opened_clips] == [[30, 35], [35, 40], [40, 45]]
    assert all(item["scale"] == 1.2 for item in transform(opened))
    assert opened["database"]["outputs"][0]["composition_version_id"] == opened["database"]["versions"][-1]["id"]

    head = load("independent-talking-head-repair-independent.json.gz")
    assert not head["database"]["outputs"]
    assert transform(head) == [{"x": 0.0, "y": 0.0, "scale": 1.0, "origin": "center", "rotation": 0.0}]
    assert clips(head)[0]["range"] == {"start": 0, "end": 382500}

    animation = load("independent-animation-delivery-repair-independent.json.gz")
    assert [[clip["range"]["start"] / 90000, clip["range"]["end"] / 90000] for clip in clips(animation)] == [[0, 2], [2, 4.25]]
    assert animation["database"]["outputs"][0]["composition_version_id"] == animation["database"]["versions"][-1]["id"]

    two = load("two-person-repair-regression.json.gz")
    assert not two["database"]["outputs"]
    assert transform(two) == [{"x": 0.0, "y": 0.0, "scale": 1.0, "origin": "center", "rotation": 0.0}]

    continuation = load("independent-talking-head-repair-continuation.json.gz")
    assert continuation["seed"]["project_id"] == head["seed"]["project_id"]
    assert transform(continuation) == [{"x": -4.0, "y": 0.0, "scale": 1.0, "origin": "center", "rotation": 0.0}]
    assert not continuation["database"]["outputs"]

    silent = load("subtitled-short-repair-source-audio.json.gz")
    silent_facts = []
    for trace in silent["trace"]:
        for message in (trace.get("payload") or {}).get("messages", []):
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    try:
                        fact = json.loads(part.get("text", ""))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(fact, dict) and fact.get("source_framing", {}).get("source_audio"):
                        silent_facts.append(fact["source_framing"]["source_audio"])
    assert silent_facts[-1] == {"stream_present": True, "fully_decoded": True, "is_silent": True}

    absent = load("independent-animation-delivery-repair-source-audio-final.json.gz")
    absent_facts = []
    for trace in absent["trace"]:
        for message in (trace.get("payload") or {}).get("messages", []):
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    try:
                        fact = json.loads(part.get("text", ""))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(fact, dict) and fact.get("source_framing", {}).get("source_audio") is not None:
                        absent_facts.append(fact["source_framing"]["source_audio"])
    assert absent_facts[-1] == {"stream_present": False}

    stop = json.loads((ROOT / "repair-stop.json").read_text()) if (ROOT / "repair-stop.json").exists() else None
    if stop is None:
        stop = json.loads(Path("scratch/first-error-attribution-20261121/live/results/repair-stop.json").read_text())
    assert stop["stop"]["body"] == {"accepted": True, "turn_state": "retracted"}
    assert stop["versions_before"] == stop["versions_after"]
    assert stop["outputs_before"] == stop["outputs_after"]

    browser = json.loads((ROOT / "browser-results.json").read_text())
    assert len(browser["plays"]) == 3
    for play in browser["plays"]:
        assert play["before_reload"]["time"] > 0 and not play["before_reload"]["paused"]
        assert play["after_reload"]["time"] > 0 and not play["after_reload"]["paused"]
        assert play["before_reload"]["src"] == play["after_reload"]["src"]

    continuation = json.loads((ROOT / "browser-continuation.json").read_text())
    assert continuation["http_status"] == 200
    assert continuation["provider_requests"] > 0
    assert continuation["versions_before_after"] == [4, 4]
    assert continuation["outputs_before_after"] == [0, 0]
    assert continuation["hard_refresh_prompt_visible"] is True

    metrics = json.loads((ROOT / "metrics.json").read_text())
    assert all(row["schema_valid"] <= row["native_calls"] for row in metrics)
    assert all(row["failed"] is None for row in metrics)
    for row in metrics:
        archived = load(row["archive"])
        usage = [item for item in archived["database"]["usage"]
                 if item["prompt_tokens"] == row["prompt_tokens"]
                 and item["completion_tokens"] == row["completion_tokens"]]
        assert len(usage) == 1
        assert float(usage[0]["cost_usd"]) == row["usage_usd"]
    report = {
        "verified": True,
        "cases": len(metrics),
        "requests": sum(row["requests"] for row in metrics),
        "prompt_tokens": sum(row["prompt_tokens"] for row in metrics),
        "completion_tokens": sum(row["completion_tokens"] for row in metrics),
        "usage_usd": round(sum(row["usage_usd"] for row in metrics), 6),
        "browser_outputs": len(browser["plays"]),
        "browser_continuation": True,
        "stop": stop["stop"]["body"],
        "source_audio": {"silent_source": silent_facts[-1], "absent_source": absent_facts[-1]},
    }
    (ROOT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

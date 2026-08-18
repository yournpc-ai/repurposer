"""reframe_clip smoke (ADR-045): compute crop_track keyframes on real footage
through the skill's procedure and render them through the REAL render service
— watch the MP4s to tune the write-side anti-dizzy constraints (task 5).

- interview_switch on xy_1 (two-person static interview; attribution turns
  reused from the spike cache /tmp/spike/xy1_predictions.json)
- speaker_follow on xy_2 (single-person stage talk, already in the bucket as
  demo/uploads/xy_2.mp4 per scripts/track_model_fixture.py)

    cd apps/api && uv run python scripts/reframe_smoke.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.models.schemas import ClipSpec  # noqa: E402
from app.pipeline.rendering import _absolutize  # noqa: E402
from app.skills.reframe.procedure import compute_crop_track  # noqa: E402
from app.tools.storage import (  # noqa: E402
    exists,
    get_output_path,
    presign_upload,
    public_url,
    save,
)

XY1_LOCAL = Path("/Users/sylas/xy_1.mp4")
XY1_KEY = "tmp/reframe_smoke_xy1.mp4"
XY2_KEY = "demo/uploads/xy_2.mp4"
PREDICTIONS = Path("/tmp/spike/xy1_predictions.json")
PROJECT = UUID("00000000-0000-0000-0000-000000000000")
USER = "00000000-0000-0000-0000-000000000000"


def _xy1_speaker_map() -> dict:
    preds = json.loads(PREDICTIONS.read_text())
    return {
        "form": "interview",
        "speakers": [
            {"id": "left", "screen_hint": "left"},
            {"id": "right", "screen_hint": "right"},
        ],
        "turns": [
            {
                "start": p["start"],
                "end": p["end"],
                "speaker": "left" if p["pred"] == "L" else "right",
            }
            for p in preds
        ],
    }


def _spec(segments: list[dict], keyframes: list[dict] | None, source_url: str, duration: float) -> dict:
    return {
        "source": {"asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "kind": "video",
                   "url": source_url, "image_urls": [], "fps": 30, "duration": duration},
        "aspect": "9:16",
        "segments": segments,
        "crop": {"x": 0.5, "y": 0.5, "scale": 1},
        "crop_track": keyframes,
        "caption_track": [],
        "translation_track": [],
        "caption_style_preset": "clean-bottom",
        "caption_position": None, "caption_enabled": False,
        "layers": [],
        "title": {"text": "", "enabled": False},
        "music": {"music_id": None, "url": None, "enabled": False, "gain_db": -18},
        "dub": None, "brand": None, "brand_ref": None, "target_language": "en",
    }


async def _render(spec: dict, basename: str) -> str:
    ClipSpec.model_validate(spec)
    baked = _absolutize(json.loads(json.dumps(spec)))
    assert baked["source"]["url"].startswith("http")
    video_key = await get_output_path(PROJECT, USER, f"{basename}.mp4")
    srt_key = await get_output_path(PROJECT, USER, f"{basename}.srt")
    body = {
        "spec": baked,
        "basename": basename,
        "outputs": {
            "video": {"key": video_key, "put_url": await presign_upload(video_key),
                      "content_type": "video/mp4"},
            "srt": {"key": srt_key, "put_url": await presign_upload(srt_key),
                    "content_type": "text/plain"},
        },
    }
    t0 = time.time()
    async with httpx.AsyncClient(timeout=600) as client:
        # 127.0.0.1, not localhost — this machine's ::1 is intercepted (503).
        r = await client.post("http://127.0.0.1:3001/render", json=body)
    print("status", r.status_code, "in", round(time.time() - t0, 1), "s")
    if r.status_code != 200:
        print(r.text[:500])
    r.raise_for_status()
    return public_url(video_key)


async def main() -> None:
    if not await exists(XY1_KEY):
        await save(XY1_KEY, XY1_LOCAL.read_bytes(), "video/mp4")
        print("uploaded", XY1_KEY)

    # interview_switch — two kept windows spanning real speaker switches
    # (L monologue ends 48.92 → R turn 49.76; R block → L turn 90.38).
    xy1_segments = [
        {"id": "w1", "start": 46.0, "end": 66.0, "hidden": False, "transition": "none"},
        {"id": "w2", "start": 88.0, "end": 105.0, "hidden": False, "transition": "none"},
    ]
    xy1_spec_probe = {"aspect": "9:16", "segments": xy1_segments}
    xy1_kfs, xy1_mode = compute_crop_track(XY1_LOCAL, xy1_spec_probe, _xy1_speaker_map(), "interview_switch")
    print(f"interview_switch: {len(xy1_kfs or [])} keyframes")
    for k in xy1_kfs or []:
        print("  ", k)
    url1 = await _render(_spec(xy1_segments, xy1_kfs, XY1_KEY, 105.0), f"reframe-smoke-interview-{int(time.time())}")
    print("INTERVIEW_URL", url1)

    # speaker_follow — a 20s stage-talk window (xy_2 is already in the bucket).
    xy2_segments = [
        {"id": "w1", "start": 30.0, "end": 50.0, "hidden": False, "transition": "none"},
    ]
    xy2_probe = {"aspect": "9:16", "segments": xy2_segments}
    xy2_kfs, xy2_mode = compute_crop_track(Path("/Users/sylas/xy_2.mp4"), xy2_probe, None, "speaker_follow")
    print(f"speaker_follow: {len(xy2_kfs or [])} keyframes")
    for k in (xy2_kfs or [])[:12]:
        print("  ", k)
    url2 = await _render(_spec(xy2_segments, xy2_kfs, XY2_KEY, 60.0), f"reframe-smoke-follow-{int(time.time())}")
    print("FOLLOW_URL", url2)


if __name__ == "__main__":
    asyncio.run(main())

"""Track-model acceptance fixture (ADR-044): render a spec carrying the new
contracts — hetero splice segment (donor window + fade entry), segment-anchored
text_callout layer, captions that must not leak onto the donor segment —
through the REAL bake seam + render service. Prints the uploaded URLs/keys.

    cd apps/api && uv run python scripts/track_model_fixture.py
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
from app.providers.storage import get_output_path, presign_upload, public_url  # noqa: E402

DEMO = "demo/uploads/xy_2.mp4"
PROJECT = UUID("00000000-0000-0000-0000-000000000000")
USER = "00000000-0000-0000-0000-000000000000"

spec = {
    "source": {"asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "kind": "video",
               "url": DEMO, "image_urls": [], "fps": 30, "duration": 60},
    "aspect": "16:9",
    "segments": [
        {"id": "mainAA", "start": 10.0, "end": 14.0, "hidden": False, "transition": "none"},
        {"id": "splice", "asset_id": "1fa85f64-5717-4562-b3fc-2c963f66afa7", "url": DEMO,
         "start": 40.0, "end": 44.0, "hidden": False, "transition": "fade"},
    ],
    "crop": {"x": 0.5, "y": 0.5, "scale": 1},
    "caption_track": [
        {"start": 10.5, "end": 11.0, "text": "MAINLINE", "lang": "en"},
        {"start": 11.0, "end": 11.5, "text": "caption", "lang": "en"},
        {"start": 41.0, "end": 41.5, "text": "DONORLEAK", "lang": "en"},
    ],
    "translation_track": [],
    "caption_style_preset": "clean-bottom",
    "caption_position": None, "caption_enabled": True,
    "layers": [
        {"id": "lay1", "kind": "text_callout",
         "anchor": {"kind": "segment", "segment_id": "mainAA", "offset_seconds": 1.0},
         "duration_seconds": 2.5, "rect": {"x": 0.25, "y": 0.62, "w": 0.5, "h": 0.14}, "z": 3,
         "media": {"kind": "text", "text": "层轨实证 LAYER"}, "provenance": "real"}
    ],
    "title": {"text": "", "enabled": False},
    "music": {"music_id": None, "url": None, "enabled": False, "gain_db": -18},
    "dub": None, "brand": None, "brand_ref": None, "target_language": "en",
}


async def main() -> None:
    ClipSpec.model_validate(spec)
    baked = _absolutize(json.loads(json.dumps(spec)))
    assert baked["source"]["url"].startswith("http")
    assert baked["segments"][1]["url"].startswith("http"), "hetero url not absolutized by the fold"
    assert "url" not in baked["segments"][0]
    print("bake fold OK (source.url + segments[*].url via the registry)")

    basename = f"trackmodel-fixture-{int(time.time())}"
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
    print(r.text[:300])
    r.raise_for_status()
    print("VIDEO_URL", public_url(video_key))
    print("KEYS", video_key, "|", srt_key)


if __name__ == "__main__":
    asyncio.run(main())

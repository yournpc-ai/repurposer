"""Harvest the multilingual-subs recipe's contrast example outputs (2026-08-14
four-case revision: EN original + CN-EN bilingual + FR subs + ES dub).

The pipeline run (the multilingual-subs chain: translate_clip zh bilingual +
translate_clip fr + dub_clip es, all fork, at 1:1) yields the EN original, the
zh-bilingual fork and the es-dub fork; the FR single-line version is produced
script-side (translate_caption_track + render service) and passed in as a
local file. This script promotes all four into the demo/ tree: downloads each
MP4 (or reads the local file), extracts a PER-CASE poster frame (the contrast
must read from the thumbnails alone), and uploads both to the protected demo/
prefix with content-hashed keys — the URLs it prints are what
`RecipeEntry.example_outputs` registers (recipes.py), with label_key
`recipes.materials.<label>`.

Usage:
    uv run python scripts/bake_subs_contrast.py <en> <zh_bilingual> <fr> <es_dub> [poster_t_seconds]

Each source is an Output UUID (fetched from the DB) or a local .mp4 path.

Idempotent in effect: content-hashed keys mean re-runs only create objects
for changed content; superseded demo objects are left in place (protected
prefix — clean up manually if a harvest is abandoned).
"""

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Output  # noqa: E402
from app.tools.storage import _get_s3_client, public_url, read  # noqa: E402

# (stem, materials label_key) per case, in argv order.
CASES = [
    ("en", "subs_en"),
    ("zh-bilingual", "subs_zh_bilingual"),
    ("fr", "subs_fr"),
    ("es-dub", "dub_es"),
]
PREFIX = "demo/outputs"
IMMUTABLE = "public, max-age=31536000, immutable"


def _poster_frame(mp4: bytes, t_s: float) -> bytes | None:
    """Extract one frame as JPEG (PyAV image2/mjpeg; no PIL in this env).

    Full decode up to the target frame — keyframe seek (skip_frame=NONKEY)
    lands on arbitrary keyframes: a t=8 poster once came back with the title
    overlay still at opacity 0 (the 2026-08-14 harvest's first posters)."""
    import av

    tmp = Path(tempfile.mkstemp(suffix=".mp4")[1])
    try:
        tmp.write_bytes(mp4)
        with av.open(str(tmp)) as inp:
            stream = inp.streams.video[0]
            fps = float(stream.average_rate)
            target = int(t_s * fps)
            frame = None
            for i, f in enumerate(inp.decode(stream)):
                frame = f
                if i >= target:
                    break
            if frame is None:
                return None
            out = Path(tempfile.mkstemp(suffix=".jpg")[1])
            with av.open(str(out), "w", format="image2") as oc:
                vstream = oc.add_stream("mjpeg", rate=1)
                vstream.width, vstream.height = frame.width, frame.height
                vstream.pix_fmt = "yuvj420p"
                for packet in vstream.encode(frame):
                    oc.mux(packet)
                for packet in vstream.encode(None):
                    oc.mux(packet)
            data = out.read_bytes()
            out.unlink(missing_ok=True)
            return data
    except Exception as e:  # poster is optional in the schema — skip on failure
        print(f"poster skipped: {e}")
        return None
    finally:
        tmp.unlink(missing_ok=True)


async def _put_demo(stem: str, suffix: str, data: bytes, content_type: str) -> str:
    digest = hashlib.md5(data).hexdigest()[:8]
    key = f"{PREFIX}/{stem}-{digest}{suffix}"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=IMMUTABLE,
    )
    url = public_url(key)
    assert url is not None
    return url


async def main() -> None:
    sources = sys.argv[1:5]
    if len(sources) != 4:
        raise SystemExit("need 4 sources (Output UUID or local .mp4): en zh-bilingual fr es-dub")
    poster_t = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0

    async with AsyncSessionLocal() as db:
        urls: dict[str, str] = {}
        posters: dict[str, str | None] = {}
        for (stem, label), src in zip(CASES, sources, strict=True):
            path = Path(src)
            if path.is_file():
                mp4 = path.read_bytes()
            else:
                output = await db.get(Output, src)
                if output is None or not (output.files or {}).get("video"):
                    raise SystemExit(f"output {src} ({stem}) missing or has no rendered video")
                mp4 = await read(output.files["video"])
            urls[stem] = await _put_demo(f"subs-contrast-{stem}", ".mp4", mp4, "video/mp4")
            poster = _poster_frame(mp4, poster_t)
            posters[stem] = (
                await _put_demo(f"subs-contrast-{stem}-poster", ".jpg", poster, "image/jpeg")
                if poster
                else None
            )
            print(f"{stem}: {len(mp4) / 1e6:.1f}MB harvested")

    print("\n--- recipes.py example_outputs ---")
    for stem, label in CASES:
        poster_field = f'poster_url="{posters[stem]}", ' if posters[stem] else ""
        print(
            f'ExampleOutput(kind="video", url="{urls[stem]}", '
            f'{poster_field}label_key="{label}"),'
        )


if __name__ == "__main__":
    asyncio.run(main())

"""Standalone harvest: download an already-rendered quote-card MP4 (from a
prior pipeline run) and upload it to the demo/ bucket under the content-
hashed key. Prints the recipe-ready URL for the operator to paste into
``recipes.py``.

Usage:
    uv run python scripts/_harvest_existing_quote.py <public_url>
"""
import asyncio
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.providers.storage import _get_s3_client, public_url  # noqa: E402

PREFIX = "demo/outputs"
IMMUTABLE = "public, max-age=31536000, immutable"


async def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: _harvest_existing_quote.py <public_url>")
    src = sys.argv[1]
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.get(src)
        if r.status_code != 200:
            raise SystemExit(f"download: HTTP {r.status_code}")
        mp4 = r.content
    print(f"downloaded {len(mp4)} bytes from {src}")

    digest = hashlib.md5(mp4).hexdigest()[:8]
    stem = "quote-card"
    key_mp4 = f"{PREFIX}/{stem}-{digest}.mp4"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.s3_bucket_name,
        Key=key_mp4,
        Body=mp4,
        ContentType="video/mp4",
        CacheControl=IMMUTABLE,
    )
    url_mp4 = public_url(key_mp4)
    assert url_mp4 is not None

    # poster (optional, ffmpeg-free PyAV)
    url_jpg = None
    try:
        import av
        container = av.open(io.BytesIO(mp4))
        for frame in container.decode(container.streams.video[0]):
            buf = io.BytesIO()
            frame.to_image().save(buf, format="JPEG", quality=82)
            poster = buf.getvalue()
            key_jpg = f"{PREFIX}/{stem}-poster-{digest}.jpg"
            await asyncio.to_thread(
                client.put_object,
                Bucket=settings.s3_bucket_name,
                Key=key_jpg,
                Body=poster,
                ContentType="image/jpeg",
                CacheControl=IMMUTABLE,
            )
            url_jpg = public_url(key_jpg)
            break
    except Exception as exc:  # noqa: BLE001
        print(f"poster skipped: {type(exc).__name__}: {exc}")

    print()
    print("=== BAKED ===")
    print(f"video_url = {url_mp4!r},")
    if url_jpg:
        print(f"poster_url = {url_jpg!r},")
    else:
        print("poster_url = None,")
    print(f"label_key = 'quotes_output',")


if __name__ == "__main__":
    asyncio.run(main())

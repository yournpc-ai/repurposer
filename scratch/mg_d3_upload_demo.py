"""MG D3 demo publish: upload the e2e-rendered film to the public demo/ tree
with a content-hashed key (immutable cache law — same discipline as
upload_recipe_assets.py, but no manifest rewrite: the MG shelf demo's URL
lives in recipeFamilies.ts).

Run: uv run python scratch/mg_d3_upload_demo.py <film.mp4> <logical-stem>
Prints the public URL to paste into recipeFamilies.ts.
"""

import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from app.config import settings  # noqa: E402
from app.providers.storage import _get_s3_client, public_url  # noqa: E402

IMMUTABLE = "public, max-age=31536000, immutable"


async def main() -> None:
    src = Path(sys.argv[1])
    stem = sys.argv[2]
    data = src.read_bytes()
    digest = hashlib.md5(data).hexdigest()[:8]
    key = f"demo/outputs/{stem}-{digest}{src.suffix}"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=data,
        ContentType="video/mp4",
        CacheControl=IMMUTABLE,
    )
    url = public_url(key)
    assert url is not None
    print(url)


asyncio.run(main())

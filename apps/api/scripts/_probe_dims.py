"""Probe dimensions of xy_2.mp4 (source) vs the rendered MP4 (output)."""
import asyncio
import io

import av
import httpx

URLS = [
    ("source xy_2.mp4",
     "https://repurposer.tos-ap-southeast-1.volces.com/demo/uploads/xy_2.mp4"),
    ("rendered MP4",
     "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/quote-card-stacked-6bc962a1.mp4"),
    ("composite PNG",
     "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/quote-stack-4a6862d2.png"),
    ("baked poster JPG",
     "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/quote-card-stacked-poster-e9ee6c89.jpg"),
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=300) as c:
        for label, url in URLS:
            r = await c.get(url, follow_redirects=True)
            if r.status_code != 200:
                print(f"{label}: HTTP {r.status_code}")
                continue
            blob = r.content
            if url.endswith(".png") or url.endswith(".jpg"):
                # PIL probe
                from PIL import Image
                im = Image.open(io.BytesIO(blob))
                print(f"{label}: {im.size[0]}x{im.size[1]} (ratio={im.size[0]/im.size[1]:.3f})")
                continue
            container = av.open(io.BytesIO(blob))
            s = container.streams.video[0]
            ratio = s.width / s.height
            print(
                f"{label}: {s.width}x{s.height} "
                f"(ratio={ratio:.3f}, codec={s.codec_context.name})"
            )
            container.close()


asyncio.run(main())
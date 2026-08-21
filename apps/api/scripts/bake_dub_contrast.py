"""Bake the dub recipe's contrast example outputs (EN/ZH/FR/ES, 2026-08-07).

Takes one clip Output from the DB, dubs it into ZH/FR/ES with the aligned
synthesis chain (EN = source render), renders all four through the render
service, and uploads the MP4s (+ one shared poster frame) to the protected
demo/ prefix with content-hashed keys — the URLs it prints are what
`RecipeEntry.example_outputs` registers (recipes.py), with label_key
`recipes.materials.dub_<lang>`.

Usage:
    uv run python scripts/bake_dub_contrast.py <output_id>

Costs MiniMax quota (3 translations + ~15 TTS calls) and 4 render-service
renders. Idempotent in effect: content-hashed keys mean re-runs only create
objects for changed content; superseded demo objects are left in place
(protected prefix — clean up manually if a bake is abandoned).
"""

import asyncio
import hashlib
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Output, Project  # noqa: E402
from app.pipeline.rendering import _absolutize  # noqa: E402
from app.tools.dub.procedure import synthesize_dub  # noqa: E402
from app.tools.storage import (  # noqa: E402
    _get_s3_client,
    delete,
    get_output_path,
    presign_upload,
    public_url,
    read,
)

LANGS = ["en", "zh", "fr", "es"]  # EN first: its MP4 donates the poster frame
PREFIX = "demo/outputs"
IMMUTABLE = "public, max-age=31536000, immutable"


async def _render(spec: dict, output: Output, user_id, lang: str) -> bytes:
    """Render one spec via the render service to a temp key; return MP4 bytes."""
    ts = int(time.time())
    video_key = await get_output_path(
        output.project_id, user_id, f"bake-dub-{lang}-{ts}.mp4"
    )
    srt_key = await get_output_path(
        output.project_id, user_id, f"bake-dub-{lang}-{ts}.srt"
    )
    payload = {
        "spec": _absolutize(spec),
        "outputs": {
            "video": {
                "key": video_key,
                "put_url": await presign_upload(
                    video_key, content_type="video/mp4", ttl=900
                ),
                "content_type": "video/mp4",
            },
            "srt": {
                "key": srt_key,
                "put_url": await presign_upload(srt_key, content_type="text/srt", ttl=900),
                "content_type": "text/srt",
            },
        },
    }
    async with httpx.AsyncClient(timeout=900) as client:
        resp = await client.post(settings.render_url, json=payload)
        if resp.status_code != 200:
            raise SystemExit(f"render {lang} failed {resp.status_code}: {resp.text[:500]}")
    data = await read(video_key)
    await delete(video_key)
    await delete(srt_key)
    return data


def _poster_frame(mp4: bytes, t_s: float = 1.0) -> bytes | None:
    """Extract one frame as JPEG (PyAV image2/mjpeg; no PIL in this env)."""
    import av

    tmp = Path(tempfile.mkstemp(suffix=".mp4")[1])
    try:
        tmp.write_bytes(mp4)
        with av.open(str(tmp)) as inp:
            stream = inp.streams.video[0]
            stream.codec_context.skip_frame = "NONKEY"
            inp.seek(int(t_s / stream.time_base), stream=stream)
            frame = next(inp.decode(stream))
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
    output_id = sys.argv[1]
    async with AsyncSessionLocal() as db:
        output = await db.get(Output, output_id)
        if output is None or not output.render_spec:
            raise SystemExit(f"output {output_id} missing or has no render_spec")
        project = await db.get(Project, output.project_id)
        assert project is not None

        urls: dict[str, str] = {}
        poster: bytes | None = None
        for lang in LANGS:
            if lang == "en":
                spec = dict(output.render_spec)
            else:
                t0 = time.time()
                spec = await synthesize_dub(db, output, project, lang)
                print(f"dub {lang}: synthesized in {time.time() - t0:.1f}s")
            t0 = time.time()
            mp4 = await _render(spec, output, project.user_id, lang)
            urls[lang] = await _put_demo(f"dub-contrast-{lang}", ".mp4", mp4, "video/mp4")
            print(f"render {lang}: {len(mp4) / 1e6:.1f}MB in {time.time() - t0:.1f}s")
            if lang == "en":
                poster = _poster_frame(mp4)
        await db.commit()  # persist cached voice_id on the asset meta

    poster_url = (
        await _put_demo("dub-contrast-poster", ".jpg", poster, "image/jpeg")
        if poster
        else None
    )

    print("\n--- recipes.py example_outputs ---")
    for lang in LANGS:
        poster_field = f'poster_url="{poster_url}", ' if poster_url else ""
        print(
            f'ExampleOutput(kind="video", url="{urls[lang]}", '
            f'{poster_field}label_key="dub_{lang}"),'
        )


if __name__ == "__main__":
    asyncio.run(main())

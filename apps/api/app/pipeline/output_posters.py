"""Deterministic, real-frame posters for exact delivered video Outputs."""
from __future__ import annotations

import hashlib
import io

import av
from PIL import Image, ImageStat

from app.models.tables import Output
from app.providers import storage


def _decoded_frame(container, stream, seconds: float):
    container.seek(max(0, int(seconds / stream.time_base)), stream=stream, backward=True)
    for frame in container.decode(stream):
        if frame.time is not None and frame.time + 0.04 >= seconds:
            return frame.to_image().convert("RGB")
    return None


def extract_poster(video: bytes) -> bytes:
    """Pick the first settled, non-blank frame from three fixed film positions."""
    with av.open(io.BytesIO(video), mode="r") as container:
        stream = next((item for item in container.streams if item.type == "video"), None)
        if stream is None:
            raise ValueError("the Output has no decodable video stream")
        duration = (
            float(stream.duration * stream.time_base)
            if stream.duration is not None and stream.time_base is not None
            else float(container.duration / av.time_base)
            if container.duration is not None
            else 0.0
        )
        targets = [duration * ratio for ratio in (0.2, 0.5, 0.8)] if duration > 0 else [0.0]
        best: Image.Image | None = None
        best_contrast = -1.0
        for target in targets:
            image = _decoded_frame(container, stream, target)
            if image is None:
                continue
            stat = ImageStat.Stat(image.convert("L").resize((160, 90)))
            mean, contrast = stat.mean[0], stat.stddev[0]
            if contrast > best_contrast:
                best, best_contrast = image, contrast
            if mean >= 10 and contrast >= 6:
                best = image
                break
        if best is None:
            raise ValueError("no actual video frame could be decoded for the poster")
        best.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        best.save(out, "JPEG", quality=88)
        return out.getvalue()


async def ensure_output_poster(output: Output) -> str:
    """Return an immutable poster key without mutating active or archived rows."""
    video_key = (output.files or {}).get("video")
    render_status = getattr(output.render_status, "value", output.render_status)
    if render_status != "completed" or not isinstance(video_key, str) or not video_key:
        raise ValueError("this Output has no completed delivered video file")
    media_digest = hashlib.sha256(video_key.encode("utf-8")).hexdigest()[:16]
    key = f"output-posters/{output.id}-{media_digest}.jpg"
    if not await storage.exists(key):
        await storage.save(key, extract_poster(await storage.read(video_key)), content_type="image/jpeg")
    return key

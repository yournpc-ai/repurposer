"""Shared media encoding and website readiness fixture helpers."""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import (
    BrandProfile,
    BrandSourceRef,
    Brief,
    BriefSlot,
    BriefSlotSource,
)
from app.pipeline.render_probe import DEFAULT_FPS

WEBSITE_URL = "https://www.legitevi.com/en"


def encode_mp4(
    path: Path,
    *,
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    frames: int = DEFAULT_FPS,
    fps: int = DEFAULT_FPS,
    audio: bool = False,
    audio_rate: int = 44100,
    tone_hz: float | None = None,
    fill_rgb: tuple[int, int, int] | None = None,
    motion_stripe: bool = True,
) -> Path:
    """Encode a deterministic MP4 fixture in-memory via PyAV (zero render-service IO)."""
    import av
    import numpy as np

    container = av.open(str(path), "w")
    stream = container.add_stream(codec, rate=fps)
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p"
    if codec == "h264":
        stream.options = {"preset": "ultrafast", "tune": "zerolatency"}
    astream = container.add_stream("aac", rate=audio_rate) if audio else None
    for i in range(frames):
        if fill_rgb is not None:
            arr = np.zeros((height, width, 3), dtype=np.uint8)
            arr[:, :, 0] = fill_rgb[0]
            arr[:, :, 1] = fill_rgb[1]
            arr[:, :, 2] = fill_rgb[2]
            if motion_stripe:
                # Slight motion stripe so frames are clearly non-black and distinct
                x0 = (i * 17) % max(1, width - 20)
                arr[10:30, x0 : x0 + 20, :] = 255
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24").reformat(format="yuv420p")
        else:
            frame = av.VideoFrame(width, height, "yuv420p")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    if astream is not None:
        remaining = int(frames / fps * audio_rate)
        pts = 0
        while remaining > 0:
            n = min(1024, remaining)
            if tone_hz is not None:
                t = (np.arange(n, dtype=np.float32) + pts) / float(audio_rate)
                wave = (0.25 * np.sin(2.0 * np.pi * tone_hz * t)).astype(np.float32)
                aframe = av.AudioFrame.from_ndarray(wave.reshape(1, n), format="fltp", layout="mono")
            else:
                aframe = av.AudioFrame(format="fltp", layout="mono", samples=n)
                for plane in aframe.planes:
                    plane.update(b"\x00" * plane.buffer_size)
            aframe.sample_rate = audio_rate
            aframe.pts = pts
            pts += n
            for packet in astream.encode(aframe):
                if packet.pts is None or packet.pts < 0:
                    continue
                container.mux(packet)
            remaining -= n
        for packet in astream.encode():
            if packet.pts is None or packet.pts < 0:
                continue
            container.mux(packet)
    container.close()
    return path


def website_question_arguments() -> dict:
    return {
        "question": "宣传片制作偏好",
        "items": [
            {
                "slot": "production_direction",
                "question": "这支片子打算在哪里播、怎么讲？",
                "options": [
                    {"label": "官网推广 · 用真实案例演示产品", "value": "官网推广 · 用真实案例演示产品"},
                    {"label": "发布会开场 · 用品牌使命串起故事", "value": "发布会开场 · 用品牌使命串起故事"},
                ],
            },
            {
                "slot": "target_seconds",
                "question": "希望片长是多少秒？",
                "options": [{"label": "30 秒", "value": 30}, {"label": "60 秒", "value": 60}],
            },
            {
                "slot": "narration_language",
                "question": "旁白用哪种语言？",
                "options": [{"label": "英文", "value": "en"}, {"label": "中文", "value": "zh"}],
            },
            {
                "slot": "subtitle_languages",
                "question": "字幕需要哪些语言？",
                "options": [{"label": "英文", "value": ["en"]}, {"label": "中文", "value": ["zh"]}],
            },
            {
                "slot": "aspect",
                "question": "画面比例选哪种？",
                "options": [{"label": "16:9", "value": "16:9"}, {"label": "9:16", "value": "9:16"}],
            },
        ],
        "default_path": "按推荐设置制作",
    }


def website_asset(status: str = "pending", *, shots: bool = True) -> dict:
    return {
        "kind": "asset",
        "type": "web_page",
        "asset_id": "asset-1",
        "status": status,
        "url": WEBSITE_URL,
        "text_snapshot_id": "snapshot-1",
        "captured_view_count": 1 if shots else 0,
        "meta": {
            "capture_url": WEBSITE_URL,
            "research": {"body": ["Citations should be as universal as hashtags."]}
            if status == "completed"
            else None,
            "shots": [{"key": "sources/hero.png"}] if shots else [],
        },
    }


def website_snapshot(*, views: bool = True) -> dict:
    return {
        "snapshot_id": "snapshot-1",
        "kind": "web",
        "digest": "a" * 64,
        "canonical_url": WEBSITE_URL,
        "citable_lines": [
            {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
        ],
        "views": [
            {
                "view_id": "hero",
                "storage_key": "sources/hero.png",
                "digest": "b" * 64,
                "width": 1440,
                "height": 900,
                "artifact_role": "view",
            }
        ]
        if views
        else [],
    }


def complete_website_brief() -> Brief:
    values = {
        "purpose": "website",
        "target_seconds": 60,
        "narrative_mode": "mission_tech",
        "narration_language": "en",
        "subtitle_languages": ["en"],
        "aspect": "16:9",
    }
    return Brief(
        **{
            slot: BriefSlot(value=value, source=BriefSlotSource.USER_STATED)
            for slot, value in values.items()
        }
    )


def website_brand_profile() -> BrandProfile:
    from app.chat.readiness import WEBSITE_BRAND_EXTRACTOR_VERSION

    return BrandProfile(
        extractor_version=WEBSITE_BRAND_EXTRACTOR_VERSION,
        source_refs=[BrandSourceRef(snapshot_id="snapshot-1", digest="a" * 64)],
        content_digest="c" * 64,
    )

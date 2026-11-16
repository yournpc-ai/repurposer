"""Publish deterministic excerpts of the accepted native-Preset evidence.

No model, capture, synthesis or render service is called. The inputs are the
existing matrix/Output MP4s; PyAV decodes exact frame windows and writes new
content-addressed H.264 excerpts. ``--publish`` copies those bytes through the
ordinary object-storage seam and writes the registry manifest consumed by Chat.
"""
from __future__ import annotations

import argparse
import asyncio
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import av

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers import storage

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "scratch/d5-native-preset-matrix"
OUTPUT = ROOT / "scratch/d5-native-text-output-2ca59717/output.mp4"
OUT = ROOT / "scratch/d5-preset-previews"
MANIFEST = ROOT / "apps/api/app/editing/preset_previews.json"

SOURCES = {
    "text": (MATRIX / "text.mp4", "4d225402-d512-4a0d-a4b5-07dda86caba3", "091be14681f4d3437d396b280c894d135469764576ef6581c9dd38738293cc28"),
    "information": (MATRIX / "information.mp4", "caf1e05a-9b0f-450b-b89d-e44cde9a65fd", "f58441e545b2ddeb4cb47336e0cc73462ec4c476ff09c0a02ef898e91f40e8ca"),
    "cards": (MATRIX / "cards.mp4", "3923f807-5ddb-48c0-972f-d83f32770001", "efb7f6d1065e78a04f9d8eef0137616131adce640954e66e2ae733dde7f814a8"),
    "aligned": (OUTPUT, None, None),
}

# preset: source, exact zero-based start frame, frame count
WINDOWS = {
    "text-reveal": ("text", 0, 120),
    "typewriter": ("text", 120, 120),
    "keyword-fill": ("text", 240, 120),
    "word-cycle": ("text", 360, 120),
    "claim-layout": ("text", 480, 120),
    "highlight-sweep": ("information", 0, 120),
    "path-underline": ("information", 120, 120),
    "callout": ("information", 240, 120),
    "flow-steps": ("information", 360, 120),
    "comparison-columns": ("information", 480, 120),
    "card-stack": ("cards", 0, 120),
    "list-reveal": ("cards", 120, 120),
    "notification-stack": ("cards", 240, 120),
    "title-lockup": ("cards", 360, 120),
    "caption-phrases": ("aligned", 0, 90),
    "text-impact": ("aligned", 60, 48),
}


def excerpt(source: Path, start: int, count: int, destination: Path) -> dict[str, Any]:
    """Decode an exact frame window and encode a silent, deterministic MP4."""
    reader = av.open(str(source), mode="r")
    writer = None
    try:
        video = reader.streams.video[0]
        fps = Fraction(video.average_rate)
        if fps <= 0:
            raise ValueError(f"{source.name} has no fixed frame rate")
        video.codec_context.skip_frame = "NONE"
        timestamp = int(start / fps / video.time_base)
        reader.seek(timestamp, stream=video, backward=True)
        buffer = destination.with_suffix(".tmp")
        writer = av.open(str(buffer), mode="w", format="mp4")
        out = writer.add_stream("libx264", rate=fps)
        out.width = video.codec_context.width
        out.height = video.codec_context.height
        out.pix_fmt = "yuv420p"
        out.options = {
            "preset": "veryfast",
            "crf": "20",
            "tune": "animation",
            "threads": "1",
        }
        encoded = 0
        for frame in reader.decode(video):
            if frame.pts is None:
                continue
            index = round(float(Fraction(frame.pts) * frame.time_base * fps))
            if index < start:
                continue
            if index >= start + count:
                break
            # A missing/corrupt source frame must not silently shorten an excerpt.
            if index != start + encoded:
                raise ValueError(f"{source.name} has a gap at source frame {start + encoded}")
            frame.pts = encoded
            for packet in out.encode(frame):
                writer.mux(packet)
            encoded += 1
            if encoded == count:
                break
        for packet in out.encode():
            writer.mux(packet)
        writer.close()
        writer = None
        if encoded != count:
            raise ValueError(f"{source.name} yielded {encoded}, expected {count} frames")
        buffer.replace(destination)
    finally:
        if writer is not None:
            writer.close()
        reader.close()
    data = destination.read_bytes()
    gcd = math.gcd(out.width, out.height)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "duration_seconds": float(Fraction(count, 1) / fps),
        "frame_count": count,
        "fps": float(fps),
        "width": out.width,
        "height": out.height,
        "aspect": f"{out.width // gcd}:{out.height // gcd}",
        "size_bytes": len(data),
    }


async def main(publish: bool) -> None:
    from app.editing.presets import PRESET_REGISTRY

    if set(WINDOWS) != set(PRESET_REGISTRY):
        raise ValueError("preview windows and PRESET_REGISTRY differ")
    OUT.mkdir(parents=True, exist_ok=True)
    items: dict[str, Any] = {}
    for preset_id, (source_name, start, count) in WINDOWS.items():
        source, version_id, version_digest = SOURCES[source_name]
        destination = OUT / f"{preset_id}.mp4"
        facts = excerpt(source, start, count, destination)
        key = f"video-presets/{preset_id}/{facts['sha256']}.mp4"
        if publish:
            await storage.save(key, destination.read_bytes(), content_type="video/mp4")
        items[preset_id] = {
            "storage_key": key,
            **facts,
            "lineage": {
                "kind": "composition_version" if version_id else "accepted_output_evidence",
                "composition_version_id": version_id,
                "content_digest": version_digest,
                "evidence_id": None if version_id else "2ca59717",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_frame_start": start,
                "source_frame_count": count,
            },
        }
        print(json.dumps({"preset_id": preset_id, **facts, "published": publish}))
    MANIFEST.write_text(
        json.dumps({"version": 1, "items": items}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.publish))

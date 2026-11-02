"""Extract hash-identified actual frames from both C4 Outputs for visual inspection."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.models.database import AsyncSessionLocal
from app.models.tables import Output
from app.providers import storage
from app.tools.video.review import _extract_frames

OUTPUTS = {
    "revision": UUID("b7b562f2-ae31-40ed-8670-6f83ffdefbbc"),
    "reuse": UUID("7468027d-e763-467f-afa4-82b74b0250a0"),
}
ROOT = Path("/Users/sylas/repurposer/scratch")


async def main() -> None:
    evidence = []
    async with AsyncSessionLocal() as db:
        for label, output_id in OUTPUTS.items():
            output = await db.get(Output, output_id)
            video = await storage.read(output.files["video"])
            frames = await _extract_frames(video, output.render_spec, [0.4, 0.8, 1.5, 3.5])
            directory = ROOT / f"c4-{label}-frames"
            directory.mkdir(exist_ok=True)
            for frame in frames:
                path = directory / f"frame-{frame.frame:03d}.jpg"
                path.write_bytes(frame.jpeg)
                assert hashlib.sha256(path.read_bytes()).hexdigest() == frame.digest
                evidence.append({
                    "output_id": str(output_id),
                    "video_sha256": hashlib.sha256(video).hexdigest(),
                    "frame": frame.frame,
                    "jpeg_sha256": frame.digest,
                    "path": str(path),
                })
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

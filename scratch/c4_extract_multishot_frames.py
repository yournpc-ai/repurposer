"""Extract actual two-shot frames with per-Output directories and hash checks."""
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
    "multishot-v1": UUID("428db9f2-4ab3-46e2-899d-437221106f0f"),
    "multishot-v2": UUID("de749105-fe48-4e5d-8b15-ffd1d2f60fcc"),
}
ROOT = Path("/Users/sylas/repurposer/scratch")


async def main() -> None:
    rows = []
    async with AsyncSessionLocal() as db:
        for label, output_id in OUTPUTS.items():
            output = await db.get(Output, output_id)
            video = await storage.read(output.files["video"])
            frames = await _extract_frames(video, output.render_spec, [3.5, 4.4, 5.8, 7.2])
            directory = ROOT / f"c4-{label}-frames"
            directory.mkdir(exist_ok=True)
            for frame in frames:
                path = directory / f"frame-{frame.frame:03d}.jpg"
                path.write_bytes(frame.jpeg)
                assert hashlib.sha256(path.read_bytes()).hexdigest() == frame.digest
                rows.append({"output_id": str(output_id), "frame": frame.frame, "path": str(path)})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

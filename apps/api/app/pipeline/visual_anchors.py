"""Visual anchors — deterministic vision for IMAGE assets (产物质量线 期 1).

The deterministic half of the beat map's visual channel (简报 §2.2): faces,
a subject box (largest face), and a safe area (face union × 1.5, clamped) —
all normalized 0–1 ``[x, y, w, h]`` against the source pixels, so the stills
editor (期 2) can place motion/crops without re-running vision. The LLM's
semantic half (what/whom the image shows, which arguments it backs) lives on
``MaterialUnderstanding.visual_anchors`` and joins by ``asset_id`` — the two
halves are separate fields by design (the 语义/声学 split's visual twin).

Family shape = prosody / speaker_map (PROCESSORS chain): downloads the
media, CPU-bound detection in a thread, degrade-on-error — an anchors
failure must never fail the asset. Reuses the vendored YuNet engine
(``app/providers/vision.py``, ADR-045's reframe/speaker_map provider).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

VISUAL_ANCHORS_VERSION = 1

_DET_LONG_SIDE = 640  # detection space cap (YuNet input), aspect kept
_SAFE_AREA_PAD = 0.5  # face union expanded by this fraction on each side


def build_visual_anchors(path: Path) -> dict[str, Any] | None:
    """Local image file → the visual_anchors block (CPU-bound, sync)."""
    import cv2  # lazy: heavy
    import numpy as np

    from app.providers.vision import detect_faces

    buf = np.frombuffer(path.read_bytes(), np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return None
    height, width = frame.shape[:2]
    scale = _DET_LONG_SIDE / max(width, height)
    det_size = (
        max(32, int(width * scale)),
        max(32, int(height * scale)),
    )
    faces = detect_faces(frame, det_size, score_threshold=0.6)

    def norm(box: tuple[float, float, float, float]) -> list[float]:
        x, y, w, h = box
        return [round(x / width, 4), round(y / height, 4), round(w / width, 4), round(h / height, 4)]

    face_boxes = [norm(f.bbox) for f in faces]
    subject_box = None
    safe_area = None
    if faces:
        biggest = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        subject_box = norm(biggest.bbox)
        x0 = min(f.bbox[0] for f in faces)
        y0 = min(f.bbox[1] for f in faces)
        x1 = max(f.bbox[0] + f.bbox[2] for f in faces)
        y1 = max(f.bbox[1] + f.bbox[3] for f in faces)
        fw, fh = x1 - x0, y1 - y0
        pad_x, pad_y = fw * _SAFE_AREA_PAD, fh * _SAFE_AREA_PAD
        sx0 = max(0.0, x0 - pad_x)
        sy0 = max(0.0, y0 - pad_y)
        sx1 = min(float(width), x1 + pad_x)
        sy1 = min(float(height), y1 + pad_y)
        safe_area = norm((sx0, sy0, sx1 - sx0, sy1 - sy0))

    return {
        "version": VISUAL_ANCHORS_VERSION,
        "width": width,
        "height": height,
        "faces": face_boxes,
        # None = no face constraint (full frame is implicitly safe).
        "subject_box": subject_box,
        "safe_area": safe_area,
    }


async def visual_anchors_processor(asset, prior) -> "Any":
    """IMAGE's visual-anchors processor; degrade-on-error (prosody precedent)."""
    from app.pipeline.asset_processing import ProcessResult  # avoid cycle at import time
    from app.providers.storage import download_to_temp

    if not asset.file_url:
        return ProcessResult()
    path = await download_to_temp(asset.file_url)
    if path is None:
        return ProcessResult()
    try:
        anchors = await asyncio.to_thread(build_visual_anchors, path)
        if anchors is None:
            return ProcessResult()
        logger.info(
            "visual_anchors_built",
            asset_id=str(asset.id),
            faces=len(anchors["faces"]),
        )
        return ProcessResult(meta={"visual_anchors": anchors})
    except Exception as e:  # noqa: BLE001 — degrade to no anchors, keep the asset
        logger.error("visual_anchors_failed", asset_id=str(asset.id), error=str(e))
        return ProcessResult()
    finally:
        path.unlink(missing_ok=True)


def _selftest() -> None:
    """A blank image must yield an empty, well-formed block (no crash)."""
    import tempfile

    import numpy as np

    import cv2

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        cv2.imwrite(fh.name, blank)
        out = build_visual_anchors(Path(fh.name))
    assert out is not None and out["faces"] == [] and out["subject_box"] is None
    assert out["width"] == 640 and out["height"] == 480
    print("visual_anchors selftest OK")


if __name__ == "__main__":
    _selftest()

"""Face detection via YuNet (OpenCV ``FaceDetectorYN`` — self-hosted, offline).

Vendored weights: ``weights/face_detection_yunet_2026may.onnx`` (MIT, Shiqi Yu /
opencv_zoo; LICENSE sits beside the file). The 2026may export is the same
weights as the 2023mar line (WIDER Hard 0.7503 — the strongest YuNet line) in a
dynamic-input wrapper, which is the form OpenCV 5.x consumes; int8 variants are
banned (accuracy drop + a 5.x total-miss bug). Loaded lazily and cached per
worker process (asr.py precedent).

Privacy boundary (ADR-045): position and motion only — no identification, no
network. Detection runs in a downscaled DETECTION space purely to find boxes;
all returned coordinates are scaled back to full-resolution source pixels.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

_WEIGHTS = Path(__file__).parent / "weights" / "face_detection_yunet_2026may.onnx"

_detector: Any = None
_detector_input: tuple[int, int] | None = None


def _get_detector(input_size: tuple[int, int]) -> Any:
    """Lazily load and cache the YuNet detector for this process.

    One instance per process; ``setInputSize`` re-targets the detection space
    when the caller's tier changes (interview 640-wide / stage 720p–1080p).
    """
    global _detector, _detector_input
    if _detector is None:
        import cv2  # lazy: heavy import

        logger.info("yunet_loading", weights=str(_WEIGHTS))
        _detector = cv2.FaceDetectorYN.create(str(_WEIGHTS), "", input_size)
        _detector_input = input_size
    elif _detector_input != input_size:
        _detector.setInputSize(input_size)
        _detector_input = input_size
    return _detector


@dataclass
class FaceDetection:
    """One detected face, all coordinates in FULL-RESOLUTION source pixels.

    Landmarks follow YuNet's order: [right eye, left eye, nose tip, right mouth
    corner, left mouth corner] (subject's right/left — mirrored on screen).
    """

    bbox: tuple[float, float, float, float]  # x, y, w, h
    landmarks: np.ndarray  # shape (5, 2)
    score: float

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return (x + w / 2, y + h / 2)

    def mouth_roi(self, pad: float = 0.6) -> tuple[int, int, int, int]:
        """Mouth region of interest ``(x, y, w, h)`` clamped to nothing (caller
        clamps to frame bounds): the mouth-corners box expanded by ``pad`` on
        each side, anchored to the lower face."""
        mx = self.landmarks[3:5, 0]
        my = self.landmarks[3:5, 1]
        x0, x1 = float(mx.min()), float(mx.max())
        y0, y1 = float(my.min()), float(my.max())
        w = max(x1 - x0, 1.0)
        h = max(y1 - y0, 1.0)
        # Mouth corners are nearly colinear — give the box real height from the
        # face scale so lips sit inside while speaking.
        face_h = self.bbox[3]
        h = max(h, face_h * 0.18)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = w * (1 + 2 * pad), h * (1 + 2 * pad)
        return (int(cx - w / 2), int(cy - h / 2), int(w), int(h))


def detect_faces(
    frame_bgr: np.ndarray,
    input_size: tuple[int, int],
    score_threshold: float = 0.6,
) -> list[FaceDetection]:
    """Detect faces in a BGR frame. ``input_size`` is the DETECTION space
    (w, h) — the frame is downscaled to it for inference and every returned
    coordinate is mapped back to the frame's own pixel space.
    """
    import cv2  # lazy: heavy import

    det_w, det_h = input_size
    src_h, src_w = frame_bgr.shape[:2]
    detector = _get_detector((det_w, det_h))
    detector.setScoreThreshold(score_threshold)

    small = (
        frame_bgr
        if (src_w, src_h) == (det_w, det_h)
        else cv2.resize(frame_bgr, (det_w, det_h), interpolation=cv2.INTER_AREA)
    )
    _, faces = detector.detect(small)
    if faces is None:
        return []

    sx, sy = src_w / det_w, src_h / det_h
    out: list[FaceDetection] = []
    for f in faces:
        x, y, w, h = f[0] * sx, f[1] * sy, f[2] * sx, f[3] * sy
        landmarks = f[4:14].reshape(5, 2) * np.array([sx, sy])
        out.append(
            FaceDetection(
                bbox=(float(x), float(y), float(w), float(h)),
                landmarks=landmarks.astype(float),
                score=float(f[14]),
            )
        )
    out.sort(key=lambda d: d.bbox[0])  # stable left-to-right screen order
    return out

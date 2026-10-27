"""Decode and inspect the local Phase-A website/MG sample renders.

Usage: uv run python scripts/inspect_video_project_samples.py \
  --root /tmp/repurposer-video-project-a2

Checks are media evidence, not LLM/OCR judgments: every video frame is decoded;
caption backgrounds must appear in their exact compiled windows; motion and
TextPart checks use pixel regions/bounds; audio is decoded and correlated with
source time zero while allowing signed AAC encoder delay. Keyframes/contact
sheets are emitted for human visual review. No listening claim is made.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import av
import numpy as np
from av.audio.resampler import AudioResampler
from PIL import Image, ImageDraw

FIXTURE_MEDIA = Path(__file__).resolve().parents[1] / "tests/fixtures/video_project/media"
WEBSITE_FRAMES = sorted(
    {
        0,
        9,
        15,
        30,
        59,
        60,
        90,
        119,
        120,
        129,
        150,
        179,
        180,
        195,
        210,
        239,
        240,
        249,
        270,
        300,
        330,
        359,
    }
)
MG_FRAMES = sorted(
    {
        0,
        3,
        6,
        9,
        15,
        27,
        60,
        89,
        90,
        99,
        104,
        108,
        122,
        150,
        179,
        180,
        184,
        188,
        192,
        196,
        200,
        204,
        207,
        213,
        216,
        225,
        240,
        252,
        269,
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


def _rgb(hex_color: str) -> np.ndarray:
    return np.array([int(hex_color[index : index + 2], 16) for index in (1, 3, 5)])


def _bbox(frame: np.ndarray, background: np.ndarray) -> list[int] | None:
    mask = np.max(np.abs(frame.astype(np.int16) - background), axis=2) > 40
    ys, xs = np.where(mask)
    if len(xs) < 20:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _size(box: list[int] | None) -> list[int]:
    _require(box is not None, "expected visible text bounds")
    return [box[2] - box[0], box[3] - box[1]]


def _runs(active: list[bool]) -> list[list[int]]:
    result = []
    start = None
    for index, value in enumerate([*active, False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            result.append([start, index])
            start = None
    return result


def _contact(
    frames: dict[int, np.ndarray],
    indices: list[int],
    path: Path,
    columns: int,
    size: tuple[int, int],
    labels: dict[int, str] | None = None,
) -> None:
    rows = (len(indices) + columns - 1) // columns
    label_height = 28
    sheet = Image.new("RGB", (columns * size[0], rows * (size[1] + label_height)), "#111111")
    draw = ImageDraw.Draw(sheet)
    for index, frame_index in enumerate(indices):
        x = (index % columns) * size[0]
        y = (index // columns) * (size[1] + label_height)
        image = Image.fromarray(frames[frame_index]).resize(size, Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y + label_height))
        label = (
            labels[frame_index]
            if labels is not None
            else f"frame {frame_index} / {frame_index / 30:.3f}s"
        )
        draw.text((x + 8, y + 7), label, fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def _decode_video(
    path: Path, spec: dict, sample_id: str, version: str, out_dir: Path
) -> dict[str, Any]:
    selected = set(WEBSITE_FRAMES if sample_id == "website" else MG_FRAMES)
    frames: dict[int, np.ndarray] = {}
    caption_active: list[bool] = []
    caption_clip = None
    if sample_id == "website":
        caption_track = next(track for track in spec["tracks"] if track["role"] == "caption")
        caption_clip = caption_track["clips"][0]
        _require(
            caption_clip["object"]["style"]["background"] is not None, "caption background missing"
        )

    container = av.open(str(path))
    stream = container.streams.video[0]
    previous_time = float("-inf")
    count = 0
    try:
        for frame in container.decode(stream):
            if frame.time is not None:
                _require(float(frame.time) >= previous_time, f"non-monotonic video PTS in {path}")
                previous_time = float(frame.time)
            array = frame.to_ndarray(format="rgb24")
            _require(
                array.shape == (spec["height"], spec["width"], 3),
                f"unexpected frame shape in {path}",
            )
            if count in selected:
                frames[count] = array.copy()
            if caption_clip is not None:
                obj = caption_clip["object"]
                box = obj["layout"]
                x, y = int(box["x"]) + 4, int(box["y"]) + 4
                width, height = int(box["width"]) - 8, int(box["height"]) - 8
                region = array[y : y + height, x : x + width]
                expected = _rgb(obj["style"]["background"])
                close = np.max(np.abs(region.astype(np.int16) - expected), axis=2) <= 18
                caption_active.append(bool(np.mean(close) > 0.5))
            count += 1
    finally:
        container.close()
    _require(
        count == spec["duration_frames"],
        f"{path}: decoded {count}, expected {spec['duration_frames']} frames",
    )
    _require(set(frames) == selected, f"{path}: missing selected frames")

    key_frames = [330] if sample_id == "website" else [60, 216, 240]
    for index in key_frames:
        Image.fromarray(frames[index]).save(out_dir / f"{version}.frame-{index:04d}.png")

    if sample_id == "website":
        groups = [[0, 30, 60, 90, 120, 150], [180, 210, 240, 270, 300, 330]]
        for number, indices in enumerate(groups, 1):
            _contact(frames, indices, out_dir / f"{version}.contact-{number}.png", 2, (640, 360))
        caption_track = next(track for track in spec["tracks"] if track["role"] == "caption")
        expected = [False] * count
        for clip in caption_track["clips"]:
            for index in range(clip["start_frame"], clip["end_frame"]):
                expected[index] = True
        measured_runs = _runs(caption_active)
        expected_runs = _runs(expected)
        _require(
            measured_runs == expected_runs, f"caption windows {measured_runs} != {expected_runs}"
        )
        center = (slice(110, 600), slice(0, 1280))
        title = (slice(36, 104), slice(40, 470))
        camera_mae = _mae(frames[30][center], frames[90][center])
        scene_mae = [
            _mae(frames[a][center], frames[b][center]) for a, b in [(119, 120), (239, 240)]
        ]
        chapter_mae = [
            _mae(frames[a][title], frames[b][title]) for a, b in [(119, 120), (239, 240)]
        ]
        _require(camera_mae > 0.2, "web camera did not move within one source view")
        _require(min(scene_mae) > 2, "web source views did not change at scene boundaries")
        _require(min(chapter_mae) > 1, "chapter text did not change at scene boundaries")
        return {
            "frames": frames,
            "report": {
                "frames_decoded": count,
                "caption_runs": measured_runs,
                "camera_center_mae": camera_mae,
                "scene_boundary_center_mae": scene_mae,
                "chapter_boundary_mae": chapter_mae,
            },
        }

    groups = [
        ("whole", [0, 6, 15, 27, 60, 89]),
        ("lines", [90, 99, 104, 108, 122, 150]),
        ("graphemes", [180, 184, 188, 196, 207, 213]),
        ("scale", [180, 207, 216, 225, 240, 252, 269]),
    ]
    for name, indices in groups:
        _contact(frames, indices, out_dir / f"{version}.{name}.png", 3, (480, 270))
    background = _rgb(spec["background"])
    bounds = {index: _bbox(frame, background) for index, frame in frames.items()}
    counts = {
        index: int(
            np.count_nonzero(np.max(np.abs(frame.astype(np.int16) - background), axis=2) > 40)
        )
        for index, frame in frames.items()
    }
    _require(counts[0] < 20 and counts[15] > 1000, "whole-text entrance is not visible")

    def region_count(index: int, start: int, end: int) -> int:
        region = frames[index][start:end].astype(np.int16)
        return int(np.count_nonzero(np.max(np.abs(region - background), axis=2) > 40))

    def top(index: int) -> int:
        return region_count(index, 220, 315)

    def bottom(index: int) -> int:
        return region_count(index, 315, 415)

    _require(counts[90] < 20, "line scene should start invisible")
    _require(top(99) > 100 and bottom(99) < top(99) * 0.1, "first line did not lead the stagger")
    _require(
        bottom(108) > 50 and top(122) > 1000 and bottom(122) > 1000, "second line did not follow"
    )
    _require(
        counts[180] < 20 and counts[184] > 20, "grapheme scene did not start from invisible parts"
    )
    _require(
        counts[200] > counts[184] and counts[213] > counts[200],
        "grapheme entrances did not accumulate",
    )
    hold = [_size(bounds[216]), _size(bounds[225])]
    settled = [_size(bounds[252]), _size(bounds[269])]
    middle = _size(bounds[240])
    _require(max(abs(a - b) for a, b in zip(hold[0], hold[1])) <= 1, "scale hold bounds drifted")
    _require(max(abs(a - b) for a, b in zip(settled[0], settled[1])) <= 1, "settled bounds drifted")
    _require(
        hold[0][0] > middle[0] > settled[0][0],
        "multi-keyframe scale did not shrink through its middle keyframe",
    )
    _require(
        hold[0][1] > middle[1] >= settled[0][1], "multi-keyframe vertical scale did not settle"
    )
    return {
        "frames": frames,
        "report": {
            "frames_decoded": count,
            "selected_nonbackground_counts": counts,
            "scale_bounds": {str(index): bounds[index] for index in [216, 225, 240, 252, 269]},
            "scale_hold_mae": _mae(frames[216], frames[225]),
            "scale_settled_mae": _mae(frames[252], frames[269]),
            "line_stagger_counts": {
                str(index): [top(index), bottom(index)] for index in [90, 99, 108, 122]
            },
        },
    }


def _audio(path: Path) -> tuple[dict[str, Any], np.ndarray | None]:
    container = av.open(str(path))
    if not container.streams.audio:
        container.close()
        return {"present": False}, None
    stream = container.streams.audio[0]
    info = {
        "present": True,
        "codec": stream.codec_context.name,
        "sample_rate": int(stream.rate),
        "channels": int(stream.channels),
    }
    resampler = AudioResampler(format="fltp", layout="stereo", rate=48000)
    chunks = []
    try:
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                chunks.append(converted.to_ndarray())
        for converted in resampler.resample(None):
            chunks.append(converted.to_ndarray())
    finally:
        container.close()
    samples = np.concatenate(chunks, axis=1)
    info.update(
        {
            "decoded_duration_seconds": samples.shape[1] / 48000,
            "rms": float(np.sqrt(np.mean(samples**2))),
            "peak": float(np.max(np.abs(samples))),
            "clipped_samples": int(np.count_nonzero(np.abs(samples) >= 0.999)),
        }
    )
    return info, samples


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denominator) if denominator else 0.0


def _source_alignment(source: np.ndarray, output: np.ndarray) -> dict[str, Any]:
    # 3 kHz low-pass/decimated mono waveform. lag = source index - output index;
    # negative lags cover the encoder delay instead of inventing a source trim.
    def decimate(samples: np.ndarray) -> np.ndarray:
        mono = samples.mean(axis=0)
        length = len(mono) // 16 * 16
        return mono[:length].reshape(-1, 16).mean(axis=1)

    source_3k = decimate(source)
    output_3k = decimate(output)
    length = 8 * 3000
    candidates = []
    for offset_seconds in [0, 1, 2, 3]:
        best = (-1.0, None)
        center = offset_seconds * 3000
        for lag in range(-300, 1):
            source_index = center + max(0, lag)
            output_index = max(0, -lag)
            if source_index + length > len(source_3k) or output_index + length > len(output_3k):
                continue
            value = _correlation(
                output_3k[output_index : output_index + length],
                source_3k[source_index : source_index + length],
            )
            if value > best[0]:
                best = (value, lag)
        candidates.append(
            {
                "source_offset_seconds": offset_seconds,
                "correlation": best[0],
                "encoder_delay_seconds": None if best[1] is None else -best[1] / 3000,
            }
        )
    winner = max(candidates, key=lambda item: item["correlation"])
    _require(
        winner["source_offset_seconds"] == 0,
        f"audio does not best match source time zero: {candidates}",
    )
    _require(winner["correlation"] > 0.98, f"source-zero audio correlation is too weak: {winner}")
    return {"winner": winner, "candidates": candidates}


def _inspect_sample(root: Path, sample_id: str) -> dict[str, Any]:
    directory = root / sample_id
    spec = json.loads((directory / "base.video-spec.json").read_text())
    decoded = {}
    audio = {}
    audio_samples = {}
    for version in ["base", "edited"]:
        decoded[version] = _decode_video(
            directory / f"{version}.mp4", spec, sample_id, version, directory
        )
        audio[version], audio_samples[version] = _audio(directory / f"{version}.mp4")
        if sample_id == "website":
            _require(audio[version]["present"], f"{sample_id}/{version} has no music stream")
            _require(
                audio[version]["sample_rate"] == 48000 and audio[version]["channels"] == 2,
                "music format drifted",
            )
            _require(
                abs(audio[version]["decoded_duration_seconds"] - 12) < 0.1, "music duration drifted"
            )
            _require(
                audio[version]["rms"] > 0.005 and audio[version]["clipped_samples"] == 0,
                "music is silent or clipped",
            )
            audio[version]["source_alignment"] = _source_alignment(
                _audio(FIXTURE_MEDIA / "music-corporate-16s.wav")[1], audio_samples[version]
            )
        elif audio[version]["present"]:
            # Remotion emits a silent stereo track even without audio clips.
            _require(
                audio[version]["sample_rate"] == 48000
                and audio[version]["channels"] == 2
                and abs(audio[version]["decoded_duration_seconds"] - 9) < 0.1
                and audio[version]["rms"] == 0
                and audio[version]["clipped_samples"] == 0,
                "MG's audio stream is not the expected bounded silent track",
            )

    base_frames = decoded["base"]["frames"]
    edited_frames = decoded["edited"]["frames"]
    target_frame = 330 if sample_id == "website" else 60
    if sample_id == "website":
        target_region = (slice(620, 692), slice(100, 1180))
    else:
        target_region = (slice(180, 480), slice(90, 1190))
    edit_mae = _mae(
        base_frames[target_frame][target_region], edited_frames[target_frame][target_region]
    )
    _require(edit_mae > 1, "edited target is not visibly changed")
    _contact(
        {0: base_frames[target_frame], 1: edited_frames[target_frame]},
        [0, 1],
        directory / "edit-comparison.png",
        2,
        (640, 360),
        {0: f"base / frame {target_frame}", 1: f"edited / frame {target_frame}"},
    )
    if sample_id == "website":
        unchanged_mae = _mae(base_frames[330][110:600], edited_frames[330][110:600])
    else:
        unchanged_mae = max(
            _mae(base_frames[150], edited_frames[150]), _mae(base_frames[240], edited_frames[240])
        )
        _require(unchanged_mae < 1, "unedited MG scenes changed visually")
    if audio_samples["base"] is not None:
        _require(
            np.array_equal(audio_samples["base"], audio_samples["edited"]),
            "audio samples changed after the text-only edit",
        )
    return {
        "sample_id": sample_id,
        "base": {**decoded["base"]["report"], "audio": audio["base"]},
        "edited": {**decoded["edited"]["report"], "audio": audio["edited"]},
        "edit_visual_mae": edit_mae,
        "unrelated_visual_mae": unchanged_mae,
        "audio_samples_identical_after_edit": bool(
            audio_samples["base"] is not None
            and np.array_equal(audio_samples["base"], audio_samples["edited"])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/tmp/repurposer-video-project-a2"))
    args = parser.parse_args()
    reports = [_inspect_sample(args.root, sample_id) for sample_id in ["website", "mg"]]
    for report in reports:
        path = args.root / report["sample_id"] / "verification.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(path)
    print(
        "decoded media checks passed; review the emitted contact sheets for text/content inspection"
    )


if __name__ == "__main__":
    main()

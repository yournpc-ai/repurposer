"""Rendered-artifact probe gate (MG D4 — 放行闸③ / 禁止事项 10).

渲染成功态 = 文件存在 + 大小非零 + probe 可读（时长/分辨率/流合法）。一座
闸门、家族分派检查项（ADR-028 同律——永不开第二座校验门）：每个路由到渲
染器的 output 在落 COMPLETED 之前必须过 ``probe_rendered_video``；未过 =
不算成功，渲染链落 FAILED 并把 ``spec.failure={stage:"probe", codes,
detail}`` 盖在 render 镜像节点上（与 storyboard 的 schema/grounding 阶段同
构——失败分类台账只读一个字段）。

纯核只认本地路径（``probe_rendered_video(path, expect)``）——测试用 PyAV
现编的小 fixture，永不真渲染。下载/清理半边住 ``rendering.py``（probe 的
临时副本即清，成功失败都清——被拒的产物本体留在对象存储作取证，临时副本
无保留价值）。

家族分派（``probe_expectation_for`` 只读 spec 自身字段）：
- film：h264 + 1920×1080 + 实际时长 = Σ场景帧（流帧计数 ±1 帧）+ 首帧可解码。
- clip（family 缺省）：存在 + 非零 + 容器可读 + 有视频流 + 首帧可解码——
  clip 的时长/分辨率语义跨段拼接，不在本闸断言；caption sidecar 存在即法，
  非零当且仅当 caption_track 非空（空轨的零字节 srt 是合法产物）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Film render constants mirrored from apps/render/src/film/Root.tsx
# (FILM_DIMENSIONS/FILM_FPS — one law, mirrored where consumed;
# app/tools/film/storyboard.py carries the allocator's FILM_FPS mirror).
# The canvas dimensions key on the spec's ``aspect`` (ADR-120 E3).
FILM_DIMENSIONS = {"16:9": (1920, 1080), "1:1": (1080, 1080), "9:16": (1080, 1920)}
FILM_FPS = 30
FILM_CODEC = "h264"

# Probe failure codes (spec.failure.codes — the stage ledger reads these).
PROBE_OUTPUT_MISSING = "PROBE_OUTPUT_MISSING"  # object absent / zero bytes
PROBE_UNREADABLE = "PROBE_UNREADABLE"  # container unreadable / no video stream / frame 0 won't decode
PROBE_CODEC_MISMATCH = "PROBE_CODEC_MISMATCH"
PROBE_RESOLUTION_MISMATCH = "PROBE_RESOLUTION_MISMATCH"
PROBE_DURATION_MISMATCH = "PROBE_DURATION_MISMATCH"


@dataclass(frozen=True)
class ProbeViolation:
    code: str
    detail: str


@dataclass(frozen=True)
class ProbeExpectation:
    """Family-dispatched check items. ``None`` = not asserted for this family.
    Duration is judged on the VIDEO STREAM's frame count vs the allocated
    frames (±1 frame): the mp4 CONTAINER duration carries muxer padding
    (observed +52ms on a 465-frame render whose stream was exact), so it is
    never the contract surface."""

    codec: str | None = None
    width: int | None = None
    height: int | None = None
    frames: int | None = None
    fps: float = FILM_FPS


def probe_expectation_for(spec: dict[str, Any]) -> ProbeExpectation:
    """Dispatch reads only ``spec.family`` (never node type/name). The film
    expectation's frame count IS Σ scene frames off the spec — the renderer
    only sums, so that sum is the contract duration."""
    if spec.get("family") != "film":
        return ProbeExpectation()
    frames = 0
    for scene in spec.get("scenes") or []:
        try:
            frames += int(scene.get("frames") or 0)
        except (TypeError, ValueError):
            # A malformed spec was the render service's 400 seat; the probe
            # gate's job is the artifact — degrade the duration check rather
            # than invent a second schema court here.
            frames = 0
            break
    width, height = FILM_DIMENSIONS.get(spec.get("aspect") or "16:9", FILM_DIMENSIONS["16:9"])
    return ProbeExpectation(
        codec=FILM_CODEC,
        width=width,
        height=height,
        frames=frames or None,
        fps=FILM_FPS,
    )


def probe_rendered_video(
    path: Path | None, expect: ProbeExpectation
) -> list[ProbeViolation]:
    """Probe one rendered video object (local copy). Empty list = the artifact
    may settle COMPLETED. Any violation = the render is NOT a success."""
    if path is None or not path.exists():
        return [ProbeViolation(PROBE_OUTPUT_MISSING, "rendered object absent from storage")]
    size = path.stat().st_size
    if size == 0:
        return [ProbeViolation(PROBE_OUTPUT_MISSING, "rendered object is zero bytes")]

    import av  # lazy — the repo's ffmpeg discipline (no system binary assumed)

    try:
        container = av.open(str(path))
    except Exception as e:  # noqa: BLE001 — any av failure = unreadable
        return [ProbeViolation(PROBE_UNREADABLE, f"container unreadable: {type(e).__name__}: {e}")]

    violations: list[ProbeViolation] = []
    with container:
        videos = [s for s in container.streams if s.type == "video"]
        if not videos:
            return [ProbeViolation(PROBE_UNREADABLE, "no video stream in container")]
        stream = videos[0]
        ctx = stream.codec_context

        if expect.codec is not None and ctx.name != expect.codec:
            violations.append(
                ProbeViolation(
                    PROBE_CODEC_MISMATCH,
                    f"codec {ctx.name!r} ≠ expected {expect.codec!r}",
                )
            )
        if expect.width is not None and (ctx.width, ctx.height) != (
            expect.width,
            expect.height,
        ):
            violations.append(
                ProbeViolation(
                    PROBE_RESOLUTION_MISMATCH,
                    f"{ctx.width}×{ctx.height} ≠ expected {expect.width}×{expect.height}",
                )
            )

        # 流合法: metadata alone doesn't prove the stream reads — decode the
        # first frame (catches truncated/corrupt payloads cheaply).
        try:
            for _ in container.decode(video=0):
                break
        except Exception as e:  # noqa: BLE001
            violations.append(
                ProbeViolation(
                    PROBE_UNREADABLE,
                    f"first frame won't decode: {type(e).__name__}: {e}",
                )
            )

        if expect.frames is not None:
            # Frame-count truth (stream metadata; fallback = stream duration
            # × rate). The container duration is NEVER consulted — see the
            # ProbeExpectation docstring.
            n = int(stream.frames or 0)
            if n <= 0 and stream.duration is not None:
                n = round(float(stream.duration * stream.time_base) * expect.fps)
            if n <= 0:
                violations.append(
                    ProbeViolation(PROBE_UNREADABLE, "frame count unavailable")
                )
            elif abs(n - expect.frames) > 1:
                violations.append(
                    ProbeViolation(
                        PROBE_DURATION_MISMATCH,
                        f"frame count {n} ≠ allocated {expect.frames} (±1 frame)",
                    )
                )
            rate = float(stream.average_rate or 0)
            if rate and abs(rate - expect.fps) > 0.01:
                violations.append(
                    ProbeViolation(
                        PROBE_DURATION_MISMATCH,
                        f"fps {rate:g} ≠ expected {expect.fps:g}",
                    )
                )
    return violations


def probe_rendered_sidecar(path: Path | None, *, allow_empty: bool) -> list[ProbeViolation]:
    """The caption sidecar's gate (clip family). EXISTENCE is the law; the
    non-empty bar applies iff the spec's caption track carries cues — the
    render service writes ``captionTrackToSrt([]) == ""``, so a zero-byte srt
    is a VALID artifact for a captionless clip and must never fail the gate
    (a non-empty track that produced an empty/missing sidecar is the broken
    delivery this gate exists to catch). Content shape is the render
    service's contract, not re-judged here."""
    if path is None or not path.exists():
        return [ProbeViolation(PROBE_OUTPUT_MISSING, "rendered sidecar absent from storage")]
    if not allow_empty and path.stat().st_size == 0:
        return [
            ProbeViolation(
                PROBE_OUTPUT_MISSING,
                "rendered sidecar is zero bytes despite a non-empty caption track",
            )
        ]
    return []

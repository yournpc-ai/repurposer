"""Controlled drawing-v1 previews and fixed Generator media.

The Agent authors source in a CompositionVersion. This tools-layer producer
executes it without business capabilities, stores immutable MP4/PNG bytes and
reuses them only for the exact program digest. Compilation never sees code.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal

import av
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.editing.schemas import Clip, CompositionContent, GeneratorObject, ProgramOutput
from app.providers import storage
from app.tools.video.preparation import store_source_bytes

_RUNNER = Path(__file__).with_name("program_runner.mjs")
_MANIFEST_PREFIX = "video-generators"
_MAX_COMMANDS = 512
_MAX_STDOUT = 64 * 1024 * 1024

_Number = Annotated[float, Field(allow_inf_nan=False, ge=-1_000_000, le=1_000_000)]
_Positive = Annotated[float, Field(allow_inf_nan=False, gt=0, le=1_000_000)]
_Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class RectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["rect"]
    x: _Number
    y: _Number
    width: _Positive
    height: _Positive
    fill: _Color
    opacity: float = Field(default=1.0, ge=0, le=1)


class EllipseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ellipse"]
    x: _Number
    y: _Number
    width: _Positive
    height: _Positive
    fill: _Color
    stroke: _Color | None = None
    stroke_width: float = Field(default=0.0, ge=0, le=1000)
    opacity: float = Field(default=1.0, ge=0, le=1)


class PolygonCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["polygon"]
    points: list[tuple[_Number, _Number]] = Field(min_length=3, max_length=128)
    fill: _Color
    stroke: _Color | None = None
    stroke_width: float = Field(default=0.0, ge=0, le=1000)
    opacity: float = Field(default=1.0, ge=0, le=1)


class LineCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["line"]
    points: list[tuple[_Number, _Number]] = Field(min_length=2, max_length=128)
    stroke: _Color
    stroke_width: _Positive
    opacity: float = Field(default=1.0, ge=0, le=1)


DrawCommand = Annotated[
    RectCommand | EllipseCommand | PolygonCommand | LineCommand,
    Field(discriminator="kind"),
]
_COMMANDS = TypeAdapter(list[DrawCommand])


class ProgramError(ValueError):
    """A bounded execution/validation diagnostic safe to return to Chat."""


def validate_drawing_commands(value: Any) -> list[DrawCommand]:
    try:
        commands = _COMMANDS.validate_python(value)
    except ValidationError as exc:
        raise ProgramError(f"invalid drawing commands: {exc}") from exc
    if len(commands) > _MAX_COMMANDS:
        raise ProgramError(f"frame has {len(commands)} commands; cap is {_MAX_COMMANDS}")
    return commands


async def _execute_program(obj: GeneratorObject) -> list[list[DrawCommand]]:
    node = shutil.which("node")
    if node is None:
        raise ProgramError("drawing-v1 requires the Node.js runtime")
    request = json.dumps(
        {
            "code": obj.code,
            "parameters": obj.parameters,
            "output": obj.output.model_dump(mode="json"),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    timeout = min(60.0, max(10.0, obj.output.duration_frames * 0.25 + 5))
    with tempfile.TemporaryDirectory(prefix="drawing-v1-") as workdir:
        process = await asyncio.create_subprocess_exec(
            node,
            "--experimental-permission",
            f"--allow-fs-read={_RUNNER}",
            "--max-old-space-size=64",
            str(_RUNNER),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env={"PATH": os.environ.get("PATH", ""), "NODE_NO_WARNINGS": "1"},
            limit=1024 * 1024,
        )
        stdin = process.stdin
        stdout_pipe = process.stdout
        stderr_pipe = process.stderr
        assert stdin is not None
        assert stdout_pipe is not None
        assert stderr_pipe is not None

        async def write_request() -> None:
            try:
                stdin.write(request)
                await stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass  # A failed process reports its real diagnostic through stderr.
            finally:
                stdin.close()

        async def read_stdout() -> bytes:
            chunks: list[bytes] = []
            total = 0
            while chunk := await stdout_pipe.read(64 * 1024):
                total += len(chunk)
                if total > _MAX_STDOUT:
                    raise ProgramError("visual program exceeded its command-output budget")
                chunks.append(chunk)
            return b"".join(chunks)

        async def read_stderr() -> bytes:
            # Drain without retaining unbounded diagnostics; only the tail is returned.
            tail = bytearray()
            while chunk := await stderr_pipe.read(64 * 1024):
                tail.extend(chunk)
                if len(tail) > 4000:
                    del tail[:-4000]
            return bytes(tail)

        tasks = [
            asyncio.create_task(write_request()),
            asyncio.create_task(read_stdout()),
            asyncio.create_task(read_stderr()),
            asyncio.create_task(process.wait()),
        ]
        group = asyncio.gather(*tasks)
        try:
            _, stdout, stderr, _ = await asyncio.wait_for(group, timeout=timeout)
        except TimeoutError:
            raise ProgramError(
                f"visual program exceeded its {timeout:g}s execution budget"
            ) from None
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if not group.done():
                group.cancel()
            await asyncio.gather(group, return_exceptions=True)
            await process.wait()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[-4000:]
        raise ProgramError(f"visual program failed: {detail or 'unknown runtime error'}")
    rows: dict[int, list[DrawCommand]] = {}
    try:
        for line in stdout.splitlines():
            payload = json.loads(line)
            rows[int(payload["frame"])] = validate_drawing_commands(payload["commands"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProgramError(f"visual program returned malformed output: {exc}") from exc
    if set(rows) != set(range(obj.output.duration_frames)):
        raise ProgramError("visual program did not return exactly one command list per frame")
    return [rows[index] for index in range(obj.output.duration_frames)]


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _paint(color: str | None, opacity: float) -> tuple[int, int, int, int] | None:
    return None if color is None else (*_rgb(color), round(opacity * 255))


def rasterize_program_frame(commands: list[DrawCommand], output: ProgramOutput) -> Image.Image:
    """Paint only validated JSON primitives; no SVG/HTML/external resources."""
    image = Image.new("RGB", (output.width, output.height), _rgb(output.background))
    draw = ImageDraw.Draw(image, "RGBA")
    for command in commands:
        opacity = command.opacity
        if isinstance(command, RectCommand):
            draw.rectangle(
                (command.x, command.y, command.x + command.width, command.y + command.height),
                fill=_paint(command.fill, opacity),
            )
        elif isinstance(command, EllipseCommand):
            box = (command.x, command.y, command.x + command.width, command.y + command.height)
            draw.ellipse(
                box,
                fill=_paint(command.fill, opacity),
                outline=_paint(command.stroke, opacity),
                width=max(1, round(command.stroke_width)),
            )
        elif isinstance(command, PolygonCommand):
            draw.polygon(command.points, fill=_paint(command.fill, opacity))
            if command.stroke and command.stroke_width:
                draw.line(
                    [*command.points, command.points[0]],
                    fill=_paint(command.stroke, opacity),
                    width=max(1, round(command.stroke_width)),
                    joint="curve",
                )
        elif isinstance(command, LineCommand):
            draw.line(
                command.points,
                fill=_paint(command.stroke, opacity),
                width=max(1, round(command.stroke_width)),
                joint="curve",
            )
    return image


def _encode_program(
    frames: list[list[DrawCommand]], output: ProgramOutput
) -> tuple[bytes, bytes, int]:
    buffer = io.BytesIO()
    container = av.open(buffer, mode="w", format="mp4")
    preview: bytes | None = None
    unique_frames: set[str] = set()
    try:
        stream = container.add_stream("libx264", rate=output.fps)
        stream.width = output.width
        stream.height = output.height
        stream.pix_fmt = "yuv420p"
        stream.options = {"preset": "veryfast", "crf": "20", "tune": "animation"}
        for index, commands in enumerate(frames):
            image = rasterize_program_frame(commands, output)
            unique_frames.add(hashlib.sha256(image.tobytes()).hexdigest())
            if index == len(frames) // 2:
                png = io.BytesIO()
                image.save(png, "PNG")
                preview = png.getvalue()
            frame = av.VideoFrame.from_image(image)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    if len(unique_frames) < 2:
        raise ProgramError(
            "visual program produced identical pixels on every frame; add real motion"
        )
    if preview is None:
        raise ProgramError("visual program produced no representative frame")
    return buffer.getvalue(), preview, len(unique_frames)


def _manifest_key(program_digest: str) -> str:
    return f"{_MANIFEST_PREFIX}/{program_digest}.json"


def _validate_cached_manifest(value: Any, obj: GeneratorObject) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("program_digest") != obj.program_digest():
        raise ProgramError("cached Generator manifest does not match the requested program")
    if (
        value.get("runtime") != obj.runtime
        or value.get("output") != obj.output.model_dump(mode="json")
    ):
        raise ProgramError("cached Generator runtime/output identity mismatch")
    media = value.get("media") or {}
    preview = value.get("preview_frame") or {}
    if not media.get("storage_key") or len(str(media.get("digest") or "")) != 64:
        raise ProgramError("cached Generator manifest lacks fixed media")
    if not preview.get("storage_key") or len(str(preview.get("digest") or "")) != 64:
        raise ProgramError("cached Generator manifest lacks its representative frame")
    return value


async def _cached_manifest(obj: GeneratorObject, *, verify_media: bool) -> dict[str, Any] | None:
    key = _manifest_key(obj.program_digest())
    if not await storage.exists(key):
        return None
    try:
        value = json.loads(await storage.read(key))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProgramError(f"cached Generator manifest is unreadable: {exc}") from exc
    manifest = _validate_cached_manifest(value, obj)
    if verify_media:
        media = manifest["media"]
        data = await storage.read(media["storage_key"])
        if hashlib.sha256(data).hexdigest() != media["digest"]:
            raise ProgramError("cached Generator media does not match its fixed digest")
    return manifest


async def ensure_generator_clip(clip: Clip) -> dict[str, Any]:
    """Reuse or produce the exact program; return its fixed execution facts."""
    obj = clip.object
    if not isinstance(obj, GeneratorObject) or obj.runtime != "drawing-v1":
        raise ProgramError(f"clip {clip.clip_id} is not a drawing-v1 GeneratorObject")
    cached = await _cached_manifest(obj, verify_media=True)
    if cached is not None:
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}

    frames = await _execute_program(obj)
    video, preview, unique_frames = _encode_program(frames, obj.output)
    media_key, media_digest = await store_source_bytes(video, ".mp4", "video/mp4")
    preview_key, preview_digest = await store_source_bytes(preview, ".png", "image/png")
    manifest = {
        "schema_version": 1,
        "runtime": obj.runtime,
        "program_digest": obj.program_digest(),
        "resources": [],
        "output": obj.output.model_dump(mode="json"),
        "media": {"storage_key": media_key, "digest": media_digest},
        "preview_frame": {"storage_key": preview_key, "digest": preview_digest},
        "diagnostics": {
            "frames": len(frames),
            "unique_frames": unique_frames,
            "command_cap_per_frame": _MAX_COMMANDS,
            "encoder": "libx264",
        },
    }
    key = _manifest_key(obj.program_digest())
    if await storage.exists(key):
        cached = _validate_cached_manifest(json.loads(await storage.read(key)), obj)
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}
    await storage.save(
        key,
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
        content_type="application/json",
    )
    return {**manifest, "clip_id": clip.clip_id, "object_id": obj.object_id}


async def prepare_generator_media(
    content: CompositionContent,
    *,
    execution_id: str | None = None,
    composition_id: str | None = None,
    regenerate_media: bool = False,
) -> dict[str, dict[str, Any]]:
    """Prepare drawing previews freely; model media requires an authorized Run."""
    from app.tools.video.generated_images import ensure_generated_image_clip

    prepared: dict[str, dict[str, Any]] = {}
    for track in content.timeline.tracks:
        for clip in track.clips:
            if not isinstance(clip.object, GeneratorObject):
                continue
            if clip.object.runtime == "drawing-v1":
                prepared[clip.object.object_id] = await ensure_generator_clip(clip)
            elif execution_id is not None:
                prepared[clip.object.object_id] = await ensure_generated_image_clip(
                    clip,
                    execution_id=execution_id,
                    composition_id=composition_id,
                    regenerate=regenerate_media,
                )
    return prepared


def _generator_clips(read: dict[str, Any]) -> list[dict[str, Any]]:
    storyboard = read["storyboard"]
    return [
        clip
        for scene in storyboard["scenes"]
        for clip in scene["clips"]
        if clip["object_kind"] == "generator"
    ] + [clip for clip in storyboard["unassigned_clips"] if clip["object_kind"] == "generator"]


async def _preview_manifests(read: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for clip in _generator_clips(read):
        if clip.get("runtime") != "drawing-v1":
            continue
        key = _manifest_key(clip["program_digest"])
        if not await storage.exists(key):
            continue
        manifest = json.loads(await storage.read(key))
        if manifest.get("program_digest") != clip["program_digest"]:
            raise ProgramError("preview identity does not match the saved program")
        rows.append((clip, manifest))
    return rows


async def enrich_generator_previews(read: dict[str, Any]) -> dict[str, Any]:
    """Attach only exact-version preview URLs; missing previews stay absent."""
    previews = []
    for clip, manifest in await _preview_manifests(read):
        previews.append({
            "clip_id": clip["clip_id"],
            "object_id": clip["object_id"],
            "program_digest": manifest["program_digest"],
            "video_url": storage.public_url(manifest["media"]["storage_key"]),
            "poster_url": storage.public_url(manifest["preview_frame"]["storage_key"]),
            "media_digest": manifest["media"]["digest"],
            "output": manifest["output"],
            "diagnostics": manifest["diagnostics"],
        })
    return {**read, "generator_previews": previews}


async def generator_preview_images(read: dict[str, Any]) -> list[Any]:
    """Representative pixels for the Agent; no automatic aesthetic claim."""
    from app.pipeline.step_context import media_input_for_image

    images = []
    for clip, manifest in await _preview_manifests(read):
        image = await media_input_for_image(
            manifest["preview_frame"]["storage_key"],
            caption=(
                f"Exact preview for {clip['clip_id']} at program digest "
                f"{manifest['program_digest']}; representative middle frame, "
                "not an aesthetic approval."
            ),
            max_px=960,
        )
        if image is not None:
            images.append(image)
    return images

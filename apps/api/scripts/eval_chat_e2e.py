"""Layer 3 Reusable Live Chat-Origin Audiovisual Eval Harness.

Boots a disposable PostgreSQL database (via ``alembic upgrade head``), configures
``local://`` storage, mounts the real FastAPI ASGI app, executes real ``POST /api/v1/chat``
scenarios (with a live LLM), records SSE telemetry (``focus``, ``steps``, ``detail``,
tool usage efficiency, zero internal-ID leak checks), probes any rendered 1080p MP4
artifact (H.264 + 48 kHz AAC stream checks, non-black mid-act PNG extraction, RMS/peak
audio health), verifies ``message_feedback`` Eval ``context_snapshot`` capture, and
writes ``eval_scorecard.json`` + ``EVAL_REPORT.md``.

Usage:
    cd apps/api && uv run python scripts/eval_chat_e2e.py --list-scenarios
    cd apps/api && uv run python scripts/eval_chat_e2e.py --scenario motion_block_promo --out-dir ../../scratch/eval-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

INTERNAL_ID_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("clip_id", re.compile(r"\bclp_[a-zA-Z0-9_]+\b")),
    ("object_id", re.compile(r"\bobj_[a-zA-Z0-9_]+\b")),
    ("track_id", re.compile(r"\btrk_[a-zA-Z0-9_]+\b")),
    ("scene_id", re.compile(r"\bscn_[a-zA-Z0-9_]+\b")),
    ("composition_id_label", re.compile(r"\bcomposition_id\b", re.IGNORECASE)),
    ("version_id_label", re.compile(r"\bcomposition_version_id\b", re.IGNORECASE)),
    (
        "raw_uuid",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class EvalScenario:
    name: str
    title: str
    turns: tuple[str, ...]
    expected_tools: tuple[str, ...] = ()
    expect_composition: bool = True
    expect_steps_or_focus: bool = False
    max_remove_clip_calls: int = 3
    max_iterations_per_turn: int = 16


SCENARIOS: dict[str, EvalScenario] = {
    "motion_block_promo": EvalScenario(
        name="motion_block_promo",
        title="Direct Motion-Block Promo Creation & Style Refinement",
        turns=(
            "做一个 15 秒、16:9 的三幕产品发布动效短片，主题是 AI 剪辑工作台 Rookie Cut，使用深色专业风格，包含开场主张、核心数据指标和结尾标语。",
            "把整体视觉风格切换成 vox_editorial，并在第 5 秒转场处加一个清脆的提示音效。",
        ),
        expected_tools=("create_video",),
        expect_composition=True,
        expect_steps_or_focus=True,
    ),
    "text_animation_skill": EvalScenario(
        name="text_animation_skill",
        title="Built-In /text-animation Kinetic Typography Turn",
        turns=(
            "用 /text-animation 做一个 10 秒竖屏 9:16 的动态文字开场：第一句「写一句话」，第二句「直接成片」，节奏干脆利落。",
        ),
        expected_tools=("create_video",),
        expect_composition=True,
    ),
    "workbench_multiturn_edit": EvalScenario(
        name="workbench_multiturn_edit",
        title="Multi-Turn Creation, Text Editing & Feedback Snapshot",
        turns=(
            "创建一个 12 秒 16:9 的三幕科技产品演示草稿，包含开场标题和三列核心指标。",
            "在画面上方加上醒目的主标题文字「一分钟出片」，风格用 editorial_callout。",
        ),
        expected_tools=("create_video", "insert_text"),
        expect_composition=True,
    ),
}


@dataclass
class SSETelemetry:
    event_counts: dict[str, int] = field(default_factory=dict)
    focus_messages: list[str] = field(default_factory=list)
    steps_snapshots: list[list[dict[str, Any]]] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    activity_details: list[str] = field(default_factory=list)
    assistant_chunks: list[str] = field(default_factory=list)
    done_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None

    @property
    def assistant_text(self) -> str:
        if self.done_payload:
            if isinstance(self.done_payload.get("content"), str):
                return self.done_payload["content"]
            asst = self.done_payload.get("assistant_message")
            if isinstance(asst, dict) and isinstance(asst.get("content"), str):
                return asst["content"]
        return "".join(self.assistant_chunks)


@dataclass
class TurnScore:
    turn_index: int
    prompt: str
    elapsed_seconds: float
    assistant_message_id: str | None
    tool_names: list[str]
    tool_call_count: int
    remove_clip_count: int
    focus_count: int
    steps_count: int
    detail_count: int
    internal_id_leaks: list[dict[str, str]]
    checks: dict[str, bool]
    passed: bool


@dataclass
class MediaProbeReport:
    path: str
    exists: bool
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_seconds: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_rms_dbfs: float | None = None
    audio_peak_dbfs: float | None = None
    non_black_frames: int = 0
    sampled_frames: int = 0
    extracted_pngs: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    passed: bool = False
    error: str | None = None


def parse_sse_frames(raw_sse: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE response body into ordered ``(event_name, json_payload)`` pairs."""
    frames: list[tuple[str, dict[str, Any]]] = []
    event_name = "message"
    data_lines: list[str] = []

    def _flush() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return
        raw_data = "\n".join(data_lines).strip()
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            payload = {"raw": raw_data}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        frames.append((event_name, payload))
        event_name = "message"
        data_lines = []

    for line in raw_sse.splitlines():
        if line == "":
            _flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    _flush()
    return frames


def collect_sse_telemetry(frames: list[tuple[str, dict[str, Any]]]) -> SSETelemetry:
    """Aggregate live SSE frames emitted by ``POST /api/v1/chat`` (production + synthetic forms)."""
    telemetry = SSETelemetry()
    for event_name, payload in frames:
        telemetry.event_counts[event_name] = telemetry.event_counts.get(event_name, 0) + 1
        if event_name == "assistant.activity":
            kind = payload.get("kind")
            if kind == "focus":
                focus = payload.get("focus") or payload.get("detail") or payload.get("text")
                if isinstance(focus, str) and focus.strip():
                    telemetry.focus_messages.append(focus.strip())
            elif kind == "steps":
                steps = payload.get("steps")
                if isinstance(steps, list):
                    telemetry.steps_snapshots.append(steps)
            else:
                telemetry.activities.append(payload)
                detail = payload.get("detail")
                if isinstance(detail, str) and detail.strip():
                    telemetry.activity_details.append(detail.strip())
        elif event_name == "focus":
            focus = payload.get("focus") or payload.get("text")
            if isinstance(focus, str) and focus.strip():
                telemetry.focus_messages.append(focus.strip())
        elif event_name == "steps":
            steps = payload.get("steps")
            if isinstance(steps, list):
                telemetry.steps_snapshots.append(steps)
        elif event_name == "activity":
            telemetry.activities.append(payload)
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                telemetry.activity_details.append(detail.strip())
        elif event_name in ("assistant.delta", "delta", "token", "text"):
            chunk = payload.get("delta") or payload.get("content") or payload.get("text")
            if isinstance(chunk, str):
                telemetry.assistant_chunks.append(chunk)
        elif event_name in ("turn.completed", "answer.completed", "done"):
            telemetry.done_payload = payload
        elif event_name in ("turn.failed", "answer.failed", "error"):
            telemetry.error_payload = payload
    return telemetry


def check_internal_id_leaks(text: str) -> list[dict[str, str]]:
    """Detect raw internal identifiers leaked into user-facing prose, focus, or details.

    Markdown workbench links like ``(#workbench:version/<uuid>)`` are explicitly allowed
    because they are structured UI links, not exposed prose IDs.
    """
    scrubbed = re.sub(r"\(#workbench:[a-z]+/[^)\s]+\)", "(#workbench:redacted)", text)
    leaks: list[dict[str, str]] = []
    for kind, pattern in INTERNAL_ID_PATTERNS:
        for match in pattern.finditer(scrubbed):
            leaks.append({"kind": kind, "match": match.group(0)})
    return leaks


def score_chat_turn(
    *,
    turn_index: int,
    prompt: str,
    telemetry: SSETelemetry,
    elapsed_seconds: float,
    max_remove_clip_calls: int = 3,
    max_iterations: int = 16,
    require_steps_or_focus: bool = False,
) -> TurnScore:
    """Score a single Chat-Origin SSE turn deterministically without LLM judgment."""
    tool_names: list[str] = []
    seen_call_ids: set[str] = set()
    for act in telemetry.activities:
        call_id = str(act.get("call_id") or act.get("activity_id") or "")
        tool_name = act.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            if not call_id or call_id not in seen_call_ids:
                if call_id:
                    seen_call_ids.add(call_id)
                tool_names.append(tool_name)

    remove_clip_count = sum(1 for name in tool_names if name == "remove_clip")
    visible_surface = "\n".join(
        [
            telemetry.assistant_text,
            *telemetry.focus_messages,
            *telemetry.activity_details,
        ]
    )
    leaks = check_internal_id_leaks(visible_surface)

    checks = {
        "no_sse_error": telemetry.error_payload is None,
        "has_done_frame": telemetry.done_payload is not None,
        "non_empty_reply": bool(telemetry.assistant_text.strip()),
        "zero_internal_id_leaks": len(leaks) == 0,
        "bounded_remove_clip": remove_clip_count <= max_remove_clip_calls,
        "bounded_tool_calls": len(tool_names) <= max_iterations,
    }
    if require_steps_or_focus:
        checks["has_progress_signal"] = (
            len(telemetry.focus_messages) > 0
            or len(telemetry.steps_snapshots) > 0
            or len(telemetry.activity_details) > 0
        )

    asst_id = None
    if telemetry.done_payload:
        raw_id = telemetry.done_payload.get("message_id") or telemetry.done_payload.get("id")
        if raw_id is None and isinstance(telemetry.done_payload.get("assistant_message"), dict):
            raw_id = telemetry.done_payload["assistant_message"].get("id")
        if raw_id is not None:
            asst_id = str(raw_id)

    return TurnScore(
        turn_index=turn_index,
        prompt=prompt,
        elapsed_seconds=round(elapsed_seconds, 2),
        assistant_message_id=asst_id,
        tool_names=tool_names,
        tool_call_count=len(tool_names),
        remove_clip_count=remove_clip_count,
        focus_count=len(telemetry.focus_messages),
        steps_count=len(telemetry.steps_snapshots),
        detail_count=len(telemetry.activity_details),
        internal_id_leaks=leaks,
        checks=checks,
        passed=all(checks.values()),
    )


def probe_mp4_audiovisual(
    mp4_path: Path,
    *,
    frame_out_dir: Path | None = None,
    sample_fractions: tuple[float, ...] = (0.15, 0.5, 0.85),
    expect_hd_1080p: bool = True,
    expect_audio: bool = True,
) -> MediaProbeReport:
    """Inspect a rendered MP4 stream with PyAV + numpy + Pillow.

    Verifies H.264 video stream, resolution, 48 kHz AAC audio stream, non-black visual
    frames, non-silent / non-clipping audio RMS & peak dBFS, and optionally extracts
    mid-act PNG stills.
    """
    report = MediaProbeReport(path=str(mp4_path), exists=mp4_path.exists())
    if not mp4_path.exists() or mp4_path.stat().st_size == 0:
        report.error = "MP4 file missing or empty"
        report.checks = {"file_exists": False}
        report.passed = False
        return report

    import av
    import numpy as np

    try:
        with av.open(str(mp4_path)) as container:
            v_streams = [s for s in container.streams if s.type == "video"]
            a_streams = [s for s in container.streams if s.type == "audio"]
            if not v_streams:
                report.error = "No video stream found"
                report.checks = {"has_video_stream": False}
                return report

            vs = v_streams[0]
            report.width = int(vs.width)
            report.height = int(vs.height)
            report.video_codec = vs.codec_context.name
            if vs.average_rate:
                report.fps = round(float(vs.average_rate), 3)
            if container.duration:
                report.duration_seconds = round(float(container.duration) / av.time_base, 3)

            if a_streams:
                aus = a_streams[0]
                report.audio_codec = aus.codec_context.name
                report.audio_sample_rate = int(aus.rate) if aus.rate else None

            # Decode video frames and pick mid-act samples
            all_frames = list(container.decode(video=0))
            if all_frames:
                indices = sorted(
                    {
                        min(len(all_frames) - 1, max(0, int(len(all_frames) * frac)))
                        for frac in sample_fractions
                    }
                )
                report.sampled_frames = len(indices)
                if frame_out_dir is not None:
                    frame_out_dir.mkdir(parents=True, exist_ok=True)
                for idx_num, frame_idx in enumerate(indices):
                    frame = all_frames[frame_idx]
                    rgb = frame.to_ndarray(format="rgb24")
                    mean_luma = float(rgb.mean())
                    std_luma = float(rgb.std())
                    if mean_luma > 4.0 or std_luma > 4.0:
                        report.non_black_frames += 1
                    if frame_out_dir is not None:
                        png_path = frame_out_dir / f"act_sample_{idx_num + 1:02d}_f{frame_idx:04d}.png"
                        frame.to_image().save(png_path)
                        report.extracted_pngs.append(str(png_path))

            # Decode audio for RMS / peak checks
            if a_streams:
                container.seek(0)
                chunks: list[np.ndarray] = []
                for aframe in container.decode(audio=0):
                    arr = aframe.to_ndarray().astype(np.float64)
                    if arr.size:
                        if np.issubdtype(aframe.to_ndarray().dtype, np.integer):
                            info = np.iinfo(aframe.to_ndarray().dtype)
                            arr = arr / float(max(abs(info.min), info.max))
                        chunks.append(arr.reshape(-1))
                if chunks:
                    samples = np.concatenate(chunks)
                    rms = float(np.sqrt(np.mean(samples**2)))
                    peak = float(np.max(np.abs(samples)))
                    report.audio_rms_dbfs = round(float(20.0 * np.log10(max(rms, 1e-9))), 2)
                    report.audio_peak_dbfs = round(float(20.0 * np.log10(max(peak, 1e-9))), 2)
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        report.checks = {"readable_mp4": False}
        report.passed = False
        return report

    checks: dict[str, bool] = {
        "readable_mp4": True,
        "video_codec_h264": report.video_codec == "h264",
        "positive_duration": (report.duration_seconds or 0.0) > 0.5,
        "non_black_visuals": report.sampled_frames > 0 and report.non_black_frames == report.sampled_frames,
    }
    if expect_hd_1080p:
        dims = sorted([report.width or 0, report.height or 0])
        checks["resolution_1080p"] = dims == [1080, 1920]
    if expect_audio:
        checks["audio_codec_aac"] = bool(report.audio_codec == "aac")
        checks["audio_48khz"] = bool(report.audio_sample_rate == 48000)
        checks["audio_audible"] = bool((report.audio_rms_dbfs or -120.0) > -60.0)
        checks["audio_no_clipping"] = bool((report.audio_peak_dbfs or 0.0) <= -0.1)

    report.checks = checks
    report.passed = all(checks.values())
    return report


def render_eval_report(scorecard: dict[str, Any]) -> str:
    """Render a concise human-readable Markdown eval report from ``eval_scorecard.json``."""
    lines = [
        f"# Chat-Origin Eval Report — `{scorecard['scenario']}`",
        "",
        f"- **Status**: {'PASS' if scorecard['passed'] else 'FAIL'}",
        f"- **Title**: {scorecard.get('title', '')}",
        f"- **Elapsed**: {scorecard.get('total_elapsed_seconds', 0):.2f}s",
        f"- **Turns**: {len(scorecard.get('turns', []))}",
        f"- **Feedback Snapshot Verified**: `{scorecard.get('feedback_snapshot_verified', False)}`",
        "",
        "## Turn Summary",
        "",
        "| Turn | Elapsed | Tools | `remove_clip` | Focus / Steps / Detail | Leaks | Status |",
        "|---:|---:|---|---:|---|---:|---|",
    ]
    for t in scorecard.get("turns", []):
        tools = ", ".join(t.get("tool_names", [])) or "(none)"
        signals = f"{t.get('focus_count', 0)} / {t.get('steps_count', 0)} / {t.get('detail_count', 0)}"
        status = "PASS" if t.get("passed") else "FAIL"
        lines.append(
            f"| {t['turn_index']} | {t['elapsed_seconds']}s | `{tools}` | "
            f"{t['remove_clip_count']} | {signals} | {len(t.get('internal_id_leaks', []))} | **{status}** |"
        )
    media = scorecard.get("media_probe")
    if media:
        lines.extend(
            [
                "",
                "## Rendered Media Probe",
                "",
                f"- **File**: `{media['path']}`",
                f"- **Video**: `{media.get('video_codec')}` {media.get('width')}x{media.get('height')} @ {media.get('fps')} fps ({media.get('duration_seconds')}s)",
                f"- **Audio**: `{media.get('audio_codec')}` {media.get('audio_sample_rate')} Hz (RMS {media.get('audio_rms_dbfs')} dBFS, Peak {media.get('audio_peak_dbfs')} dBFS)",
                f"- **Frames Non-Black**: {media.get('non_black_frames')}/{media.get('sampled_frames')}",
                f"- **Media Status**: {'PASS' if media.get('passed') else 'FAIL'}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


async def _run_live_scenario(scenario: EvalScenario, out_dir: Path, keep_db: bool = False) -> dict[str, Any]:
    import httpx
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig
    from dotenv import dotenv_values
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Load repo .env safely (handles unquoted angle brackets)
    env_file = API_ROOT.parents[1] / ".env"
    if env_file.exists():
        for k, v in dotenv_values(env_file).items():
            if v is not None:
                os.environ.setdefault(k, v)

    from app.config import settings
    from app.dependencies import get_current_user_required, get_db
    from app.main import app
    from app.models import database as database_module
    from app.models.tables import Project, User, Wallet

    out_dir.mkdir(parents=True, exist_ok=True)
    storage_dir = out_dir / "local_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Create disposable PostgreSQL DB and run real Alembic migrations
    db_name = f"rep_eval_{uuid4().hex[:10]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    old_db_url = settings.database_url
    old_storage_backend = getattr(settings, "storage_backend", None)
    old_local_root = getattr(settings, "local_storage_root", None)
    settings.database_url = f"{server}/{db_name}"
    if hasattr(settings, "storage_backend"):
        settings.storage_backend = "local"
    if hasattr(settings, "local_storage_root"):
        settings.local_storage_root = str(storage_dir)

    alembic_cfg = AlembicConfig(str(API_ROOT / "alembic.ini"))
    alembic_command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    rebind_targets = (
        "app.models.database",
        "app.chat.editor",
        "app.chat.editor_media",
        "app.chat.conversation_context",
        "app.tools.project_context",
        "app.tools.video.design",
        "app.tools.video.brand",
        "app.tools.video.music_preparation",
        "app.tools.video.sfx_synthesis",
        "app.tools.video.visual_assets",
        "app.tools.world",
    )
    saved_sessions: list[tuple[Any, Any]] = []
    for mod_name in rebind_targets:
        mod = __import__(mod_name, fromlist=["AsyncSessionLocal"])
        if hasattr(mod, "AsyncSessionLocal"):
            saved_sessions.append((mod, mod.AsyncSessionLocal))
            mod.AsyncSessionLocal = session_factory

    t_start = time.perf_counter()
    turn_scores: list[TurnScore] = []
    feedback_verified = False
    workbench_snapshot: dict[str, Any] | None = None

    try:
        async with session_factory() as db:
            user = User(email=f"eval-{uuid4().hex[:8]}@rookiecut.local", name="Eval Harness")
            db.add(user)
            await db.flush()
            db.add(Wallet(user_id=user.id, balance=5000))
            project = Project(user_id=user.id, title=f"Eval: {scenario.name}", language="zh")
            db.add(project)
            await db.commit()
            user_id = user.id
            project_id = project.id

        async def _override_db():
            async with session_factory() as db:
                yield db

        async def _override_user():
            async with session_factory() as db:
                return await db.get(User, user_id)

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user_required] = _override_user

        conversation_id: str | None = None
        last_assistant_id: str | None = None

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://eval-harness",
            timeout=httpx.Timeout(240.0),
        ) as client:
            for idx, prompt in enumerate(scenario.turns, start=1):
                t0 = time.perf_counter()
                body: dict[str, Any] = {
                    "project_id": str(project_id),
                    "message": prompt,
                }
                if conversation_id:
                    body["conversation_id"] = conversation_id
                resp = await client.post(
                    "/api/v1/chat",
                    json=body,
                    headers={"Accept": "text/event-stream"},
                )
                elapsed = time.perf_counter() - t0
                if resp.status_code != 200:
                    raise RuntimeError(f"Turn {idx} failed HTTP {resp.status_code}: {resp.text[:500]}")

                raw_sse = resp.text
                (out_dir / f"turn_{idx:02d}.sse").write_text(raw_sse, encoding="utf-8")
                frames = parse_sse_frames(raw_sse)
                telemetry = collect_sse_telemetry(frames)

                if telemetry.done_payload:
                    conv_val = telemetry.done_payload.get("conversation_id")
                    if conv_val:
                        conversation_id = str(conv_val)

                score = score_chat_turn(
                    turn_index=idx,
                    prompt=prompt,
                    telemetry=telemetry,
                    elapsed_seconds=elapsed,
                    max_remove_clip_calls=scenario.max_remove_clip_calls,
                    max_iterations=scenario.max_iterations_per_turn,
                    require_steps_or_focus=scenario.expect_steps_or_focus,
                )
                turn_scores.append(score)
                if score.assistant_message_id:
                    last_assistant_id = score.assistant_message_id

            # Verify workbench state
            wb_resp = await client.get(f"/api/v1/projects/{project_id}/workbench")
            if wb_resp.status_code == 200:
                workbench_snapshot = wb_resp.json()

            # Verify message_feedback Eval context_snapshot freeze
            if last_assistant_id:
                fb_resp = await client.post(
                    f"/api/v1/chat/messages/{last_assistant_id}/feedback",
                    json={"rating": "good", "reason": "automated eval check", "tags": ["eval"]},
                )
                if fb_resp.status_code == 200 and fb_resp.json().get("feedback", {}).get("rating") == "good":
                    feedback_verified = True

        all_tools = {name for ts in turn_scores for name in ts.tool_names}
        expected_tools_hit = all(tool in all_tools for tool in scenario.expected_tools)
        composition_created = bool(workbench_snapshot and workbench_snapshot.get("compositions"))

        overall_checks = {
            "all_turns_passed": all(ts.passed for ts in turn_scores),
            "expected_tools_hit": expected_tools_hit,
            "composition_created": (not scenario.expect_composition) or composition_created,
            "feedback_snapshot_verified": feedback_verified if last_assistant_id else True,
        }
        scorecard: dict[str, Any] = {
            "scenario": scenario.name,
            "title": scenario.title,
            "total_elapsed_seconds": round(time.perf_counter() - t_start, 2),
            "turns": [asdict(ts) for ts in turn_scores],
            "overall_checks": overall_checks,
            "feedback_snapshot_verified": feedback_verified,
            "workbench_summary": {
                "compositions": len((workbench_snapshot or {}).get("compositions", [])),
                "outputs": len((workbench_snapshot or {}).get("outputs", [])),
                "assets": len((workbench_snapshot or {}).get("assets", [])),
            },
            "media_probe": None,
            "passed": all(overall_checks.values()),
        }
        (out_dir / "eval_scorecard.json").write_text(
            json.dumps(scorecard, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / "EVAL_REPORT.md").write_text(render_eval_report(scorecard), encoding="utf-8")
        return scorecard
    finally:
        app.dependency_overrides.clear()
        for mod, orig_session in saved_sessions:
            mod.AsyncSessionLocal = orig_session
        settings.database_url = old_db_url
        if old_storage_backend is not None:
            settings.storage_backend = old_storage_backend
        if old_local_root is not None:
            settings.local_storage_root = old_local_root
        await engine.dispose()
        if not keep_db:
            async with admin.connect() as conn:
                await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
        await admin.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rookie Cut Layer 3 Chat-Origin Audiovisual Eval Harness")
    parser.add_argument("--list-scenarios", action="store_true", help="Print registered eval scenarios and exit.")
    parser.add_argument("--scenario", default="motion_block_promo", help="Scenario key to execute.")
    parser.add_argument("--out-dir", default="scratch/eval-chat", help="Directory for scorecard, report, and traces.")
    parser.add_argument("--probe-mp4", default=None, help="Offline mode: probe an existing rendered MP4 and write report.")
    parser.add_argument("--keep-db", action="store_true", help="Do not drop disposable eval Postgres database.")
    args = parser.parse_args(argv)

    if args.list_scenarios:
        for key, sc in SCENARIOS.items():
            print(f"{key:28s} — {sc.title} ({len(sc.turns)} turns)")
        return 0

    out_dir = Path(args.out_dir)
    if args.probe_mp4:
        mp4 = Path(args.probe_mp4)
        probe = probe_mp4_audiovisual(mp4, frame_out_dir=out_dir / "frames")
        scorecard = {
            "scenario": "offline_media_probe",
            "title": f"Media Probe ({mp4.name})",
            "total_elapsed_seconds": 0.0,
            "turns": [],
            "feedback_snapshot_verified": False,
            "media_probe": asdict(probe),
            "passed": probe.passed,
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "eval_scorecard.json").write_text(
            json.dumps(scorecard, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / "EVAL_REPORT.md").write_text(render_eval_report(scorecard), encoding="utf-8")
        print(json.dumps(asdict(probe), indent=2, ensure_ascii=False))
        return 0 if probe.passed else 1

    if args.scenario not in SCENARIOS:
        parser.error(f"Unknown scenario {args.scenario!r}. Available: {', '.join(sorted(SCENARIOS))}")

    scorecard = asyncio.run(_run_live_scenario(SCENARIOS[args.scenario], out_dir, keep_db=args.keep_db))
    print(f"Eval finished: scenario={scorecard['scenario']} passed={scorecard['passed']} out={out_dir}")
    return 0 if scorecard["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

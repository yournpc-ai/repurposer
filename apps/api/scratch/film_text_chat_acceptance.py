"""T2a REAL Chat acceptance: Chinese text film, two produced versions.

This harness drives only the public Chat/API seam (POST /chat SSE + the
ordinary answer endpoint). It never writes a render spec or calls render
directly. It records the transcript, run/spec/ledger facts, downloads the two
produced MP4s, and checks the no-voiceover/no-music law.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import av  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import chat_scenarios as cs  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    ConversationUsage,
    CreditTransaction,
    FilmNarration,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.providers import storage  # noqa: E402

STATE_FILE = Path("/tmp/t2a_text_film_state.json")
EVIDENCE_DIR = Path(__file__).resolve().parent / "t2a-acceptance"
TRANSCRIPT = EVIDENCE_DIR / "transcript.md"
FACTS_JSON = EVIDENCE_DIR / "facts.json"

COPY = """好的内容，不该只出现一次。
一场分享，可以长成文章、短片和讨论。
你把专业讲清楚，助手负责送到更多人面前。
从一次表达开始，让作品持续被看见。"""
COPY_LINES = COPY.splitlines()
REPLACEMENT = "一次分享，也能持续长出新的讨论。"

FIRST_MESSAGE = (
    "用下面这段中文做一支约 20 秒的竖屏文字片，不配音、不配乐。"
    "文字逐字保留；先展示分镜，等我确认后再制作。\n\n"
    f"{COPY}"
)
CONFIRM_MESSAGE = "确认，按这版开始制作。"
REVISE_MESSAGE = (
    f"把第二幕文案改成「{REPLACEMENT}」，其他幕保持不变；"
    "改好后生成新版，原版保留。仍然不配音、不配乐。"
)


class AcceptanceFailure(AssertionError):
    pass


def check(condition: bool, label: str, detail: object = "") -> None:
    if not condition:
        raise AcceptanceFailure(f"{label}" + (f" — {detail}" if detail else ""))


def _stream_text(stream: cs.StreamTurn) -> str:
    completed = stream.completed or {}
    row_texts = [
        str((event.get("row") or {}).get("content") or "")
        for event in stream.row_events
        if event.get("op") == "append"
    ]
    envelope = str(((completed.get("assistant_message") or {}).get("content")) or "")
    return "\n".join(t for t in [*row_texts, envelope] if t)


def _turn_record(label: str, user_text: str, stream: cs.StreamTurn) -> dict[str, Any]:
    completed = stream.completed or {}
    assistant = completed.get("assistant_message") or {}
    return {
        "label": label,
        "user": user_text,
        "terminal": cs.terminal_tool_of(completed) if completed else None,
        "run_id": completed.get("run_id"),
        "failed": stream.failed,
        "assistant": assistant.get("content") or "",
        "question_kind": (assistant.get("question") or {}).get("kind"),
        "activity": [
            {
                "kind": a.get("kind"),
                "key": a.get("key"),
                "status": a.get("status"),
                "duration_ms": a.get("duration_ms"),
            }
            for a in stream.activities
        ],
    }


async def _pending(pid: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(pid))
        check(project is not None, "project exists", pid)
        return json.loads(json.dumps(project.pending_brief or {}))


async def _runs(pid: str) -> list[WorkflowRun]:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(WorkflowRun)
                    .where(WorkflowRun.project_id == uuid.UUID(pid))
                    .order_by(WorkflowRun.created_at)
                )
            ).scalars()
        )
        # Convert inside the session (rollback/expire traps are real).
        return [
            WorkflowRun(
                id=r.id,
                project_id=r.project_id,
                status=r.status,
                progress=r.progress,
                context=json.loads(json.dumps(r.context or {})),
            )
            for r in rows
        ]


async def _steps(run_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == uuid.UUID(run_id))
                    .order_by(WorkflowStep.seq)
                )
            ).scalars()
        )
        return [
            {
                "id": str(s.id),
                "kind": s.kind,
                "status": s.status,
                "spec": json.loads(json.dumps(s.spec or {})),
                "estimate": json.loads(json.dumps(s.estimate or {})),
                "cost": json.loads(json.dumps(s.cost or {})),
                "error": s.error,
            }
            for s in rows
        ]


async def _film_outputs(pid: str) -> list[Output]:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Output)
                    .where(Output.project_id == uuid.UUID(pid), Output.type == "film")
                    .order_by(Output.created_at)
                )
            ).scalars()
        )
        return [
            Output(
                id=o.id,
                project_id=o.project_id,
                workflow_step_id=o.workflow_step_id,
                type=o.type,
                language=o.language,
                status=o.status,
                provenance=o.provenance,
                payload=json.loads(json.dumps(o.payload or {})),
                files=json.loads(json.dumps(o.files or {})),
                source_ref=json.loads(json.dumps(o.source_ref or {})),
                render_spec=json.loads(json.dumps(o.render_spec or {})),
                render_status=o.render_status,
                render_error=o.render_error,
                work_id=o.work_id,
                archived_at=o.archived_at,
            )
            for o in rows
        ]


async def _usage_rows(user_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(ConversationUsage)
                    .where(ConversationUsage.user_id == uuid.UUID(user_id))
                    .order_by(ConversationUsage.created_at)
                )
            ).scalars()
        )
        return [
            {
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cached_tokens": r.cached_tokens,
                "cost_usd": r.cost_usd,
                "model": r.model,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


async def _ledger_rows(user_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(CreditTransaction)
                    .where(CreditTransaction.user_id == uuid.UUID(user_id))
                    .order_by(CreditTransaction.created_at)
                )
            ).scalars()
        )
        return [
            {
                "kind": t.kind,
                "amount": t.amount,
                "note": t.note,
                "ref": json.loads(json.dumps(t.ref or {})),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ]


async def _narration_count(pid: str) -> int:
    async with AsyncSessionLocal() as db:
        return int(
            await db.scalar(
                select(func.count(FilmNarration.id)).where(
                    FilmNarration.project_id == uuid.UUID(pid)
                )
            )
            or 0
        )


async def _download_output(output: Output, filename: str) -> Path:
    key = str((output.files or {}).get("video") or "")
    check(bool(key), "output carries its video object key", output.files)
    data = await storage.read(key)
    path = EVIDENCE_DIR / filename
    path.write_bytes(data)
    return path


def _probe_mp4(path: Path) -> dict[str, Any]:
    container = av.open(str(path))
    video_streams = [s for s in container.streams if s.type == "video"]
    audio_streams = [s for s in container.streams if s.type == "audio"]
    check(bool(video_streams), "MP4 has a video stream", path.name)
    video = video_streams[0]
    duration_s = (
        float(video.duration * video.time_base)
        if video.duration is not None
        else (container.duration or 0) / 1_000_000
    )
    decoded = 0
    for _ in container.decode(video):
        decoded += 1
        if decoded >= 10:
            break
    container.close()
    check(decoded > 0, "MP4 decodes video frames", path.name)

    audio: dict[str, Any] = {"streams": len(audio_streams)}
    if audio_streams:
        # Remotion may legally emit a silent AAC track; decode it and measure
        # instead of mistaking container shape for narration/music.
        audio_container = av.open(str(path))
        stream = audio_container.streams.audio[0]
        max_amp = 0.0
        samples = 0
        for frame in audio_container.decode(stream):
            arr = frame.to_ndarray()
            if arr.size:
                max_amp = max(max_amp, float(abs(arr).max()))
                samples += int(arr.size)
        audio_container.close()
        audio.update({"samples": samples, "max_amplitude": max_amp})
        audio["audible"] = bool(samples and max_amp > 1e-4)
    else:
        audio["audible"] = False
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "duration_s": duration_s,
        "video_stream": {"codec": video.codec.name, "frames_decoded_probe": decoded},
        "audio": audio,
    }


def _check_silent_spec(output: Output, label: str) -> None:
    spec = output.render_spec or {}
    scenes = spec.get("scenes") or []
    check(bool(scenes), f"{label}: render spec carries scenes", spec.keys())
    check(not spec.get("music"), f"{label}: no music bed in spec", spec.get("music"))
    check(
        all(not (s.get("audio")) for s in scenes),
        f"{label}: no narration audio in any scene",
        [s.get("audio") for s in scenes],
    )
    check(
        all(not (s.get("captions")) for s in scenes),
        f"{label}: no narration captions in any scene",
        [s.get("captions") for s in scenes],
    )


def _scene_copy(scene: dict[str, Any]) -> Any:
    return scene.get("lines")


async def _consume_trigger(ctx: cs.Ctx, conversation_id: str, run_id: str) -> dict[str, Any] | None:
    review = await cs.wait_trigger_review(ctx, conversation_id, run_id, timeout=60.0)
    if review is not None and (review.get("question") or {}).get("kind") == "question":
        res = await ctx.answer(review["id"], {"kind": "bail"})
        check(res.status_code == 200, "trigger review bail", res.text)
    return review


async def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_FILE.read_text())
    user_id = state["user_id"]
    pid = state["project_id"]
    records: list[dict[str, Any]] = []
    facts: dict[str, Any] = {"state": state, "copy": COPY, "replacement": REPLACEMENT}

    ctx = cs.Ctx(uuid.UUID(user_id), keep=True)
    ctx.client.headers["Accept-Language"] = "zh-CN,zh;q=0.9"
    try:
        # 1. Text + target + no voiceover/music + review-only. This must design
        # and present, never produce.
        first = await ctx.chat_stream(pid, FIRST_MESSAGE, surface="chat")
        records.append(_turn_record("design", FIRST_MESSAGE, first))
        check(first.failed is None, "design turn succeeds", first.failed)
        first_turn = first.completed or {}
        first_text = _stream_text(first)
        check(first_turn.get("run_id") is None, "unconfirmed design starts no run", first_turn)
        check(
            any(a.get("key") == "chat.activity.storyboardDone" for a in first.activities),
            "design_storyboard evidence settles in Activity",
            [a.get("key") for a in first.activities],
        )
        for line in COPY_LINES:
            check(line in first_text, "presentation quotes the user's line verbatim", line)
        pending = await _pending(pid)
        params = pending.get("film_storyboard_params") or {}
        check(pending.get("film_review_hold") is True, "first draft holds for review", pending)
        check(params.get("text") == COPY, "the source text is pinned verbatim", params)
        check(params.get("verbatim") is True, "the source text role is verbatim", params)
        check(params.get("target_seconds") == 20, "the target duration is pinned", params)
        check(params.get("voiceover") is False, "voiceover is explicitly off", params)
        check(params.get("music_mood") == "off", "music is explicitly off", params)
        board = pending.get("film_storyboard") or {}
        scenes = board.get("scenes") or []
        check(len(scenes) == 4, "four text planes are presented", scenes)
        check(all(s.get("type") == "words" for s in scenes), "all scenes are text planes", scenes)
        check(
            abs(sum(float(s.get("seconds") or 0) for s in scenes) - 20.0) < 0.6,
            "presented board totals about 20s",
            [s.get("seconds") for s in scenes],
        )
        check(await cs.count_runs(pid) == 0, "no run exists before confirmation", None)
        facts["design_pending"] = {
            "params": params,
            "version": pending.get("film_storyboard_version"),
            "review_hold": pending.get("film_review_hold"),
            "scene_seconds": [s.get("seconds") for s in scenes],
        }

        # 2. Explicit user confirmation starts production (auto/auto settings;
        # the confirmation is the approval words, not a hidden script).
        confirm = await ctx.chat_stream(pid, CONFIRM_MESSAGE, surface="chat")
        records.append(_turn_record("confirm original", CONFIRM_MESSAGE, confirm))
        check(confirm.failed is None, "confirmation turn succeeds", confirm.failed)
        run1 = (confirm.completed or {}).get("run_id")
        check(run1 is not None, "explicit confirmation births run 1", confirm.completed)
        run1_id = str(run1)
        status1 = await cs.wait_run_terminal(run1_id, timeout=600.0)
        check(status1 == "completed", "run 1 completes", status1)
        outputs1 = await _film_outputs(pid)
        check(len(outputs1) == 1, "one original film output exists", [str(o.id) for o in outputs1])
        original = outputs1[0]
        check(
            str(original.render_status) == "RenderStatus.COMPLETED" or str(original.render_status) == "completed",
            "original film render completed",
            original.render_error,
        )
        original_path = await _download_output(original, "v1-original.mp4")
        original_probe = _probe_mp4(original_path)
        _check_silent_spec(original, "original")
        check(
            19.0 <= original_probe["duration_s"] <= 21.5,
            "original MP4 duration is about 20s",
            original_probe,
        )
        check(original_probe["audio"]["audible"] is False, "original has no audible audio", original_probe)
        steps1 = await _steps(run1_id)
        check(
            all((s.get("cost") or {}).get("units", {}).get("tts_chars", 0) == 0 for s in steps1),
            "run 1 records zero TTS units",
            [s.get("cost") for s in steps1],
        )
        facts["run1"] = {
            "id": run1_id,
            "status": status1,
            "output_id": str(original.id),
            "path": str(original_path),
            "probe": original_probe,
            "steps": steps1,
            "scene_copies": [_scene_copy(s) for s in (original.render_spec or {}).get("scenes", [])],
            "scene_frames": [s.get("frames") for s in (original.render_spec or {}).get("scenes", [])],
            "music": (original.render_spec or {}).get("music"),
        }
        await _consume_trigger(ctx, str((confirm.completed or {}).get("conversation_id")), run1_id)

        # 3. Revision through Chat only: second scene changes, all else and the
        # original artifact stay. Auto/auto starts the revised run when the
        # user's message explicitly authorizes generation.
        revise = await ctx.chat_stream(pid, REVISE_MESSAGE, surface="chat")
        records.append(_turn_record("revise and produce", REVISE_MESSAGE, revise))
        check(revise.failed is None, "revision turn succeeds", revise.failed)
        run2 = (revise.completed or {}).get("run_id")
        if run2 is None:
            # One lawful extra confirmation beat remains within the authorized
            # five turns if the revised plan docked instead of auto-starting.
            followup = await ctx.chat_stream(pid, "确认生成新版。", surface="chat")
            records.append(_turn_record("confirm revision", "确认生成新版。", followup))
            check(followup.failed is None, "revision confirmation succeeds", followup.failed)
            run2 = (followup.completed or {}).get("run_id")
        check(run2 is not None, "revision births run 2", (revise.completed or {}))
        run2_id = str(run2)
        status2 = await cs.wait_run_terminal(run2_id, timeout=600.0)
        check(status2 == "completed", "run 2 completes", status2)

        outputs2 = await _film_outputs(pid)
        check(len(outputs2) == 2, "the revised output is added while the original remains", [str(o.id) for o in outputs2])
        revised = outputs2[-1]
        check(str(revised.id) != str(original.id), "revision is a new output", [original.id, revised.id])
        check(original.archived_at is None and revised.archived_at is None, "both versions remain active", None)
        revised_path = await _download_output(revised, "v2-revised-second-scene.mp4")
        revised_probe = _probe_mp4(revised_path)
        _check_silent_spec(revised, "revised")
        check(revised_probe["audio"]["audible"] is False, "revised has no audible audio", revised_probe)

        spec1 = original.render_spec or {}
        spec2 = revised.render_spec or {}
        scenes1 = spec1.get("scenes") or []
        scenes2 = spec2.get("scenes") or []
        check(len(scenes1) == len(scenes2) == 4, "scene count stays unchanged", (len(scenes1), len(scenes2)))
        check(
            _scene_copy(scenes1[1]) != _scene_copy(scenes2[1]),
            "scene 2 changed",
            (_scene_copy(scenes1[1]), _scene_copy(scenes2[1])),
        )
        check(
            REPLACEMENT in " ".join(map(str, _scene_copy(scenes2[1]))),
            "scene 2 carries the replacement verbatim",
            _scene_copy(scenes2[1]),
        )
        for i in (0, 2, 3):
            check(
                scenes1[i] == scenes2[i],
                f"scene {i + 1} stays byte-identical",
                {"before": scenes1[i], "after": scenes2[i]},
            )
        steps2 = await _steps(run2_id)
        check(
            all((s.get("cost") or {}).get("units", {}).get("tts_chars", 0) == 0 for s in steps2),
            "run 2 records zero TTS units",
            [s.get("cost") for s in steps2],
        )
        check(await _narration_count(pid) == 0, "no narration reuse rows were created", None)
        facts["run2"] = {
            "id": run2_id,
            "status": status2,
            "output_id": str(revised.id),
            "path": str(revised_path),
            "probe": revised_probe,
            "steps": steps2,
            "scene_copies": [_scene_copy(s) for s in scenes2],
            "scene_frames": [s.get("frames") for s in scenes2],
            "music": spec2.get("music"),
        }
        facts["narration_rows"] = 0
        await _consume_trigger(ctx, str((revise.completed or {}).get("conversation_id")), run2_id)

        facts["conversation_usage"] = await _usage_rows(user_id)
        facts["ledger"] = await _ledger_rows(user_id)
        facts["runs_total"] = len(await _runs(pid))
        facts["outputs_total"] = len(await _film_outputs(pid))
        return 0
    finally:
        await ctx.close()
        lines = ["# T2a text-film acceptance transcript", ""]
        for r in records:
            lines.extend(
                [
                    f"## {r['label']}",
                    "",
                    f"**User:** {r['user']}",
                    "",
                    f"terminal={r['terminal']} run_id={r['run_id']} failed={r['failed']}",
                    "",
                    "**Assistant:**",
                    "",
                    r["assistant"],
                    "",
                    "**Activity:**",
                    "",
                    "```json",
                    json.dumps(r["activity"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        TRANSCRIPT.write_text("\n".join(lines), encoding="utf-8")
        FACTS_JSON.write_text(json.dumps(facts, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

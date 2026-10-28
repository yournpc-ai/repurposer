"""B-VI narration diagnostic journey; keeps its own project and raw evidence."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.editing.store import content_of
from app.models.schemas import WorkflowStatus
from app.models.tables import (
    Composition,
    CompositionVersion,
    ConversationUsage,
    CreditTransaction,
    Output,
    VideoNarration,
    WorkflowRun,
    WorkflowStep,
)
from scripts.chat_scenarios import Ctx, make_user, topup_wallet

ROOT = Path("/Users/sylas/repurposer")
OUT = ROOT / "artifacts" / "video-project-b" / "b-vi-narration"
SESSION = OUT / "session.json"
TERMINAL = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}


def load() -> dict:
    return json.loads(SESSION.read_text())


def save(value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def dump(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def ctx_for(session: dict) -> Ctx:
    return Ctx(UUID(session["user_id"]), keep=True)


async def chat(session: dict, stage: str, message: str) -> dict:
    ctx = ctx_for(session)
    try:
        completed = await ctx.chat(session["project_id"], message)
        dump(f"{stage}.json", completed)
        session["conversation_id"] = completed["conversation_id"]
        session["last_stage"] = stage
        session["last_run_id"] = completed.get("run_id")
        save(session)
        assistant = completed["assistant_message"]
        print(json.dumps({
            "stage": stage,
            "run_id": completed.get("run_id"),
            "assistant": assistant.get("content"),
            "blocks": assistant.get("blocks"),
        }, ensure_ascii=False, indent=2))
        return completed
    finally:
        await ctx.close()


async def latest_storyboard(session: dict) -> tuple[dict, dict, dict]:
    ctx = ctx_for(session)
    try:
        messages = await ctx.messages(session["conversation_id"])
        candidates = [
            (message, block)
            for message in messages
            for block in message.get("blocks") or []
            if block.get("kind") == "video_storyboard"
        ]
        if not candidates:
            raise RuntimeError("no video_storyboard block")
        message, block = candidates[-1]
        response = await ctx.client.get(
            f"/chat/video/versions/{block['composition_version_id']}/storyboard"
        )
        response.raise_for_status()
        return message, block, response.json()
    finally:
        await ctx.close()


async def ack(session: dict, *, expect_run: bool | None = None) -> None:
    message, block, payload = await latest_storyboard(session)
    dump(f"storyboard-v{block['version']}.json", payload)
    ctx = ctx_for(session)
    try:
        response = await ctx.client.post(
            f"/chat/messages/{message['id']}/video-presentation",
            json={
                "composition_version_id": block["composition_version_id"],
                "presentation_digest": block["presentation_digest"],
            },
        )
        response.raise_for_status()
        result = response.json()
        session["last_run_id"] = result.get("run_id")
        save(session)
        if expect_run is not None:
            assert bool(result.get("run_id")) is expect_run, result
        print(json.dumps({"ack": result, "version": block["version"]}, ensure_ascii=False, indent=2))
    finally:
        await ctx.close()


async def wait_terminal(session: dict, timeout: float = 600) -> str:
    run_id = session.get("last_run_id")
    if not run_id:
        return "NO_RUN"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, UUID(run_id))
            if run is not None and run.status in TERMINAL:
                print(f"run {run_id}: {run.status}")
                return str(run.status)
        await asyncio.sleep(2)
    raise TimeoutError(f"run {run_id} did not settle")


async def evidence(session: dict) -> None:
    project_id = UUID(session["project_id"])
    user_id = UUID(session["user_id"])
    async with AsyncSessionLocal() as db:
        runs = list((await db.scalars(select(WorkflowRun).where(
            WorkflowRun.project_id == project_id
        ).order_by(WorkflowRun.created_at))).all())
        run_ids = [run.id for run in runs]
        steps = list((await db.scalars(select(WorkflowStep).where(
            WorkflowStep.run_id.in_(run_ids)
        ).order_by(WorkflowStep.created_at))).all()) if run_ids else []
        outputs = list((await db.scalars(select(Output).where(
            Output.project_id == project_id
        ).order_by(Output.created_at))).all())
        versions = list((await db.scalars(select(CompositionVersion).join(
            Composition, CompositionVersion.composition_id == Composition.id
        ).where(Composition.origin_project_id == project_id).order_by(CompositionVersion.created_at))).all())
        narrations = list((await db.scalars(select(VideoNarration).where(
            VideoNarration.user_id == user_id
        ).order_by(VideoNarration.created_at))).all())
        usage = list((await db.scalars(select(ConversationUsage).where(
            ConversationUsage.project_id == project_id
        ).order_by(ConversationUsage.created_at))).all())
        ledger = list((await db.scalars(select(CreditTransaction).where(
            CreditTransaction.user_id == user_id
        ).order_by(CreditTransaction.created_at))).all())
        value = {
            "project_id": str(project_id),
            "runs": [{
                "id": str(run.id), "status": str(run.status), "context": run.context,
                "created_at": run.created_at,
            } for run in runs],
            "steps": [{
                "id": str(step.id), "run_id": str(step.run_id), "kind": step.kind,
                "status": step.status, "attempt": step.attempt, "estimate": step.estimate,
                "cost": step.cost, "spec": step.spec, "error": step.error,
            } for step in steps],
            "outputs": [{
                "id": str(output.id), "status": str(output.render_status),
                "workflow_step_id": str(output.workflow_step_id),
                "composition_id": str(output.composition_id),
                "composition_version_id": str(output.composition_version_id),
                "archived_at": output.archived_at, "files": output.files,
                "payload": output.payload, "render_spec": output.render_spec,
                "render_error": output.render_error,
            } for output in outputs],
            "versions": [{
                "id": str(version.id), "version": version.version,
                "content_digest": version.content_digest,
                "content": content_of(version).model_dump(mode="json"),
            } for version in versions],
            "narrations": [{
                "content_hash": row.content_hash, "text": row.text, "status": row.status,
                "voice_id": row.voice_id, "language": row.language,
                "storage_key": row.storage_key, "audio_digest": row.audio_digest,
                "duration_s": row.duration_s, "subtitles": row.subtitles,
                "usage_characters": row.usage_characters, "trace_id": row.trace_id,
                "error": row.error,
            } for row in narrations],
            "conversation_usage": [{
                "prompt_tokens": row.prompt_tokens, "completion_tokens": row.completion_tokens,
                "cost_usd": float(row.cost_usd), "model": row.model,
            } for row in usage],
            "credit_transactions": [{
                "kind": row.kind, "amount": row.amount, "ref": row.ref,
                "idempotency_key": row.idempotency_key,
            } for row in ledger],
        }
        dump("evidence.json", value)
        print(json.dumps({
            "runs": [(str(run.id), str(run.status)) for run in runs],
            "outputs": [(str(o.id), str(o.render_status), str(o.composition_version_id)) for o in outputs],
            "versions": [version.version for version in versions],
            "narration_originals": [(row.text, row.status, row.duration_s, row.usage_characters) for row in narrations],
            "conversation_usd": sum(float(row.cost_usd) for row in usage),
        }, ensure_ascii=False, indent=2, default=str))


async def refresh(session: dict) -> None:
    ctx = ctx_for(session)
    try:
        before = await ctx.runs(session["project_id"])
        messages = await ctx.messages(session["conversation_id"])
        blocks = [block for message in messages for block in message.get("blocks") or []
                  if block.get("kind") == "video_storyboard"]
        assert blocks
        after = await ctx.runs(session["project_id"])
        assert len(before) == len(after)
        dump("refresh-replay.json", {
            "runs_before": len(before), "runs_after": len(after), "storyboard_blocks": blocks,
        })
        print(f"refresh retained {len(blocks)} storyboard versions and {len(after)} Runs")
    finally:
        await ctx.close()


async def main() -> None:
    stage = sys.argv[1]
    if stage == "design":
        user_id = await make_user()
        await topup_wallet(user_id)
        session = {"user_id": str(user_id)}
        ctx = ctx_for(session)
        try:
            await ctx.set_confirmation(execution="auto", credits="auto")
            session["project_id"] = await ctx.new_project("B-VI 两幕旁白闭环")
            save(session)
        finally:
            await ctx.close()
        await chat(session, stage,
            "设计一支8秒、16:9的两幕MG短片。第一幕0到4秒，屏上标题是「问题」，准确旁白是「先看问题。」；第二幕4到8秒，屏上标题是「答案」，准确旁白是「再看答案。」。只使用这两句中文旁白，不改写、不增删；使用现有声音和背景音乐。先完整呈现首稿供我审阅，不要制作。")
        return
    session = load()
    if stage == "ack_first":
        await ack(session, expect_run=False)
    elif stage == "produce":
        await chat(session, stage, "开始制作刚才已经完整审阅的分镜，保持两幕剪切点和两句旁白不变。")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "caption":
        await chat(session, stage,
            "只把第一幕的人工字幕改为「先看挑战。」，不要改第一幕旁白「先看问题。」，不要改其他内容，也不要制作。保存并呈现这个版本。")
        await ack(session, expect_run=False)
        await evidence(session)
    elif stage == "revise":
        await chat(session, stage,
            "只把第二幕旁白改为「答案在这里。」，第一幕人工字幕「先看挑战。」和旁白「先看问题。」必须保持不变；所有画面、音乐和两幕剪切点不变。制作并交付这个新版本。")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "conflict":
        await chat(session, stage,
            "只把第二幕旁白改为「这句旁白现在被刻意写得非常长，远远不可能在四秒钟的固定镜头里正常说完，因此必须明确告诉我冲突。」，不要删词、改写、截断或移动剪切点，其他内容不变，并尝试制作。")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "failed"
        await evidence(session)
    elif stage == "present_conflict":
        await chat(session, stage,
            "完整呈现刚刚已经保存的最新第4版分镜，不要改任何文字，也不要制作。")
        await ack(session, expect_run=False)
        await evidence(session)
    elif stage == "produce_conflict":
        await chat(session, stage,
            "按刚才完整审阅的第4版尝试制作；不要删词、改写、截断或移动剪切点。")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "failed"
        await evidence(session)
    elif stage == "refresh":
        await refresh(session)
    elif stage == "evidence":
        await evidence(session)
    elif stage == "wait":
        await wait_terminal(session)
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    asyncio.run(main())

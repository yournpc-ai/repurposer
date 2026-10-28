"""Drive one real Chat journey for the MiniMax image-v1 consumer.

This is a diagnostic driver, not a scenario-matrix family. It keeps the
project and writes raw SSE plus database evidence under artifacts/video-project-b/b-v/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import WorkflowStatus
from app.models.tables import (
    ConversationUsage,
    CreditTransaction,
    Output,
    WorkflowRun,
    WorkflowStep,
)
from scripts.chat_scenarios import Ctx, make_user, topup_wallet

ROOT = Path("/Users/sylas/repurposer")
OUT = ROOT / "artifacts" / "video-project-b" / "b-v"
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


async def wait_terminal(session: dict, timeout: float = 600) -> str:
    run_id = session.get("last_run_id")
    if not run_id:
        return "NO_RUN"
    async def poll() -> str:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, UUID(run_id))
            if run is not None and run.status in TERMINAL:
                return str(run.status)
        return "PENDING"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        status = await poll()
        if status != "PENDING":
            print(f"run {run_id}: {status}")
            return status
        await asyncio.sleep(2)
    raise TimeoutError(f"run {run_id} did not settle")


async def ack(session: dict) -> None:
    ctx = ctx_for(session)
    try:
        if not session.get("conversation_id"):
            response = await ctx.conversation(session["project_id"])
            response.raise_for_status()
            session["conversation_id"] = response.json()["id"]
            save(session)
        messages = await ctx.messages(session["conversation_id"])
        candidates = [
            (message, block)
            for message in messages
            for block in message.get("blocks") or []
            if block.get("kind") == "video_storyboard"
        ]
        if not candidates:
            raise RuntimeError("no replayed video_storyboard block found")
        message, block = candidates[-1]
        version_id = block["composition_version_id"]
        read = await ctx.client.get(f"/chat/video/versions/{version_id}/storyboard")
        read.raise_for_status()
        payload = read.json()
        generator_clips = [
            clip
            for scene in payload["storyboard"]["scenes"]
            for clip in scene["clips"]
            if clip["object_kind"] == "generator"
        ]
        assert all(clip["runtime"] == "image-v1" for clip in generator_clips)
        assert all(clip["provider"] == "minimax" and clip["model"] == "image-01" for clip in generator_clips)
        assert all(clip["prompt"] for clip in generator_clips)
        dump(f"storyboard-v{block['version']}.json", payload)
        response = await ctx.client.post(
            f"/chat/messages/{message['id']}/video-presentation",
            json={
                "composition_version_id": version_id,
                "presentation_digest": block["presentation_digest"],
            },
        )
        response.raise_for_status()
        result = response.json()
        session["last_run_id"] = result.get("run_id")
        save(session)
        print(json.dumps({
            "ack": result,
            "version": block["version"],
            "generator_requests": [
                {key: clip.get(key) for key in ("runtime", "provider", "model", "prompt", "output", "program_digest")}
                for clip in generator_clips
            ],
        }, ensure_ascii=False, indent=2))
    finally:
        await ctx.close()


async def evidence(session: dict) -> None:
    project_id = UUID(session["project_id"])
    async with AsyncSessionLocal() as db:
        runs = list((await db.scalars(
            select(WorkflowRun).where(WorkflowRun.project_id == project_id).order_by(WorkflowRun.created_at)
        )).all())
        run_ids = [run.id for run in runs]
        steps = list((await db.scalars(
            select(WorkflowStep).where(WorkflowStep.run_id.in_(run_ids)).order_by(WorkflowStep.created_at)
        )).all()) if run_ids else []
        outputs = list((await db.scalars(
            select(Output).where(Output.project_id == project_id).order_by(Output.created_at)
        )).all())
        ledger = list((await db.scalars(
            select(CreditTransaction).where(CreditTransaction.user_id == UUID(session["user_id"])).order_by(CreditTransaction.created_at)
        )).all())
        usage = list((await db.scalars(
            select(ConversationUsage).where(ConversationUsage.project_id == project_id).order_by(ConversationUsage.created_at)
        )).all())
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
            "credit_transactions": [{
                "id": str(row.id), "kind": row.kind, "amount": row.amount,
                "ref": row.ref, "idempotency_key": row.idempotency_key,
            } for row in ledger],
            "conversation_usage": [{
                "prompt_tokens": row.prompt_tokens, "completion_tokens": row.completion_tokens,
                "cost_usd": float(row.cost_usd), "model": row.model,
            } for row in usage],
        }
        dump("evidence.json", value)
        print(json.dumps({
            "runs": [(str(run.id), str(run.status), (run.context or {}).get("regenerate_media", False)) for run in runs],
            "outputs": [(str(o.id), str(o.render_status), str(o.composition_version_id), o.archived_at) for o in outputs],
            "image_units": [(s.kind, s.status, (s.cost or {}).get("units")) for s in steps],
            "conversation_usd": sum(float(row.cost_usd) for row in usage),
        }, ensure_ascii=False, indent=2, default=str))


async def refresh(session: dict) -> None:
    ctx = ctx_for(session)
    try:
        before = await ctx.runs(session["project_id"])
        messages = await ctx.messages(session["conversation_id"])
        candidates = [
            (message, block)
            for message in messages
            for block in message.get("blocks") or []
            if block.get("kind") == "video_storyboard"
        ]
        blocks = [block for _, block in candidates]
        assert blocks, "refresh lost all storyboard references"
        latest_message, latest = candidates[-1]
        read = await ctx.client.get(f"/chat/video/versions/{latest['composition_version_id']}/storyboard")
        read.raise_for_status()
        payload = read.json()
        assert any(
            clip["object_kind"] == "generator" and clip.get("prompt")
            for scene in payload["storyboard"]["scenes"] for clip in scene["clips"]
        )
        replay_ack = await ctx.client.post(
            f"/chat/messages/{latest_message['id']}/video-presentation",
            json={
                "composition_version_id": latest["composition_version_id"],
                "presentation_digest": latest["presentation_digest"],
            },
        )
        replay_ack.raise_for_status()
        ack_result = replay_ack.json()
        assert not ack_result.get("accepted") and not ack_result.get("run_id")
        after = await ctx.runs(session["project_id"])
        assert len(before) == len(after)
        dump("refresh-replay.json", {"runs_before": len(before), "runs_after": len(after), "ack_replay": ack_result, "blocks": blocks, "latest_read": payload})
        print(f"refresh retained {len(blocks)} storyboard references; ACK replay did not start work; Run count stayed {len(after)}")
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
            session["project_id"] = await ctx.new_project("B-V generated image")
            save(session)
        finally:
            await ctx.close()
        await chat(session, stage,
            "Create a 4-second 16:9 video. Use an AI-generated still background of a minimalist abstract sunrise over layered mountains, with no text in the image. Add the separate editable native title 'Ideas take shape'. Review the storyboard first; do not produce yet.")
        return
    session = load()
    if stage == "redesign":
        await chat(session, stage,
            "Create a 4-second 16:9 video. Use an AI-generated still background of a minimalist abstract sunrise over layered mountains, with no text in the image. Add the separate editable native title 'Ideas take shape'. Review the storyboard first; do not produce yet.")
    elif stage == "ack":
        await ack(session)
    elif stage == "produce":
        await chat(session, stage, "Start production for the storyboard I just reviewed.")
        assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "revise":
        await chat(session, stage,
            "Change only the independent native title to 'Ideas in focus'. Save this revision and produce the revised video; do not regenerate the AI image.")
        await ack(session)
        if session.get("last_run_id"):
            assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "present":
        await chat(session, stage,
            "Show the saved revised storyboard card for my review. Do not start production yet.")
        await ack(session)
    elif stage == "produce_revision":
        await chat(session, stage,
            "Produce the revised storyboard I just reviewed, and do not regenerate the AI image.")
        if session.get("last_run_id"):
            assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "regenerate":
        await chat(session, stage,
            "Keep the title and every other content choice unchanged, but explicitly regenerate the AI background image and deliver the video again.")
        if session.get("last_run_id"):
            assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "produce_latest":
        await chat(session, stage,
            "Produce the same reviewed storyboard again without regenerating the AI image.")
        if session.get("last_run_id"):
            assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "wait":
        await wait_terminal(session)
        await evidence(session)
    elif stage == "evidence":
        await evidence(session)
    elif stage == "refresh":
        await refresh(session)
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    asyncio.run(main())

"""Normal-Chat driver for the exact-Output content-review journey."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import WorkflowStatus
from app.models.tables import (
    CompositionVersion,
    ConversationUsage,
    CreditTransaction,
    Output,
    WorkflowRun,
    WorkflowStep,
)
from scripts.chat_scenarios import Ctx

ROOT = Path("/Users/sylas/repurposer")
OUT = ROOT / "artifacts" / "video-project-b" / "content-review"
SESSION = OUT / "session.json"
INITIAL = {
    "user_id": "e1ae7e64-58c1-43ed-9660-806ad3843ce8",
    "project_id": "432c0cd3-c0c2-4156-960e-777ae9f168d6",
    "conversation_id": "3f35c3f6-bd75-401a-9399-c28e862728f8",
}
TERMINAL = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}


def load() -> dict:
    if not SESSION.exists():
        save(INITIAL)
    return json.loads(SESSION.read_text())


def save(value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def dump(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def ctx_for(session: dict) -> Ctx:
    ctx = Ctx(UUID(session["user_id"]), keep=True)
    ctx.client.timeout = httpx.Timeout(600.0)
    return ctx


async def send(session: dict, label: str, message: str, output_id: str | None) -> dict:
    ctx = ctx_for(session)
    try:
        extra = {"mentions": [{"type": "output", "id": output_id, "label": "delivered video"}]} if output_id else {}
        turn = await ctx.chat(session["project_id"], message, **extra)
        dump(f"{label}.json", turn)
        session["conversation_id"] = turn["conversation_id"]
        session["last_run_id"] = turn.get("run_id")
        session["last_stage"] = label
        save(session)
        print(json.dumps({
            "label": label,
            "run_id": turn.get("run_id"),
            "assistant": (turn.get("assistant_message") or {}).get("content"),
            "blocks": (turn.get("assistant_message") or {}).get("blocks"),
        }, ensure_ascii=False, indent=2))
        return turn
    finally:
        await ctx.close()


async def latest_storyboard(session: dict) -> tuple[dict, dict, dict]:
    ctx = ctx_for(session)
    try:
        messages = await ctx.messages(session["conversation_id"])
        message, block = [
            (message, block)
            for message in messages
            for block in message.get("blocks") or []
            if block.get("kind") == "video_storyboard"
        ][-1]
        response = await ctx.client.get(f"/chat/video/versions/{block['composition_version_id']}/storyboard")
        response.raise_for_status()
        return message, block, response.json()
    finally:
        await ctx.close()


async def ack(session: dict, expect_run: bool) -> None:
    message, block, payload = await latest_storyboard(session)
    dump(f"storyboard-v{block['version']}.json", payload)
    ctx = ctx_for(session)
    try:
        response = await ctx.client.post(
            f"/chat/messages/{message['id']}/video-presentation",
            json={"composition_version_id": block["composition_version_id"], "presentation_digest": block["presentation_digest"]},
        )
        response.raise_for_status()
        result = response.json()
        session["last_run_id"] = result.get("run_id")
        save(session)
        assert bool(result.get("run_id")) is expect_run, result
        print(json.dumps({"ack": result, "version": block["version"]}, indent=2))
    finally:
        await ctx.close()


async def wait_terminal(session: dict) -> None:
    run_id = session.get("last_run_id")
    if not run_id:
        print("NO_RUN")
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 900
    while loop.time() < deadline:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, UUID(run_id))
            if run is not None and run.status in TERMINAL:
                print(f"run {run_id}: {run.status}")
                if run.status != WorkflowStatus.COMPLETED:
                    raise RuntimeError(f"run failed: {run.context}")
                return
        await asyncio.sleep(2)
    raise TimeoutError(run_id)


async def replay(session: dict) -> None:
    ctx = ctx_for(session)
    try:
        messages = await ctx.messages(session["conversation_id"])
        results = await ctx.results(session["project_id"])
        runs = await ctx.runs(session["project_id"])
        dump("message-replay.json", messages)
        dump("results-replay.json", results)
        dump("runs-replay.json", runs)
        print(f"replayed {len(messages)} messages, {len(runs)} Runs")
    finally:
        await ctx.close()


async def evidence(session: dict) -> None:
    project_id, user_id = UUID(session["project_id"]), UUID(session["user_id"])
    async with AsyncSessionLocal() as db:
        outputs = list((await db.scalars(select(Output).where(Output.project_id == project_id).order_by(Output.created_at))).all())
        runs = list((await db.scalars(select(WorkflowRun).where(WorkflowRun.project_id == project_id).order_by(WorkflowRun.created_at))).all())
        run_ids = [run.id for run in runs]
        steps = list((await db.scalars(select(WorkflowStep).where(WorkflowStep.run_id.in_(run_ids)).order_by(WorkflowStep.created_at))).all())
        versions = list((await db.scalars(select(CompositionVersion).where(CompositionVersion.composition_id == UUID("2eb8f349-70c6-45c1-9474-efafe149dffc")).order_by(CompositionVersion.version))).all())
        usage = list((await db.scalars(select(ConversationUsage).where(ConversationUsage.project_id == project_id).order_by(ConversationUsage.created_at))).all())
        ledger = list((await db.scalars(select(CreditTransaction).where(CreditTransaction.user_id == user_id).order_by(CreditTransaction.created_at))).all())
        value = {
            "outputs": [{"id": output.id, "workflow_step_id": output.workflow_step_id, "composition_id": output.composition_id,
                "composition_version_id": output.composition_version_id, "render_status": output.render_status,
                "archived_at": output.archived_at, "files": output.files, "payload": output.payload,
                "quality": output.quality, "render_spec": output.render_spec} for output in outputs],
            "versions": [{"id": version.id, "version": version.version, "base_version_id": version.base_version_id,
                "content_digest": version.content_digest, "settings": version.settings, "sources": version.sources,
                "scenes": version.scenes, "timeline": version.timeline} for version in versions],
            "runs": [{"id": run.id, "status": run.status, "context": run.context} for run in runs],
            "steps": [{"id": step.id, "run_id": step.run_id, "kind": step.kind, "status": step.status,
                "attempt": step.attempt, "estimate": step.estimate, "cost": step.cost, "error": step.error} for step in steps],
            "conversation_usage": [{"cost_usd": row.cost_usd, "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens, "model": row.model} for row in usage],
            "credit_transactions": [{"kind": row.kind, "amount": row.amount, "ref": row.ref,
                "idempotency_key": row.idempotency_key} for row in ledger],
        }
        dump("evidence.json", value)
        print(json.dumps({"versions": [v.version for v in versions], "runs": [(str(r.id)[:8], str(r.status)) for r in runs],
            "outputs": [(str(o.id)[:8], str(o.composition_version_id)[:8], bool((o.quality or {}).get("content_review"))) for o in outputs],
            "conversation_usd": sum(float(row.cost_usd) for row in usage)}, default=str, indent=2))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["send", "ack", "wait", "replay", "evidence"])
    parser.add_argument("label", nargs="?")
    parser.add_argument("message", nargs="?")
    parser.add_argument("--output")
    parser.add_argument("--expect-run", action="store_true")
    args = parser.parse_args()
    session = load()
    if args.command == "send":
        assert args.label and args.message
        await send(session, args.label, args.message, args.output)
    elif args.command == "ack":
        await ack(session, args.expect_run)
    elif args.command == "wait":
        await wait_terminal(session)
        await evidence(session)
    elif args.command == "replay":
        await replay(session)
    else:
        await evidence(session)


if __name__ == "__main__":
    asyncio.run(main())

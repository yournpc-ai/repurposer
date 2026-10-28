"""Real Chat journey for the enhanced AgentVeil webpage-shot consumer."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

from app.editing.store import content_of
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetType, WorkflowStatus
from app.models.tables import (
    Asset,
    Composition,
    CompositionVersion,
    ConversationUsage,
    CreditTransaction,
    Output,
    SourceSnapshot,
    WorkflowRun,
    WorkflowStep,
    User,
)
from app.platform.auth import create_access_token
from scripts.chat_scenarios import Ctx, make_user, topup_wallet

ROOT = Path("/Users/sylas/repurposer")
OUT = ROOT / "artifacts" / "video-project-b" / "web-capture"
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
    ctx = Ctx(UUID(session["user_id"]), keep=True)
    ctx.client.timeout = httpx.Timeout(600.0)
    return ctx


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


async def ack(session: dict, *, expect_run: bool) -> None:
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
        assert bool(result.get("run_id")) is expect_run, result
        print(json.dumps({"ack": result, "version": block["version"]}, ensure_ascii=False, indent=2))
    finally:
        await ctx.close()


async def wait_terminal(session: dict, timeout: float = 900) -> str:
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
        assets = list((await db.scalars(select(Asset).where(
            Asset.project_id == project_id, Asset.type == AssetType.WEB_PAGE,
        ).order_by(Asset.created_at))).all())
        versions = list((await db.scalars(select(CompositionVersion).join(
            Composition, CompositionVersion.composition_id == Composition.id,
        ).where(Composition.origin_project_id == project_id).order_by(
            CompositionVersion.created_at,
        ))).all())
        contents = [content_of(version) for version in versions]
        snapshot_ids = {binding.snapshot_id for content in contents for binding in content.sources}
        snapshots = list((await db.scalars(select(SourceSnapshot).where(
            SourceSnapshot.id.in_(snapshot_ids),
        ))).all()) if snapshot_ids else []
        runs = list((await db.scalars(select(WorkflowRun).where(
            WorkflowRun.project_id == project_id,
        ).order_by(WorkflowRun.created_at))).all())
        run_ids = [run.id for run in runs]
        steps = list((await db.scalars(select(WorkflowStep).where(
            WorkflowStep.run_id.in_(run_ids),
        ).order_by(WorkflowStep.created_at))).all()) if run_ids else []
        outputs = list((await db.scalars(select(Output).where(
            Output.project_id == project_id,
        ).order_by(Output.created_at))).all())
        usage = list((await db.scalars(select(ConversationUsage).where(
            ConversationUsage.project_id == project_id,
        ).order_by(ConversationUsage.created_at))).all())
        ledger = list((await db.scalars(select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
        ).order_by(CreditTransaction.created_at))).all())
        value = {
            "project_id": str(project_id),
            "assets": [{
                "id": str(asset.id), "status": str(asset.processing_status),
                "error": asset.processing_error, "extracted_text": asset.extracted_text,
                "meta": asset.meta,
            } for asset in assets],
            "snapshots": [{
                "id": str(snapshot.id), "asset_id": str(snapshot.asset_id),
                "digest": snapshot.digest, "captured_at": snapshot.captured_at,
                "meta": snapshot.meta,
            } for snapshot in snapshots],
            "versions": [{
                "id": str(version.id), "version": version.version,
                "content_digest": version.content_digest,
                "content": content.model_dump(mode="json"),
            } for version, content in zip(versions, contents, strict=True)],
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
            "assets": [{
                "id": str(asset.id)[:8], "status": str(asset.processing_status),
                "text_chars": len(asset.extracted_text or ""),
                "body_lines": len(((asset.meta or {}).get("research") or {}).get("body") or []),
                "page": bool((asset.meta or {}).get("page")),
                "element_images": sum(
                    1 for shot in (asset.meta or {}).get("shots") or []
                    for element in shot.get("elements") or [] if element.get("image_key")
                ),
            } for asset in assets],
            "snapshots": [str(snapshot.id)[:8] for snapshot in snapshots],
            "versions": [version.version for version in versions],
            "runs": [(str(run.id)[:8], str(run.status)) for run in runs],
            "outputs": [(str(output.id)[:8], str(output.render_status)) for output in outputs],
            "conversation_usd": sum(float(row.cost_usd) for row in usage),
        }, ensure_ascii=False, indent=2, default=str))


async def refresh(session: dict) -> None:
    ctx = ctx_for(session)
    try:
        before = await ctx.runs(session["project_id"])
        messages = await ctx.messages(session["conversation_id"])
        blocks = [block for message in messages for block in message.get("blocks") or []
                  if block.get("kind") == "video_storyboard"]
        after = await ctx.runs(session["project_id"])
        assert len(before) == len(after)
        dump("refresh-replay.json", {
            "runs_before": len(before), "runs_after": len(after), "storyboard_blocks": blocks,
        })
        print(f"refresh retained {len(blocks)} storyboard versions and {len(after)} Runs")
    finally:
        await ctx.close()


async def browser(session: dict) -> None:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, UUID(session["user_id"]))
        assert user is not None
        token = create_access_token(user.id)
        user_json = json.dumps({"id": str(user.id), "email": user.email, "name": user.name})
    process = await asyncio.create_subprocess_exec(
        "node", str(ROOT / "scratch" / "bvi_browser_refresh.mjs"),
        f"http://localhost:3000/projects/{session['project_id']}",
        token, user_json, str(OUT / "browser"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    print(stdout.decode())
    if process.returncode:
        raise RuntimeError(f"browser journey failed with exit {process.returncode}")


async def main() -> None:
    stage = sys.argv[1]
    if stage == "design":
        user_id = await make_user()
        await topup_wallet(user_id)
        session = {"user_id": str(user_id)}
        ctx = ctx_for(session)
        try:
            await ctx.set_confirmation(execution="auto", credits="auto")
            session["project_id"] = await ctx.new_project("AgentVeil enhanced webpage shot")
            save(session)
        finally:
            await ctx.close()
        await chat(session, stage,
            "Use https://agentveil.dev/ to design an English website launch film. "
            "For the FIRST chapter walk, focus the camera on the real page heading "
            "“Don’t just stop the agent. Give it the next move.” and make that heading "
            "a clear close-up. Use the page’s real content for the other chapters. "
            "Present the complete first storyboard for my review; do not produce yet.")
        await evidence(session)
        return
    session = load()
    if stage == "direction":
        await chat(session, stage,
            "Keep that direction. Design and present the complete storyboard now, "
            "with the first chapter walk focused on the named real heading. Do not produce yet.")
        await evidence(session)
    elif stage == "ack_first":
        await ack(session, expect_run=False)
    elif stage == "camera":
        await chat(session, stage,
            "Make a targeted revision of the current storyboard with revise_video, not a "
            "redraft. Use focus_web on clip clp_chapter_1_walk_web with element_id s1e8 "
            "so the server recomputes the first chapter camera from the frozen real heading. "
            "Do not change any other content or the bound snapshots. Fully present the "
            "revision; do not produce yet.")
        await ack(session, expect_run=False)
        await evidence(session)
    elif stage == "produce":
        await chat(session, stage,
            "Start producing the storyboard I have just fully reviewed. Keep the first "
            "chapter’s camera target and all webpage material unchanged.")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "revise":
        await chat(session, stage,
            "Only change the FIRST chapter’s displayed chapter title to “Review the next move”. "
            "Do not change the webpage snapshots, the camera target, or any other content. "
            "Save and fully present this revision; do not produce yet.")
        await ack(session, expect_run=False)
        await evidence(session)
    elif stage == "reproduce":
        await chat(session, stage,
            "Produce the revised storyboard I have just fully reviewed. Reuse the unchanged "
            "webpage material and keep the first chapter’s camera target unchanged.")
        if session.get("last_run_id") is None:
            await ack(session, expect_run=True)
        assert await wait_terminal(session) == "completed"
        await evidence(session)
    elif stage == "refresh":
        await refresh(session)
    elif stage == "browser":
        await browser(session)
    elif stage == "evidence":
        await evidence(session)
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    asyncio.run(main())

"""Run event stream (CHAT_ARCH §8): SSE is a pushed read of DB state.

The single source of truth is the ``workflow_steps`` table — there is no
event store, no delivery guarantee, no replay. Reconnect = re-read the
current state (the snapshot frame makes that idempotent). The 1s tail is
enough at single-worker scale; a LISTEN/NOTIFY bridge can replace the poll
internally later WITHOUT changing the client contract.
"""

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user_required
from app.models.database import AsyncSessionLocal
from app.models.schemas import WorkflowStatus
from app.models.tables import Project, User, WorkflowRun, WorkflowStep
from app.pipeline.outputs import aggregate_run_summary, workflow_step_to_response

router = APIRouter()

_TERMINAL = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
_TAIL_INTERVAL = 1.0
_HEARTBEAT_INTERVAL = 15.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _step_frame(node: WorkflowStep) -> dict:
    return workflow_step_to_response(node).model_dump(mode="json")


def _hash(frame: dict) -> str:
    return hashlib.sha1(json.dumps(frame, sort_keys=True, default=str).encode()).hexdigest()


def _run_frame(run: WorkflowRun, nodes: list[WorkflowStep]) -> dict:
    frame = {
        "id": str(run.id),
        "status": run.status,
        "progress": run.progress,
        "error": run.error,
        # The overlay interleaves chat messages and run blocks by real time
        # (#5: the stream keeps chronological order), so the run needs its
        # anchor in every frame.
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if run.status in _TERMINAL:
        frame["summary"] = aggregate_run_summary(nodes)
    return frame


async def _load(run_id: UUID) -> tuple[WorkflowRun | None, list[WorkflowStep]]:
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            return None, []
        nodes = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == run_id)
                    .order_by(WorkflowStep.seq)
                )
            )
            .scalars()
            .all()
        )
        # Detach from the session — frames are read-only snapshots.
        db.expunge_all()
        return run, nodes


@router.get("/{run_id}/events")
async def run_events(
    run_id: UUID,
    request: Request,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> StreamingResponse:
    """Stream a run's state: snapshot → step.updated / run.updated diffs →
    close on terminal state. 15s heartbeat comment frames keep proxies alive.

    Disconnect cleanup is cancel-based, same posture as the chat SSE: the
    ASGI server cancels the generator when the client goes away (any yield
    after that raises) — no ``request.is_disconnected()`` polling, which the
    middleware stack's receive-channel bookkeeping breaks."""
    run = await db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    project = await db.get(Project, run.project_id)
    if project is None or str(project.user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def stream() -> AsyncGenerator[str, None]:
        step_hashes: dict[str, str] = {}
        run_sig: str | None = None

        run, nodes = await _load(run_id)
        if run is None:
            return
        frames = [_step_frame(n) for n in nodes]
        for frame in frames:
            step_hashes[frame["id"]] = _hash(frame)
        run_frame = _run_frame(run, nodes)
        run_sig = _hash(run_frame)
        yield _sse("run.snapshot", {"run": run_frame, "steps": frames})

        last_beat = time.monotonic()
        while True:
            await asyncio.sleep(_TAIL_INTERVAL)

            run, nodes = await _load(run_id)
            if run is None:
                return
            for node in nodes:
                frame = _step_frame(node)
                digest = _hash(frame)
                if step_hashes.get(frame["id"]) != digest:
                    step_hashes[frame["id"]] = digest
                    yield _sse("step.updated", frame)

            run_frame = _run_frame(run, nodes)
            digest = _hash(run_frame)
            if digest != run_sig:
                run_sig = digest
                yield _sse("run.updated", run_frame)

            now = time.monotonic()
            if now - last_beat >= _HEARTBEAT_INTERVAL:
                last_beat = now
                yield ": heartbeat\n\n"

            if run.status in _TERMINAL:
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

"""Real user journeys against a live API and worker.

Every creative request enters through the ordinary HTTP Chat surface. Assertions
cover user-visible results and the persisted world facts needed to verify them;
they do not lock LLM wording or duplicate deterministic core API tests.

Run from apps/api:
    uv run python test/journeys/chat.py
    uv run python test/journeys/chat.py --only builtin_promo_skill
    uv run python test/journeys/chat.py --only lost_user,consultation
    uv run python test/journeys/chat.py --keep
    JOURNEY_API_BASE=http://127.0.0.1:8000/api/v1 uv run python test/journeys/chat.py

The live API, current migrations, a fresh dev worker and provider quota are
required. Journeys that explicitly produce media spend money and need separate
authorization. Fixture media is copied to the scenario/ storage prefix before
project deletion can unlink it. Browser interaction and final audiovisual
quality remain real-UI acceptance, not something this runner claims to prove.
"""

import argparse
import asyncio
import itertools
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import delete, func, select, update  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.pipeline.orchestrator import maybe_finalize_run  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    Composition,
    CompositionVersion,
    Conversation,
    CreditTransaction,
    GraphNode,
    Journey,
    Message,
    Operation,
    Output,
    Project,
    SkillVersion,
    SourceSnapshot,
    User,
    UserSkill,
    Wallet,
    WorkflowRun,
    WorkflowStep,
    now_utc,
)
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    MaterialUnderstanding,
    RenderStatus,
    WorkflowStatus,
)
from app.platform.auth import create_access_token  # noqa: E402
from app.platform.billing import (  # noqa: E402
    CreditsInsufficientError,
    check_hold,
    get_or_create_wallet,
)

BASE = os.getenv("JOURNEY_API_BASE", "http://127.0.0.1:8000/api/v1")
TIMEOUT = httpx.Timeout(300.0)  # plan-path turns are real LLM calls (remix turns with a real transcript excerpt have crossed 180s on a slow provider)


class JourneyFailure(AssertionError):
    pass


class ExternalServiceBlocked(RuntimeError):
    pass


def check(condition: bool, label: str, detail: object = "") -> None:
    if not condition:
        raise JourneyFailure(f"{label}" + (f" — {detail}" if detail else ""))


class StreamTurn(NamedTuple):
    """One SSE chat turn's full frame record (Ctx.chat_stream)."""

    deltas: list[str]
    thinking: list[dict]
    previews: list[dict]
    completed: dict | None
    failed: dict | None
    # ADR-085 interim_prose frames: each entry is one interim_prose's full text.
    interim_prose_rows: list[str]
    # Parallel to interim_prose_rows: True = the frame arrived BEFORE any read
    # activity settled — the waiter seat (ADR-104: pre-read speech is legal
    # waiter talk; with the pre-execute emission seat the wire order makes
    # the discrimination exact — a waiter strictly precedes its read's
    # settle frame, result talk strictly follows its predecessor read's
    # settle).
    interim_prose_pre_read: list[bool]
    # ADR-087 §3 activity frames: the append-oriented work stream — each
    # entry is one assistant.activity payload {activity_id, seq, kind,
    # status, key}.
    activities: list[dict]
    # Every data frame as {event, data} in ARRIVAL order — the per-type
    # lists lose the cross-type order, and the ordering is the forensic
    # surface for stream-law failures.
    raw_events: list[dict]
    # Transcript array mirror (ADR-108 §3): the assistant.row.append /
    # assistant.row.update frames in arrival order — append fixes a row's
    # array position, update mutates it in place.
    row_events: list[dict]


class Ctx:
    """Per-run context: an authed HTTP client plus cleanup bookkeeping."""

    def __init__(self, user_id: uuid.UUID, keep: bool) -> None:
        self.client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
            timeout=TIMEOUT,
        )
        self.user_id = user_id
        self.keep = keep
        self.project_ids: list[str] = []

    async def close(self) -> None:
        await self.client.aclose()

    async def new_project(self, title: str) -> str:
        res = await self.client.post(
            "/projects", json={"title": title, "event_name": ""}
        )
        check(res.status_code == 201, "create project", res.text)
        pid = res.json()["id"]
        self.project_ids.append(pid)
        return pid

    async def chat(self, pid: str, message: str, **extra: object) -> dict:
        res = await self.client.post(
            "/chat",
            json={"project_id": pid, "message": message, **extra},
        )
        if res.status_code in {502, 503, 504}:
            raise ExternalServiceBlocked(f"Chat provider/storage unavailable: HTTP {res.status_code} {res.text[:300]}")
        check(res.status_code == 201, f"/chat {message[:30]!r}", res.text)
        turn = res.json()
        # journey 公共断言（dock 形态——每个回合信封自动携带）。
        check_dock_shape(turn.get("assistant_message") or {}, f"/chat {message[:30]!r}")
        return turn

    async def chat_stream(self, pid: str, message: str, **extra: object) -> "StreamTurn":
        """One SSE chat turn (Accept: text/event-stream) — the FULL frame
        record: ordered prose deltas, the assistant.thinking phase frames,
        the question.preview frames (pre-execution, rolled back on a flip),
        the turn.completed envelope, and turn.failed if any.

        journey 公共断言（ADR-114 §3.2）在回合成功收官时自动携带：SSE 线
        格式律 / Activity 帧形态 / interim_prose 形态 / 选项问预览帧律 /
        dock 形态。"""
        deltas: list[str] = []
        thinking: list[dict] = []
        previews: list[dict] = []
        interim_prose_rows: list[str] = []
        interim_prose_pre_read: list[bool] = []
        activities: list[dict] = []
        raw_events: list[dict] = []
        row_events: list[dict] = []
        read_settled_seen = False
        completed: dict | None = None
        failed: dict | None = None
        async with self.client.stream(
            "POST",
            "/chat",
            json={"project_id": pid, "message": message, **extra},
            headers={"Accept": "text/event-stream"},
        ) as res:
            if res.status_code in {502, 503, 504}:
                raise ExternalServiceBlocked(f"Chat stream unavailable: HTTP {res.status_code}")
            check(res.status_code == 200, f"/chat stream {message[:30]!r}", res.status_code)
            event = ""
            async for line in res.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    raw_events.append({"event": event, "data": payload})
                    if event == "assistant.delta":
                        deltas.append(payload["text"])
                    elif event == "assistant.thinking":
                        thinking.append(payload)
                    elif event == "question.preview":
                        previews.append(payload)
                    elif event == "assistant.interim_prose":
                        interim_prose_rows.append(payload["text"])
                        interim_prose_pre_read.append(not read_settled_seen)
                    elif event == "assistant.activity":
                        activities.append(payload)
                        if payload.get("kind") == "read" and payload.get(
                            "status"
                        ) in ("completed", "failed", "cancelled"):
                            read_settled_seen = True
                    elif event == "assistant.row.append":
                        row_events.append({"op": "append", **payload})
                    elif event == "assistant.row.update":
                        row_events.append({"op": "update", **payload})
                    elif event == "turn.completed":
                        completed = payload
                    elif event == "turn.failed":
                        failed = payload
        turn = StreamTurn(
            deltas=deltas,
            thinking=thinking,
            previews=previews,
            completed=completed,
            failed=failed,
            interim_prose_rows=interim_prose_rows,
            interim_prose_pre_read=interim_prose_pre_read,
            activities=activities,
            raw_events=raw_events,
            row_events=row_events,
        )
        if failed is not None and completed is None:
            raise ExternalServiceBlocked(f"Chat stream failed before an envelope: {failed}")
        if completed is not None:
            check_turn_stream_laws(turn, f"/chat stream {message[:30]!r}")
        return turn

    async def answer(self, question_id: str, body: dict) -> httpx.Response:
        return await self.client.post(f"/chat/messages/{question_id}/answer", json=body)

    async def set_confirmation(self, *, execution: str, credits: str) -> None:
        """ADR-117 D1: pin the turn's confirmation regime for the journey
        (PUT /auth/settings one-key merge — each leg explicit, never a
        partial assumption)."""
        res = await self.client.put(
            "/auth/settings",
            json={"confirm_execution": execution, "confirm_credits": credits},
        )
        check(res.status_code == 200, "PUT /auth/settings", res.text)
        body = res.json()
        check(
            body.get("confirm_execution") == execution
            and body.get("confirm_credits") == credits,
            "the settings echo the stamped prefs",
            body,
        )

    async def conversation(self, pid: str, **params: object) -> httpx.Response:
        """GET /chat/conversation — 200 with pending_question, or 404 pre-chat."""
        return await self.client.get(
            "/chat/conversation", params={"project_id": pid, **params}
        )

    async def messages(self, conversation_id: str) -> list[dict]:
        res = await self.client.get(f"/chat/conversations/{conversation_id}/messages")
        check(res.status_code == 200, "GET conversation messages", res.text)
        return res.json()["items"]

    async def skills(self) -> list[dict]:
        res = await self.client.get("/chat/skills")
        check(res.status_code == 200, "GET chat Skills", res.text)
        return res.json()["items"]

    async def video_storyboard(self, version_id: str, scrub: dict | None = None) -> dict:
        res = await self.client.get(
            f"/chat/video/versions/{version_id}/storyboard",
            params={"scrub": json.dumps(scrub)} if scrub is not None else None,
        )
        check(res.status_code == 200, "GET canonical video storyboard", res.text)
        return res.json()

    async def acknowledge_video_presentation(self, turn: dict) -> tuple[dict, dict]:
        """The browser's presentation ACK after the exact static storyboard DTO.

        A pre-production reply never receives a complete-video preview. When
        the persisted block names a Scrub target, only that local projection
        may arrive, pinned to the same immutable version and content digest.
        """
        message = turn.get("assistant_message") or {}
        blocks = [
            block for block in message.get("blocks") or []
            if block.get("kind") == "video_storyboard"
        ]
        check(len(blocks) == 1,
              "the design/revision reply carries exactly one storyboard block",
              {"blocks": message.get("blocks"), "content": message.get("content")})
        block = blocks[0]
        version_id = str(block["composition_version_id"])
        read = await self.video_storyboard(version_id, block.get("scrub"))
        check(read.get("base_ref", {}).get("composition_version_id") == version_id
              and read.get("content_digest") == block.get("content_digest")
              and read.get("presentation_digest") == block.get("presentation_digest"),
              "the public DTO matches the presenting message's exact version",
              {"block": block, "read": {k: read.get(k) for k in (
                  "composition_version_id", "content_digest", "presentation_digest")}})
        scrub = block.get("scrub")
        if scrub is None:
            check("video_preview" not in read and "preview_required" not in read,
                  "a default storyboard never ships a dynamic full-film spec", read)
        else:
            preview = read.get("video_preview") or {}
            check(preview.get("status") in {"ready", "pending_media"},
                  "an explicitly requested Scrub is ready or honestly pending media",
                  preview)
            check((preview.get("scope") or {}).get("target") == scrub,
                  "the preview is exactly the persisted local Scrub target", preview)
            if preview.get("status") == "ready":
                spec = preview.get("video_spec") or {}
                check(spec.get("provenance") == read["base_ref"]
                      and spec.get("duration_frames", 0) > 0
                      and bool(spec.get("tracks")),
                      "the scoped spec pins the presented version and digest",
                      {"provenance": spec.get("provenance"), "base_ref": read["base_ref"]})
            else:
                check(bool(preview.get("pending")),
                      "pending Scrub names its actual unfinished media", preview)
        res = await self.client.post(
            f"/chat/messages/{message['id']}/video-presentation",
            json={
                "composition_version_id": version_id,
                "presentation_digest": read["presentation_digest"],
            },
        )
        check(res.status_code == 200, "ACK the completed video presentation", res.text)
        ack = res.json()
        check(ack.get("accepted") is True,
              "the current presentation receipt is accepted", ack)
        return read, ack

    async def results(self, pid: str) -> dict:
        res = await self.client.get(f"/projects/{pid}/results")
        check(res.status_code == 200, "GET results", res.text)
        return res.json()

    async def graph(self, pid: str) -> dict:
        """The persistent graph's one read frame (ADR-057 K3 直读端点)."""
        res = await self.client.get(f"/projects/{pid}/graph")
        check(res.status_code == 200, "GET project graph", res.text)
        return res.json()

    async def runs(self, pid: str) -> list[dict]:
        res = await self.client.get(f"/projects/{pid}/runs")
        check(res.status_code == 200, "GET runs", res.text)
        return res.json()

    async def cleanup(self) -> None:
        if self.keep:
            return
        if self.project_ids:
            # Operation rows FK-block project deletion (no ondelete cascade) —
            # edit-ops scenarios must journal away before the API delete.
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(Operation).where(
                        Operation.project_id.in_([uuid.UUID(p) for p in self.project_ids])
                    )
                )
                await db.commit()
        for pid in self.project_ids:
            await self.client.delete(f"/projects/{pid}")
        self.project_ids.clear()


# ---- DB seeding helpers (in-process, same DB the API uses) -----------------


async def make_user() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"scenario-{uuid.uuid4().hex[:8]}@test.local",
            name="journey-bot",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return uuid.UUID(str(user.id))


async def seed_asset(
    pid: str,
    user_id: uuid.UUID,
    type_: AssetType,
    filename: str,
    *,
    extracted_text: str | None = None,
    meta: dict | None = None,
    processed: bool = False,
    file_url: str | None = None,
    status: AssetStatus | None = None,
    request_processing: bool = False,
) -> str:
    """A fake file-backed asset row — enough for the clips-media gate and the
    intent router's filename context; the bytes never exist. ``extracted_text``
    satisfies the "transcript" required-input check (registry requires).
    ``meta`` carries e.g. the ASR-detected ``language`` the plan context
    surfaces for transform-target decisions. ``processed`` stamps the row
    COMPLETED (the declared-material promotion's end state) — the worker's
    asset queue then never touches the fake bytes (writer chains).
    ``file_url`` points at a REAL bucket object (demo-bucket fixtures — the
    worker really processes a PENDING one). ``status`` overrides the derived
    state (remix's FAILED exemplar — the warm never fires for it).
    ``request_processing`` stamps ``processing_requested_at`` — the ADR-102
    dormant law's claim gate: without it a real-bytes PENDING row sleeps
    forever (the worker only claims stamped rows; the scenario's own fixture
    must declare the request, not wait for a chat-side stamp seat).
    Returns the row's id."""
    async with AsyncSessionLocal() as db:
        asset = Asset(
            user_id=user_id,
            project_id=uuid.UUID(pid),
            type=type_,
            file_url=file_url or f"scenario/{filename}",
            title=filename,
            extracted_text=extracted_text,
            meta=meta,
            processing_status=(
                status
                or (AssetStatus.COMPLETED if processed else AssetStatus.PENDING)
            ),
            processing_requested_at=(
                now_utc() if request_processing and not processed and status is None else None
            ),
        )
        db.add(asset)
        await db.flush()
        asset_id = str(asset.id)
        await db.commit()
        return asset_id


async def seed_understanding(pid: str) -> None:
    """A content-addressed material_understanding row (ADR-083's assemble-time
    injection data face): the digest is computed from the project's live asset
    rows with the pipeline's own ``asset_digest``, so the plan turn's reuse
    lookup hits exactly as an upload-time warm row would."""
    from app.pipeline.step_context import asset_digest

    async with AsyncSessionLocal() as db:
        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(Asset.project_id == uuid.UUID(pid))
                    .order_by(Asset.created_at)
                )
            )
            .scalars()
            .all()
        )
        check(bool(assets), "seed_understanding needs the asset seeded first")
        understanding = MaterialUnderstanding(
            overall_summary=(
                "A keynote on urban heat: cities are getting hotter, and "
                "shade trees plus reflective roofs can cool whole "
                "neighborhoods by several degrees."
            ),
            core_thesis=(
                "Neighborhood cooling through shade trees and reflective "
                "surfaces is the cheapest climate adaptation a city can buy."
            ),
            themes=[
                "urban heat",
                "neighborhood cooling",
                "shade trees",
                "reflective roofs",
            ],
            target_audience="city planners and residents",
        )
        db.add(
            Output(
                project_id=uuid.UUID(pid),
                type="material_understanding",
                language="en",
                source_ref={"asset_hash": asset_digest(assets), "warmed": True},
                payload=understanding.model_dump(mode="json"),
            )
        )
        await db.commit()


async def seed_completed_run(pid: str) -> None:
    """A settled run row — the plan path must never claim a project that has
    runs (the chat-path caption gate's phase seat, writing_without_material)."""
    async with AsyncSessionLocal() as db:
        db.add(
            WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.COMPLETED,
                context={"outputs": [{"type": "post"}], "target_language": "en"},
            )
        )
        await db.commit()


async def set_project_language(pid: str, language: str) -> None:
    """Pin the project's locale — the caption gate's alt-language candidate
    (writing_without_material) derives off it."""
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(pid))
        project.language = language
        await db.commit()


async def topup_wallet(user_id: uuid.UUID, amount: int = 200000) -> None:
    """Real runs burn real credits — top the scenario wallet up so the
    journey asserts its own flow, not a 422 (material_to_clips/guided_exploration/interview_to_framing/remix/builtin_promo_skill)."""
    async with AsyncSessionLocal() as db:
        wallet = await get_or_create_wallet(db, user_id)
        wallet.balance = int(wallet.balance) + amount
        await db.commit()


async def wait_run_terminal(run_id: str, timeout: float = 90.0) -> str:
    """Poll a run to a terminal state (fixture runs fail fast at preprocess —
    scenario/ bytes never exist). Stray-run retry loops must settle a
    wrong-tool run before the next turn, or the active-run guard eats it."""
    terminal = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
    for _ in range(int(timeout / 2)):
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            if run is not None and run.status in terminal:
                return str(run.status)
        await asyncio.sleep(2)
    return "TIMEOUT"


async def seed_active_run(pid: str) -> str:
    """An authority-holding run: RUNNING + one inert ``running`` node. The
    claim loop only takes ``pending`` rows and the per-tick reap (900s)
    never fires inside a scenario, so the row holds the project's execution
    authority until ``settle_seeded_run`` ends it. Returns the run id."""
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.RUNNING,
            context={
                "outputs": [{"type": "post"}],
                "target_language": "en",
                "autonomy": "review",
            },
        )
        db.add(run)
        await db.flush()
        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="plan",
                status="running",
                seq=1,
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()
        return str(run.id)


async def settle_seeded_run(run_id: str) -> None:
    """Settle a seeded inert run the way its worker execution would end:
    nodes done, then maybe_finalize_run — the finalizer is the authority-
    handoff seat, so this drives the parked-run resume hook for real."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(WorkflowStep)
            .where(
                WorkflowStep.run_id == uuid.UUID(run_id),
                WorkflowStep.status.in_(["pending", "running"]),
            )
            .values(status="done", finished_at=datetime.now(UTC))
        )
        await db.commit()
    await maybe_finalize_run(uuid.UUID(run_id))


async def count_runs(pid: str) -> int:
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(WorkflowRun.id).where(WorkflowRun.project_id == uuid.UUID(pid))
                )
            )
            .all()
        )
        return len(rows)


async def run_row(run_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, uuid.UUID(run_id))
        check(run is not None, f"run {run_id} exists")
        return {"status": str(run.status), "context": run.context or {}}


async def step_rows(run_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowStep)
                .where(WorkflowStep.run_id == uuid.UUID(run_id))
                .order_by(WorkflowStep.seq)
            )
        ).scalars().all()
        return [
            {"id": str(s.id), "kind": s.kind, "status": s.status, "spec": s.spec or {}, "error": s.error}
            for s in rows
        ]


async def message_row(message_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        msg = await db.get(Message, uuid.UUID(message_id))
        check(msg is not None, f"message {message_id} exists")
        return {
            "question": msg.question,
            "answer": msg.answer,
            # The dock 戳记 assertions read the plan chain off the row (the
            # envelope path is the other seat) — the journey's own contract.
            "intent": msg.intent,
            "workflow_run_id": str(msg.workflow_run_id) if msg.workflow_run_id else None,
            "content": msg.content,
        }


async def wait_run_status(run_id: str, wanted: set[str], timeout: float = 45.0) -> dict:
    """Poll a run until it reaches one of ``wanted`` statuses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        row = await run_row(run_id)
        if row["status"] in wanted:
            return row
        if asyncio.get_event_loop().time() > deadline:
            raise JourneyFailure(
                f"run did not reach {sorted(wanted)} within {timeout}s (worker down?) — last {row['status']}"
            )
        await asyncio.sleep(2)


async def wait_asset_status(
    asset_id: str, wanted: set[AssetStatus], timeout: float = 420.0
) -> AssetStatus:
    """Poll an asset row to a wanted processing state (real-bytes seeds: the
    dev worker really ASRs the PENDING demo-bucket source)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        async with AsyncSessionLocal() as db:
            asset = await db.get(Asset, uuid.UUID(asset_id))
            check(asset is not None, f"asset {asset_id} exists")
            if asset.processing_status in wanted:
                return asset.processing_status
        if asyncio.get_event_loop().time() > deadline:
            raise JourneyFailure(
                f"asset did not reach {sorted(str(s) for s in wanted)} within {timeout}s "
                f"(worker down?) — last {asset.processing_status}"
            )
        await asyncio.sleep(3)


async def wait_step_terminal(
    run_id: str, kind: str, timeout: float = 600.0
) -> dict:
    """Poll a run's steps until the named kind settles (done/failed/skipped).
    The caller asserts WHICH terminal is acceptable — a failed step surfaces
    its error verbatim."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        for step in await step_rows(run_id):
            if step["kind"] == kind and step["status"] in ("done", "failed", "skipped"):
                return step
        if asyncio.get_event_loop().time() > deadline:
            raise JourneyFailure(
                f"step {kind} did not settle within {timeout}s — steps: "
                f"{[(s['kind'], s['status']) for s in await step_rows(run_id)]}"
            )
        await asyncio.sleep(3)


async def outputs_of(pid: str, type_: str) -> list[Output]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == uuid.UUID(pid), Output.type == type_
                    )
                )
            ).scalars().all()
        )


async def composition_versions_of(pid: str) -> list[CompositionVersion]:
    """Read the real work/version lineage born through the Chat design door."""
    async with AsyncSessionLocal() as db:
        return list((
            await db.scalars(
                select(CompositionVersion)
                .join(Composition, CompositionVersion.composition_id == Composition.id)
                .where(Composition.origin_project_id == uuid.UUID(pid))
                .order_by(CompositionVersion.version)
            )
        ).all())


# ---- Assertion helpers ------------------------------------------------------


def is_plan_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


def terminal_tool_of(turn: dict) -> str:
    """The terminal tool the turn closed on, discriminated off the terminal
    envelope (ADR-077 判词② — the tool NAME never crosses the wire, 简报 §3;
    the envelope's SHAPE is the discriminator):

    - the plan settles + a run is born → ``start_run``
    - an unanswered task_book question docks → ``present_plan``
    - any other unanswered plain question → ``ask_user``
    - a run born with no settled question → ``run_birth`` (chat path: the
      ONLY same-turn birth left is edit_graph's approved-continuation
      branch — propose_tasks always docks; the envelope does not
      discriminate further, the scenarios assert the wiring outcome instead)
    - prose only → ``answer``
    """
    msg = turn.get("assistant_message") or {}
    q = msg.get("question") or {}
    if turn.get("answered_question") is not None and turn.get("run_id"):
        return "start_run"
    # The dock's OWN answer state discriminates, not this turn's settlement
    # of a PREVIOUS question — the enriched-brief answer turn legitimately
    # settles the pending ask AND docks the plan in one beat.
    if q.get("kind") == "task_book" and q.get("answer") is None:
        return "present_plan"
    if q.get("kind") == "question":
        return "ask_user"
    if turn.get("run_id"):
        return "run_birth"
    return "answer"


# ---- Activity work evidence (ADR-087 §3) ------------------------------------
# The Activity channel (assistant.activity frames) is the ONLY work-evidence
# channel (Phase 3 Batch B: the phase-side corroboration signal retired).
def _work_evidence(stream: "StreamTurn") -> tuple[bool, bool]:
    """(had_reads, had_repair) from the ACTIVITY channel — the ONLY work-
    evidence channel after Phase 3 Batch B.

    言语提交协议批 (G1): the repair span opens SILENTLY — a rejection's
    wire evidence is the half-started call's CANCELLED frame (and the rare
    born-terminal repair frame), never a repair active row. had_repair
    keeps its old semantics ("this turn had a rejection" — the stream-law
    skip): any cancelled frame or any repair-kind frame."""
    had_reads = any(a["kind"] == "read" for a in stream.activities)
    had_repair = any(
        a["kind"] == "repair" or a["status"] == "cancelled" for a in stream.activities
    )
    return had_reads, had_repair


def check_stream_law(
    stream: "StreamTurn", content: str, label: str, *, allow_reads: bool = True
) -> None:
    """The SSE 打字机律's tool-loop form (tool_loop.py on_delta 的 iteration-0
    唯一座位): iteration 0's speech streams verbatim; later iterations run
    quiet (a rejected iteration's speech is REPLACED speech, the repair-
    never-streams law). Therefore:

    - a genuinely single-provider-call turn: concat(deltas) == envelope content;
    - a trace-confirmed multi-call turn may settle with zero deltas only when
      its successful envelope carries the final prose; existing deltas keep the
      same prefix/interim ownership checks as read-first turns;
    - read-first turn (accepted reads in iteration 0 — read ACTIVITY frames
      present, the only evidence seat after Batch B): iteration-0 prose
      either rode the CHECKPOINT channel (eligible read — the waiter seat,
      ADR-104: flushed pre-execute, never enters the ledger, so the
      envelope does NOT contain it) or stayed in the ledger (non-eligible
      read — 账本兜底) and then PREFIXES the composed content
      (言语账本: kept parts + the terminal part join on a blank line);
    - a rejected iteration breaks even the prefix relation (its streamed
      speech was replaced) — LLM variance the scenarios cannot foresee, so
      this helper skips the turn entirely when a repair ACTIVITY appears.

    Both relations compare the STRIPPED concat: the envelope is edge-stripped
    by design (``_compose_speech`` strips every part) while the wire carries
    raw provider deltas, so leading "\n\n" tokenizer noise is variance, not
    a violation."""
    concat = "".join(stream.deltas)
    had_reads, had_repair = _work_evidence(stream)
    if had_repair:
        return  # replaced speech: even the prefix relation is void
    streamed = concat.strip()
    provider_calls = _p1_provider_calls(stream.completed) if stream.completed else []
    multi_round = len(provider_calls) > 1
    if (had_reads and allow_reads) or stream.interim_prose_rows or (multi_round and streamed):
        interim_prose_text = {c.strip() for c in stream.interim_prose_rows}
        check(
            not streamed
            or content.startswith(streamed)
            or streamed in interim_prose_text,
            f"{label}: the read-first stream law (kept speech prefixes the "
            "content, or rode the interim_prose channel — ADR-104)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )
    elif multi_round or (
        not streamed and stream.completed and stream.completed.get("run_id")
        and ((stream.completed.get("user_message") or {}).get("intent") or {}).get("video_confirmation")
    ):
        check(
            bool(content.strip()),
            f"{label}: a zero-delta settled turn needs its final prose in the envelope",
            None,
        )
    else:
        check(
            streamed == content,
            f"{label}: the single-iteration stream law (concat(deltas) == content)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )


def check_turn_stream_law(stream: "StreamTurn", content: str, question: dict, label: str) -> None:
    """The ask-branch-aware stream law (journey 公共断言的 SSE 线格式座):
    an OPTIONS ask's content IS the streamed framing (the question rides the
    dock title); a TEXT ask keeps the bare question IN the speech —
    content = framing + "\\n\\n" + question, appended at compose, never
    streamed. The generic single-iteration law (concat == content) is
    structurally false for TEXT asks; which branch the turn takes is the
    LLM's call, so the journey asserts the BRANCH's law. Everything else
    delegates to :func:`check_stream_law`."""
    _, had_repair = _work_evidence(stream)
    if had_repair:
        return  # replaced speech voids even the prefix relation
    if question.get("kind") == "question" and not (question.get("options") or []):
        streamed = "".join(stream.deltas).strip()
        bare = (question.get("question") or "").strip()
        expected = f"{streamed}\n\n{bare}" if streamed else bare
        check(
            content == expected,
            f"{label}: a TEXT ask's bare question appends at compose "
            "(blank-line join), never streamed",
            f"{''.join(stream.deltas)[:120]!r} vs {content[:120]!r}",
        )
        return
    if question.get("kind") == "task_book":
        # 估价尾行 (ADR-111 §2 / BILLING §2.1 — 2026-10-23 T5/T7 取证):
        # content = [iteration-0 ledger speech] + the dock echo (composed
        # at the terminal call, never streamed) + the code-composed
        # estimate whisper (appended at compose, blank-line join — the
        # reminder tail's same doctrine; the settled envelope paces it out
        # whole client-side). Iteration-0 read-first speech may instead
        # ride the INTERIM PROSE channel (ADR-104 — never enters the ledger).
        streamed = "".join(stream.deltas).strip()
        interim_prose_text = {c.strip() for c in stream.interim_prose_rows}
        check(
            not streamed
            or content.startswith(streamed)
            or streamed in interim_prose_text,
            f"{label}: task_book turn's iteration-0 speech prefixes the "
            "content or rode the interim_prose channel (ADR-104)",
            f"{streamed[:120]!r} vs {content[:120]!r}",
        )
        check(
            "\n\n（估价" in content
            or "\n\n(Estimated" in content
            or "\n\n(From" in content
            or "\n\n(Credits" in content
            or content.strip().startswith(("（估价", "(Estimated", "(From", "(Credits")),
            f"{label}: the dock echo carries the compose-appended estimate "
            "whisper (blank-line join, never streamed)",
            content[-120:],
        )
        return
    check_stream_law(stream, content, label)


# ---- ADR-084 speech-contract markers -----------------------------------------
# NEGATIVE shapes only (禁令 #7 — the LLM's own phrasing is never locked; what
# the contract bans is a SHAPE, and a banned shape is assertable).

# Process narration: read-iteration process talk must never persist into the
# settled message (ADR-104: pre-read speech rides the interim_prose channel as
# its own segment — the settled reply stands alone; post-read interim_prose_rows
# carry results, never process narration).
# 词边界 adjudication（C-6，2026-09-19）：IGNORECASE 下裸 `I'?ll` 会把
# "will pull from" 的 "ill pull" 误判为第一人称过程叙述（"the caption text
# will pull from …" 是诚实披露而非过程泄漏）。合同不变（ADR-084 禁的是第一
# 人称过程话入终答），断言补 \b 词界。
PROCESS_NARRATION = re.compile(
    r"(\bI'?ll (pull|check|inspect|look into|fetch|take a look)|"
    r"\bLet me (check|pull|inspect|look|fetch)|"
    r"\bI'?m going to (pull|check|inspect|look)|"
    r"我先(查|看|拉|读)|让我(先)?(查|看|拉|读))",
    re.IGNORECASE,
)


def check_interim_prose_shape(stream: "StreamTurn", content: str, label: str) -> None:
    """Interim prose shape laws (ADR-109 言语座位通用化; opportunistic —
    entries are EARNED, so absence is legal; when they fired, the shape
    must hold): ≤4/turn (节奏护栏), never empty, never process narration
    POST-READ (pre-read waiter speech is legal — ADR-104 服务员话术律;
    phase-turn expectation sentences are the legal pre-read form), and the
    settled reply never repeats one verbatim."""
    if not stream.interim_prose_rows:
        return
    check(
        len(stream.interim_prose_rows) <= 4,
        f"{label}: interim_prose_rows are capped at ≤4 per turn (ADR-109 rhythm guardrail)",
        stream.interim_prose_rows,
    )
    check(
        all(c.strip() for c in stream.interim_prose_rows),
        f"{label}: interim_prose_rows are never empty",
        stream.interim_prose_rows,
    )
    check(
        # The waiter exemption (ADR-104): interim prose that arrived BEFORE
        # any read settled is pre-read waiter speech — legal process talk
        # by the waiter-line law. The results-only bar polices POST-read
        # entries (grounded judgment, never process narration).
        not PROCESS_NARRATION.search(
            " ".join(
                c for c, pre in zip(stream.interim_prose_rows, stream.interim_prose_pre_read) if not pre
            )
        ),
        f"{label}: post-read interim_prose_rows carry results, never process narration",
        stream.interim_prose_rows,
    )
    for cp in stream.interim_prose_rows:
        check(
            cp.strip() not in content,
            f"{label}: the settled reply never repeats interim prose verbatim",
            {"interim_prose": cp[:120], "settled": content[:120]},
        )


_ACTIVITY_KINDS = {"read", "draft", "run", "repair"}
_ACTIVITY_TERMINAL = {"completed", "failed", "cancelled"}
_ACTIVITY_RECEIPT_FIELDS = {
    "video_review": {"kind", "frames", "findings", "output_issue_codes", "scope"},
    "video_draft_review": {
        "kind", "evidence_id", "draft_digest", "content_digest", "media_digest",
        "source_range_seconds", "scene_ids", "continuous",
    },
    "video_revision": {
        "kind", "version", "settings", "scenes", "clips", "transitions_changed", "components",
    },
    "component": {"kind", "components"},
    "skill_read": {
        "kind", "package_identity", "skill_reference", "owner_id", "reads", "preview_checks", "media_files",
    },
    "sfx_search": {"kind", "candidate_set_id", "topic", "members"},
    "sfx_import": {
        "kind", "candidate_set_id", "member_index", "asset_id", "snapshot_id",
        "snapshot_digest", "title", "duration_seconds",
    },
    "music_search": {"kind", "candidate_set_id", "topic", "members"},
    "music_selection": {
        "kind", "candidate_set_id", "member_index", "music_id", "title", "duration_seconds",
    },
}


def check_activity_shape(stream: "StreamTurn", label: str) -> None:
    """ADR-087 §3 activity shape laws (opportunistic — a bare-reply turn
    legally has ZERO frames; when frames flew, the shape must hold):
    ① the wire whitelist is {activity_id, seq, kind, status, key} + the
    timing/fact extensions {at, count, duration_ms} + the completed-only typed
    receipt sideband (no params / raw results / reasoning ever leak); ② kind is a user-semantic category, never a tool
    name; ③ seq is strictly increasing; ④ a status flip appends a NEW frame
    on the same activity_id (never a mutation) — explore milestones are
    BORN-COMPLETED instant facts (one terminal frame, no active birth),
    exempt from the birth/flip laws; ⑤ T16-B wire twin — when the envelope
    lands, every activity's LAST frame is terminal (no dangling active)."""
    acts = stream.activities
    if not acts:
        return
    for a in acts:
        keys = set(a.keys())
        check(
            {"activity_id", "seq", "kind", "status", "key"} <= keys
            and keys <= {
                "activity_id", "seq", "kind", "status", "key", "at", "count",
                "duration_ms", "receipt",
            },
            f"{label}: activity frame carries only the whitelist fields",
            a,
        )
        check(
            a["kind"] in _ACTIVITY_KINDS,
            f"{label}: kind is a user-semantic category, never a tool name",
            a,
        )
        check(
            a["status"] in _ACTIVITY_TERMINAL | {"active"},
            f"{label}: status is one of active/completed/failed/cancelled",
            a,
        )
        check(
            a["key"] is None or (isinstance(a["key"], str) and a["key"]),
            f"{label}: key is null or a non-empty i18n key",
            a,
        )
        if "receipt" in a:
            receipt = a["receipt"]
            check(
                a["status"] == "completed" and isinstance(receipt, dict),
                f"{label}: only a completed Activity carries a typed receipt",
                a,
            )
            if isinstance(receipt, dict):
                kind = receipt.get("kind")
                check(
                    kind in _ACTIVITY_RECEIPT_FIELDS
                    and set(receipt) == _ACTIVITY_RECEIPT_FIELDS[kind],
                    f"{label}: receipt {kind!r} carries only its registered evidence fields",
                    receipt,
                )
    seqs = [a["seq"] for a in acts]
    check(
        seqs == sorted(seqs) and len(set(seqs)) == len(seqs),
        f"{label}: activity seq is strictly increasing",
        seqs,
    )
    # Stable identity law (④): frames sharing an activity_id are ONE work
    # item's state flips — a span's first frame is the active birth, kind
    # never mutates mid-activity, exactly one terminal frame closes the id
    # (and nothing follows it), and the copy key follows the status-form
    # law: failed/cancelled REUSE the active key, completed swaps to the
    # past-tense form. A born-completed milestone is an instant fact: no
    # birth/flip laws apply.
    by_id: dict[str, list[dict]] = {}
    for a in acts:
        by_id.setdefault(a["activity_id"], []).append(a)
    for aid, frames in by_id.items():
        check(
            len({f["kind"] for f in frames}) == 1,
            f"{label}: kind never mutates across an activity's flips ({aid})",
            frames,
        )
        if len(frames) == 1 and frames[0]["status"] in _ACTIVITY_TERMINAL:
            continue  # born-completed milestone — an instant fact
        check(
            frames[0]["status"] == "active",
            f"{label}: a span's first frame is its active birth ({aid})",
            frames,
        )
        check(
            all(f["status"] == "active" for f in frames[:-1]),
            f"{label}: only the terminal frame leaves active ({aid})",
            frames,
        )
        active_keys = {f["key"] for f in frames[:-1]}
        terminal = frames[-1]
        if terminal["status"] == "completed":
            check(
                terminal["key"] is not None and terminal["key"] not in active_keys,
                f"{label}: completion swaps to the past-tense key ({aid})",
                frames,
            )
        elif terminal["status"] in ("failed", "cancelled"):
            check(
                terminal["key"] in active_keys,
                f"{label}: failed/cancelled reuse the active key ({aid})",
                frames,
            )
    last_status: dict[str, str] = {}
    for a in acts:  # append-oriented: the LAST frame per id is its state
        last_status[a["activity_id"]] = a["status"]
    dangling = {k: v for k, v in last_status.items() if v not in _ACTIVITY_TERMINAL}
    check(
        not dangling,
        f"{label}: T16-B — no activity outlives the turn (envelope sweep)",
        dangling,
    )


# ---- dock 形态（journey 公共断言）--------------------------------------------

# 选项载荷边界 lint（ADR-100 — 选项永不携带执行参数）：负形断言。
# label 全档（label 是方向名，带参即 shadow plan）；description 收窄
# 档（证据句合法引用源事实——"the 3 strongest moments" 不是参数，条数
# 词只在 label 档查；字幕模式族只查标识符形 source_only/target_only——
# 散文里的 bilingual 是用户语言内容词，与双语同律放行）。
_INT_LABEL_LINT = [
    re.compile(r"\d+\s*[:×x]\s*\d+"),                                      # 画幅 9:16
    re.compile(r"\b\d+\s*(seconds?|secs?|minutes?|mins?|秒|分钟)\b", re.I),  # 时长
    re.compile(r"\b(?:bilingual|source_only|target_only)\b", re.I),         # 字幕模式参数方言词（用户语言内容词合法）
    re.compile(r"\bcredits?\b|积分", re.I),                                  # 成本
    re.compile(r"\b\d+\s*(?:clips?|cards?|posts?|shorts?|条|张|篇)\b", re.I),  # 条数
]
_INT_DESC_LINT = [
    _INT_LABEL_LINT[0],
    _INT_LABEL_LINT[1],
    re.compile(r"\b(?:source_only|target_only)\b", re.I),  # 只查标识符形
    _INT_LABEL_LINT[3],
]

_INT_EXPLORATION_PROMPTS = (
    "what could I make from this keynote? give me a few directions",
    "what are some good next steps for this video?",
    "any ideas for what to do with the keynote?",
)


def check_dock_shape(msg: dict, label: str) -> None:
    """dock 形态律（journey 公共断言——每个回合信封自动携带）：

    - task_book 计划行自完备：链随 intent 列（非空）+ derived 列表；
      estimate_credits 在场时良构——total = [low, high] 非负有
      序、per_task 按任务序对齐（None ≡ 零报价），且 **Σ per_task ≡
      total**（报价对账律，orchestrator 前缀编译差分三面同源）。
    - 选项问结构律：1–5 选项（决断 ≤3 / 探索 ≤5 的分族节奏归 prompt
      法条座位，journey 只守结构外界）/ label 非空 ≤40 / recommended_id
      至多其一且指在 docked 选项上 / 载荷永不携带执行参数（负形 lint
      ——shadow plan 是本档的定义性违界）。

    default_path 恒在律不在此（ask 家族专属——trigger 建议 dock 是另
    一族，归各旅程的场景级断言）。"""
    q = msg.get("question") or {}
    if not q:
        return
    if q.get("kind") == "task_book":
        tasks = ((msg.get("intent") or {}).get("tasks")) or []
        check(
            bool(tasks),
            f"{label}: the plan dock self-carries the chain (intent column)",
            msg.get("intent"),
        )
        check(
            isinstance(q.get("derived"), list),
            f"{label}: the plan dock's derived preview rides as a list",
            q,
        )
        est = q.get("estimate_credits")
        if est is not None:
            total = est.get("total")
            check(
                isinstance(total, list)
                and len(total) == 2
                and all(isinstance(v, int) for v in total)
                and 0 <= total[0] <= total[1],
                f"{label}: estimate total is a non-negative ordered [low, high]",
                est,
            )
            per_task = est.get("per_task")
            if per_task is not None:
                check(
                    len(per_task) == len(tasks),
                    f"{label}: per_task aligns with the task list by index",
                    est,
                )
                lows = highs = 0
                for entry in per_task:
                    check(
                        entry is None
                        or (
                            isinstance(entry, list)
                            and len(entry) == 2
                            and all(isinstance(v, int) for v in entry)
                            and 0 <= entry[0] <= entry[1]
                        ),
                        f"{label}: each per_task entry is null or a [low, high] range",
                        est,
                    )
                    if entry is not None:
                        lows += entry[0]
                        highs += entry[1]
                check(
                    (lows, highs) == (total[0], total[1]),
                    f"{label}: Σ per_task ≡ total exactly (报价对账律)",
                    est,
                )
    elif q.get("kind") == "question":
        options = q.get("options") or []
        if options:
            check(
                1 <= len(options) <= 5,
                f"{label}: 1-5 options on the dock",
                options,
            )
            ids = {str(o.get("id")) for o in options}
            recommended_id = q.get("recommended_id")
            check(
                recommended_id is None or recommended_id in ids,
                f"{label}: recommended_id names at most one docked option",
                q,
            )
            for o in options:
                text = str(o.get("label") or "")
                check(
                    bool(text.strip()) and len(text) <= 40,
                    f"{label}: label non-empty and ≤40",
                    text,
                )
                # shadow plan 负形的适用边界 (2026-10-23 T8 取证): the lints
                # guard REGISTERED param slots — the param has a structured
                # home, so prose must not smuggle it. A slot-less freeform
                # disambiguation dock's SUBSTANCE may be a numeric tradeoff
                # (「窗口前移到 17–25s 还是守 20s 起只剩 5s」——素材物理边界
                # 的诚实控问), where naming the numbers in prose IS the
                # question; linting those descriptions would ban the honest
                # correction the 顾问姿态 requires.
                if not q.get("slot"):
                    continue
                for pat in _INT_LABEL_LINT:
                    check(
                        not pat.search(text),
                        f"{label}: labels never carry execution params (shadow plan 负形)",
                        f"{pat.pattern} in {text!r}",
                    )
                desc = str(o.get("description") or "")
                for pat in _INT_DESC_LINT:
                    check(
                        not pat.search(desc),
                        f"{label}: descriptions never carry execution params (shadow plan 负形)",
                        f"{pat.pattern} in {desc!r}",
                    )


def check_turn_stream_laws(stream: "StreamTurn", label: str) -> None:
    """SSE 回合的 journey 公共断言全家桶（``Ctx.chat_stream`` 在信封成功
    收官时自动携带）：线格式律（含文字问/选项问合成枝）+ Activity 帧形态
    + interim_prose 形态 + 选项问预览帧律 + dock 形态。"""
    msg = stream.completed["assistant_message"]
    content = msg.get("content") or ""
    q = msg.get("question") or {}
    check_turn_stream_law(stream, content, q, label)
    check_activity_shape(stream, label)
    check_interim_prose_shape(stream, content, label)
    # question.preview 预览帧律（言语提交协议 G2：预览骑缓冲、接受才释
    # 放——收到的预览即权威件，与信封 dock 载荷逐字段一致）。文字类提问
    # 永不预览 dock（与 R1 文字问门禁同律）——只有选项问 dock 触发本律。
    if q.get("kind") == "question" and (q.get("options") or []):
        # 言语提交协议 (ADR-099 §7) 的 retracted close 形豁免：回合中途被守卫
        # 拒（如 bare ask 缺框架言语 → execute_guardrail 拒绝）→ retract →
        # 收官 _resolve_deferred 走 drop——散文与预览帧全部不落线，信封整体
        # pacing 出权威 dock（零 delta 路径既有法）。该形 = 零 delta 且零
        # preview；干净收官（flush+disarm）的选项问恒有 preview 帧，零 delta
        # 而 preview 缺席只在 retracted close 成立。（2026-10-23 下批 B 旅程
        # T1 实证：intent_router 首 ask 被 guardrail 拒后重试接受，预览合法
        # 缺席——此前本律未给该形豁免。）
        if not stream.deltas and not stream.previews:
            check_dock_shape(msg, label)
            return
        check(
            len(stream.previews) >= 1,
            f"{label}: the ask's question.preview frame precedes the terminal envelope",
            stream.thinking,
        )
        preview = stream.previews[-1]
        check(
            preview.get("question") == q.get("question"),
            f"{label}: the preview's bare question IS the docked payload's",
            preview,
        )
        check(
            [o.get("id") for o in preview.get("options") or []]
            == [o.get("id") for o in q.get("options") or []],
            f"{label}: the preview's options match the docked payload's",
            preview,
        )
        check(
            preview.get("slot") == q.get("slot"),
            f"{label}: the preview's slot matches the docked payload's",
            preview,
        )
        check(
            isinstance(preview.get("allow_freeform"), bool),
            f"{label}: the preview carries allow_freeform",
            preview,
        )
        check(
            bool((preview.get("default_path") or "").strip()),
            f"{label}: the preview carries the default path",
            preview,
        )
    check_dock_shape(msg, label)


def has_prose(msg: dict) -> bool:
    """The assistant message carries a non-empty prose reply."""
    return bool((msg.get("content") or "").strip())


def plan_tasks(plan: dict) -> list[dict]:
    """The docked chain (ADR-043): pending_brief.intent.tasks — the plan
    card's rows, one {tool, params} dict per task."""
    return ((plan or {}).get("intent") or {}).get("tasks") or []


def task_params(task: dict) -> dict:
    return task.get("params") or {}


async def pending_plan(ctx: Ctx, pid: str) -> dict | None:
    """The project's pending plan via the results endpoint (None when none)."""
    return (await ctx.results(pid)).get("pending_brief")


async def wait_trigger_review(
    ctx: Ctx, conversation_id: str, run_id: str, timeout: float = 90.0
) -> dict | None:
    """Poll the conversation for the run-completed trigger turn's review row
    (ADR-077 判词③ T3): the pipeline fires the proactive turn fire-and-forget
    at run terminal, and the agent's wrap_up persists an assistant row whose
    intent dump is ``{type: "trigger_review", trigger, ref, suggestions}``.
    Returns the message row, or None on timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for m in await ctx.messages(conversation_id):
            intent = m.get("intent") or {}
            if intent.get("type") == "trigger_review" and intent.get("ref") == run_id:
                return m
        await asyncio.sleep(2)
    return None


def has_reminder_tail(content: str) -> bool:
    """The code-composed interjection reminder tail (ADR-053 R2 — code-forced
    text, so locking its marker is legal: it is code, never the LLM's voice)."""
    return "Still waiting for your answer:" in content or "还在等你的回答：" in content


async def seed_keynote_project(ctx: Ctx, title: str) -> tuple[str, str]:
    """谱系场景素材种子：一个 COMPLETED 视频资产（worker-immune）+ 内容
    理解行（plan-turn 装配的 grounding 面）→ (pid, asset_id)。探索类提问
    的具体下一步方向从这里长出来——suggestions 永不空穴来风（契约：只在
    当前上下文存在具体可供选择的下一步方向时出现）。"""
    pid = await ctx.new_project(title)
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
        extracted_text=(
            "On urban heat: cities are getting hotter, and shade trees plus "
            "reflective roofs can cool whole neighborhoods by several degrees."
        ),
        processed=True, meta={"language": "en"},
    )
    await seed_understanding(pid)
    return pid, asset_id


def check_options_dock(question: dict, label: str) -> None:
    """选项 dock 的谱系锁（ADR-100：一切可点选项归 dock——ask_user 选项
    问承接探索/浏览的方向建议）：kind=question / 1-5 选项 / label ≤40 /
    载荷永不携带执行参数（负形 lint）/ recommended 至多其一且必须指在
    docked 选项上 / default_path 恒在（每个问题都可安全跳过）。"""
    check(question.get("kind") == "question",
          f"{label}: the directions dock as a real options question", question)
    options = question.get("options") or []
    check(1 <= len(options) <= 5,
          f"{label}: 1-5 options on the dock", options)
    check(bool((question.get("default_path") or "").strip()),
          f"{label}: the default path rides every ask (安全跳过)", question)
    recommended_id = question.get("recommended_id")
    check(recommended_id is None
          or recommended_id in {str(o.get("id")) for o in options},
          f"{label}: recommended_id names at most one docked option", question)
    for o in options:
        text = str(o.get("label") or "")
        check(bool(text.strip()) and len(text) <= 40,
              f"{label}: label non-empty and ≤40", text)
        for pat in _INT_LABEL_LINT:
            check(not pat.search(text),
                  f"{label}: labels never carry execution params (shadow plan 负形)",
                  f"{pat.pattern} in {text!r}")
        desc = str(o.get("description") or "")
        for pat in _INT_DESC_LINT:
            check(not pat.search(desc),
                  f"{label}: descriptions never carry execution params (shadow plan 负形)",
                  f"{pat.pattern} in {desc!r}")


async def elicit_options_dock_turn(
    ctx: Ctx, pid: str, label: str,
    prompts: tuple[str, ...] = _INT_EXPLORATION_PROMPTS,
) -> dict:
    """驱动一个探索 → ask_user 选项 dock 回合（ADR-100：浏览/探索的方向
    建议全归 dock）→ turn。

    LLM 方差口径：纯 answer 散文 = 措辞重试（模型有选择散文答复的自由）；
    present_plan = 错档硬红（探索问永不直接承诺——事故④第一跳形态）。"""
    for prompt in prompts:
        turn = await ctx.chat(pid, prompt)
        tool = terminal_tool_of(turn)
        check(tool != "present_plan",
              f"{label}: an exploration question never docks a plan (事故④第一跳形态)",
              turn)
        q = turn["assistant_message"].get("question") or {}
        if tool == "ask_user" and (q.get("options") or []):
            return turn
    raise JourneyFailure(
        f"{label}: no options-dock turn after {len(prompts)} tries"
    )


async def conversation_items(ctx: Ctx, pid: str) -> list[dict]:
    """The conversation's message list over the wire (持久化事实的客户端观察面)."""
    res = await ctx.conversation(pid)
    check(res.status_code == 200, "the conversation exists after the first turn",
          res.status_text if hasattr(res, "status_text") else res.status_code)
    return await ctx.messages(res.json()["id"])


async def check_incremental_design_turn(ctx: Ctx, turn: dict, label: str) -> None:
    """Verify one real high-level save, with a draft digest chain only when used."""
    turn_id = str((turn.get("user_message") or {}).get("id") or "")
    check(bool(turn_id), f"{label}: the settled turn has its real user-message id", turn)
    async with AsyncSessionLocal() as db:
        conversation = await db.scalar(select(Conversation).where(
            Conversation.id == uuid.UUID(turn["conversation_id"]),
            Conversation.user_id == ctx.user_id,
        ))
        context = dict(conversation.context or {}) if conversation is not None else {}
    check(conversation is not None, f"{label}: owned conversation is readable", None)
    items = [
        item for item in (context.get("items") or [])
        if item.get("turn_id") == turn_id
        and (item.get("tool") == "design_video" or item.get("target_tool") == "design_video")
    ]
    successful_saves = 0
    draft_id = None
    latest_ref = None
    for item in items:
        args = item.get("executed_arguments") or item.get("arguments") or {}
        save = args.get("save", False)
        check(isinstance(save, bool), f"{label}: design save flag is boolean", item.get("id"))
        try:
            result = json.loads(item.get("text") or "")
        except (TypeError, json.JSONDecodeError):
            result = None
        if isinstance(result, dict) and result.get("draft_retired"):
            continue
        returned_ref = result.get("draft_ref") if isinstance(result, dict) else None
        if isinstance(returned_ref, dict):
            if latest_ref is None:
                check(args.get("draft_ref") is None,
                      f"{label}: a new working draft does not borrow an older identity",
                      item.get("id"))
            else:
                check(args.get("draft_ref") == latest_ref,
                      f"{label}: each write authenticates the latest draft digest",
                      {"call": item.get("id"), "sent": args.get("draft_ref"),
                       "expected": latest_ref})
            if draft_id is None:
                draft_id = returned_ref.get("draft_id")
            check(returned_ref.get("draft_id") == draft_id
                  and isinstance(returned_ref.get("draft_digest"), str),
                  f"{label}: all writes keep one working-draft identity",
                  {"call": item.get("id"), "returned": returned_ref})
            latest_ref = returned_ref
        if item.get("ok") and save:
            successful_saves += 1
            if args.get("draft_ref") is not None:
                check(latest_ref is not None and args.get("draft_ref") == latest_ref,
                      f"{label}: final save validates the assembled working draft",
                      {"call": item.get("id"), "sent": args.get("draft_ref"),
                       "expected": latest_ref})
            else:
                check(bool(args.get("shots")),
                      f"{label}: a direct high-level save carries bounded shots",
                      item.get("id"))
            check(any(str(key).startswith("composition:")
                      for key in item.get("resource_keys") or []),
                  f"{label}: the successful save records its Composition resource",
                  item.get("id"))
    check(successful_saves == 1,
          f"{label}: the high-level design is saved exactly once", successful_saves)


# ---- 共享 fixture（demo 桶常住对象，reset_db 保护前缀）--------------------------
#
# fixture 纪律：源片一律先拷 ``scenario/`` 前缀——``delete_project`` 会 unlink
# 每个资产的 ``file_url``，共享 demo 键直接引用随清理被删。真字节素材若需
# worker 真处理（ASR），seed 时必须显式 ``request_processing=True``（ADR-102
# 休眠律：无 ``processing_requested_at`` 盖章的 PENDING 行 worker 永不认领）。
REMIX_SOURCE_KEY = "demo/uploads/demo_talk.mp4"
REMIX_EXEMPLAR_KEY = "demo/outputs/highlight-clips-preview-ec8e575b.mp4"
# 14.5s 双人访谈段（xy_1 [172.5,187.0]，约 6.6s 处一次干净的问→答切换——烘焙
# 配方卡「访谈分镜」demo 的同一源，实证 form=interview + 真 crop_track）。
INTERVIEW_SOURCE_KEY = "demo/uploads/xy_1_interview_15s.mp4"


async def copy_fixture(key: str, dest_prefix: str) -> str:
    """Copy a shared demo-bucket fixture to a scenario-owned key. NEVER seed
    an asset pointing at the shared object directly: project deletion unlinks
    every asset's ``file_url`` (``delete_project`` → ``delete_file``), so a
    shared key referenced by a scenario project dies with its cleanup."""
    from app.config import settings
    from app.providers.storage import _get_s3_client

    dest = f"{dest_prefix}/{key.rsplit('/', 1)[-1]}"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.copy_object,
        Bucket=settings.s3_bucket_name,
        Key=dest,
        CopySource={"Bucket": settings.s3_bucket_name, "Key": key},
    )
    return dest


# demo_talk（~119s）的合成转写种子：真字节 + 逐词时间轴 + speaker_map，
# processed=True 自证处理终态（worker 不碰——fixture 自证比等盖章口确定），
# clips 链的选段/剪切/render 全在真字节上跑。
_SE2_SENTENCES = [
    (0.0, "Welcome back to the founder notes."),
    (6.0, "Today I want to walk through how we think about pricing."),
    (14.0, "Our pricing is simple."),
    (18.0, "The starter tier is free forever."),
    (24.0, "The pro tier costs ten dollars a month."),
    (30.0, "You only pay when your team actually grows."),
    (38.0, "Let me switch gears and talk about the roadmap for a moment."),
    (52.0, "We are shipping the new dashboard next quarter."),
    (64.0, "Back to pricing for a second."),
    (68.0, "Every paid tier includes the analytics dashboard."),
    (76.0, "Annual billing saves you two months."),
    (84.0, "That is the whole announcement for this week."),
]


def _talk_words() -> list[dict]:
    words: list[dict] = []
    for line_start, sentence in _SE2_SENTENCES:
        t = line_start
        for w in sentence.split():
            words.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2)})
            t += 0.5
    return words


def no_decompile_canvas_node(graph: dict) -> bool:
    """decompile folds into the prelude — it must never read back as a
    standalone canvas node."""
    return not any(
        (n.get("spec") or {}).get("tool") == "decompile" for n in graph.get("nodes") or []
    )


# ==============================================================================
# 用户旅程矩阵
# ==============================================================================


async def lost_user_full_journey(ctx: Ctx) -> None:
    """lost_user 迷失用户全旅程（auto 档——默认档旅程, ADR-117 §2）：裸愿望 → 主题问
    （SSE——选项预览律的旅程座位）→ 作答回填（自由文本 slot 握手 + 选项点选
    两路）/ 跳过 → draft-from-persona 计划 → dock 呈现即开工（同回合
    settled+born，confirmed_via="auto"）。途中锁契约拍：待决重建零内存
    态、一行一答 409、选项点选不 500（kind 守卫）、lifecycle stamp 拍①
    （fresh project preparing）。dock 等待态的 stamp/draft 拍（拍②③ +
    图先展示后运行）随 ask 档迁到 guided_exploration——本旅程跑默认档。

    LLM 方差说明：router 判 ask 是设计行为（prompt 策略行）；若个别模型把
    "I want a social post." 直接判 draft，首段断言会红——那是 prompt 回归
    信号。options 空合法（无 persona 时储藏室为空）。"""
    # 默认档钉住（顺序无关——Ctx 全矩阵共享一个 user）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    pid = await ctx.new_project("lost_user bare wish journey")

    # Lifecycle stamp 拍①：fresh project = preparing / not-ready / 零 blocker
    #（stamp 是唯一 lifecycle 读面，产物永不说话）。
    stamp0 = (await ctx.results(pid))["lifecycle"]
    check(stamp0["state"] == "preparing" and not stamp0["plan_ready"]
          and not stamp0["confirmation_ready"] and stamp0["blockers"] == [],
          "a fresh project reads preparing / not-ready on the stamp", stamp0)

    # turn1 走 SSE——选项问预览帧律（journey 自动断言）在此座上 exercised。
    stream1 = await ctx.chat_stream(pid, "I want a social post.")
    check(stream1.failed is None, "the ask turn never fails", stream1.failed)
    check(stream1.completed is not None, "the ask turn completes", stream1.failed)
    turn1 = stream1.completed
    msg1 = turn1["assistant_message"]
    check(turn1["run_id"] is None, "a bare wish never starts a run", turn1)
    check(terminal_tool_of(turn1) == "ask_user",
          "the rootless wish closes on the ask_user call", turn1)
    q1 = msg1.get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the rootless wish docks the topic ask first (never an empty plan)", msg1)
    check(bool((q1.get("default_path") or "").strip()),
          "the default path rides as the schema tooth", q1)
    # ask 三分解剖：content = 框架散文，payload.question = 裸问题（dock 标题 /
    # QA 归档 / 提醒尾读它）。散文缺字段时 content 回退裸问题——回归信号。
    check(bool((q1.get("question") or "").strip()),
          "the bare question rides the payload (dock title's source)", q1)
    check(has_prose(msg1) and (msg1.get("content") or "") != q1.get("question"),
          "the framing prose IS the message content (the ask's echo)",
          (msg1.get("content") or "")[:200])
    options = q1.get("options") or []
    check(len(options) == 0 or 2 <= len(options) <= 3,
          "options: 3 one-word picks (2 only for a genuinely binary choice), "
          "or empty when the persona pantry is empty",
          options)
    plan1 = await pending_plan(ctx, pid)
    check(plan1 is None or plan1.get("intent") is None,
          "no plan parks on an ask turn (brief-only row or none)", plan1)

    # 契约拍①：待决重建零内存态——刷新/跨设备座。
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the pending question rebuilds (the refresh / cross-device seat)",
          res.json())

    # 自由文本作答 —— slot 握手判定结算（router 在 pending 块上下文里把槽位
    # 值提案 user-stated，代码结算 freeform 并回填）。
    turn2 = await ctx.chat(pid, "Make it about the EU AI Act for researchers.")
    aq = turn2.get("answered_question")
    check(aq is not None and aq["id"] == msg1["id"],
          "the free-text answer settles the pending ask (judged — code settles)",
          turn2)
    check((aq.get("answer") or {}).get("kind") == "freeform",
          "the judged settlement lands kind=freeform (the user's own words)",
          aq.get("answer"))
    brief = ((await pending_plan(ctx, pid)) or {}).get("brief") or {}
    topic = brief.get("topic") or {}
    check(topic.get("source") == "user-stated" and bool(topic.get("value")),
          "the slot backfills user-stated from the answer", topic)

    # 契约拍②：一行一答——已答问题再答 = 409。
    dup = await ctx.answer(msg1["id"], {"kind": "bail"})
    check(dup.status_code == 409, "re-answering the settled ask is a conflict",
          dup.status_code)

    # 契约拍③：选项点选作答（500 事故补盖——点选路曾裸奔）。第二项目同问
    # 点选：200 + answer.kind=option + slot 回填 user-stated（回填的是 label
    # 不是 id）+ plan path 接续带 follow_up。
    pid2 = await ctx.new_project("lost_user option pick")
    turn1b = await ctx.chat(pid2, "I want a social post.")
    msg1b = turn1b["assistant_message"]
    q1b = msg1b.get("question") or {}
    opts = q1b.get("options") or []
    if q1b.get("slot") == "topic" and opts:
        pick = await ctx.answer(msg1b["id"],
                                {"kind": "option", "option_id": opts[0]["id"]})
        check(pick.status_code == 200, "the option pick settles (no 500)",
              pick.text)
        body = pick.json()
        check(((body.get("answered_question") or {}).get("answer") or {})
              .get("kind") == "option",
              "the pick lands kind=option", body.get("answered_question"))
        brief2 = ((await pending_plan(ctx, pid2)) or {}).get("brief") or {}
        topic2 = brief2.get("topic") or {}
        check(topic2.get("source") == "user-stated"
              and topic2.get("value") == opts[0]["label"],
              "the option pick backfills the slot with the LABEL (not the id)",
              topic2)
        check(body.get("follow_up") is not None,
              "the plan path resumes with a follow-up", body)
    else:
        check(True, "option-pick beat skipped (pantry empty — exempt)", q1b)

    # 评审卡：作答轮直接出书，或推一轮。auto 档终点（ADR-117 §2）：
    # present_plan 呈现即开工——dock 回合的信封读 settled+born
    # （terminal_tool_of 读作 start_run 形；与口头确认同形 = 设计如此，
    # 工具名永不过线），零确认拍。
    turn_dock = turn2
    if turn_dock["run_id"] is None and not is_plan_dock(turn_dock["assistant_message"]):
        turn_dock = await ctx.chat(pid, "go ahead")
    msg2 = turn_dock["assistant_message"]
    check(turn_dock["run_id"] is not None,
          "auto 档呈现即开工 — the dock turn births the run (no confirm beat)",
          turn_dock)
    check(turn_dock["answered_question"] is not None,
          "the dock settles on the presentation-time start", turn_dock)
    aq2 = turn_dock["answered_question"]
    check((aq2.get("question") or {}).get("kind") == "task_book",
          "the settled row IS the docked plan", aq2)
    check(((aq2.get("question") or {}).get("requires_confirmation")) is False,
          "auto 档戳记 = 零确认拍（requires_confirmation=False  stamped at dock）",
          aq2.get("question"))
    check((aq2.get("answer") or {}).get("kind") == "start",
          "the presentation-time start lands kind=start", aq2.get("answer"))
    ftopic = ((aq2.get("question") or {}).get("brief") or {}).get("topic") or {}
    check(ftopic.get("source") == "user-stated" and bool(ftopic.get("value")),
          "the review card stamps the merged brief into the payload", ftopic)
    row_derived = (aq2.get("question") or {}).get("derived")
    check(isinstance(row_derived, list) and len(row_derived) >= 1,
          "the dock row self-carries the derived preview (payload)",
          aq2.get("question"))
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on the presentation-time start")

    # confirmed_scope 快照：常驻授权通道的戳（confirmed_via="auto"）。
    s1_run_ctx = (await run_row(turn_dock["run_id"]))["context"]
    check((s1_run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
          "confirmed_via = auto（呈现即开工的常驻授权戳）",
          s1_run_ctx.get("confirmed_scope"))

    # 第三项目：rootless 闸门（措辞方差两连）→ 跳过 → draft-from-persona。
    pid3 = await ctx.new_project("lost_user rootless gate")
    turn_c = await ctx.chat(pid3, "make me something for my audience")
    check(not is_plan_dock(turn_c["assistant_message"]),
          "a rootless wish never docks a groundless plan", turn_c)
    check(turn_c["run_id"] is None, "a rootless wish never starts a run", turn_c)
    if terminal_tool_of(turn_c) != "ask_user":
        # answer 族答复 = 顾问姿态方差，换新项目重试（历史会带偏后续判定）；
        # 连续两项目无 ask = lost_user 实证面漂移（红 = router/prompt 回归信号）。
        pid3 = await ctx.new_project("lost_user rootless gate retry")
        turn_c = await ctx.chat(pid3, "I want a social post.")
        check(terminal_tool_of(turn_c) == "ask_user",
              "the rootless wish docks the ask gate", turn_c)
    q_c = turn_c["assistant_message"]["question"]
    check(q_c.get("answer") is None, "the gate docks unanswered", q_c)

    # × 跳过 → 默认路径生效：draft-from-persona 计划 dock 并同拍开工（auto
    # 档零确认拍——信封的 follow_up 是已结算 dock 行，workflow_run_id 戳在
    # 上面），asked 簿记挡住第二轮同槽问（问环有界）。跳过后 router 应判
    # draft；若再判 ask(topic)，asked 簿记翻回 draft——同归宿，只看终点。
    ans = await ctx.answer(turn_c["assistant_message"]["id"], {"kind": "bail"})
    check(ans.status_code in (200, 201), "the skip is accepted", ans.text)
    follow = ans.json().get("follow_up") or {}
    check((follow.get("question") or {}).get("kind") == "task_book"
          and follow.get("answer") is not None
          and bool(follow.get("workflow_run_id")),
          "skipping takes the default path — the plan docks AND starts on "
          "presentation (auto 档零确认拍)", follow)
    check(ans.json().get("answered_question") is not None,
          "the skipped ask settles as answered", ans.json())

    # 开工即清 pending_brief——计划快照读 follow_up 行自带的三座（reasons /
    # asked / echo 散文），不再读项目行。
    reasons = ((follow.get("question") or {}).get("reasons")) or []
    check("draft_from_persona" in reasons,
          "the draft-from-persona reason rides the docked plan", reasons)
    asked = (((follow.get("question") or {}).get("brief") or {}).get("asked")) or []
    check("topic" in asked,
          "the asked roll records the topic ask (the loop is bounded)", asked)
    echo = (follow.get("content") or "")
    check("persona" in echo.lower() or "人设" in echo,
          "the echo carries the default-path declaration", echo)


async def material_to_clips_full_chain(ctx: Ctx) -> None:
    """material_to_clips 素材→短片全链（旗舰链本，需 dev worker + demo 桶 fixture + MiniMax
    配额）：真字节素材（合成转写自证处理终态）→ 方向建议 dock（SSE——选项
    预览律座）→ 途中插话（提醒尾 + pending 保持 + 下轮回填）→ clips 计划
    dock 呈现即开工（auto 档，ADR-117 §2——settled+born 同拍 + 零确认拍戳
    记 + confirmed_via=auto）→ auto 出生 run 真收官 → ask 档计划期修订链
    （面板钉存活 / chat 恒胜 / supersede 机器标记 / fill-key 幂等 / 打字
    母不答）→ SSE 散文确认 → 修订 run completed + clip 产物 → 触发回合
    reviewer → chat 修订 wiring 横切（同 id 原地改写 → 子图重跑）→ 扩张
    dock（新付费工作确认门 + Start 放行）。

    LLM 方差口径：方向 dock / 计划 dock 的措辞与路由是模型裁量（有界 nudge
    兜底）；锁的全是设计行为（插话不结算 / 提醒尾必在 / 修订恒胜 / 扩张必
    经确认门）。红了 = prompt 或机制回归信号，不是剧本松劲。"""
    # 默认档钉住（顺序无关——Ctx 全矩阵共享一个 user）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    fixture_prefix = f"scenario/s2-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("material_to_clips material to clips")
    await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s2-talk.mp4",
        file_url=src_key,  # 真字节——select_clips 真的剪
        extracted_text=" ".join(s for _, s in _SE2_SENTENCES),
        meta={
            "words": _talk_words(),
            "speaker_map": {"turns": [{"start": 0.0, "end": 95.0, "speaker": "host"}]},
            "language": "en",
        },
        processed=True,
    )
    await topup_wallet(ctx.user_id)  # clips 真渲染 + article 真 LLM 都花积分

    # ① 方向建议 dock（SSE——选项问预览帧律的确定性座位：探索 dock 恒带
    #    1–3 选项）→ 插话 → 自由文本作答回填。
    dock_turn: dict | None = None
    for prompt in _INT_EXPLORATION_PROMPTS:
        stream = await ctx.chat_stream(pid, prompt)
        check(stream.failed is None, "the exploration turn never fails", stream.failed)
        turn = stream.completed
        tool = terminal_tool_of(turn)
        check(tool != "present_plan",
              "an exploration question never docks a plan (事故④第一跳形态)", turn)
        q = turn["assistant_message"].get("question") or {}
        if tool == "ask_user" and (q.get("options") or []):
            dock_turn = turn
            break
    check(dock_turn is not None, "no options-dock turn after 3 tries", None)
    conv_id = dock_turn["conversation_id"]
    q1 = dock_turn["assistant_message"]["question"]
    check_options_dock(q1, "material_to_clips directions")
    check(not (dock_turn["assistant_message"].get("suggestions") or []),
          "消息流零选项 — the row carries no inline suggestion block",
          dock_turn["assistant_message"])

    # ①b 插话：与待决问题无关的能力问 → 正常回答 + 代码拼装提醒尾（原问题 +
    #    default_path 逐字，代码强制文本可锁）→ 问题保持待决。
    default_path = (q1.get("default_path") or "").strip()
    turn_i = await ctx.chat(pid, "By the way, what can you generate?")
    check(terminal_tool_of(turn_i) == "answer",
          "the interjection closes on the answer call", turn_i)
    check(turn_i.get("answered_question") is None,
          "an interjection never settles the pending ask", turn_i)
    check(not turn_i["assistant_message"].get("question"),
          "the interjection turn docks no new question", turn_i["assistant_message"])
    content_i = turn_i["assistant_message"].get("content") or ""
    check(has_prose(turn_i["assistant_message"]),
          "the interjection gets its normal answer", turn_i["assistant_message"])
    check(has_reminder_tail(content_i),
          "the reply ends with the code-composed reminder tail", content_i[-200:])
    check(default_path in content_i,
          "the tail carries the ask's default path verbatim", content_i[-200:])
    check(bool((q1.get("question") or "").strip()) and q1["question"] in content_i,
          "the tail quotes the BARE question, not the framing prose",
          content_i[-200:])
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id")
          == dock_turn["assistant_message"]["id"],
          "the ask stays pending through the interjection", res.json())

    # ①c 自由文本作答（点名 clips 方向）→ plan path 接续 → clips 计划 dock
    #    呈现即开工（auto 档，ADR-117 §2——settled+born 同拍，零确认拍）。
    res_a = await ctx.answer(dock_turn["assistant_message"]["id"],
                             {"kind": "freeform",
                              "text": "cut 3 vertical highlight clips from the talk"})
    check(res_a.status_code in (200, 201), "the freeform direction settles",
          res_a.text)
    follow = res_a.json().get("follow_up") or {}
    dock_msg: dict | None = None
    run1_id: str | None = None
    if follow.get("workflow_run_id"):
        dock_msg, run1_id = follow, str(follow["workflow_run_id"])
    dock_stream: StreamTurn | None = None
    for nudge in ("就按这个方向出计划——3 条竖屏高光短片。",
                  "the highlight clips plan, please",
                  "cut the highlights — 3 vertical clips"):
        if dock_msg is not None:
            break
        stream = await ctx.chat_stream(pid, nudge)
        check(stream.failed is None, "the plan nudge never fails", stream.failed)
        check(not is_plan_dock(stream.completed["assistant_message"]),
              "a held clips dock (守卫线/不可报价) is off-journey — estimate "
              "回归信号", stream.completed["assistant_message"])
        if stream.completed["run_id"] is not None:
            dock_msg = stream.completed["assistant_message"]
            run1_id = stream.completed["run_id"]
            dock_stream = stream
            break
    check(dock_msg is not None and run1_id is not None,
          "auto 档：the clips plan docks AND starts on presentation within "
          "3 nudges (零确认拍)", None)
    # 开工戳记（读库行一座，与信封路径无关）：kind=start + 零确认拍 +
    # 链带 clips + confirmed_via=auto + pending_brief 即清。
    dock_row = await message_row(dock_msg["id"])
    check((dock_row.get("answer") or {}).get("kind") == "start",
          "the presentation-time start lands kind=start", dock_row.get("answer"))
    check(((dock_row.get("question") or {}).get("requires_confirmation")) is False,
          "auto 档戳记 = 零确认拍（requires_confirmation=False at dock）",
          dock_row.get("question"))
    tasks = ((dock_row.get("intent") or {}).get("tasks")) or []
    check(any(t["tool"] == "select_clips" for t in tasks),
          "the docked chain carries the clips tool", tasks)
    run1_ctx = (await run_row(run1_id))["context"]
    check((run1_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
          "confirmed_via = auto（呈现即开工的常驻授权戳）",
          run1_ctx.get("confirmed_scope"))
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on the presentation-time start")
    if dock_stream is not None:
        # SSE draft 律（计划复述座）：信封散文 IS 持久化的计划复述。
        content = dock_msg.get("content") or ""
        echo = ((dock_row.get("intent") or {}).get("answer")) or ""
        check(content == echo,
              "the streamed draft's envelope content IS the persisted plan echo",
              f"{content[:120]!r} vs {echo[:120]!r}")

    # ①d auto 出生 run 真收官（出生即真跑——clips 链在真字节上 completed）+
    # 触发回合消费（建议问先 bail——后续修订消息不能被判定结算吃掉，③b 同
    # 款卫生）。然后钉 ask 档再进修订链：dock 恒等用户的拍，消除收官竞态
    # （auto 档的结构 held 与 ask 等待在信封面同形，计划期机器与档无关）。
    row1 = await wait_run_status(run1_id, {"completed", "failed"}, timeout=600.0)
    check(row1["status"] == "completed",
          "the auto-born run delivers on the real bytes", row1["status"])
    review1 = await wait_trigger_review(ctx, conv_id, run1_id)
    check(review1 is not None,
          "the auto-born run's trigger turn speaks its review row", run1_id)
    if (review1.get("question") or {}).get("kind") == "question":
        bail1 = await ctx.answer(review1["id"], {"kind": "bail"})
        check(bail1.status_code in (200, 201),
              "run1's review question is bailed (revision determinism)",
              bail1.text)
    await ctx.set_confirmation(execution="ask", credits="ask")

    # ② 修订链：面板钉存活 / chat 恒胜 / supersede / fill-key 幂等 / 打字母不答。
    #    开工即清的 pending_brief 由 dock_row 的 intent 列顶替（面板钉模拟器
    #    的胚子）；ids1 = auto 出生 run 的世界（修订 dock 在其上长草稿）。
    def pin_count(plan: dict, count: int) -> dict:
        """Simulate a panel hand edit: the select_clips count set in params —
        the edited chain IS the prior_intent (no merge machinery)."""
        edited = dict(plan["intent"])
        edited["tasks"] = [
            {**t, "params": {**task_params(t), "count": count}}
            if t["tool"] == "select_clips" else t
            for t in plan_tasks(plan)
        ]
        return edited

    plan1 = {"intent": dock_row.get("intent") or {}}  # 开工前的链（shim）
    first_qid = dock_msg["id"]
    ids1 = {n["id"] for n in (await ctx.graph(pid))["nodes"]}
    # 面板钉 count=4（区别于作答里的 3，钉存活才可见）+ 无关 refine 加德语版。
    turn2 = await ctx.chat(
        pid, "also add a German version of the clips", prior_intent=pin_count(plan1, 4)
    )
    check(terminal_tool_of(turn2) == "present_plan",
          "the refinement re-docks on present_plan", turn2)
    check(is_plan_dock(turn2["assistant_message"]), "the refinement re-docks",
          turn2["assistant_message"])
    check(turn2["assistant_message"]["id"] != first_qid,
          "the old plan is superseded by a new question row")
    tasks = plan_tasks(await pending_plan(ctx, pid))
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    # coerce_numbers_to_str 是 dock 边界的现行法：手改存活锁值不锁 JSON 类型。
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "4",
          "the panel hand edit survives an unrelated refine", tasks)
    check(any((task_params(t).get("target_language")
               or task_params(t).get("language")) == "de" for t in tasks),
          "the German fork arrived", tasks)
    graph2 = await ctx.graph(pid)
    ids2 = {n["id"] for n in graph2["nodes"]}
    check(ids1 < ids2,
          "the German fork grows a new draft node (superset, never twins)", ids2 - ids1)
    msgs = await ctx.messages(conv_id)
    old = next(m for m in msgs if m["id"] == first_qid)
    check((old.get("answer") or {}).get("text") == "superseded",
          "the superseded plan carries the machine marker", old.get("answer"))

    # chat 修订恒胜（覆盖面板钉）。
    plan2 = await pending_plan(ctx, pid)
    turn3 = await ctx.chat(
        pid, "clips only need 2", prior_intent=pin_count(plan2, 4)
    )
    check(terminal_tool_of(turn3) == "present_plan",
          "the chat revision re-docks", turn3)
    tasks = plan_tasks(await pending_plan(ctx, pid))
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "2",
          "the chat revision overrides the panel pin (chat always wins)", tasks)
    # 参数微调 = 同 fill_key 复用——图节点零双生。
    graph3 = await ctx.graph(pid)
    check(sorted(n["id"] for n in graph3["nodes"]) == sorted(ids2),
          "a param refine reuses the same nodes (fill-key idempotency — no twins)",
          graph3["nodes"])

    # task_book 待决不参与任何结算：打字母永不当选项答掉。
    live_qid = turn3["assistant_message"]["id"]
    turn4 = await ctx.chat(pid, "a")
    check(turn4.get("answered_question") is None,
          "a typed letter never answers a task_book", turn4)
    q_row = await message_row(live_qid)
    check(q_row.get("answer") is None or (q_row["answer"] or {}).get("text") == "superseded",
          "the plan stays pending or is superseded by a re-dock — never letter-answered",
          q_row.get("answer"))

    # ②d 去掉德语版——收缩修订重 dock，终链 = clips-only count 2。
    docked5: dict | None = None
    for prompt in ("drop the German version — just 2 English highlight clips",
                   "remove the German clips, keep the 2 English ones"):
        turn5 = await ctx.chat(pid, prompt)
        if is_plan_dock(turn5["assistant_message"]):
            tasks5 = plan_tasks(await pending_plan(ctx, pid))
            if not any((task_params(t).get("target_language")
                        or task_params(t).get("language")) == "de" for t in tasks5):
                docked5 = turn5
                tasks = tasks5
                break
    check(docked5 is not None, "the German fork leaves the chain on request", tasks)
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "2",
          "the shrink keeps the chat-won count", tasks)
    graph5 = await ctx.graph(pid)

    # ③ SSE 散文确认（ask 档——dock 等到的口头拍，与 Start 钮同一机器）→
    #    start_run + 草稿图原地填充（同 id 无双生；run1 世界在其下不动）。
    stream_s = await ctx.chat_stream(pid, "looks good, start")
    check(stream_s.failed is None, "the confirm turn never fails", stream_s.failed)
    turn_s = stream_s.completed
    check(terminal_tool_of(turn_s) == "start_run",
          "the prose confirmation closes on the start_run call", turn_s)
    run2_id = turn_s["run_id"]
    check(run2_id is not None, "prose confirmation starts the run", turn_s)
    check(turn_s["answered_question"] is not None, "the plan settles on start", turn_s)
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on start")
    filled_graph = await ctx.graph(pid)
    check(sorted(n["id"] for n in filled_graph["nodes"])
          == sorted(n["id"] for n in graph5["nodes"]),
          "start fills the SAME nodes in place (fill-key idempotency — never twins)",
          # 双侧 dump（同上——单侧 dump 无法归因多/少的是哪侧）。
          {"draft": graph5["nodes"], "filled": filled_graph["nodes"]})
    check(not any(n.get("state") == "draft" for n in filled_graph["nodes"]),
          "the draft world re-queues on start", filled_graph["nodes"])

    # ③b 真链收官 + 触发回合 reviewer 发言：intent dump = {type:
    #    trigger_review, trigger, ref, suggestions=labels}；建议 dock 成真实
    #    编号选项问。断言 dump 形态与 dock 良构；言语内容不锁（LLM 文案）。
    row = await wait_run_status(run2_id, {"completed", "failed"}, timeout=600.0)
    check(row["status"] == "completed",
          "the clips chain completes on the real bytes", row["status"])
    check(len(await outputs_of(pid, "clip")) >= 1, "the clip outputs land", None)
    review = await wait_trigger_review(ctx, conv_id, run2_id)
    check(review is not None,
          "the run-completed trigger turn speaks its review row", run2_id)
    rintent = (review or {}).get("intent") or {}
    check(rintent.get("trigger") == "run_completed" and rintent.get("ref") == run2_id,
          "the review dump names trigger + ref", rintent)
    sugs = rintent.get("suggestions") or []
    check(0 <= len(sugs) <= 3, "0–3 suggestion labels (schema-bounded)", sugs)
    check(all(isinstance(s, str) and s.strip() for s in sugs),
          "each suggestion is a user-voice label", sugs)
    if sugs:
        question = (review or {}).get("question") or {}
        check(question.get("kind") == "question",
              "the suggestions dock as a real options question", question)
        options = question.get("options") or []
        check([o.get("id") for o in options] == [str(i + 1) for i in range(len(sugs))]
              and [o.get("label") for o in options] == sugs,
              "the dock options are the numbered labels (1/2/3 grammar)",
              options)
        # Journey 卫生（非断言）：建议问先 × 跳过收掉——后续修订消息不能被
        # 判定结算吃掉（wiring 修订路才是断言对象）。
        bail = await ctx.answer(review["id"], {"kind": "bail"})
        check(bail.status_code in (200, 201),
              "the review suggestions question is bailed (revision determinism)",
              bail.text)

    # ④ 修订 = wiring 横切：chat 修订 → WiringProposal（edit_prompt + run
    #    子图）→ 节点程序行原地改写（同 id 无双生）→ 子图重跑起 run。锁的是
    #    设计行为；红了 = chat_intent prompt 回归信号。两 run 世界有两个
    #    clips 节点——模型指认哪一个是 LLM 裁量（wiring 提案自带 node id），
    #    断言锁「恰一个 clips 节点原地改写」不锁指认。
    graph_before = await ctx.graph(pid)
    clips_before = {
        n["id"]: (n.get("spec") or {}).get("prompt")
        for n in graph_before["nodes"]
        if (n.get("spec") or {}).get("tool") == "select_clips"
    }
    check(len(clips_before) >= 1, "the runs' fills grew clips graph nodes",
          graph_before["nodes"])
    turn_rev = await ctx.chat(pid, "把选段再大胆一点——只留最有冲击力的瞬间。")
    check(terminal_tool_of(turn_rev) == "run_birth",
          "the revision closes on a proposal tool's run birth (chat path)", turn_rev)
    check(turn_rev["run_id"] is not None,
          "the revision rides the wiring path — the subgraph rerun is born",
          turn_rev)
    graph_after = await ctx.graph(pid)
    check(sorted(n["id"] for n in graph_after["nodes"])
          == sorted(n["id"] for n in graph_before["nodes"]),
          "the revision reuses the SAME nodes (edit_prompt + rerun — never a twin)",
          graph_after["nodes"])
    after_by_id = {n["id"]: n for n in graph_after["nodes"]}
    edited = [
        nid for nid, prompt in clips_before.items()
        if (after_by_id[nid].get("spec") or {}).get("prompt") != prompt
    ]
    check(len(edited) == 1,
          "edit_prompt rewrote exactly one clips node's program in place",
          {nid: (after_by_id[nid].get("spec") or {}).get("prompt")
           for nid in clips_before})
    check(after_by_id[edited[0]].get("state") != "draft",
          "the rerun re-queues its node", after_by_id[edited[0]].get("state"))
    # 修订 run 先收官（扩张 Start 会撞出生地活跃 422——等待是 journey 卫生）；
    # 其收官触发回合同样先 bail（否则扩张拍的消息被判定结算吃掉）。
    await wait_run_status(turn_rev["run_id"], {"completed", "failed"}, timeout=600.0)
    review2 = await wait_trigger_review(ctx, conv_id, turn_rev["run_id"], timeout=90.0)
    if review2 is not None and (review2.get("question") or {}).get("kind") == "question":
        await ctx.answer(review2["id"], {"kind": "bail"})

    # ⑤ 扩张 → 确认门（已批图之外的新付费工作必须 dock 确认才放行——无论
    #    LLM 走 edit_graph(add_node+run) 还是 propose_tasks，回合都 dock
    #    task_book + 零 run；Start 才生 run。路由无关断言：信封形状 +
    #    draft 预览 + Start 后链上生 run）。
    turn_exp: dict | None = None
    for prompt in ("write a long-form article from the talk as a new piece",
                   "add an article version alongside the clips",
                   "the article, please"):
        cand = await ctx.chat(pid, prompt)
        check(cand.get("run_id") is None,
              "扩张同 turn 直跑 = 教义红线（new paid work must never run "
              "unauthorized）", cand)
        if is_plan_dock(cand["assistant_message"]):
            turn_exp = cand
            break
    check(turn_exp is not None,
          "the expansion ask docks a plan within 3 prompts", None)
    check(terminal_tool_of(turn_exp) == "present_plan",
          "the expansion turn closes on the plan dock", turn_exp)
    graph_docked = await ctx.graph(pid)
    draft_tools = [
        (n.get("spec") or {}).get("tool")
        for n in graph_docked["nodes"]
        if n.get("state") == "draft"
    ]
    check("write_article" in draft_tools,
          "the dock's draft stamp previews the article node (the door's "
          "mutation rolled back; canonical fill keys)", draft_tools)
    res_exp = await ctx.answer(turn_exp["assistant_message"]["id"],
                               {"kind": "start"})
    check(res_exp.status_code == 200, "dock Start answers the plan", res_exp.text)
    run_exp = res_exp.json()["answered_question"].get("workflow_run_id")
    check(run_exp, "a run was born on Start", res_exp.json())
    runs_exp = await ctx.client.get(f"/projects/{pid}/runs")
    born_exp = next((r for r in runs_exp.json() if r.get("id") == run_exp),
                    None) or {}
    exp_tools = [
        t.get("tool")
        for t in (born_exp.get("context") or {}).get("tasks") or []
    ]
    check("write_article" in exp_tools,
          "the born run carries the expansion chain", exp_tools)
    # Journey 卫生：扩张 run（writer 链读 transcript 文本，会 completed）的
    # 触发回合是 fire-and-forget；不消费它就 cleanup 会让在飞 LLM 调用撞上
    # 项目删除（messages conversation FK 竞态）。等到落地就 bail；超时静默。
    await wait_run_terminal(run_exp, timeout=600.0)
    review3 = await wait_trigger_review(ctx, conv_id, run_exp, timeout=90.0)
    if review3 is not None and (review3.get("question") or {}).get("kind") == "question":
        await ctx.answer(review3["id"], {"kind": "bail"})


async def material_suggestion_exploration(ctx: Ctx) -> None:
    """guided_exploration 素材→建议→探索（需 dev worker + MiniMax 配额）：方向建议选项 dock
    （消息流零选项 + 持久化事实 + × 安全跳过）→ 发现型目标（SSE 全链：
    chat.explore.* 活动键族 + 决策包 dock 三面）→ 探索三族出生（一条
    journey， ExplorationRow 表座——探索族永不入图）→ Start →
    run.context.confirmed_scope 五字段快照 → 产物真落地 → 确定性尾
    （I-EXPLORE-01 执行门拒收 / 幂等重放 / 无时间轴降级诚实 / 图面零探索
    节点）。fixture 纪律：scenario/ 前缀真桶拷贝；时间轴落在 demo_talk
    真实时长内（~119s）；words 逐词真值（门在出生时刻逐字校验 excerpt）。"""
    from app.chat.exploration_tools import execute_exploration_tool
    from app.chat.perception import SearchTranscriptParams, run_perception_tool
    from app.models.tables import ExplorationRow
    from app.pipeline.graph_store import WiringRejected, apply_wiring_ops

    # ask 档钉住（ADR-117——本旅程保留确认拍族断言：dock 等待 / typed Start /
    # 草稿图横切 / lifecycle stamp 拍②③，均从 lost_user 迁入或原生）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    fixture_prefix = f"scenario/s3-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("guided_exploration discovery chain")
    project_uuid = uuid.UUID(pid)
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s3-talk.mp4",
        file_url=src_key,  # 真字节——cut_segments 真的剪
        extracted_text=" ".join(s for _, s in _SE2_SENTENCES),
        meta={
            "words": _talk_words(),
            "speaker_map": {"turns": [{"start": 0.0, "end": 95.0, "speaker": "host"}]},
            "language": "en",
        },
        processed=True,  # worker 的资产队列不碰（时间轴/文本即种子）
    )
    await topup_wallet(ctx.user_id)  # cut_segments 真渲染 + writer 真 LLM

    # ① 建议 beat：探索问 → 选项 dock（可点选可 ×，散文恒带默认路径）；
    #    消息流零选项——assistant 行永不携带 suggestions 交互块。
    turn0 = await elicit_options_dock_turn(ctx, pid, "guided_exploration directions")
    msg0 = turn0["assistant_message"]
    check(terminal_tool_of(turn0) == "ask_user",
          "the exploration turn closes on the options dock", turn0)
    check_options_dock(msg0.get("question") or {}, "guided_exploration directions")
    check(not (msg0.get("suggestions") or []),
          "消息流零选项 — the row carries no inline suggestion block", msg0)
    check(turn0["run_id"] is None, "an options ask never starts a run", turn0)
    row0 = next(m for m in await conversation_items(ctx, pid) if m["id"] == msg0["id"])
    check((row0.get("question") or {}).get("kind") == "question",
          "the options dock persists on the message row", row0)
    check(not (row0.get("suggestions") or []),
          "the persisted row carries no inline suggestion block", row0)
    bail = await ctx.answer(msg0["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201),
          "the options dock bails clean (× = safe skip)", bail.text)

    # ② 发现型目标（SSE 全链）。
    stream = await ctx.chat_stream(
        pid,
        "Find the parts where I talk about pricing — cut those into a clip, "
        "and write an English post from them.",
    )
    check(stream.failed is None, "the discovery turn never fails", stream.failed)
    check(stream.completed is not None, "the discovery turn completes", stream.activities)

    # 工作会话活动键族：读的开/收 + 三个里程碑帧（出生即完成，count 唯一载荷）。
    # 用哪把读具是模型的合法裁量——ADR-107：锚定转录 ≤8000 字符内联进
    # digest，短文源头不搜索（本 fixture 的 ~119s talk 正在预算内），所以旅
    # 程锁「发现回合落地前读过素材」不变量，不锁 search_transcript 的帧。
    acts = stream.activities
    read_opens = [
        a
        for a in acts
        if (a.get("key") or "").startswith("chat.inspecting.")
        or a.get("key") == "chat.explore.searching"
    ]
    read_settles = [
        a
        for a in acts
        if (a.get("key") or "").startswith("chat.inspectingDone.")
        or (a.get("key") or "").startswith("chat.inspectingFailed.")
        or a.get("key") == "chat.explore.searchingDone"
    ]
    check(
        read_opens and all(a["status"] == "active" for a in read_opens),
        "the discovery turn grounds via visible reads (open frames)",
        acts,
    )
    check(
        read_settles
        and all(a["status"] in ("completed", "failed") for a in read_settles),
        "the reads settle (done/failed mirror frames)",
        acts,
    )
    for key in ("candidatesReady", "selectsReady", "plansReady"):
        frames = [a for a in acts if a.get("key") == f"chat.explore.{key}"]
        check(
            len(frames) == 1
            and frames[0]["kind"] == "draft"
            and frames[0]["status"] == "completed"
            and isinstance(frames[0].get("count"), int)
            and frames[0]["count"] >= 1,
            f"the {key} milestone lands born-completed with its count",
            acts,
        )

    # 决策包 dock：plans 阅读层 + 编译链证据 + quote。
    dock_msg = stream.completed["assistant_message"]
    check(is_plan_dock(dock_msg), "the discovery chain docks the decision package", dock_msg)
    question = dock_msg["question"]
    plans_payload = question.get("plans") or []
    check(plans_payload, "the dock carries the plans reading layer", question)
    check(
        all(p.get("plan_id") and "title" in p and p.get("outputs") for p in plans_payload),
        "every plan row carries plan_id / title / outputs",
        plans_payload,
    )
    intent_dump = dock_msg.get("intent") or {}
    dock_tools = [t.get("tool") for t in intent_dump.get("tasks") or []]
    check(
        "cut_segments" in dock_tools and "write_post" in dock_tools,
        "the compiled chain = cut_segments + write_post (编译移出 LLM)",
        dock_tools,
    )
    check(
        "select_clips" not in dock_tools,
        "the compiler never emits select_clips (the execution world has no "
        "second discoverer)",
        dock_tools,
    )
    check("estimate_credits" in question, "the quote rides the dock (费用语义)", question)
    check("derived" in question, "the derived preview rides the dock", question)
    # ADR-117 §4 戳记（ask 档）：呈现时算好的确认需要——本座断言它欠拍
    # （两档 ask + 有报价 → reason 归 pref 族），auto 档的对偶戳在 lost_user。
    check(question.get("requires_confirmation") is True,
          "ask 档戳记 = dock 欠确认拍（requires_confirmation=True）", question)
    check(str(question.get("confirm_reason") or "").endswith("_pref"),
          "the reason names the pref family (money first when both ask)",
          question.get("confirm_reason"))

    # 草稿图横切（图先展示后运行——自 lost_user 迁入 ask 档座）：dock 即 stamp——
    # draft 节点 + 逐节点估价，零消耗直到 start。
    draft_graph = await ctx.graph(pid)
    draft_nodes = [
        n for n in draft_graph["nodes"]
        if n.get("state") == "draft"
        and (n.get("spec") or {}).get("prototype") in ("generator", "editor")
    ]
    check(len(draft_nodes) >= 1, "the dock stamps the draft graph (图先展示后运行)",
          draft_graph["nodes"])
    check(not any(
        (n.get("spec") or {}).get("role") == "task_book"
        for n in draft_graph["nodes"]
    ), "the read frame hides the task_book node (confirm seat = dock pill)",
       draft_graph["nodes"])
    check(any(n.get("estimate_credits") for n in draft_nodes),
          "draft nodes carry their own quotes (逐节点估价)", draft_nodes)
    draft_ids = sorted(n["id"] for n in draft_graph["nodes"])

    # Lifecycle stamp 拍②（自 lost_user 迁入）：docked 全估价链读 plan_ready ∧
    # confirmation_ready。
    stamp1 = (await ctx.results(pid))["lifecycle"]
    check(stamp1["plan_ready"] is True
          and stamp1["confirmation_ready"] is True
          and stamp1["blockers"] == []
          and stamp1["state"] == "confirmation_ready",
          "the docked plan reads plan_ready ∧ confirmation_ready on the stamp",
          stamp1)

    # Lifecycle stamp 拍③（自 lost_user 迁入）：活跃 run 扣住确认权而计划保持
    # docked——plan_ready 恒真、confirmation_ready 翻假、blocker 点名
    # active_run、rollup 读 running；落定即交还（PLAN_READY ≠ confirm
    # authority）。
    seeded_run = await seed_active_run(pid)
    stamp2 = (await ctx.results(pid))["lifecycle"]
    check(stamp2["plan_ready"] is True
          and stamp2["confirmation_ready"] is False
          and "active_run" in stamp2["blockers"]
          and stamp2["state"] == "running",
          "an active run blocks confirmation while the plan stays docked",
          stamp2)
    await settle_seeded_run(seeded_run)
    stamp2b = (await ctx.results(pid))["lifecycle"]
    check(stamp2b["confirmation_ready"] is True
          and stamp2b["blockers"] == [],
          "settling the run hands confirmation readiness back", stamp2b)

    # 探索三族出生，一条 journey（ExplorationRow 表座——探索族永不入图）。
    async with AsyncSessionLocal() as db:
        explore_rows = list(
            (
                await db.execute(
                    select(ExplorationRow).where(
                        ExplorationRow.project_id == project_uuid,
                    )
                )
            ).scalars().all()
        )
        kinds = {r.spec.get("exploration_kind") for r in explore_rows}
        check(
            {"candidate_set", "select", "content_plan"} <= kinds,
            "the exploration three families are born",
            kinds,
        )
        journey_ids = {str(r.journey_id) for r in explore_rows}
        check(len(journey_ids) == 1, "the whole chain rides ONE journey", journey_ids)
        journeys = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Journey)
                    .where(Journey.project_id == project_uuid)
                )
            ).scalar_one()
        )
        check(journeys == 1, "exactly one Journey row", journeys)
    db_plan_ids = {
        str(r.id) for r in explore_rows if r.spec.get("exploration_kind") == "content_plan"
    }
    check(
        {p["plan_id"] for p in plans_payload} == db_plan_ids,
        "the dock's plan ids == the table's content_plan rows",
        (plans_payload, [str(r.id) for r in explore_rows]),
    )

    # 恢复路复证（plans 双座的第二座）：pending_question 直读 plans。
    conv = await ctx.conversation(pid)
    check(conv.status_code == 200, "the conversation reads back", conv.text)
    pending = conv.json().get("pending_question") or {}
    check(
        (pending.get("question") or {}).get("plans"),
        "the restore path's pending_question carries plans (pending_brief 座)",
        pending,
    )

    # ③ 确认 → run 出生 → Confirmed Scope Snapshot。
    res = await ctx.answer(dock_msg["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the decision package", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "a run was born on Start", res.json())

    # 同 id 原地填充（自 lost_user 迁入——same compile → same fill keys, never
    # twins）：start 后图面 = draft 拍的同批 id，零 draft 态残留。
    filled_graph = await ctx.graph(pid)
    check(sorted(n["id"] for n in filled_graph["nodes"]) == draft_ids,
          "start fills the SAME nodes in place (never twins)",
          # 双侧 dump（取证律——单侧 dump 曾让一轮红无法归因）。
          {"draft": draft_graph["nodes"], "filled": filled_graph["nodes"]})
    check(not any(n.get("state") == "draft" for n in filled_graph["nodes"]),
          "the draft world re-queues on start", filled_graph["nodes"])

    run_ctx = (await run_row(run_id))["context"]
    scope = run_ctx.get("confirmed_scope") or {}
    check(bool(scope), "the run carries the Confirmed Scope Snapshot", run_ctx)
    check(
        scope.get("confirmation_id") == dock_msg["id"],
        "confirmation_id = the docked message (确认点可追)",
        scope,
    )
    check(bool(scope.get("confirmed_at")), "confirmed_at stamped", scope)
    check(
        scope.get("confirmed_via") == "dock_pill",
        "confirmed_via = dock_pill (typed Start 座位)",
        scope,
    )
    check(
        {p.get("plan_id") for p in scope.get("plans") or []}
        == {p["plan_id"] for p in plans_payload},
        "the snapshot's plans = the docked reading layer",
        scope,
    )
    check(
        [t.get("tool") for t in scope.get("compiled_scope") or []] == dock_tools,
        "the snapshot's compiled_scope = the chain the run was born with",
        (scope.get("compiled_scope"), dock_tools),
    )
    check(
        scope.get("quote") == question.get("estimate_credits"),
        "the snapshot's quote = the quote shown at confirm time",
        (scope.get("quote"), question.get("estimate_credits")),
    )

    # ④ 产物落地（真渲染 + 真 writer）。
    final = await wait_run_terminal(run_id, timeout=600.0)
    check(final == "completed", "the discovery run completes", final)
    clips = await outputs_of(pid, "clip")
    check(len(clips) >= 1, "cut_segments' clip output lands", len(clips))
    posts = await outputs_of(pid, "post")
    check(len(posts) >= 1, "the post output lands", len(posts))

    # ⑤ 确定性尾（零 LLM 进程内——执行门 / 幂等 / 降级 / 图面负形）。
    async with AsyncSessionLocal() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_uuid))
        ).scalar_one()
        rows = list(
            (
                await db.execute(
                    select(ExplorationRow).where(
                        ExplorationRow.project_id == project_uuid,
                    )
                )
            ).scalars().all()
        )
        cset = next(r for r in rows if r.spec.get("exploration_kind") == "candidate_set")
        sel = next(r for r in rows if r.spec.get("exploration_kind") == "select")
        explore_ids = {str(r.id) for r in rows}

        # I-EXPLORE-01: 执行门拒收探索产物（run / delete / connect 全拒——
        # 探索族不在 graph_nodes，任何图写口引用即悬空拒收）。
        for ops in (
            [{"op": "run", "nodes": [str(cset.id)]}],
            [{"op": "delete_node", "node": str(sel.id)}],
            [{"op": "connect", "from_node": str(cset.id), "to_node": str(sel.id)}],
        ):
            try:
                await apply_wiring_ops(db, project_uuid, ops)
            except WiringRejected:
                pass
            else:
                raise JourneyFailure(f"I-EXPLORE-01: the wiring door accepted {ops}")

        # 幂等重放：identical call → the SAME artifact, no twin。
        idem_args = {
            "asset_id": asset_id,
            "topic": "pricing",
            "goal": "s3 idempotency probe",
            "members": [{"start": 12.0, "end": 18.9, "speaker": "host"}],
        }
        first = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        second = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        id_of = lambda text: re.search(r"candidate_set_id: ([0-9a-f-]{36})", text).group(1)  # noqa: E731
        check(
            id_of(first) == id_of(second),
            "idempotent replay returns the existing artifact",
            (first, second),
        )
        explore_ids.add(id_of(first))

        # 无时间轴降级: an asset without words is an honest door rejection
        # and the reads say so — never a fabricated range。
        bare_asset_id = await seed_asset(
            pid, ctx.user_id, AssetType.VIDEO, "s3-bare.mp4",
            extracted_text="A talk without word-level timestamps.",
            meta={"language": "en"},
            processed=True,
        )
        obs = await run_perception_tool(
            db, project, "search_transcript",
            SearchTranscriptParams(query="pricing", asset_id=uuid.UUID(bare_asset_id)),
        )
        check(
            "timeline-ready" in obs.text or "word-level" in obs.text,
            "the no-timeline read is an honest empty, never a fabricated hit",
            obs.text,
        )
        rejected = await execute_exploration_tool(
            db, project, "propose_candidates",
            {**idem_args, "asset_id": bare_asset_id, "goal": "s3 degradation probe"},
        )
        check(
            rejected.startswith("The door rejected"),
            "exploration on a wordless asset is a door rejection",
            rejected,
        )
        await db.commit()

        journeys = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Journey)
                    .where(Journey.project_id == project_uuid)
                )
            ).scalar_one()
        )
        check(
            journeys == 2,
            "chain journey + idem-probe journey — adopt never mints twins "
            "(rejected calls never mint)",
            journeys,
        )

    # 图面负形（Workspace v4.2 C1——探索族永不入图，画布零探索节点）。
    graph = await ctx.graph(pid)
    check(
        all(n["id"] not in explore_ids for n in graph["nodes"]),
        "the exploration family never enters the graph (画布零探索节点)",
        [n["id"] for n in graph["nodes"] if n["id"] in explore_ids],
    )

    # Journey 卫生（非断言）：run 收官的 trigger 回合是 fire-and-forget；
    # 不消费它就 cleanup 会让在飞的 LLM 调用撞上项目删除（messages
    # conversation FK 竞态）。等到落地就 bail 掉建议问；超时静默通过。
    conv_id = (stream.completed or {}).get("conversation_id")
    if conv_id:
        review = await wait_trigger_review(ctx, conv_id, run_id, timeout=90.0)
        if review is not None and (review.get("question") or {}).get("kind") == "question":
            await ctx.answer(review["id"], {"kind": "bail"})


async def no_material_writers(ctx: Ctx) -> None:
    """writing_without_material 无素材→图文 + caption mode 默认吸收：写手族（post / quotes /
    carousel）无素材直生（root = 主题，六素材硬门全卸）；caption 三拍——
    A) 有独立第二语言（项目 de / 素材 en）且无字幕关键词 → 无字幕 dock
       问，计划直接 dock 且 intent.caption_mode == "source_only"；Start 后
       run.context.caption_mode 同为 source_only；
    B) 用户原话带"双语" → 用户原话恒胜：bilingual 随 dock 的 intent，
       Start 后 run.context.caption_mode == "bilingual"；
    C) 关键词设定 → 追问（修订轮不再提字幕）→ 面板 Start：设定值经暂存
       继承存活（"未提及" ≠ "撤回"，服务端从 stored pending 继承）。

    LLM 判定有抖动（"make a quote card" 可能回反问或提别的链——两者都
    合法），各部各给 3 次尝试直到目标工具的计划落地。

    fixture 纪律：素材必须可读——单行占位文本 + 无 understanding 会让诚实
    读路拿到 _WARM_DEAD_TEXT（字节不存在，warm 建不出），模型依法拒 dock
    或给 paste-text 选项（轮盘式随机命中）。厚转录 + seed_understanding
    让乐观 dock 与先读后 dock 两条合法路都通。"""
    # ask 档钉住（ADR-117——本旅程的 typed Start / dock 等待断言全是确认拍族）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    material = (
        "Cities are getting hotter, and the bill lands on the people least "
        "able to pay it. A shaded street can be ten degrees cooler than the "
        "block next to it — that is not an amenity, that is infrastructure. "
        "When we plant a row of trees we are not decorating the neighborhood; "
        "we are buying the cheapest climate adaptation a city can get. "
        "Reflective roofs do the same work from the top down, bouncing the "
        "heat back before it ever enters the building. The mayors who "
        "understand this are not asking whether to fund shade — they are "
        "asking why they waited so long."
    )

    async def dock_writer(pid: str, prompts: tuple[str, ...], tool: str,
                          label: str) -> dict:
        docked: dict | None = None
        tools_seen: list = []
        for prompt in prompts:
            turn = await ctx.chat(pid, prompt)
            if not is_plan_dock(turn["assistant_message"]):
                continue  # ask-back / prose — nudge again
            plan = await pending_plan(ctx, pid)
            tools_seen = [t.get("tool") for t in plan_tasks(plan)]
            if tool in tools_seen:
                docked = turn
                break
            # Wrong chain docked — bail the plan before nudging again (a live
            # dock would read the next chat message as its revision/Start).
            await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
        check(docked is not None, f"{label}: no {tool} plan dock after 3 turns",
              tools_seen)
        return docked

    # A) distinct alt language, no caption wording → no question ever docks;
    #    the plan carries the visible default (source_only) end-to-end.
    pid = await ctx.new_project("writing_without_material-A caption default absorbed")
    await set_project_language(pid, "de")
    # Fixture declaration: the language fact is the declared COMPLETED row's
    # meta — worker-immune by construction.
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid)
    await seed_completed_run(pid)
    docked_a: dict | None = None
    tools_seen_a: list = []
    for prompt in ("make a quote card from the video",
                   "pull the sharpest quotes from my keynote into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid, prompt)
        q = turn["assistant_message"].get("question") or {}
        check(
            not any(str(o.get("id", "")).startswith("caption_mode_")
                    for o in q.get("options") or []),
            "A: no caption-mode question ever docks (default absorption)",
            q,
        )
        if not is_plan_dock(turn["assistant_message"]):
            continue
        plan = await pending_plan(ctx, pid)
        tools_seen_a = [t.get("tool") for t in plan_tasks(plan)]
        if "write_quotes" in tools_seen_a:
            docked_a = turn
            break
        await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
    check(docked_a is not None, "A: no write_quotes plan dock after 3 turns",
          tools_seen_a)
    check(terminal_tool_of(docked_a) == "present_plan",
          "A: the turn closes straight on the plan dock (no caption gate)",
          docked_a)
    check(docked_a.get("run_id") is None,
          "A: no run before Start (same-turn create_run is forbidden)",
          docked_a)
    plan = await pending_plan(ctx, pid)
    check(((plan or {}).get("intent") or {}).get("caption_mode") == "source_only",
          "A: the visible default rides the docked intent", plan)
    res = await ctx.answer(docked_a["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "A: dock Start answers the plan", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "A: a run was born on Start", res.json())
    runs = await ctx.client.get(f"/projects/{pid}/runs")
    born = next((r for r in runs.json() if r.get("id") == run_id), None) or {}
    check((born.get("context") or {}).get("caption_mode") == "source_only",
          "A: run.context.caption_mode", born.get("context"))
    await wait_run_terminal(run_id)  # journey 卫生：Start 的 run 落定再起下家

    # B) the user's own words always win: a literal "bilingual" stamps the
    #    mode over any default.
    pid_b = await ctx.new_project("writing_without_material-B user wording wins")
    await set_project_language(pid_b, "de")
    await seed_asset(pid_b, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid_b)
    await seed_completed_run(pid_b)
    docked_b = await dock_writer(
        pid_b,
        ("make a bilingual quote card from the video",
         "pull the keynote's sharpest lines into bilingual quote cards",
         "bilingual quote cards, please"),
        "write_quotes", "B",
    )
    plan_b = await pending_plan(ctx, pid_b)
    check(((plan_b or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "B: the user's wording stamps bilingual on the docked intent", plan_b)
    res_b = await ctx.answer(docked_b["assistant_message"]["id"], {"kind": "start"})
    check(res_b.status_code == 200, "B: dock Start answers the plan", res_b.text)
    rid_b = res_b.json()["answered_question"].get("workflow_run_id")
    runs = await ctx.client.get(f"/projects/{pid_b}/runs")
    born_b = next((r for r in runs.json() if r.get("id") == rid_b), None) or {}
    check((born_b.get("context") or {}).get("caption_mode") == "bilingual",
          "B: run.context.caption_mode follows the user's wording",
          born_b.get("context"))
    await wait_run_terminal(rid_b)  # journey 卫生

    # C) 设定 → 追问 → Start：the mode survives a refinement turn that
    #    doesn't re-mention it (stash inherit) AND a panel Start that strips
    #    the field ("not mentioned" ≠ "retracted" — the server inherits from
    #    the stored pending brief).
    pid_c = await ctx.new_project("writing_without_material-C mode survives refinement")
    await set_project_language(pid_c, "de")
    await seed_asset(pid_c, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid_c)
    docked_c = await dock_writer(
        pid_c,
        ("make bilingual quote cards from the video",
         "pull the keynote's sharpest quotes into bilingual cards",
         "bilingual quote cards, please"),
        "write_quotes", "C",
    )
    plan_qid = docked_c["assistant_message"]["id"]
    plan_c = await pending_plan(ctx, pid_c)
    check(((plan_c or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "C: the keyword stamps bilingual on the first dock", plan_c)
    for nudge in ("make it 3 cards instead",
                  "change that to 3 quote cards",
                  "actually, only 3 cards"):  # 修订措辞 — 散文确认会绕过追问路径
        turn = await ctx.chat(pid_c, nudge)
        plan = await pending_plan(ctx, pid_c)
        check(((plan or {}).get("intent") or {}).get("caption_mode") == "bilingual",
              "C: the refinement turn keeps the stamped caption_mode", plan)
        if is_plan_dock(turn["assistant_message"]):
            plan_qid = turn["assistant_message"]["id"]
            break
    # Start THROUGH THE PANEL: the frontend's normalize strips fields it
    # doesn't edit, so its Start payload carries the plan's intent minus
    # caption_mode — the server must inherit the stamped mode from the
    # stored pending brief ("not mentioned" ≠ "retracted").
    plan = await pending_plan(ctx, pid_c)
    panel_intent = dict((plan or {}).get("intent") or {})
    check(bool(panel_intent), "C: pending plan carries an intent", plan)
    panel_intent.pop("caption_mode", None)
    res = await ctx.answer(plan_qid, {"kind": "start", "intent": panel_intent})
    check(res.status_code == 200, "C: plan start accepted", res.text)
    rid_c = res.json()["answered_question"].get("workflow_run_id")
    check(rid_c, "C: run id on the answered plan", res.json())
    runs = await ctx.client.get(f"/projects/{pid_c}/runs")
    born_c = next((r for r in runs.json() if r.get("id") == rid_c), None) or {}
    check((born_c.get("context") or {}).get("caption_mode") == "bilingual",
          "C: run.context.caption_mode survives set → refine → Start",
          born_c.get("context"))
    await wait_run_terminal(rid_c)  # journey 卫生

    # D) 无素材直生 — post：主题即根，写手零素材跑（六素材硬门全卸）。
    pid_d = await ctx.new_project("writing_without_material-D post without material")
    docked_d = await dock_writer(
        pid_d,
        ("Write a LinkedIn post about the EU AI Act for researchers.",
         "draft a LinkedIn post on the EU AI Act, aimed at researchers",
         "the post, please"),
        "write_post", "D",
    )
    check(docked_d.get("run_id") is None, "D: no run before Start", docked_d)
    await ctx.answer(docked_d["assistant_message"]["id"], {"kind": "bail"})

    # E) 无素材直生 — quotes：alt-language 项目（de）零素材，全程零字幕
    #    dock 问（默认值能扛的参数永不阻塞）。
    pid_e = await ctx.new_project("writing_without_material-E quotes without material")
    await set_project_language(pid_e, "de")
    docked_e: dict | None = None
    for prompt in ("make a quote card about remote work",
                   "pull three sharp lines about remote work into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid_e, prompt)
        q = turn["assistant_message"].get("question") or {}
        check(not any(str(o.get("id", "")).startswith("caption_mode_")
                      for o in q.get("options") or []),
              "E: no caption-mode question ever docks (默认值能扛的参数永不阻塞)", q)
        if not is_plan_dock(turn["assistant_message"]):
            continue
        plan_e = await pending_plan(ctx, pid_e)
        if "write_quotes" in [t.get("tool") for t in plan_tasks(plan_e)]:
            docked_e = turn
            break
        await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
    check(docked_e is not None, "E: no write_quotes plan dock after 3 turns")
    mode_e = (((await pending_plan(ctx, pid_e)) or {}).get("intent") or {}).get("caption_mode")
    check(mode_e in (None, "source_only"),
          "E: the absorbed default never reads bilingual unprompted", mode_e)
    await ctx.answer(docked_e["assistant_message"]["id"], {"kind": "bail"})

    # F) 无素材直生 — carousel。
    pid_f = await ctx.new_project("writing_without_material-F carousel without material")
    docked_f = await dock_writer(
        pid_f,
        ("make a carousel about remote work",
         "turn the remote-work theme into a carousel",
         "the carousel, please"),
        "write_carousel", "F",
    )
    check(docked_f.get("run_id") is None, "F: no run before Start", docked_f)
    await ctx.answer(docked_f["assistant_message"]["id"], {"kind": "bail"})


async def research_grounds_writer(ctx: Ctx) -> None:
    """research_to_writing 调研→写作：research 全链（有界 loop 节点）——chat 出书 → 面板手编
    chain 为 [research, write_post] 起步 → research step done +
    spec.research_brief 钢印 + writer 在 research 之后完成 + post 产物存在。

    网络方差说明：活 DDG 可能全灭（无网 / 被限流）——诚实降级下 brief 带
    caveat 自述、run 照样 completed。断言只看「钢印存在 + 步骤有序 +
    产物存在」，不看简报内容质量（那是 prompt / provider 层的事）。"""
    # ask 档钉住（ADR-117——dock 等待 + 面板手编 typed Start 是确认拍族断言）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    pid = await ctx.new_project("research_to_writing research grounds writer")

    turn1 = await ctx.chat(
        pid,
        "Write a LinkedIn post about the EU AI Act's 2026 enforcement — "
        "research the latest developments first.",
    )
    check(terminal_tool_of(turn1) == "present_plan",
          "a rooted topic closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]),
          "a rooted topic docks a plan", turn1["assistant_message"])
    plan = (await ctx.results(pid)).get("pending_brief")
    qid = turn1["assistant_message"]["id"]

    # 面板手编起步（material_to_clips 先例）：chain 换成确定性的 [research, write_post]。
    edited = dict(plan["intent"])
    edited["tasks"] = [
        {
            "tool": "research",
            "params": {"query": "EU AI Act 2026 enforcement latest developments"},
        },
        {"tool": "write_post", "params": {"language": "en"}},
    ]
    res = await ctx.answer(qid, {"kind": "start", "intent": edited})
    check(res.status_code == 200, "the research chain starts", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "a run was born", res.json())

    row = await wait_run_status(run_id, {"completed", "failed"}, timeout=600.0)
    check(row["status"] == "completed",
          "the run completes (research is best-effort, never a blocker)", row["status"])

    steps = await step_rows(run_id)
    research_steps = [s for s in steps if s["kind"] == "research"]
    check(len(research_steps) == 1, "one hoisted research step", [s["kind"] for s in steps])
    rs = research_steps[0]
    check(rs["status"] == "done",
          "the research step completes even on a dry trail", rs["error"])
    check(isinstance((rs["spec"] or {}).get("research_brief"), dict),
          "the brief is stamped into the step spec (spec.research_brief)", rs["spec"])
    writer = next(s for s in steps if s["kind"] == "write_post")
    check(writer["status"] == "done",
          "the writer completes after the research edge", writer["error"])

    async with AsyncSessionLocal() as db:
        outs = (
            await db.execute(
                select(Output).where(
                    Output.project_id == uuid.UUID(pid), Output.type == "post"
                )
            )
        ).scalars().all()
    check(len(outs) >= 1, "the post output exists", len(outs))


async def consult_never_deadends(ctx: Ctx) -> None:
    """consultation 纯咨询不死路：能力问（SSE——单轮流式律座）/ 闲聊 / 无根
    "start it" → 纯 answer 终态，零计划零 dock 零 run，纯信息答永不带
    建议卡（能力目录换皮 = 噪音）；浏览问（"还有其他推荐吗"族）在推荐
    格局已建立后仍归 ask_user 选项 dock——永不两级跳劫持（present_plan
    承诺 dock / 字幕闸选项 = 硬红）。纯散文 answer = 方差重试。"""
    pid = await ctx.new_project("consultation consult")

    # 能力问走 SSE——单轮流式律（concat(deltas) == 信封散文）在此座
    # exercised（journey 自动断言）。
    stream1 = await ctx.chat_stream(pid, "what can you do?")
    check(stream1.failed is None, "the capability turn never fails", stream1.failed)
    turn1 = stream1.completed
    check(terminal_tool_of(turn1) == "answer",
          "a capability question closes on the answer call", turn1)
    check(turn1["run_id"] is None, "capability question starts no run", turn1)
    check(not turn1["assistant_message"].get("question"), "no question docks",
          turn1["assistant_message"])
    check(not (turn1["assistant_message"].get("suggestions") or []),
          "no suggestion card on a bare capability answer (能力目录换皮 = 噪音)",
          turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose answer lands")

    turn1b = await ctx.chat(pid, "do you support multiple languages?")
    check(terminal_tool_of(turn1b) == "answer",
          "a pure info question closes on the answer call", turn1b)
    check(not turn1b["assistant_message"].get("question")
          and not (turn1b["assistant_message"].get("suggestions") or []),
          "an info question docks nothing and suggests nothing",
          turn1b["assistant_message"])

    turn2 = await ctx.chat(pid, "hello, how are you today?")
    check(terminal_tool_of(turn2) == "answer",
          "small talk closes on the answer call", turn2)
    check(turn2["run_id"] is None, "small talk starts no run", turn2)
    check(not turn2["assistant_message"].get("question"),
          "small talk docks nothing", turn2["assistant_message"])
    check(has_prose(turn2["assistant_message"]), "small talk gets an answer")

    turn3 = await ctx.chat(pid, "start it")
    check(terminal_tool_of(turn3) in ("ask_user", "answer"),
          "a baseless start closes on ask_user (出书门槛) or answer — never "
          "present_plan / start_run (LLM 方差: the rootless-start phrasing "
          "reads as either a work wish or a capability question)", turn3)
    check(turn3["run_id"] is None, "a baseless start never launches a run", turn3)
    check(not is_plan_dock(turn3["assistant_message"]),
          "a baseless start never docks a groundless plan either (出书门槛接住)",
          turn3["assistant_message"])
    check(await count_runs(pid) == 0, "no run the whole journey")
    plan = await pending_plan(ctx, pid)
    check(plan is None or plan.get("intent") is None,
          "no plan parks on consults", plan)

    # 浏览问永不劫持（事故④回归锁）：推荐格局已建立后，自定义措辞的浏览问
    # → ask_user 选项 dock——present_plan / 字幕闸 = 硬红（事故④原形态）。
    pid_b, _ = await seed_keynote_project(ctx, "consultation browse question")
    setup = await elicit_options_dock_turn(ctx, pid_b, "consultation browse setup")
    bail = await ctx.answer(setup["assistant_message"]["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201),
          "the setup dock settles (浏览问不被待决题吃掉)", bail.text)
    got: dict | None = None
    for prompt in ("还有其他推荐吗？", "anything else you'd recommend?",
                   "还有别的方向可以看看吗？"):
        turn = await ctx.chat(pid_b, prompt)
        msg = turn["assistant_message"]
        check(not is_plan_dock(msg),
              "a browse question is never hijacked into a plan dock (事故④第一跳)",
              turn)
        q = msg.get("question") or {}
        check(not any(str(o.get("id", "")).startswith("caption_mode_")
                      for o in q.get("options") or []),
              "no caption gate on a browse question (事故④第二跳)", q)
        if terminal_tool_of(turn) == "ask_user" and (q.get("options") or []):
            got = turn
            break
    check(got is not None,
          "no options-dock browse answer after 3 tries (浏览问无档可去 = 事故④温床)")
    check_options_dock(got["assistant_message"].get("question") or {}, "consultation browse")
    bail = await ctx.answer(got["assistant_message"]["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201), "the browse dock bails clean", bail.text)
    check(await count_runs(pid_b) == 0, "no run the whole journey")


async def second_circle_revision(ctx: Ctx) -> None:
    """revision_and_undo 修订第二圈（确定性尾剧本，零 LLM——锁真实 DB + 真实 API 门）：
    落地 clip → 精确编辑两族实应用（remove_range 删字幕 cue +
    set_caption_style 换预设）→ 同 id 原地改写无双生 → undo 两连逐级回退
    → wipe 归档（不删除、publication / journal 不连坐）→ 归档不可变 409
    墙 → 换态 restore（同 work 至多一 active）→ 读面跟随。"""
    from app.pipeline.edit_span import ResolvedSpan, resolve_quote_span
    from app.pipeline.outputs import archive_outputs
    from app.models.tables import Publication
    from app.models.schemas import PublicationState

    pid = await ctx.new_project("revision_and_undo second circle")
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s7.mp4", processed=True
    )

    cues = [
        {"start": 10.0, "end": 10.8, "text": "Welcome back", "lang": "en"},
        {"start": 10.8, "end": 11.5, "text": "to the show", "lang": "en"},
        {"start": 12.0, "end": 13.2, "text": "today we talk pricing", "lang": "en"},
    ]
    spec = {
        "segments": [
            {
                "id": "s1",
                "start": 10.0,
                "end": 40.0,
                "hidden": False,
                "asset_id": asset_id,
                "url": "scenario/s7.mp4",
            }
        ],
        "caption_track": cues,
        "source": {
            "kind": "video",
            "url": "scenario/s7.mp4",
            "asset_id": asset_id,
            "duration": 120.0,
        },
        "aspect": "9:16",
    }
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.COMPLETED,
            context={"target_language": "en", "ui_language": "en"},
        )
        db.add(run)
        await db.flush()
        step = WorkflowStep(
            run_id=run.id, kind="select_clips", status="done", seq=1,
        )
        db.add(step)
        await db.flush()
        output = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=step.id,
            type="clip",
            language="en",
            provenance="real",
            payload={"duration": 30},
            render_spec=spec,
        )
        db.add(output)
        await db.flush()
        oid = output.id
        db.add(
            WorkflowStep(
                run_id=run.id, kind="render", status="done", seq=2,
                inputs=[str(step.id)], spec={"output_id": str(oid)},
            )
        )
        db.add(
            Publication(
                user_id=ctx.user_id,
                project_id=uuid.UUID(pid),
                output_id=oid,
                payload={"title": "s7"},
                state=PublicationState.PUBLISHED,
                idempotency_key=f"s7-{oid}",
            )
        )
        await db.commit()
        work_id = output.work_id

    # ① edit door: quote → span (the resolver's exact tier) → remove_range
    #    op through the real operations API — the door edit_output rides。
    span = resolve_quote_span(cues, "welcome back")
    check(isinstance(span, ResolvedSpan) and span.tier == "exact",
          "the quote resolves at the exact tier", span)
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "remove_range", "params": {"start": span.start, "end": span.end}}]},
    )
    check(res.status_code == 201, "remove_range op applies", res.text)
    body = res.json()
    check(body["output"]["id"] == str(oid),
          "the edit rewrites the SAME row in place (同 id 无双生)", body["output"]["id"])
    new_track = body["output"]["render_spec"]["caption_track"]
    check(
        all("Welcome" not in c["text"] for c in new_track),
        "the cut cue leaves the caption track", new_track,
    )
    check(len(body["operations"]) == 1, "the op journals", body["operations"])

    # ② 第二族实应用: set_caption_style 换预设（同 id + journal）。
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "set_caption_style",
                       "params": {"preset": "karaoke-highlight", "enabled": True}}]},
    )
    check(res.status_code == 201, "set_caption_style op applies", res.text)
    body = res.json()
    check(body["output"]["id"] == str(oid),
          "the style edit rewrites the SAME row too", body["output"]["id"])
    check(body["output"]["render_spec"].get("caption_style_preset") == "karaoke-highlight",
          "the caption preset lands on the spec", body["output"]["render_spec"])
    # POST 回声 = 本批 ops；累计台账在 GET /operations（undoable journal）。
    journal = await ctx.client.get(f"/outputs/{oid}/operations")
    check(journal.status_code == 200, "the journal reads", journal.text)
    ops = [r for r in journal.json() if r["source"] == "editor"]
    check([r["op"] for r in ops] == ["remove_range", "set_caption_style"],
          "both ops journal", journal.json())

    # ③ undo 两连逐级回退: 先撤样式（预设回退），再撤剪切（cue 回轨）。
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 200, "the first undo applies", res.text)
    check(res.json()["output"]["render_spec"].get("caption_style_preset")
          != "karaoke-highlight",
          "undo reverts the caption preset", res.json()["output"]["render_spec"])
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 200, "the second undo applies", res.text)
    restored_track = res.json()["output"]["render_spec"]["caption_track"]
    check(
        any("Welcome" in c["text"] for c in restored_track),
        "undo restores the cut cue", restored_track,
    )

    # ④ wipe 归档（不重删）: archive the delivered row, birth the successor
    #    with the inherited work_id — publication survives, the journal stays
    #    readable, the visible read face swaps versions。
    async with AsyncSessionLocal() as db:
        await archive_outputs(db, [oid])
        newborn = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=None,
            type="clip",
            language="en",
            provenance="real",
            payload={"duration": 28},
            render_spec=spec,
            work_id=work_id,  # 按位继承 — the wipe's birth-loop shape
        )
        db.add(newborn)
        await db.flush()
        newborn_id = newborn.id
        await db.commit()
    async with AsyncSessionLocal() as db:
        pub = (
            await db.execute(
                select(func.count()).select_from(Publication).where(
                    Publication.output_id == oid
                )
            )
        ).scalar_one()
        check(pub == 1, "publication survives the archive (不连坐)", pub)
        ops_count = (
            await db.execute(
                select(func.count()).select_from(Operation).where(
                    Operation.output_id == oid
                )
            )
        ).scalar_one()
        check(ops_count >= 2, "the operations journal survives", ops_count)
    res = await ctx.client.get(f"/outputs/{oid}/operations")
    check(res.status_code == 200, "the archived row's journal stays readable",
          res.status_code)
    res = await ctx.client.get(f"/projects/{pid}/results")
    check(res.status_code == 200, "results reads", res.text)
    visible_ids = [o["id"] for o in res.json().get("outputs", [])]
    check(str(oid) not in visible_ids, "the archived version leaves the read face",
          visible_ids)
    check(str(newborn_id) in visible_ids, "the successor is the visible version",
          visible_ids)

    # ④b 归档不可变: the archived row is read-only history — every public
    #    mutate door refuses with 409 while the journal stays readable. The
    #    ONLY way back to mutable is the 换态 below。
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "set_title", "params": {"text": "tamper", "enabled": True}}]},
    )
    check(res.status_code == 409, "archived row rejects op writes", res.text)
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 409, "archived row rejects undo", res.text)
    res = await ctx.client.put(f"/outputs/{oid}", json={"payload": {"title": "tamper"}})
    check(res.status_code == 409, "archived row rejects PUT", res.text)
    res = await ctx.client.post(f"/outputs/{oid}/regenerate", json={})
    check(res.status_code == 409, "archived row rejects regenerate", res.text)

    # ⑤ 换态: restore the archived version — it becomes the work's ONE active
    #    row; the successor archives. A second restore on the now-active row
    #    refuses (400)。
    res = await ctx.client.post(f"/outputs/{oid}/restore")
    check(res.status_code == 200, "restore 换态 applies", res.text)
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Output).where(Output.work_id == work_id)
                )
            ).scalars().all()
        )
        actives = [r for r in rows if r.archived_at is None]
        check(len(actives) == 1 and actives[0].id == oid,
              "同 work 内至多一 active — the restored row", rows)
    res = await ctx.client.post(f"/outputs/{oid}/restore")
    check(res.status_code == 400, "restoring the active row refuses",
          res.status_code)
    res = await ctx.client.get(f"/projects/{pid}/results")
    visible_ids = [o["id"] for o in res.json().get("outputs", [])]
    check(str(oid) in visible_ids and str(newborn_id) not in visible_ids,
          "the read face follows the 换态", visible_ids)


async def interview_to_framing(ctx: Ctx) -> None:
    """interview_to_framing 访谈→分镜（需 dev worker + demo 桶 fixture + MiniMax 配额）：访谈
    素材真处理（worker 真 ASR + speaker_map → form=interview 前提断言）→
    用户口头选定分镜方向（「镜头跟着说话人切换」）→ dock 呈现即开工（auto
    档，ADR-117 §2）→ plan 链必含 select_clips + reframe_clip（选择执行律）
    → run completed → 成片 render_spec 带非空 crop_track（确定性尾——选了
    就要像配方卡那样成片，静默中央裁剪的结构通路在此锁死）。中间（router
    直接出书还是先问）是 LLM 裁量，nudge 有界兜底，红了 = prompt 回归信号。
    fixture 律：素材先拷 scenario/ 前缀隔离 + 显式 request_processing 盖章
    （ADR-102 休眠律——无盖章 worker 永不认领）。"""
    fixture_prefix = f"scenario/s8-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(INTERVIEW_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("interview_to_framing interview framing")
    src = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "xy_1_interview_15s.mp4",
        file_url=src_key,  # PENDING — the worker really ASRs + speaker-maps it
        request_processing=True,  # ADR-102 休眠律：fixture 自证盖章
    )
    status = await wait_asset_status(
        src, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(status == AssetStatus.COMPLETED,
          "the interview fixture is really processed (ASR + speaker_map)", status)
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, uuid.UUID(src))
        speaker_map = (asset.meta or {}).get("speaker_map") or {}
    check(speaker_map.get("form") == "interview"
          and bool(speaker_map.get("turns")),
          "the seat's premise: the fixture judges interview-form with "
          "attributed turns (the bake's proven source)",
          speaker_map.get("form"))

    await topup_wallet(ctx.user_id)  # clips + reframe + render 真链
    # 默认档钉住（Ctx 全矩阵共享一个 user——guided_exploration/writing_without_material/research_to_writing 会把档翻去 ask）。
    await ctx.set_confirmation(execution="auto", credits="auto")

    # 用户口头选定分镜方向——选择执行律：链必含 select_clips + reframe_clip。
    # auto 档（ADR-117 §2）：dock 回合呈现即开工（settled+born 同信封，零
    # 确认拍）；守卫线/不可报价 held 时口头确认拍补一枪（任何档恒问一次的
    # 合法分支）。开工即清 pending_brief——链读 settled 行的 intent 列。
    turn_dock = await ctx.chat(pid, "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。")
    for _ in range(2):
        if turn_dock["run_id"] is not None or is_plan_dock(turn_dock["assistant_message"]):
            break
        # LLM 裁量兜底（先问了 caption/数量等）——一句推进，路由恒在 plan path。
        turn_dock = await ctx.chat(pid, "就按这个方向出计划吧——竖屏切片，镜头跟人。")
    born_at_dock = turn_dock["run_id"] is not None
    if not born_at_dock:
        check(is_plan_dock(turn_dock["assistant_message"]),
              "the framing-chosen turns dock the plan",
              turn_dock["assistant_message"])
        turn_dock = await ctx.chat(pid, "开始吧")
    aq = turn_dock.get("answered_question")
    check(turn_dock["run_id"] is not None and aq is not None
          and ((aq.get("question") or {}).get("kind") == "task_book"),
          "the dock settles AND the run is born (auto 档: born at the dock "
          "turn itself; held 分支: born at the guardrail confirm beat)",
          turn_dock)
    check((aq.get("answer") or {}).get("kind") == "start",
          "the start lands kind=start", aq.get("answer"))
    if born_at_dock:
        check(((aq.get("question") or {}).get("requires_confirmation")) is False,
              "auto 档戳记 = 零确认拍（requires_confirmation=False at dock）",
              aq.get("question"))
        s8_run_ctx = (await run_row(turn_dock["run_id"]))["context"]
        check((s8_run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
              "confirmed_via = auto（呈现即开工的常驻授权戳）",
              s8_run_ctx.get("confirmed_scope"))
    tools = [t.get("tool") for t in ((aq.get("intent") or {}).get("tasks") or [])]
    check("select_clips" in tools and "reframe_clip" in tools,
          "选择执行律：the chosen framing direction lands select_clips + "
          "reframe_clip (never a silent center-crop chain)", tools)
    check(tools.index("reframe_clip") > tools.index("select_clips"),
          "the reframe rides after the clips producer (topology order)", tools)
    run_id = turn_dock["run_id"]

    final = await wait_run_terminal(run_id, timeout=600.0)
    check(final == "completed",
          "the framing run completes on the real interview bytes", final)
    reframe_step = next(
        (s for s in await step_rows(run_id) if s["kind"] == "reframe_clip"), None
    )
    check(reframe_step is not None and reframe_step["status"] == "done",
          "the reframe step ran and completed", reframe_step)
    clips = await outputs_of(pid, "clip")
    check(len(clips) >= 1, "the clips land", len(clips))
    check(
        any((o.render_spec or {}).get("crop_track") for o in clips),
        "确定性尾：at least one clip's render_spec carries a real crop_track "
        "(选了就要像配方卡那样成片——静默中央裁剪永禁)",
        [(str(o.id), len((o.render_spec or {}).get("crop_track") or [])) for o in clips],
    )

    # Journey 卫生（非断言——guided_exploration 同款）：run 收官的触发回合是
    # fire-and-forget；不消费它就 cleanup 会让在飞 LLM 调用撞上项目删除。
    review = await wait_trigger_review(ctx, turn_dock["conversation_id"], run_id,
                                       timeout=90.0)
    if review is not None and (review.get("question") or {}).get("kind") == "question":
        await ctx.answer(review["id"], {"kind": "bail"})


async def credits_boundary(ctx: Ctx) -> None:
    """credits_boundary 付费边界：钱包置零 → dock 计划 → typed Start 收结构化 422
    {code, balance, required}（/generate 同形同义）→ 零 run、零台账行
    （hold 与 run 同事务回滚）；不可证载荷 scope.unproven 门先于余额检查
    开火；负余额用户下一次 hold 必拒——含 0 元 hold（gate at the start）；
    活跃 run 时 Start 服务端 machine-readable 阻断（前端按钮 disabled 只是
    第一道防线），被阻的 Start 永不生 run。"""
    # 专用 fixture 用户：钱包手工置零——不动共享 ctx 用户的余额（material_to_clips 等
    # 剧本还要起真 run）；结束后清台账/钱包行（FK 序）。
    user_id = await make_user()
    local = Ctx(user_id, keep=False)
    try:
        # ask 档钉住（ADR-117——本旅程的 typed Start / 422 门断言全是确认拍族；
        # 默认 auto 档下 dock 回合的 auto-drive 会在零余额门上 held，断言虽同形
        # 通过，钉住消除该变量）。
        await local.set_confirmation(execution="ask", credits="ask")
        async with AsyncSessionLocal() as db:
            db.add(Wallet(user_id=user_id, balance=0))
            await db.commit()

        # 账户控制台 credits 槽的供给端：GET /wallet 必须真服务。
        res_w = await local.client.get("/wallet")
        check(res_w.status_code == 200
              and (res_w.json() or {}).get("balance") == 0,
              "GET /wallet serves the console credits slot", res_w.text)

        pid = await local.new_project("credits_boundary credits 422")
        # 素材要够实——单行文字稿触发模型「无可引用」的诚实拒 dock 轮盘
        # （实测 1/2 概率），而本本的断言对象是 422 载荷，不是 dock 边界裁量。
        await seed_asset(pid, user_id, AssetType.TRANSCRIPT, "talk.txt",
                         extracted_text=(
                             "My talk about grid storage auctions: why the "
                             "capacity market pays for availability, how the "
                             "auction clearing price is set, and what last "
                             "year's three price spikes taught operators about "
                             "bidding strategy."
                         ),
                         processed=True)
        turn1 = await local.chat(pid, "write a LinkedIn post from my talk")
        check(is_plan_dock(turn1["assistant_message"]),
              "turn1 docks a task_book", turn1["assistant_message"])

        # typed Start（答题端点 kind=start）——结构化 422。
        res = await local.answer(turn1["assistant_message"]["id"], {"kind": "start"})
        check(res.status_code == 422, "typed Start is a 422 on zero balance", res.text)
        detail = (res.json() or {}).get("detail") or {}
        check(detail.get("code") == "credits.insufficient",
              "the payload carries the user-level code", detail)
        check(detail.get("balance") == 0, "balance rides the payload", detail)
        check(isinstance(detail.get("required"), int) and detail["required"] > 0,
              "required rides the payload", detail)
        check(await count_runs(pid) == 0, "no run was born", None)

        # /generate 的 tasks 载荷必须是服务端可证的 approved retry——先种一条
        # 已确认历史链（本请求正是它的 exact retry），门放行后出生地的
        # credits 422 才是本断言的目标。
        async with AsyncSessionLocal() as db:
            db.add(
                WorkflowRun(
                    project_id=uuid.UUID(pid),
                    status=WorkflowStatus.COMPLETED,
                    context={
                        "tasks": [{"tool": "write_post", "params": {"language": "en"}}],
                        "target_language": "en",
                        "scope": "full",
                        "operation": "regenerate",
                    },
                )
            )
            await db.commit()

        # typed /generate（legacy fallback 路）——同形同义。
        res2 = await local.client.post(
            f"/projects/{pid}/generate",
            json={
                "tasks": [{"tool": "write_post", "params": {"language": "en"}}],
                "target_language": "en",
            },
        )
        check(res2.status_code == 422, "/generate is a 422 on zero balance", res2.text)
        detail2 = (res2.json() or {}).get("detail") or {}
        check(detail2.get("code") == "credits.insufficient"
              and detail2.get("balance") == 0 and detail2.get("required", 0) > 0,
              "the /generate payload is the same shape", detail2)

        # 不可证载荷 → machine-readable 422 scope.unproven，永不 create_run——
        # 门先于余额检查开火（不可证即拒，与余额无关），run 计数恒等于刚种的 1。
        res3 = await local.client.post(
            f"/projects/{pid}/generate",
            json={
                "tasks": [{"tool": "write_post", "params": {"language": "fr"}}],
                "target_language": "fr",
            },
        )
        check(res3.status_code == 422,
              "/generate unproven chain is a 422", res3.text)
        detail3 = (res3.json() or {}).get("detail") or {}
        check(detail3.get("code") == "scope.unproven"
              and "no_exact_retry" in (detail3.get("reasons") or []),
              "the unproven payload is machine-readable", detail3)
        check(await count_runs(pid) == 1,
              "the unproven request never reaches the birthplace", None)

        # 台账零行：check_hold 拒在 hold_run 之前，run 行也随事务回滚。
        async with AsyncSessionLocal() as db:
            n = (
                await db.execute(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(CreditTransaction.user_id == user_id)
                )
            ).scalar_one()
        check(n == 0, "no ledger rows leaked from the rejected births", n)

        # 负余额 hold 必拒——含 0 元 hold。
        async with AsyncSessionLocal() as db:
            wallet = await db.get(Wallet, user_id)
            wallet.balance = -50
            await db.commit()
        raised: CreditsInsufficientError | None = None
        async with AsyncSessionLocal() as db:
            try:
                await check_hold(db, user_id=user_id, required=0)
            except CreditsInsufficientError as e:
                raised = e
        check(raised is not None and raised.balance == -50,
              "a negative balance fails even a free (0) hold", raised)

        # Start 服务端四合取强制——活跃 run 冲突时服务端 machine-readable
        # 阻断；被阻的 Start 永不生 run（计数恒 = 历史 1 + 活跃 1）。
        await seed_active_run(pid)
        res4 = await local.answer(turn1["assistant_message"]["id"], {"kind": "start"})
        check(res4.status_code == 422,
              "typed Start is server-blocked on an active run", res4.text)
        detail4 = (res4.json() or {}).get("detail") or {}
        check(detail4.get("code") == "start.blocked"
              and "active_run" in (detail4.get("blockers") or []),
              "the Start blocker is machine-readable", detail4)
        check(await count_runs(pid) == 2, "the blocked Start births no run", None)
    finally:
        await local.cleanup()
        await local.close()
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
            await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await db.commit()


async def remix_flagship(ctx: Ctx) -> None:
    """remix Remix 旗舰（需 dev worker + demo 桶 fixture + MiniMax 配额）：
    P1 warm 路径（ask 档钉住——零 run 成本前提的结构保障：直接 dock 的合法
    分支在 auto 档会同拍开工，破坏该前提）——@mention 指认参考片（免问路，
    pin 由代码结算）→ pin 落定即拆解，agent 主动说看懂了案例；P2 run 路径
    （auto 档，ADR-117 §2——dock 呈现即开工，零确认拍）——两视频 + 一句
    「做成案例那样子」→ mention pin → dock 同拍 start → decompile 新鲜物化
    （参考片 seeded 为 FAILED 处理态 = warm 永不点火的现实形态——run 路径
    不看处理态只读字节）→ 触发回合说话 → 产物参数 = 骨架（条数/画幅/字幕
    色三断）→ 画布无 decompile 孤儿节点。角色提问机器一路（router 主动问
    asset_role）是 LLM 裁量，不做 e2e 锁定。复用不重复发声由结构锁住
    （reuse 早退在火前）+ (conversation, trigger, ref) 去重，本剧本末尾
    断言消息恰一条。P1 合法分支：mention 回合直接 dock 计划（LLM 裁量）→
    warm review 准入依法静默（ADR-080 永不压 docked plan——计划 echo 已经
    叙事），该面锁 pin 落账、review 等待合法跳过；无 dock 的回合锁
    「主动说看懂了案例」。"""
    fixture_prefix = f"scenario/s10-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    ex_key = await copy_fixture(REMIX_EXEMPLAR_KEY, fixture_prefix)
    # ---- P1: warm 路径 —— pin 落定即拆解、主动说话（无 run） ------------------
    # ask 档钉住（ADR-117——P1 前提是零 run 成本：LLM 裁量的直接 dock 分支在
    # auto 档会呈现即开工；钉 ask 让 dock 恒等用户的拍，两个合法分支形态不
    # 变）。P2 开工前再翻回 auto。
    # 消歧走 @mention 指认：角色 pin 由代码结算，不依赖 LLM 是否选择提问——
    # 提问机器一路的 dock 决策是 LLM 裁量，e2e 只锁确定性路径。
    await ctx.set_confirmation(execution="ask", credits="ask")
    pid1 = await ctx.new_project("remix-P1 warm path")
    src1 = await seed_asset(
        pid1, ctx.user_id, AssetType.VIDEO, "s10-p1-source.mp4", processed=True
    )
    ex1 = await seed_asset(
        pid1,
        ctx.user_id,
        AssetType.VIDEO,
        "highlight-clips-preview.mp4",
        processed=True,
        file_url=ex_key,
    )
    # fixture 纪律（writing_without_material/credits_boundary 同族轮盘）：src1 无真字节，模型「先读源片再承诺」
    # 是合法路——无 understanding 行时诚实读路拿到 _WARM_DEAD_TEXT / failed
    # 观察，依法拒 dock（pin 永不落账，红）。seed_understanding 让先读路与
    # 乐观 dock 路都通（digest 覆盖全项目素材集，与观察的 reuse 键同构）。
    await seed_understanding(pid1)
    turn1 = await ctx.chat(
        pid1,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex1, "label": "highlight-clips-preview.mp4"}],
    )
    conv1 = turn1["conversation_id"]
    brief1 = (await ctx.results(pid1)).get("pending_brief") or {}
    # The pin persists on the first PendingPlan WRITE — a bare-answer turn
    # writes nothing and the pin evaporates with it. Re-mention on each
    # continuation until a write lands (bounded — three prose-only turns =
    # stuck, fail loud).
    for _ in range(3):
        if brief1.get("exemplar_asset_id") == ex1:
            break
        turn1 = await ctx.chat(
            pid1,
            "参考案例就是 @这条，继续。",
            mentions=[{"type": "asset", "id": ex1, "label": "highlight-clips-preview.mp4"}],
        )
        brief1 = (await ctx.results(pid1)).get("pending_brief") or {}
    check(brief1.get("exemplar_asset_id") == ex1,
          "the @mention pins the exemplar by code (免问路)",
          {"brief": brief1,
           "last_content": (turn1["assistant_message"].get("content") or "")[:200]})
    # pin 落定（随 PendingPlan 写入）→ warm 拆解（fire-and-forget）→ 触发回合
    # 主动说话。合法分支：pin 落账回合直接 dock 了计划 = warm review 准入
    # 依法静默（ADR-080 永不压 docked plan——计划 echo 已经叙事），该面锁
    # pin 落账 + dock 形态即走完 P1；无 dock 的回合照旧锁主动发言。
    if is_plan_dock(turn1["assistant_message"]):
        check(brief1.get("intent") is not None,
              "the mention turn docked the plan — the warm review's silence "
              "is lawful (ADR-080: never talk over a docked plan)",
              brief1)
    else:
        review1 = await wait_trigger_review(ctx, conv1, ex1, timeout=240.0)
        check(review1 is not None,
              "the warm path's decompile speaks (「我看了你的案例」)", ex1)
        rintent1 = (review1 or {}).get("intent") or {}
        check(rintent1.get("trigger") == "craft_decompiled" and rintent1.get("ref") == ex1,
              "the warm review dump names trigger + exemplar ref", rintent1)
        check(bool(((review1 or {}).get("content") or "").strip()),
              "the agent's case understanding is spoken, not silent", review1)

    # ---- P2: run 路径 —— 新鲜物化必发声 + exemplar 参数 + 画布孤儿修复 ----
    pid2 = await ctx.new_project("remix-P2 run path")
    src2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "demo_talk.mp4",
        file_url=src_key,  # PENDING — the worker really ASRs it
        request_processing=True,  # ADR-102 休眠律：fixture 自证盖章
    )
    ex2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "highlight-clips-preview.mp4",
        file_url=ex_key,
        status=AssetStatus.FAILED,  # warm 永不点火的现实形态（如参考片自身
        # ASR 失败）——run 路径不看处理态只读字节，拆解的火因此必走 run 座位。
        # 已知代价（在册，勿再「修」）：Start 门的 material gatherer 是项目级
        # any()，失败的 REFERENCE 资产也阻塞 Start（material_failed）。
    )
    src_status = await wait_asset_status(
        src2, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(src_status == AssetStatus.COMPLETED,
          "the real source asset is ASR-processed by the dev worker", src_status)
    await topup_wallet(ctx.user_id)  # remix = 全模态真链，补足避免 422 噪音

    # auto 档翻回（ADR-117 §2——run 路径：dock 呈现即开工，零确认拍；开工即
    # 清 pending_brief，pin/链改读 run.context 与 settled 行的 intent 列）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    turn2 = await ctx.chat(
        pid2,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
    )
    conv2 = turn2["conversation_id"]
    brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
    # Same bounded re-mention recovery as P1: the pin only lands with the
    # first PendingPlan write. auto 档新增出口——dock 同拍开工（brief 即清，
    # pin 改读 run.context）。
    run_id = turn2["run_id"]
    for _ in range(3):
        if brief2.get("exemplar_asset_id") == ex2 or run_id is not None:
            break
        turn2 = await ctx.chat(
            pid2,
            "参考案例就是 @这条，继续。",
            mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
        )
        brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
        run_id = turn2["run_id"]
    if run_id is not None:
        pinned2 = (await run_row(run_id))["context"].get("exemplar_asset_id") == ex2
    else:
        pinned2 = brief2.get("exemplar_asset_id") == ex2
    check(pinned2,
          "P2's @mention pins the exemplar by code",
          {"brief": brief2, "terminal": terminal_tool_of(turn2),
           "run_id": run_id,
           "question": (turn2["assistant_message"].get("question") or {}),
           "content_head": (turn2["assistant_message"].get("content") or "")[:200]})

    # 计划 dock：mention 回合可能直接出书（auto 档同拍开工）；若路由仍 dock
    # 了角色问（mention 的 pin 已随写入落账，问题只是再确认），按选项答掉它
    # （答复同样代码落 pin），再回推到出书。held 分支（守卫线/不可报价——
    # ADR-117 §4 任何档恒问一次）留在 dock 等待态，下方口头确认拍开工。
    follow = turn2["assistant_message"]
    q2 = follow.get("question") or {}
    if run_id is None and q2.get("kind") == "question" and q2.get("slot") == "asset_role":
        ans2 = await ctx.answer(follow["id"], {"kind": "option", "option_id": src2})
        check(ans2.status_code in (200, 201), "P2's role answer settles", ans2.text)
        follow = ans2.json().get("follow_up") or {}
        if follow.get("workflow_run_id"):
            run_id = str(follow["workflow_run_id"])
    if run_id is None and not is_plan_dock(follow):
        # 显式覆盖：骨架缺席不该阻塞出书（读工具已被告知 FAILED = 直接出方案，
        # 此话术兜底 agent 仍犹豫的残差）。
        turn_dock = await ctx.chat(
            pid2, "参考片的骨架暂时拿不到也没关系——按你的判断直接出方案，不用等它。"
        )
        follow = turn_dock["assistant_message"]
        run_id = turn_dock["run_id"]
    if run_id is None:
        check(is_plan_dock(follow), "the pinned plan docks", follow)
        tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
        if not any(t.get("tool") == "select_clips" for t in tasks):
            # LLM 路由方差的一次纠偏——旗舰旅程的合法产物就是 clips 链。
            turn_fix = await ctx.chat(pid2, "把原视频剪成案例那样的竖屏短片")
            run_id = turn_fix["run_id"]
            if run_id is None:
                check(is_plan_dock(turn_fix["assistant_message"]),
                      "the corrective re-docks the clips plan", turn_fix)
                tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
            else:
                tasks = (((turn_fix.get("answered_question") or {}).get("intent")
                          or {}).get("tasks")) or []
        check(any(t.get("tool") == "select_clips" for t in tasks),
              "the remix plan carries the clips chain (旗舰旅程的合法链)", tasks)
    else:
        born_tasks = ((await run_row(run_id))["context"].get("tasks")) or []
        check(any(t.get("tool") == "select_clips" for t in born_tasks),
              "auto 档 dock 即开工——链在出生时已定（错链开工 = router 回归"
              "信号）", born_tasks)
    graph2 = await ctx.graph(pid2)
    check(no_decompile_canvas_node(graph2),
          "decompile never reads back as a canvas node (draft or live)",
          graph2["nodes"])

    held_confirm = run_id is None
    if held_confirm:
        # held 分支——守卫线/不可报价的口头确认拍（与 Start 钮同一机器）。
        turn3 = await ctx.chat(pid2, "looks good, start")
        check(terminal_tool_of(turn3) == "start_run",
              "the guardrail confirm closes on start_run", turn3)
        run_id = turn3["run_id"]
    check(run_id is not None, "the remix run is born", None)
    run_ctx = (await run_row(run_id))["context"]
    check(run_ctx.get("exemplar_asset_id") == ex2,
          "the exemplar pin rides run.context into the run — source stays "
          "None on the mention path (两视频项目素材由 exemplar 排除法确定性解析)",
          run_ctx)
    if not held_confirm:
        check((run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
              "confirmed_via = auto（呈现即开工的常驻授权戳）",
              run_ctx.get("confirmed_scope"))

    # decompile 步骤新鲜物化（参考片 FAILED → warm 从未点火 → 非复用）。
    dec_step = await wait_step_terminal(run_id, "decompile", timeout=420.0)
    check(dec_step["status"] == "done",
          "the decompile step completes on the real exemplar bytes", dec_step)
    dec_summary = str((dec_step["spec"] or {}).get("summary") or "")
    check("复用" not in dec_summary and "Reused" not in dec_summary,
          "the run path materializes FRESH (no warm row existed)", dec_summary)
    # 骨架行：run 路径所物化（warmed=False, source_ref 指认参考片）。
    skeletons = [
        o for o in await outputs_of(pid2, "craft_skeleton")
        if (o.source_ref or {}).get("asset_id") == ex2
    ]
    check(len(skeletons) == 1, "exactly one skeleton row names the exemplar",
          [o.source_ref for o in skeletons])
    check((skeletons[0].source_ref or {}).get("warmed") is False,
          "the skeleton is the RUN path's materialization, not the warm's",
          skeletons[0].source_ref)
    skel = skeletons[0].payload

    # run 路径拆解 → 触发回合说话（与 warm 同权）；恰一条（复用不重复发声的
    # 结构锁 + 去重在本项目内同 ref 恒一条）。
    review2 = await wait_trigger_review(ctx, conv2, ex2, timeout=240.0)
    check(review2 is not None,
          "the RUN path's fresh decompile speaks (与 warm 同权)", ex2)
    rintent2 = (review2 or {}).get("intent") or {}
    check(rintent2.get("trigger") == "craft_decompiled",
          "the run-path review dump names the craft trigger", rintent2)
    craft_msgs = [
        m for m in await ctx.messages(conv2)
        if (m.get("intent") or {}).get("type") == "trigger_review"
        and (m.get("intent") or {}).get("ref") == ex2
    ]
    check(len(craft_msgs) == 1,
          "exactly one craft speech per (conversation, exemplar) — no double-speak",
          len(craft_msgs))

    # 产物落库 + exemplar 参数断言（自洽读骨架行）：画幅 / 字幕色 = 代码映射
    # （确定性，严等）；条数帽 = 优先级律 explicit > exemplar > default，实现
    # 条数是 agent 的内容判断，断言只锁「不超具约束力的帽 + 至少一条」。
    clips_step = await wait_step_terminal(run_id, "select_clips", timeout=600.0)
    check(clips_step["status"] == "done",
          "the clips step completes on the real source", clips_step)
    clips = [
        o for o in await outputs_of(pid2, "clip")
        if str(o.workflow_step_id) == clips_step["id"]
    ]
    slot = (clips_step["spec"] or {}).get("slot") or {}
    explicit_count = slot.get("count") if isinstance(slot, dict) else None
    expected_cap = (
        max(1, min(10, int(explicit_count)))
        if explicit_count
        else max(1, min(10, int(skel["rhythm"]["shot_count"])))
    )
    check(1 <= len(clips) <= expected_cap,
          "clip count respects the BINDING cap (explicit slot count > skeleton cap; "
          "count_default=1 without either)",
          (len(clips), expected_cap, explicit_count, skel["rhythm"]["shot_count"]))
    specs = [o.render_spec or {} for o in clips]
    check(all(s.get("aspect") == skel["aspect"] for s in specs),
          "every clip's aspect = the skeleton's measured aspect",
          [s.get("aspect") for s in specs])
    if (skel.get("captions") or {}).get("present") and skel["captions"].get("color"):
        check(all((s.get("brand") or {}).get("caption_color") == skel["captions"]["color"]
                  for s in specs),
              "every clip's caption color = the skeleton's palette-snapped color",
              [(s.get("brand") or {}).get("caption_color") for s in specs])

    # 终态：run 图无 decompile 孤儿节点；decompile 步骤骑 task book 内部族。
    filled_graph = await ctx.graph(pid2)
    check(no_decompile_canvas_node(filled_graph),
          "the run-filled graph carries NO decompile orphan node",
          filled_graph["nodes"])








async def _seed_temporal_journey(ctx: Ctx, pid: str):
    """An 88s website/native/music work; only the revision turn uses an LLM."""
    from pydantic import TypeAdapter
    from app.editing.edits import Op
    from app.editing.store import apply_composition_edits
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import SourceSnapshot

    async with AsyncSessionLocal() as db:
        stem = f"scenario/s13/{uuid.uuid4().hex}"
        image = SourceSnapshot(
            owner_id=ctx.user_id, kind="image", storage_key=f"{stem}/still.png", digest="a" * 64,
        )
        audio = SourceSnapshot(
            owner_id=ctx.user_id, kind="audio", storage_key=f"{stem}/music.wav", digest="b" * 64,
            duration_ticks=88 * SOURCE_TIMEBASE,
        )
        web = SourceSnapshot(
            owner_id=ctx.user_id, kind="web", storage_key=f"{stem}/page.json", digest="c" * 64,
            meta={"views": [{
                "view_id": "view-main", "heading": "Fixture page", "width": 1920, "height": 1080,
                "storage_key": f"{stem}/view.png", "digest": "d" * 64,
            }]},
        )
        db.add_all([image, audio, web])
        await db.flush()
        ops: list[dict] = [
            {"op": "set_settings", "settings": {"width": 1920, "height": 1080}},
            *[
                {"op": "bind_source", "snapshot_id": str(snapshot.id)}
                for snapshot in (image, audio, web)
            ],
        ]
        scene_ranges = [
            ("scn_open", 0, 8),
            ("scn_chapter_1", 8, 28),
            ("scn_chapter_2", 28, 48),
            ("scn_chapter_3", 48, 68),
            ("scn_chapter_4", 68, 80),
            ("scn_close", 80, 88),
        ]
        for scene_id, start, end in scene_ranges:
            ops.append({"op": "add_scene", "scene": {
                "scene_id": scene_id,
                "range": {"start": start * SOURCE_TIMEBASE, "end": end * SOURCE_TIMEBASE},
                "intent": scene_id,
                "visual_description": f"Visible direction for {scene_id}",
            }})
        for track_id, kind, role, order in (
            ("trk_stills", "visual", "main", 0),
            ("trk_web", "visual", "main", 1),
            ("trk_title", "visual", "title", 2),
            ("trk_music", "audio", "music", 0),
        ):
            ops.append({"op": "add_track", "track": {
                "track_id": track_id, "kind": kind, "role": role, "order": order,
            }})

        def add_clip(track_id: str, clip: dict) -> None:
            ops.append({"op": "add_clip", "track_id": track_id, "clip": clip})

        layout = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        for clip_id, object_id, start, end in (
            ("clp_still_a", "obj_still_a", 0, 4),
            ("clp_still_b", "obj_still_b", 4, 8),
        ):
            add_clip("trk_stills", {
                "clip_id": clip_id,
                "range": {"start": start * SOURCE_TIMEBASE, "end": end * SOURCE_TIMEBASE},
                "scene_id": "scn_open",
                "source": {"snapshot_id": str(image.id), "snapshot_digest": image.digest},
                "object": {"kind": "image", "object_id": object_id, "layout": layout},
            })
        for scene_id, start, end in scene_ranges:
            duration = (end - start) * SOURCE_TIMEBASE
            add_clip("trk_web", {
                "clip_id": f"clp_web_{scene_id}",
                "range": {"start": start * SOURCE_TIMEBASE, "end": end * SOURCE_TIMEBASE},
                "scene_id": scene_id,
                "source": {"snapshot_id": str(web.id), "snapshot_digest": web.digest},
                "object": {
                    "kind": "web", "object_id": f"obj_web_{scene_id}",
                    "view_id": "view-main", "layout": layout,
                },
                "animations": [
                    {
                        "animation_id": f"anm_scale_{scene_id}",
                        "target_object_id": f"obj_web_{scene_id}",
                        "property": "transform.scale",
                        "keyframes": [{"at": 0, "value": 1}, {"at": duration, "value": 1.2}],
                    },
                    {
                        "animation_id": f"anm_camera_{scene_id}",
                        "target_object_id": f"obj_web_{scene_id}",
                        "property": "transform.position",
                        "keyframes": [
                            {"at": 0, "value": [0, 0]},
                            {"at": duration // 2, "value": [120, -40]},
                            {"at": duration, "value": [80, -20]},
                        ],
                    },
                ],
            })
            add_clip("trk_title", {
                "clip_id": f"clp_text_{scene_id}",
                "range": {"start": start * SOURCE_TIMEBASE, "end": end * SOURCE_TIMEBASE},
                "scene_id": scene_id,
                "object": {
                    "kind": "text", "object_id": f"obj_text_{scene_id}",
                    "text": f"Exact copy for {scene_id}",
                    "layout": {"x": 160, "y": 100, "width": 1600, "height": 160},
                    "style": {"font_size": 72, "color": "#FFFFFF"},
                },
                "animations": [
                    {
                        "animation_id": f"anm_blur_{scene_id}",
                        "target_object_id": f"obj_text_{scene_id}", "property": "filter.blur",
                        "keyframes": [{"at": 0, "value": 12}, {"at": duration, "value": 0}],
                    },
                    {
                        "animation_id": f"anm_spacing_{scene_id}",
                        "target_object_id": f"obj_text_{scene_id}", "property": "text.letter_spacing",
                        "keyframes": [{"at": 0, "value": 0.2}, {"at": duration, "value": 0}],
                    },
                ],
            })
        add_clip("trk_music", {
            "clip_id": "clp_music",
            "range": {"start": 0, "end": 88 * SOURCE_TIMEBASE},
            "scene_id": None,
            "source": {
                "snapshot_id": str(audio.id), "snapshot_digest": audio.digest,
                "source_range": {"start": 0, "end": 88 * SOURCE_TIMEBASE},
            },
            "object": {"kind": "audio", "object_id": "obj_music", "gain_db": -18},
            "animations": [{
                "animation_id": "anm_music_gain", "target_object_id": "obj_music",
                "property": "audio.gain",
                "keyframes": [{"at": 0, "value": 0.8}, {"at": 88 * SOURCE_TIMEBASE, "value": 1}],
            }],
        })
        ops.append({"op": "set_transition", "transition": {
            "transition_id": "trn_open", "from_clip_id": "clp_still_a", "to_clip_id": "clp_still_b",
            "duration": SOURCE_TIMEBASE,
        }})
        composition, version, _ = await apply_composition_edits(
            db,
            owner_id=ctx.user_id,
            origin_project_id=uuid.UUID(pid),
            name="Temporal journey",
            skill_provenance={"fixture": "temporal-journey", "preserve": "verbatim"},
            ops=TypeAdapter(list[Op]).validate_python(ops),
        )
        return composition.id, version.id


async def temporal_revision_without_production(ctx: Ctx) -> None:
    """temporal_revision 通用时间修订：88→30 秒恰好落 v2；随后缩短一章只落 v3，
    下游等距前移、保留段时长与全局音乐不变，两个回合均零 Run。"""
    from app.editing.store import content_of
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import Composition, CompositionVersion

    pid = await ctx.new_project("temporal_revision temporal revision")
    composition_id, version_id = await _seed_temporal_journey(ctx, pid)
    turn = await ctx.chat(
        pid,
        "Compress Temporal journey from 88 seconds to 30 seconds. Keep all four "
        "chapters, the opening/closing, copy, layout, camera moves, animation "
        "values and music style unchanged. Update the storyboard only; do not produce.",
    )
    check(turn.get("run_id") is None, "temporal revision starts no Run", turn)
    check(not is_plan_dock(turn["assistant_message"]),
          "storyboard-only temporal revision docks no production plan", turn["assistant_message"])

    async with AsyncSessionLocal() as db:
        versions = list((await db.scalars(
            select(CompositionVersion)
            .where(CompositionVersion.composition_id == composition_id)
            .order_by(CompositionVersion.version)
        )).all())
        run_count = await db.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.project_id == uuid.UUID(pid))
        )
        composition_count = await db.scalar(
            select(func.count()).select_from(Composition).where(Composition.origin_project_id == uuid.UUID(pid))
        )
    check(run_count == 0, "the project still has zero Runs", run_count)
    check(composition_count == 1, "revision does not create another work", composition_count)
    check(len(versions) == 2 and versions[0].id == version_id,
          "one Chat revision creates exactly one new version", [v.version for v in versions])
    before_row, after_row = versions
    check(after_row.base_version_id == before_row.id and after_row.skill_provenance == before_row.skill_provenance,
          "v2 is a child of the fixture and preserves skill provenance", None)
    before, after = content_of(before_row), content_of(after_row)
    duration = max(c.range.end for t in after.timeline.tracks for c in t.clips)
    check(abs(duration - 30 * SOURCE_TIMEBASE) <= SOURCE_TIMEBASE // 30,
          "max(all clip.range.end) is 30s within one output frame", duration / SOURCE_TIMEBASE)
    check([s.scene_id for s in after.scenes] == [s.scene_id for s in before.scenes],
          "opening, four chapters and closing keep their stable ids", None)
    check([(s.intent, s.visual_description) for s in after.scenes]
          == [(s.intent, s.visual_description) for s in before.scenes],
          "Scene intent and visual copy are not rewritten by a time map", None)
    check(after.sources == before.sources and after.settings == before.settings,
          "SourceSnapshot bindings and canvas settings are unchanged", None)

    before_clips = {c.clip_id: c for t in before.timeline.tracks for c in t.clips}
    after_clips = {c.clip_id: c for t in after.timeline.tracks for c in t.clips}
    check(set(after_clips) == set(before_clips), "every Clip keeps its stable id", None)
    before_animations = {
        a.animation_id: a for c in before_clips.values() for a in c.animations
    }
    for clip_id, revised in after_clips.items():
        original = before_clips[clip_id]
        check(revised.object == original.object,
              f"{clip_id}: copy/layout/object values stay unchanged", None)
        check(revised.scene_id == original.scene_id and revised.linked_group_id == original.linked_group_id,
              f"{clip_id}: structural membership stays unchanged", None)
        check({a.animation_id for a in revised.animations} == {a.animation_id for a in original.animations},
              f"{clip_id}: animation identities stay unchanged", None)
        check((revised.source is None) == (original.source is None) and (
            revised.source is None or original.source is None or (
                revised.source.snapshot_id == original.source.snapshot_id
                and revised.source.snapshot_digest == original.source.snapshot_digest
            )
        ), f"{clip_id}: immutable source identity stays unchanged", None)
        for animation in revised.animations:
            previous = before_animations[animation.animation_id]
            check([k.value for k in animation.keyframes] == [k.value for k in previous.keyframes],
                  f"{animation.animation_id}: time mapping never changes values", None)
            check(all(
                abs(new.at - old.at * 30 / 88) <= SOURCE_TIMEBASE // 30
                for new, old in zip(animation.keyframes, previous.keyframes)
            ), f"{animation.animation_id}: local keyframes follow the Timeline map", None)
            for new, old in zip(animation.keyframes, previous.keyframes):
                if old.at == original.range.duration:
                    check(new.at == revised.range.duration,
                          f"{animation.animation_id}: terminal keyframe shares the Clip's quantized output end",
                          {"keyframe_at": new.at, "clip_duration": revised.range.duration})
    music = after_clips["clp_music"]
    check(music.source is not None and music.source.source_range is not None
          and music.source.source_range.start == before_clips["clp_music"].source.source_range.start
          and music.source.source_range.duration == music.range.duration,
          "music is recropped at explicit 1×, never silently rate-changed", None)
    check([t.transition_id for t in after.timeline.transitions]
          == [t.transition_id for t in before.timeline.transitions]
          and after.timeline.transitions[0].duration < before.timeline.transitions[0].duration,
          "the Transition keeps its identity and follows output time", None)

    v2_row, v2 = after_row, after
    trim_turn = await ctx.chat(
        pid,
        "Shorten chapter 2 by 2 seconds. Move chapter 3, chapter 4 and the closing "
        "forward by those 2 seconds. Keep every retained downstream section's "
        "duration unchanged and leave the global music untouched. Save the "
        "storyboard only; do not produce.",
    )
    check(trim_turn.get("run_id") is None, "Scene trim starts no Run", trim_turn)
    check(not is_plan_dock(trim_turn["assistant_message"]),
          "Scene trim docks no production plan", trim_turn["assistant_message"])
    async with AsyncSessionLocal() as db:
        versions = list((await db.scalars(
            select(CompositionVersion)
            .where(CompositionVersion.composition_id == composition_id)
            .order_by(CompositionVersion.version)
        )).all())
        run_count = await db.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.project_id == uuid.UUID(pid))
        )
    check(run_count == 0, "Scene trim still has zero Runs", run_count)
    check(len(versions) == 3,
          "a satisfied Scene trim does not extend the ending in another version",
          [v.version for v in versions])
    v3_row = versions[-1]
    check(v3_row.base_version_id == v2_row.id,
          "the sole Scene-trim revision is based on v2", None)
    v3 = content_of(v3_row)
    v2_scenes = {scene.scene_id: scene for scene in v2.scenes}
    downstream = {"scn_chapter_3", "scn_chapter_4", "scn_close"}
    for scene in v3.scenes:
        old = v2_scenes[scene.scene_id]
        if scene.scene_id == "scn_chapter_2":
            check(scene.range.start == old.range.start
                  and scene.range.end == old.range.end - 2 * SOURCE_TIMEBASE,
                  "chapter 2 alone shortens by 2 seconds", None)
        elif scene.scene_id in downstream:
            check(scene.range.start == old.range.start - 2 * SOURCE_TIMEBASE
                  and scene.range.end == old.range.end - 2 * SOURCE_TIMEBASE
                  and scene.range.duration == old.range.duration,
                  f"{scene.scene_id}: downstream translates without stretching", None)
        else:
            check(scene.range == old.range,
                  f"{scene.scene_id}: upstream range stays unchanged", None)
    v2_music = next(c for t in v2.timeline.tracks for c in t.clips if c.clip_id == "clp_music")
    v3_music = next(c for t in v3.timeline.tracks for c in t.clips if c.clip_id == "clp_music")
    check(v3_music == v2_music,
          "global music range, source window and animation are completely untouched", None)
    duration = max(c.range.end for t in v3.timeline.tracks for c in t.clips)
    check(duration == 30 * SOURCE_TIMEBASE,
          "a music-only tail still owns the real 30-second timeline duration",
          duration / SOURCE_TIMEBASE)


async def _seed_speech_temporal_journey(ctx: Ctx, pid: str):
    """A 20s native-text/Speech work; only the revision turn uses an LLM."""
    from pydantic import TypeAdapter
    from app.editing.edits import Op
    from app.editing.store import apply_composition_edits
    from app.editing.timing import SOURCE_TIMEBASE

    duration = 20 * SOURCE_TIMEBASE
    ops = TypeAdapter(list[Op]).validate_python([
        {"op": "set_settings", "settings": {"width": 1920, "height": 1080}},
        {"op": "add_scene", "scene": {
            "scene_id": "scn_speech", "range": {"start": 0, "end": duration},
            "intent": "Reviewed narration", "speech_clip_ids": ["clp_speech"],
        }},
        {"op": "add_track", "track": {
            "track_id": "trk_title", "kind": "visual", "role": "title", "order": 0,
        }},
        {"op": "add_track", "track": {
            "track_id": "trk_dialogue", "kind": "audio", "role": "dialogue", "order": 0,
        }},
        {"op": "add_clip", "track_id": "trk_title", "clip": {
            "clip_id": "clp_title", "range": {"start": 0, "end": duration},
            "scene_id": "scn_speech",
            "object": {
                "kind": "text", "object_id": "obj_title", "text": "Keep the reviewed narration",
                "layout": {"x": 160, "y": 240, "width": 1600, "height": 240},
                "style": {"font_size": 72, "color": "#FFFFFF"},
            },
        }},
        {"op": "add_clip", "track_id": "trk_dialogue", "clip": {
            "clip_id": "clp_speech", "range": {"start": 0, "end": duration},
            "scene_id": "scn_speech",
            "object": {
                "kind": "speech", "object_id": "obj_speech",
                "text": "这段已经审阅的旁白必须保持原文和语速。",
                "voice_id": "fixture-voice", "language": "zh",
            },
        }},
    ])
    async with AsyncSessionLocal() as db:
        composition, version, _ = await apply_composition_edits(
            db,
            owner_id=ctx.user_id,
            origin_project_id=uuid.UUID(pid),
            name="Speech timing",
            skill_provenance={"fixture": "speech-capability"},
            ops=ops,
        )
        return composition.id, version.id


async def speech_capability_refusal_closes_honestly(ctx: Ctx) -> None:
    """speech_edit_refusal 旁白时间映射失败闭：一次正常 Chat、一次确定性拒绝、零新版零 Run，
    最终回复必须说明真实版本/时长/未制作，不漫游到其他产品建议。"""
    from app.editing.store import content_of
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import CompositionVersion, Conversation

    pid = await ctx.new_project("speech_edit_refusal speech capability refusal")
    composition_id, version_id = await _seed_speech_temporal_journey(ctx, pid)
    turn = await ctx.chat(
        pid,
        "把这条带旁白的片子等比压缩到10秒，现有文案、旁白、画面和布局都不要换。"
        "请直接在当前版本上修改，不要重新设计，只保存分镜，不制作视频。"
        "如果做不到，请明确说明原因，不要偷偷删掉旁白、改变语速或用重新创作代替修改。",
    )
    check(terminal_tool_of(turn) == "answer",
          "a capability refusal closes with an honest answer", turn)
    check(turn.get("run_id") is None, "Speech refusal starts no Run", turn)
    content = (turn.get("assistant_message") or {}).get("content") or ""
    check("第 1 版" in content and "20 秒" in content,
          "the reply names the standing version and actual duration", content)
    check("没有保存新版本" in content and "没有开始制作" in content,
          "the reply states zero new version and zero production", content)
    check("旁白" in content and "金句卡" not in content,
          "the reply addresses narration instead of unrelated product suggestions", content)

    async with AsyncSessionLocal() as db:
        versions = list((await db.scalars(
            select(CompositionVersion).where(CompositionVersion.composition_id == composition_id)
        )).all())
        run_count = await db.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.project_id == uuid.UUID(pid))
        )
        forensic_rows = list((await db.scalars(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.project_id == uuid.UUID(pid),
                Message.intent["type"].astext == "activity_forensics",
            )
        )).all())
    rejections = [
        rejection
        for row in forensic_rows
        for rejection in (row.intent or {}).get("rejections", [])
        if rejection.get("tool_name") == "revise_video"
    ]
    check(len(rejections) == 1,
          "the first deterministic media refusal ends the revision loop",
          rejections)
    check("cannot preserve its reviewed semantics" in rejections[0].get("detail", ""),
          "the sole refusal is the Speech capability boundary", rejections[0])
    check(len(versions) == 1 and versions[0].id == version_id,
          "the refused edit creates no CompositionVersion", [v.version for v in versions])
    check(run_count == 0, "the refused edit still has zero Runs", run_count)
    standing = content_of(versions[0])
    duration = max(c.range.end for t in standing.timeline.tracks for c in t.clips)
    check(duration == 20 * SOURCE_TIMEBASE,
          "the saved Speech work remains exactly 20 seconds", duration / SOURCE_TIMEBASE)


async def _seed_promo_product_assets(ctx: Ctx, pid: str) -> dict[str, str]:
    """Real captured-page PNGs, a real image and real video bytes as inputs.

    These are material fixtures only. No Composition or CompositionVersion is
    handwritten: the bound promo-video Director must create the work in Chat.
    """
    from app.providers import storage

    fixture_root = (
        Path(__file__).resolve().parent.parent
        / "tests" / "fixtures" / "video_project" / "media"
    )
    prefix = f"scenario/s15/{uuid.uuid4().hex}"
    shots = []
    for view_id, filename, source_y, heading in (
        ("hero", "web-hero.png", 0, "Agentveil product overview"),
        ("decide", "web-decide.png", 534, "Review a risky action"),
        ("proof", "web-proof.png", 2961, "Evidence before decision"),
    ):
        key = f"{prefix}/{filename}"
        await storage.save(key, (fixture_root / filename).read_bytes(), content_type="image/png")
        shots.append({
            "view_id": view_id,
            "key": key,
            "y": source_y,
            "heading": heading,
            "elements": [],
        })
    web_id = await seed_asset(
        pid,
        ctx.user_id,
        AssetType.WEB_PAGE,
        "agentveil-capture",
        processed=True,
        meta={
            "capture_url": "https://agentveil.dev/",
            "origin": {"kind": "scenario_captured_web_fixture"},
            "shots": shots,
            "research": {
                "title": "Agentveil — keep agents moving without losing control",
                "description": "Review real agent actions and decide what happens next.",
                "h1": "Watch an agent hit a risky action and keep working.",
                "h2": "Know when it's yours to decide.",
                "paragraphs": [
                    "Agentveil keeps the evidence visible before a consequential action.",
                    "Review the real context, then choose the next step.",
                ],
                "body_truncated": False,
            },
        },
    )
    image_key = f"{prefix}/product-proof.png"
    await storage.save(
        image_key,
        (fixture_root / "web-proof.png").read_bytes(),
        content_type="image/png",
    )
    image_id = await seed_asset(
        pid,
        ctx.user_id,
        AssetType.IMAGE,
        "product-proof.png",
        processed=True,
        file_url=image_key,
        meta={"origin": {"kind": "scenario_product_image"}},
    )
    video_key = await copy_fixture(REMIX_SOURCE_KEY, prefix)
    video_id = await seed_asset(
        pid,
        ctx.user_id,
        AssetType.VIDEO,
        "product-recording.mp4",
        processed=True,
        file_url=video_key,
        meta={"language": "en", "origin": {"kind": "scenario_product_recording"}},
    )
    return {"web": web_id, "image": image_id, "video": video_id}


def _native_copy_without_whitespace(content) -> str:
    return "".join(
        clip.object.text
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.object.kind == "text" and getattr(clip.object, "caption", None) is None
    ).replace("\n", "").replace(" ", "")


def _media_kinds_in_scene_order(content) -> list[str]:
    result = []
    for scene in content.scenes:
        kinds = [
            clip.object.kind
            for track in content.timeline.tracks
            for clip in track.clips
            if clip.scene_id == scene.scene_id
            and clip.object.kind in {"web", "image", "video", "generator"}
        ]
        result.append(kinds[0] if kinds else "text")
    return result


def _check_complete_video_storyboard(read: dict, label: str) -> None:
    board = read.get("storyboard") or {}
    scenes = board.get("scenes") or []
    check(bool(scenes), f"{label}: the canonical storyboard has scenes", board)
    check(all(
        scene.get("scene_id")
        and scene.get("clips")
        and scene.get("range_seconds", {}).get("end", 0)
        > scene.get("range_seconds", {}).get("start", 0)
        for scene in scenes
    ), f"{label}: every scene has a positive window and real clips", scenes)
    check(board.get("duration_seconds", 0) > 0
          and board.get("settings", {}).get("width")
          and board.get("settings", {}).get("fps"),
          f"{label}: duration and production settings are complete",
          {"duration": board.get("duration_seconds"), "settings": board.get("settings")})


def _check_only_text_revision(before, after, clip_id: str, new_text: str) -> None:
    """A targeted copy edit changes no unrelated scene, clip, source or setting."""
    check(before.settings == after.settings and before.sources == after.sources,
          "targeted text revision preserves settings and immutable source bindings", None)
    before_clips = {
        clip.clip_id: clip
        for track in before.timeline.tracks for clip in track.clips
    }
    after_clips = {
        clip.clip_id: clip
        for track in after.timeline.tracks for clip in track.clips
    }
    check(set(before_clips) == set(after_clips) and clip_id in before_clips,
          "targeted text revision adds and removes no clips", None)
    check(before.timeline.transitions == after.timeline.transitions,
          "targeted text revision preserves transitions", None)
    before_tracks = {track.track_id: track for track in before.timeline.tracks}
    after_tracks = {track.track_id: track for track in after.timeline.tracks}
    check(set(before_tracks) == set(after_tracks), "track identities are unchanged", None)
    for track_id, old_track in before_tracks.items():
        new_track = after_tracks[track_id]
        check((new_track.kind, new_track.role, new_track.order)
              == (old_track.kind, old_track.role, old_track.order),
              f"{track_id}: kind/role/order are unchanged", None)
    for other_id in before_clips.keys() - {clip_id}:
        check(after_clips[other_id] == before_clips[other_id],
              f"{other_id}: unrelated clip is byte-for-byte unchanged", None)

    old_clip = before_clips[clip_id]
    new_clip = after_clips[clip_id]
    check(old_clip.object.kind == "text" and new_clip.object.kind == "text",
          "the named revision target is a native TextObject", None)
    check(new_clip.object.text == new_text,
          "only the requested replacement copy lands", new_clip.object.text)
    check(new_clip.object.model_copy(update={"text": old_clip.object.text}) == old_clip.object,
          "the target TextObject keeps every non-text field", None)
    check((new_clip.range, new_clip.scene_id, new_clip.source, new_clip.linked_group_id)
          == (old_clip.range, old_clip.scene_id, old_clip.source, old_clip.linked_group_id),
          "the target clip keeps timing, scene, source and grouping", None)

    old_scenes = {scene.scene_id: scene for scene in before.scenes}
    new_scenes = {scene.scene_id: scene for scene in after.scenes}
    check(set(old_scenes) == set(new_scenes), "targeted text revision preserves scene ids", None)
    for scene_id, old_scene in old_scenes.items():
        new_scene = new_scenes[scene_id]
        if scene_id != old_clip.scene_id:
            check(new_scene == old_scene,
                  f"{scene_id}: unrelated scene is completely unchanged", None)
        else:
            check(new_scene.model_copy(
                update={"visual_description": old_scene.visual_description}
            ) == old_scene,
                  "the target scene changes at most its visual summary", None)


async def promo_skill_storyboard_revision_and_delivery(ctx: Ctx) -> None:
    """builtin_promo_skill 两种 arc 的真实宣传视频旅程；仅 product-evidence 变体制作一次。

    message-first-spotlight 用纯文案首稿覆盖零素材/零 Run 负形。
    两个首稿与开放重稿都读取真实 ToolExchange，断言同一工作草稿至少两次
    成功增量写入、digest 连续续写和最后一次保存；声明需要动态预览的固定素材
    版本必须有同 version/digest 的 ready 预览，而不是只凭版本行推断创作过程。
    product-evidence 用真实网页捕获 fixture + 图片 + 视频 + 精确文案首稿，
    经开放全结构重稿、定点文案修订和本地 Music 候选/选曲后，由一条后续明示
    消息进入普通 Chat 授权/Run 链。候选展示本身零版本零 Run；选曲只冻结真实
    Music 并在新版本创建 music 轨，既有 SFX 始终留 effect 轨。交付只认消息
    自己的 output_refs；刷新与交付后 @output 修订都不制造第二归属或第二个
    付费 Run。全程不直接调用 produce_video。曲库没有真实可播放曲目时本段
    诚实失败，绝不从本机 Downloads 隐式取文件或伪造候选。
    """
    from app.config import settings
    from app.editing.store import content_of

    await ctx.set_confirmation(execution="auto", credits="auto")
    skills = await ctx.skills()
    promo = next((item for item in skills
                  if (item.get("reference") or {}).get("kind") == "builtin"
                  and item["reference"].get("skill_id") == "promo-video"), None)
    check(promo is not None
          and "progressive_skill_package" in (promo.get("capabilities") or []),
          "the real picker exposes the complete promo-video Skill", skills)
    skill_ref = promo["reference"]

    # Copy-only message-first variant: a second arc without another paid Run.
    pid_copy = await ctx.new_project("builtin_promo_skill message-first copy promo")
    copy_text = "A practical course for clearer product launches. Join the next workshop."
    copy_turn = await ctx.chat(
        pid_copy,
        "Design a message-led first storyboard only: "
        "exactly 2 scenes and 8 seconds, no narration and no music. Use this exact "
        f"copy in order: {copy_text} Do not produce a video.",
        skill=skill_ref,
    )
    check(copy_turn.get("run_id") is None and await count_runs(pid_copy) == 0,
          "message-first first design starts no production", copy_turn)
    copy_read, _ = await ctx.acknowledge_video_presentation(
        copy_turn    )
    await check_incremental_design_turn(ctx, copy_turn, "message-first first draft")
    _check_complete_video_storyboard(copy_read, "message-first first draft")
    copy_versions = await composition_versions_of(pid_copy)
    check(len(copy_versions) == 1 and copy_versions[0].version == 1,
          "message-first design creates exactly one first version", None)
    copy_provenance = copy_versions[0].skill_provenance or {}
    check(copy_provenance.get("skill") == "promo-video"
          and copy_provenance.get("skill_reference") == skill_ref,
          "the copy variant persists its explicit installed Skill",
          copy_provenance)
    copy_content = content_of(copy_versions[0])
    check(_native_copy_without_whitespace(copy_content)
          == copy_text.replace(" ", ""),
          "message-first preserves the user's exact copy without invented claims",
          _native_copy_without_whitespace(copy_content))
    check(not copy_content.sources,
          "copy-only/no-music design fabricates no media source", copy_content.sources)
    copy_history = await ctx.messages(copy_turn["conversation_id"])
    copy_user = next(row for row in copy_history if row.get("role") == "user")
    check(copy_user.get("skill") == skill_ref,
          "the explicit Skill chip persists on the real user message", copy_user)
    check(await count_runs(pid_copy) == 0,
          "the complete message-first journey remains Run-free after its ACK", None)

    # Product-evidence mixed-material variant and the one real production.
    pid = await ctx.new_project("builtin_promo_skill product-evidence mixed promo")
    await topup_wallet(ctx.user_id)
    material_ids = await _seed_promo_product_assets(ctx, pid)
    mentions = [
        {"type": "asset", "id": material_ids["web"], "label": "Agentveil captured site"},
        {"type": "asset", "id": material_ids["image"], "label": "Product proof image"},
        {"type": "asset", "id": material_ids["video"], "label": "Product recording"},
    ]
    product_copy = (
        "Agentveil keeps every risky action visible. "
        "Review the evidence. Decide what ships."
    )
    first_turn = await ctx.chat(
        pid,
        "Design an evidence-led first storyboard only: exactly "
        "3 scenes and 12 seconds. Use the mentioned captured Agentveil webpage, "
        "the product image and a short real window of the recording; include all "
        "three kinds of evidence. Keep this exact on-screen copy in order: "
        f"{product_copy} No narration and no music. Do not produce.",
        skill=skill_ref,
        mentions=mentions,
    )
    check(first_turn.get("run_id") is None and await count_runs(pid) == 0,
          "the complete first product storyboard holds with zero Run", first_turn)
    first_read, _ = await ctx.acknowledge_video_presentation(
        first_turn    )
    await check_incremental_design_turn(ctx, first_turn, "product-evidence first draft")
    _check_complete_video_storyboard(first_read, "product-evidence first draft")
    versions = await composition_versions_of(pid)
    check(len(versions) == 1 and versions[0].version == 1,
          "the mixed first draft is one CompositionVersion", None)
    first = content_of(versions[0])
    first_kinds = {
        clip.object.kind
        for track in first.timeline.tracks for clip in track.clips
    }
    check({"web", "image", "video"} <= first_kinds,
          "the first draft really combines web, image and video evidence", first_kinds)
    check(_native_copy_without_whitespace(first) == product_copy.replace(" ", ""),
          "the product draft preserves the exact supplied copy", None)
    first_provenance = versions[0].skill_provenance or {}
    check(first_provenance.get("skill_reference") == skill_ref,
          "product evidence uses the explicitly bound installed package", first_provenance)
    composition_id = versions[0].composition_id

    # Open redraft: whole structure replacement, not a disguised targeted edit.
    redraft_turn = await ctx.chat(
        pid,
        "Open-redraft this same composition into a different 3-scene, 12-second "
        "structure. Replace the previous arrangement wholesale: lead with the real "
        "recording, move the webpage evidence to the middle, and finish on the "
        "supplied product image with the next-step copy. Keep those same three real "
        "sources, no narration and no music. Save the storyboard only; do not produce.",
    )
    check(redraft_turn.get("run_id") is None and await count_runs(pid) == 0,
          "the open structural redraft starts no production", redraft_turn)
    redraft_read, _ = await ctx.acknowledge_video_presentation(
        redraft_turn    )
    await check_incremental_design_turn(ctx, redraft_turn, "open structural redraft")
    _check_complete_video_storyboard(redraft_read, "open structural redraft")
    versions = await composition_versions_of(pid)
    check(len(versions) == 2
          and versions[1].composition_id == composition_id
          and versions[1].base_version_id == versions[0].id,
          "open redraft is a child version of the same work", None)
    redraft = content_of(versions[1])
    check(_media_kinds_in_scene_order(redraft) == ["video", "web", "image"],
          "the open redraft really replaces scene order with recording/web/image",
          _media_kinds_in_scene_order(redraft))
    check((versions[1].skill_provenance or {}).get("skill_reference") == skill_ref,
          "redraft preserves birth Skill lineage without rebinding it", None)

    # Targeted native text edit: every unrelated fact remains intact.
    target_clip = next(
        clip for track in redraft.timeline.tracks for clip in track.clips
        if clip.object.kind == "text"
        and getattr(clip.object, "caption", None) is None
        and clip.object.text.strip()
    )
    revised_copy = "Review the proof, then choose the next release."
    text_turn = await ctx.chat(
        pid,
        f"Change only native text clip {target_clip.clip_id} to exactly: "
        f"{revised_copy!r}. Keep every other scene, text object, layout, animation "
        "choice, source and timing unchanged. Save one revised storyboard only; "
        "do not produce.",
    )
    check(text_turn.get("run_id") is None and await count_runs(pid) == 0,
          "targeted text revision remains draft-only", text_turn)
    await ctx.acknowledge_video_presentation(text_turn)
    versions = await composition_versions_of(pid)
    check(len(versions) == 3 and versions[2].base_version_id == versions[1].id,
          "the targeted edit creates exactly one child version", None)
    revised = content_of(versions[2])
    _check_only_text_revision(redraft, revised, target_clip.clip_id, revised_copy)

    # Real local-library BGM candidates are presentation-only in this turn.
    music_search_turn = await ctx.chat(
        pid,
        "Show me up to five real background-music candidates from the local "
        "Music library so I can listen and compare them. Do not select or apply "
        "one, change the storyboard or produce a video in this turn.",
    )
    check(music_search_turn.get("run_id") is None and await count_runs(pid) == 0,
          "BGM candidate presentation starts no production", music_search_turn)
    check(len(await composition_versions_of(pid)) == 3,
          "BGM candidate presentation creates no CompositionVersion", None)
    search_history = await ctx.messages(music_search_turn["conversation_id"])
    music_sets = [
        event
        for row in search_history
        if (row.get("intent") or {}).get("type") == "candidates_log"
        for event in ((row.get("intent") or {}).get("events") or [])
        if event.get("kind") == "music_set"
    ]
    check(len(music_sets) == 1,
          "the settled search turn persists exactly one real Music candidate set",
          music_sets)
    music_set = music_sets[0]
    music_members = music_set.get("members") or []
    check(1 <= len(music_members) <= 5,
          "the deployed Music library supplies 1–5 real candidates", music_set)
    selected_member = music_members[0]
    selected_music_id = selected_member.get("music_id")
    check(selected_member.get("provider") == "music_library"
          and selected_member.get("provider_id") == selected_music_id
          and isinstance(selected_member.get("duration_seconds"), int)
          and not isinstance(selected_member.get("duration_seconds"), bool)
          and selected_member["duration_seconds"] > 0
          and selected_member.get("start") == 0
          and selected_member.get("end") == selected_member["duration_seconds"]
          and bool(selected_member.get("preview_url")),
          "the selected member carries a real playable library identity and duration",
          selected_member)

    # A later ordinary ordinal selects, freezes and applies that exact Music.
    music_turn = await ctx.chat(
        pid,
        "Use the first background-music candidate just shown. Add it to the "
        "current storyboard as a background-music Clip on a music track, separate "
        "from any sound-effect tracks. Use a real source window that fits the "
        "current work and save one revised storyboard only; do not produce.",
    )
    check(music_turn.get("run_id") is None and await count_runs(pid) == 0,
          "ordinal Music selection/application remains draft-only", music_turn)
    await ctx.acknowledge_video_presentation(music_turn)
    versions = await composition_versions_of(pid)
    check(len(versions) == 4 and versions[3].base_version_id == versions[2].id,
          "the selected Music creates exactly one child version", None)
    with_music = content_of(versions[3])
    music_tracks = [
        track for track in with_music.timeline.tracks if track.role == "music"
    ]
    music_clips = [clip for track in music_tracks for clip in track.clips]
    check(len(music_clips) == 1
          and music_clips[0].object.kind == "audio"
          and music_clips[0].source is not None,
          "the revision lands exactly one native AudioObject Clip on a music track",
          [(track.role, len(track.clips)) for track in with_music.timeline.tracks])
    check(all(
        clip.source is None or clip.source.snapshot_id != music_clips[0].source.snapshot_id
        for track in with_music.timeline.tracks if track.role == "effect"
        for clip in track.clips
    ), "the selected BGM never leaks into an effect track", None)
    music_snapshot_id = music_clips[0].source.snapshot_id
    async with AsyncSessionLocal() as db:
        music_snapshot = await db.get(SourceSnapshot, music_snapshot_id)
    check(music_snapshot is not None
          and music_snapshot.digest == music_clips[0].source.snapshot_digest
          and ((music_snapshot.meta or {}).get("music") or {}).get("music_id")
          == selected_music_id,
          "prepare_video_materials froze the exact selected Music into the bound snapshot",
          music_snapshot.meta if music_snapshot else None)

    # Production is born ONLY from this later explicit user message through Chat.
    production_request = "Produce this exact current storyboard now."
    produce_turn = await ctx.chat(pid, production_request)
    run_id = produce_turn.get("run_id")
    check(run_id is not None,
          "the later explicit production message starts the ordinary authorized Run",
          produce_turn)
    check(len(await composition_versions_of(pid)) == 4,
          "production does not redesign or add another draft version", None)
    check(await count_runs(pid) == 1,
          "the whole design/redraft/revision journey has exactly one paid Run", None)
    run = await run_row(run_id)
    run_context = run["context"]
    check(run_context.get("version_ref") == {
        "composition_id": str(composition_id),
        "composition_version_id": str(versions[3].id),
        "content_digest": versions[3].content_digest,
    }, "the Run pins the exact reviewed v4, never current-by-implication", run_context)
    production_user = produce_turn.get("user_message") or {}
    check(run_context.get("video_authorized_by") == production_user.get("id"),
          "the persisted authorization names the later explicit production message",
          {"context": run_context, "user": production_user})

    final = await wait_run_terminal(run_id, timeout=900.0)
    check(final == "completed", "the sole promo production Run completes", final)
    steps = await step_rows(run_id)
    produce_step = next((step for step in steps if step["kind"] == "produce_video"), None)
    check(produce_step is not None and produce_step["status"] == "done",
          "the Chat-born produce_video step completes", steps)
    video_outputs = await outputs_of(pid, "video")
    check(len(video_outputs) == 1, "one paid Run lands exactly one video Output", None)
    output = video_outputs[0]
    check(output.render_status == RenderStatus.COMPLETED
          and bool((output.files or {}).get("video"))
          and output.composition_id == composition_id
          and output.composition_version_id == versions[3].id,
          "the delivered Output is complete and pins the authorized v4",
          {"render_status": str(output.render_status), "files": output.files})
    check((output.render_spec or {}).get("provenance") == run_context.get("version_ref"),
          "Output and Run carry the same immutable version provenance", output.render_spec)

    delivery = await wait_trigger_review(
        ctx, produce_turn["conversation_id"], run_id, timeout=120.0
    )
    check(delivery is not None, "the real run-completed delivery arrives", None)
    delivery_intent = delivery.get("intent") or {}
    check(delivery.get("workflow_run_id") == run_id
          and delivery_intent.get("type") == "trigger_review"
          and delivery_intent.get("trigger") == "run_completed"
          and delivery_intent.get("output_refs") == [str(output.id)],
          "this delivery message alone owns its exact Output ref", delivery)

    # A refresh/history read preserves the same ownership; no Run-neighbour fallback.
    refreshed = await ctx.messages(produce_turn["conversation_id"])
    refreshed_delivery = next(row for row in refreshed if row.get("id") == delivery.get("id"))
    check((refreshed_delivery.get("intent") or {}).get("output_refs") == [str(output.id)],
          "history refresh keeps the Output on the original delivery only",
          refreshed_delivery)
    check(sum(
        str(output.id) in ((row.get("intent") or {}).get("output_refs") or [])
        for row in refreshed
    ) == 1, "no second message claims the delivered Output after refresh", None)

    # Post-delivery revision resolves the @output to its exact v4 and saves v5 only.
    post_target = next(
        clip for track in with_music.timeline.tracks for clip in track.clips
        if clip.object.kind == "text"
        and getattr(clip.object, "caption", None) is None
        and clip.object.text.strip()
        and clip.clip_id != target_clip.clip_id
    ) if sum(
        clip.object.kind == "text"
        and getattr(clip.object, "caption", None) is None
        and bool(clip.object.text.strip())
        for track in with_music.timeline.tracks for clip in track.clips
    ) > 1 else target_clip
    post_copy = "Keep the evidence visible; choose the next release."
    post_turn = await ctx.chat(
        pid,
        f"For the delivered video referenced here, revise only text clip "
        f"{post_target.clip_id} to exactly: {post_copy!r}. Save a new draft "
        "but do not produce it.",
        mentions=[{"type": "output", "id": str(output.id), "label": "Delivered promo"}],
    )
    check(post_turn.get("run_id") is None and await count_runs(pid) == 1,
          "post-delivery @output revision creates no second production", post_turn)
    await ctx.acknowledge_video_presentation(post_turn)
    versions = await composition_versions_of(pid)
    check(len(versions) == 5 and versions[4].base_version_id == versions[3].id,
          "the delivered Output's exact version is the post-delivery edit base", None)
    post_revision = content_of(versions[4])
    _check_only_text_revision(with_music, post_revision, post_target.clip_id, post_copy)
    check(len(await outputs_of(pid, "video")) == 1,
          "a draft revision creates no new Output", None)
    final_history = await ctx.messages(produce_turn["conversation_id"])
    check(sum(
        str(output.id) in ((row.get("intent") or {}).get("output_refs") or [])
        for row in final_history
    ) == 1 and not any(
        (row.get("intent") or {}).get("output_refs")
        for row in final_history
        if row.get("id") != delivery.get("id")
    ), "post-delivery revision and refresh never reassign the old Output", None)


async def external_skill_fixed_image_and_adversarial_packages(ctx: Ctx) -> None:
    """external_skill 外部包真实服务导入 + Chat 固定图片资源 + 恶意输入失败闭。

    当前没有公开 HTTP package-import 端点，因此导入段诚实走真实
    build_skill_draft/import_external_skill 服务；picker、owner 拒绝、设计和
    呈现仍走真实 HTTP Chat 路由。原始脚本/TSX 只作不可信参考，零 Run。
    """
    from app.config import settings
    from app.editing.store import content_of
    from app.skills.external import (
        ExternalSkillError,
        SkillInputDeclaration,
        SkillPolicy,
        build_skill_draft,
    )
    from app.skills.package_reader import (
        SkillPackageError,
        SkillPackageReader,
        open_external_skill_package,
    )
    from app.skills.package_session import ReadSkillReferenceArgs, SkillPackageSession
    from app.skills.store import SkillNotFoundError, import_external_skill

    check(settings.component_bake_enabled,
          "external_skill requires Video Project plus the controlled remotion-project runner",
          {"component_bake": settings.component_bake_enabled})
    fixture_image = (
        Path(__file__).resolve().parent.parent
        / "tests" / "fixtures" / "video_project" / "media" / "web-hero.png"
    ).read_bytes()
    media_path = "gallery/media/effects/fixed-image.png"
    shot_path = "references/shots/effects/fixed-image.md"
    demo_path = "demos/effects/fixed-image/FixedImage.tsx"
    script_path = "assets/scripts/never-run.py"
    root = b"""---
name: scenario-fixed-image
description: A fixed-image promotional visual method with untrusted references.
allowed-tools: [Bash]
---
Read the fixed-image shot, inspect its real preview and use only the server-derived image binding in a newly authored controlled visual. Never execute package scripts or raw demo TSX.
"""
    shot = b"""---
name: fixed-image
energy: calm
use_for: Build a short evidence-led visual around one supplied fixed image.
---
Use the fixed image as real evidence. Its demo is demos/effects/fixed-image/FixedImage.tsx.
"""
    # An unconditional throw makes accidental execution of the raw reference
    # observable: a successful controlled design must not run this file.
    demo = b"""import { AbsoluteFill, Img } from 'remotion';
throw new Error('RAW_PACKAGE_TSX_MUST_NOT_RUN');
export const FixedImage = () => <AbsoluteFill><Img src={'fixed.png'} /></AbsoluteFill>;
"""
    script = b"raise RuntimeError('EXTERNAL_PACKAGE_SCRIPT_MUST_NOT_RUN')\n"
    library = json.dumps({
        "schema_version": 1,
        "shots": [{
            "id": "fixed-image",
            "path": shot_path,
            "category": "effects",
            "name": "fixed-image",
            "previews": [{"path": media_path}],
        }],
    }, separators=(",", ":")).encode()
    files = {
        "SKILL.md": root,
        shot_path: shot,
        demo_path: demo,
        script_path: script,
        "gallery/api/library.json": library,
        media_path: fixture_image,
    }
    draft = build_skill_draft(
        files,
        declared_capabilities={"runtime:remotion-source"},
        source_uri="https://example.invalid/scenario-fixed-image",
        source_revision="scenario-v1",
        declared_inputs=[SkillInputDeclaration(
            name="creative_goal",
            description="The user's requested visual and exact native title.",
            binding="instruction",
            required=True,
        )],
        policy=SkillPolicy(
            mode="adaptive",
            adaptation_bounds=[
                "Keep the package image fixed; author only a new controlled visual around it."
            ],
        ),
    )
    by_path = {source.path: source for source in draft.references}
    check(by_path[demo_path].role == "implementation"
          and by_path[script_path].role == "script",
          "raw TSX and scripts remain untrusted reference roles", None)
    dependencies = {
        (item.kind, item.name)
        for item in draft.capability_report.unauthorized_dependencies
    }
    check(("script", script_path) in dependencies
          and ("allowed_tool", "Bash") in dependencies,
          "scripts and allowed-tools are reported as dependencies, never permissions",
          dependencies)
    check("runtime:remotion-source" in draft.capability_report.supported,
          "the reviewed external package declares its real controlled capability",
          draft.capability_report)

    async with AsyncSessionLocal() as db:
        version, replayed = await import_external_skill(
            db, owner_id=ctx.user_id, draft=draft
        )
        check(not replayed, "the first external package import creates a version", None)
        replay, replayed = await import_external_skill(
            db, owner_id=ctx.user_id, draft=draft
        )
        check(replayed and replay.id == version.id,
              "identical package import is idempotent", None)
        await db.commit()
        version_id = version.id
        source_hash = version.source_hash
        version_digest = version.version_digest

    # Path escape fails before any package is accepted.
    try:
        build_skill_draft({"../SKILL.md": root}, declared_capabilities=set())
    except ExternalSkillError as exc:
        check("path" in str(exc).lower(), "path escape has a bounded diagnostic", exc)
    else:
        check(False, "path escape must fail closed", None)

    # A transient tampered row exercises the real immutable reader without
    # writing around the DB immutability trigger or poisoning shared storage.
    async with AsyncSessionLocal() as db:
        persisted = await db.get(SkillVersion, version_id)
        skill_row = await db.get(UserSkill, persisted.skill_id)
        fields = {
            column.name: getattr(persisted, column.name)
            for column in SkillVersion.__table__.columns
        }
        tampered_references = json.loads(json.dumps(fields["references"]))
        tampered_references[0]["text"] += "\nDIGEST_TAMPER"
        fields["references"] = tampered_references
        tampered = SkillVersion(**fields)
        try:
            SkillPackageReader(version=tampered, skill=skill_row)
        except SkillPackageError as exc:
            check("digest" in str(exc).lower(),
                  "persisted source digest tamper fails closed", exc)
        else:
            check(False, "digest-tampered SkillVersion must not be readable", None)

        reader = await open_external_skill_package(
            db, owner_id=ctx.user_id, skill_version_id=version_id
        )
        package = SkillPackageSession(
            reader, owner_id=ctx.user_id, package_identity=version_id
        )
        await package.read_initial(["SKILL.md"])
        script_read = await package.observe(
            "read_skill_reference", ReadSkillReferenceArgs(path=script_path)
        )
        check(script_read.ok is False,
              "the bounded package reader refuses the unauthorized script root",
              script_read.text)
        binding = await package.fixed_image_binding(media_path)
        fixed_bytes = await package.read_fixed_image(binding)
        import hashlib
        check(hashlib.sha256(fixed_bytes).hexdigest() == binding["snapshot_digest"],
              "the fixed-image reader verifies real bytes against their digest", None)
        check(await db.get(SourceSnapshot, uuid.UUID(binding["snapshot_id"])) is None,
              "the package image has no SourceSnapshot before its first real consumer",
              binding)

    # Cross-owner reads are indistinguishable from absence in both service and Chat.
    other_ctx = Ctx(await make_user(), keep=ctx.keep)
    try:
        other_pid = await other_ctx.new_project("external_skill foreign Skill access")
        async with AsyncSessionLocal() as db:
            try:
                await open_external_skill_package(
                    db, owner_id=other_ctx.user_id, skill_version_id=version_id
                )
            except SkillNotFoundError:
                pass
            else:
                check(False, "cross-owner package open must fail closed", None)
        foreign_skills = await other_ctx.skills()
        check(not any(
            (item.get("reference") or {}).get("skill_version_id") == str(version_id)
            for item in foreign_skills
        ), "the foreign owner's picker never leaks the SkillVersion", None)
        foreign_ref = {"kind": "external", "skill_version_id": str(version_id)}
        rejected = await other_ctx.client.post(
            "/chat",
            json={
                "project_id": other_pid,
                "message": "Use this foreign external Skill to design a video.",
                "skill": foreign_ref,
            },
        )
        check(rejected.status_code == 404
              and (rejected.json().get("detail") or {}).get("code") == "skill.unavailable",
              "cross-owner explicit Chat binding fails before any Agent/LLM turn",
              rejected.text)
        check(await count_runs(other_pid) == 0
              and not await composition_versions_of(other_pid),
              "cross-owner rejection creates no work or Run", None)
    finally:
        await other_ctx.cleanup()
        await other_ctx.close()

    options = await ctx.skills()
    external_ref = {"kind": "external", "skill_version_id": str(version_id)}
    check(any(item.get("reference") == external_ref for item in options),
          "the owner's real picker exposes the immutable external version", None)
    pid = await ctx.new_project("external_skill external fixed-image design")
    design_turn = await ctx.chat(
        pid,
        "Using the bound external Skill, design only a 4-second component-mode "
        "storyboard titled exactly 'Fresh package evidence'. Read the fixed-image "
        "shot and its real preview, then use that exact server-provided fixed-image "
        "binding as a Generator resource in a newly authored visual. No narration "
        "and no music. Do not execute the package's raw demo TSX or scripts and do "
        "not produce a video.",
        skill=external_ref,
    )
    check(design_turn.get("run_id") is None and await count_runs(pid) == 0,
          "external fixed-image design never starts production", design_turn)
    read, _ = await ctx.acknowledge_video_presentation(design_turn)
    _check_complete_video_storyboard(read, "external fixed-image design")
    versions = await composition_versions_of(pid)
    check(len(versions) == 1,
          "the real external-Skill Chat creates its first version through design_video",
          None)
    provenance = versions[0].skill_provenance or {}
    external_provenance = provenance.get("external_skill") or {}
    check(provenance.get("skill_reference") == external_ref
          and external_provenance.get("skill_version_id") == str(version_id)
          and external_provenance.get("source_hash") == source_hash
          and external_provenance.get("version_digest") == version_digest,
          "the work pins the owner's exact immutable external SkillVersion",
          provenance)

    content = content_of(versions[0])
    generators = [
        clip.object
        for track in content.timeline.tracks for clip in track.clips
        if clip.object.kind == "generator"
    ]
    matching_resources = [
        resource
        for generator in generators
        if generator.producer == "remotion-project" and generator.project is not None
        for resource in generator.project.resources
        if resource.path == media_path
    ]
    check(len(matching_resources) == 1,
          "the new controlled Generator uses the real package image, not raw TSX execution",
          [getattr(generator, "producer", None) for generator in generators])
    resource = matching_resources[0]
    check(str(resource.snapshot_id) == binding["snapshot_id"]
          and resource.snapshot_digest == binding["snapshot_digest"]
          and resource.content_type == binding["content_type"],
          "the Generator resource exactly matches the server-derived fresh binding",
          {"resource": resource, "binding": binding})
    async with AsyncSessionLocal() as db:
        snapshot = await db.get(SourceSnapshot, uuid.UUID(binding["snapshot_id"]))
    check(snapshot is not None and snapshot.digest == binding["snapshot_digest"]
          and (snapshot.meta or {}).get("origin") == "external_skill_package"
          and (snapshot.meta or {}).get("skill_version_id") == str(version_id)
          and (snapshot.meta or {}).get("package_path") == media_path,
          "first real use materializes a fresh owner/package-pinned SourceSnapshot",
          snapshot.meta if snapshot else None)
    check(await count_runs(pid) == 0,
          "the external-Skill journey remains a short zero-Run design", None)


def _p1_turn_id(turn: dict | str) -> str:
    if isinstance(turn, str):
        return turn
    turn_id = str((turn.get("user_message") or {}).get("turn_id") or "")
    check(bool(turn_id), "P1 response exposes its real turn id", turn)
    return turn_id


def _p1_provider_calls(turn: dict | str) -> list[dict]:
    from app.config import settings

    path = Path(settings.llm_trace_path)
    check(path.is_file(), "P1 token/provider verification requires LLM_TRACE_PATH", str(path))
    requests = {}
    outcomes = {}
    turn_id = _p1_turn_id(turn)
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("turn_id") != turn_id:
            continue
        if row.get("phase") == "request":
            requests[row["model_call_id"]] = row
        elif row.get("phase") in {"response", "error"}:
            outcomes[row["model_call_id"]] = row
    calls = []
    for call_id, request in requests.items():
        outcome = outcomes.get(call_id)
        if outcome is not None:
            calls.append({"request": request, "outcome": outcome})
    calls.sort(key=lambda call: call["request"].get("started_at") or "")
    check(bool(calls), "P1 turn has real provider exchanges", turn_id)
    return calls


def _p1_tool_calls(call: dict) -> list[tuple[str, dict]]:
    result = []
    response = call["outcome"].get("response") or {}
    items = [
        item
        for choice in response.get("choices") or []
        for item in (choice.get("message") or {}).get("tool_calls") or []
    ]
    items.extend(response.get("tool_calls") or [])
    for item in items:
        function = item.get("function") or item
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        result.append((function.get("name") or "", args))
    return result


def _p1_report_tokens(label: str, turn: dict) -> list[dict]:
    calls = _p1_provider_calls(turn)
    per_call = []
    for call in calls:
        request, outcome = call["request"], call["outcome"]
        usage = (outcome.get("response") or {}).get("usage") or {}
        inventory = request.get("inventory") or {}
        project_chars = history_chars = current_media_chars = historical_media_chars = 0
        current_media_parts = historical_media_parts = 0
        for message in (request.get("payload") or {}).get("messages") or []:
            content = message.get("content")
            text = content if isinstance(content, str) else ""
            if "CURRENT PROJECT EVIDENCE" in text or "BOUND SKILL METHOD" in text:
                project_chars += len(text)
            if (
                message.get("role") in {"assistant", "tool"}
                or "CONVERSATION TOOL HISTORY" in text
                or "Previous user request (historical turn" in text
            ):
                history_chars += len(json.dumps(content, ensure_ascii=False))
            parts = content if isinstance(content, list) else []
            for part in parts:
                if not isinstance(part, dict) or part.get("type") == "text":
                    continue
                caption = str(part.get("caption") or "")
                size = len(json.dumps(part, ensure_ascii=False))
                if "Historical observation" in caption:
                    historical_media_parts += 1
                    historical_media_chars += size
                else:
                    current_media_parts += 1
                    current_media_chars += size
        per_call.append({
            "model_call_id": request.get("model_call_id"),
            "provider_prompt_tokens": usage.get("prompt_tokens"),
            "tools": [name for name, _ in _p1_tool_calls(call)],
            "char_estimates_not_tokens": {
                "system": sum(
                    item.get("json_chars", 0) for item in inventory.get("messages") or []
                    if item.get("role") == "system"
                ),
                "tools": (inventory.get("top_level") or {}).get("tools", {}).get("json_chars", 0),
                "project_text": project_chars,
                "history_text": history_chars,
                "current_media": {"parts": current_media_parts, "json_chars": current_media_chars},
                "historical_media": {"parts": historical_media_parts, "json_chars": historical_media_chars},
            },
        })
    auxiliary = []
    if calls:
        started = calls[0]["request"].get("started_at") or ""
        finished = max(call["outcome"].get("finished_at") or "" for call in calls)
        from app.config import settings

        all_requests = {}
        for line in Path(settings.llm_trace_path).read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("phase") == "request":
                all_requests[row.get("model_call_id")] = row
                continue
            if row.get("phase") not in {"response", "error"}:
                continue
            request = all_requests.get(row.get("model_call_id"))
            if request is None or row.get("turn_id") or row.get("project_id"):
                continue
            at = request.get("started_at") or ""
            if started <= at and (row.get("finished_at") or "") <= finished:
                auxiliary.append({
                    "model_call_id": row.get("model_call_id"),
                    "seat": request.get("seat"),
                    "provider_prompt_tokens": ((row.get("response") or {}).get("usage") or {}).get("prompt_tokens"),
                })
    chat_total = sum(item["provider_prompt_tokens"] or 0 for item in per_call)
    auxiliary_total = sum(item["provider_prompt_tokens"] or 0 for item in auxiliary)
    summary = {
        "label": label,
        "turn_id": _p1_turn_id(turn),
        "model_calls": len(per_call) + len(auxiliary),
        "chat_model_calls": len(per_call),
        "auxiliary_preparation_model_calls": auxiliary,
        "prompt_tokens_per_call": [item["provider_prompt_tokens"] for item in per_call],
        "single_call_peak": max((item["provider_prompt_tokens"] or 0) for item in per_call),
        "whole_turn_prompt_token_sum": chat_total + auxiliary_total,
        "calls": per_call,
    }
    print("P1_TOKENS", json.dumps(summary, ensure_ascii=False))
    return calls


async def _p1_report_first_draft(
    ctx: Ctx, turn: dict, label: str, *, require_saved: bool = True,
) -> None:
    from app.chat.conversation_context import context_items

    async with AsyncSessionLocal() as db:
        conversation = await db.get(Conversation, uuid.UUID(turn["conversation_id"]))
    items = [
        item for item in context_items(conversation.context)
        if item.get("turn_id") == _p1_turn_id(turn)
        and item.get("target_tool") in {None, "design_video"}
        and item.get("tool") in {"design_video", "correct_tool_candidate"}
    ]
    first = next((item for item in items if item.get("tool") == "design_video"), None)
    check(first is not None, f"{label}: the first high-level submission is recorded", items)
    saved = any(
        item.get("tool") == "design_video" and item.get("ok")
        and "Video version" in item.get("text", "")
        for item in items
    )
    presented = bool((turn.get("assistant_message") or {}).get("blocks"))
    print("P1_FIRST_DRAFT", json.dumps({
        "label": label,
        "turn_id": _p1_turn_id(turn),
        "first_submission_valid": bool(first.get("ok")),
        "corrected_then_saved": bool(not first.get("ok") and saved),
        "saved": saved,
        "storyboard_presented": presented,
    }, ensure_ascii=False))
    if require_saved:
        check(saved and presented, f"{label}: a valid final save is presented as a Storyboard", items)


async def _seed_p1_promo_baseline(ctx: Ctx, pid: str, skill_ref: dict):
    from app.editing.schemas import CompositionContent
    from app.editing.store import apply_composition_edits

    def text_clip(scene_id, suffix, text, start, end, font_size, y, weight):
        return {
            "clip_id": f"clp_{scene_id}_{suffix}", "scene_id": scene_id,
            "range": {"start": start, "end": end}, "source": None, "animations": [],
            "object": {
                "kind": "text", "object_id": f"obj_{scene_id}_{suffix}", "text": text,
                "layout": {"x": 153.6, "y": y, "width": 1612.8, "height": font_size * 1.6},
                "style": {
                    "font_size": font_size, "color": "#F8FAFC", "weight": weight,
                    "align": "center", "line_height": 1.2,
                },
            },
        }

    content = CompositionContent.model_validate({
        "settings": {"width": 1920, "height": 1080, "background": "#0B1020"},
        "sources": [],
        "scenes": [
            {
                "scene_id": "opening", "range": {"start": 0, "end": 270000},
                "intent": "建立开场标题", "visual_description": "开场标题稳定呈现。",
                "speech_clip_ids": [],
            },
            {
                "scene_id": "second", "range": {"start": 270000, "end": 585000},
                "intent": "形成第二镜", "visual_description": "第二镜保留明确下一步。",
                "speech_clip_ids": [],
            },
        ],
        "timeline": {
            "tracks": [
                {"track_id": "trk_main", "kind": "visual", "role": "main", "order": 0, "clips": []},
                {
                    "track_id": "trk_title", "kind": "visual", "role": "title", "order": 1,
                    "clips": [
                        text_clip("opening", "name", "让价值有据可查", 0, 270000, 112, 432.0, 700),
                        text_clip("second", "name", "让价值有据可查", 270000, 585000, 104, 432.0, 700),
                    ],
                },
                {
                    "track_id": "trk_subtitle", "kind": "visual", "role": "caption", "order": 2,
                    "clips": [
                        text_clip("opening", "tagline", "真实证据", 0, 270000, 56, 604.8, 500),
                        text_clip("second", "action", "查看证据", 270000, 585000, 52, 604.8, 500),
                    ],
                },
            ],
            "transitions": [],
        },
    })
    async with AsyncSessionLocal() as db:
        _, version, _ = await apply_composition_edits(
            db,
            owner_id=ctx.user_id,
            origin_project_id=uuid.UUID(pid),
            content=content,
            name="P1 seeded baseline",
            skill_provenance={
                "skill": "promo-video",
                "skill_reference": skill_ref,
                "skill_version": skill_ref.get("version"),
                "arc_id": "product-evidence",
                "language": "zh",
                "copy_evidence": [],
                "builder_version": "promo-native-v1",
            },
        )
        return version


async def _p1_revise(ctx: Ctx, pid: str, message: str, label: str, expected_version: int, **extra):
    turn = await ctx.chat(pid, message, **extra)
    calls = _p1_report_tokens(f"{label}_v{expected_version}", turn)
    revisions = [args for call in calls for name, args in _p1_tool_calls(call) if name == "revise_video"]
    check(revisions and all(not {"tracks", "clips", "ops", "scenes"} & set(args) for args in revisions),
          f"{label}: actual execution stays on the bounded revision tool", revisions)
    declarations = [
        (item.get("function") or {}).get("parameters") or {}
        for call in calls
        for item in (call["request"].get("payload") or {}).get("tools") or []
        if (item.get("function") or {}).get("name") == "revise_video"
    ]
    check(declarations and all(
        "action" in (schema.get("properties") or {})
        and not {"tracks", "clips", "ops", "scenes"} & set(schema.get("properties") or {})
        for schema in declarations
    ), f"{label}: final provider declarations expose only high-level revision intent", declarations)
    assistant = turn.get("assistant_message") or {}
    if assistant.get("blocks"):
        await ctx.acknowledge_video_presentation(turn)
    versions = await composition_versions_of(pid)
    check(len(versions) == expected_version,
          f"{label}: saves exactly version {expected_version}", message)
    check(await count_runs(pid) == 0 and not await outputs_of(pid, "video"),
          f"{label}: no Run or video Output starts", None)
    return turn, versions[-1]


async def _p1_skill_ref(ctx: Ctx) -> dict:
    skills = await ctx.skills()
    promo = next(
        item for item in skills
        if (item.get("reference") or {}).get("skill_id") == "promo-video"
    )
    return promo["reference"]


def _p1_assert_generic_design_wire(calls: list[dict]) -> None:
    declarations = [
        (item.get("function") or {})
        for call in calls
        for item in (call["request"].get("payload") or {}).get("tools") or []
        if (item.get("function") or {}).get("name") == "design_video"
    ]
    check(declarations, "the provider really receives design_video declarations", None)
    raw = {"tracks", "clips", "sources", "settings", "ops", "shots"}
    check(all(not raw & set((item.get("parameters") or {}).get("properties") or {})
              for item in declarations),
          "every declared design_video uses the common high-level draft/scene protocol",
          declarations)
    check(any("scene" in ((item.get("parameters") or {}).get("properties") or {})
              for item in declarations),
          "a real provider request declares the high-level single-Scene input", declarations)
    designs = [
        args for call in calls for name, args in _p1_tool_calls(call) if name == "design_video"
    ]
    check(designs and all(not raw & set(args) for args in designs),
          "executed model arguments contain neither legacy shots nor raw entities/ops", designs)


def _p1_media_parts(calls: list[dict]) -> list[dict]:
    return [
        part
        for call in calls
        for message in (call["request"].get("payload") or {}).get("messages") or []
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if isinstance(part, dict) and part.get("type") != "text"
    ]


async def _p1_active_draft(ctx: Ctx, turn: dict) -> dict:
    from app.chat.conversation_context import context_items

    async with AsyncSessionLocal() as db:
        conversation = await db.get(Conversation, uuid.UUID(turn["conversation_id"]))
    candidates = [
        item for item in context_items(conversation.context)
        if (item.get("candidate") or {}).get("active", True)
        and (item.get("candidate") or {}).get("target_tool") == "design_video"
        and isinstance(item.get("executed_arguments"), dict)
    ]
    check(candidates, "ConversationContext retains the real working draft", turn)
    item = candidates[-1]
    return {
        "draft_id": item["candidate"]["candidate_id"],
        "draft_digest": item["candidate"]["candidate_digest"],
        "item_id": item["id"],
        "arguments": item["executed_arguments"],
    }


async def _p1_skill_receipt(ctx: Ctx, pid: str, skill_ref: dict) -> dict:
    from app.tools.project_context import settled_skill_read_receipts

    async with AsyncSessionLocal() as db:
        receipts = await settled_skill_read_receipts(
            db, project_id=uuid.UUID(pid), owner_id=ctx.user_id,
        )
    matches = [item for item in receipts.values() if item.get("skill_reference") == skill_ref]
    check(len(matches) == 1, "the built-in Promo has one durable merged read receipt", receipts)
    return matches[0]


async def promo_p1_first_draft(ctx: Ctx) -> None:
    """A real four-second video window through built-in Promo; zero Runs."""
    from app.editing.timing import SOURCE_TIMEBASE, output_ticks_to_source_ticks
    from app.editing.store import content_of

    skill_ref = await _p1_skill_ref(ctx)
    pid = await ctx.new_project("P1 real video four-second first draft")
    video_key = await copy_fixture(REMIX_SOURCE_KEY, f"scenario/p1/{uuid.uuid4().hex}")
    video_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "person-demo.mp4", processed=True,
        file_url=video_key, meta={"language": "en", "origin": {"kind": "p1_four_second_source"}},
    )
    turn = await ctx.chat(
        pid,
        "Use the mentioned real video as the source of exactly one evidence-push shot. "
        "Select one valid 4-second shot from that real source. No on-screen text, "
        "no narration and no music. Save the first storyboard only. Do not produce.",
        skill=skill_ref,
        mentions=[{"type": "asset", "id": video_id, "label": "Real video"}],
    )
    calls = _p1_report_tokens("real_video_four_second_first_draft", turn)
    _p1_assert_generic_design_wire(calls)
    read, _ = await ctx.acknowledge_video_presentation(turn)
    _check_complete_video_storyboard(read, "real-video four-second first draft")
    versions = await composition_versions_of(pid)
    check(len(versions) == 1 and await count_runs(pid) == 0 and not await outputs_of(pid, "video"),
          "the four-second video draft saves once with zero Runs/Outputs", pid)
    content = content_of(versions[0])
    clips = [
        clip for track in content.timeline.tracks for clip in track.clips
        if clip.object.kind == "video"
    ]
    check(len(clips) == 1, "the saved version has exactly one native Video Clip", clips)
    clip = clips[0]
    async with AsyncSessionLocal() as db:
        snapshots = list((await db.scalars(select(SourceSnapshot).where(
            SourceSnapshot.asset_id == uuid.UUID(video_id),
            SourceSnapshot.owner_id == ctx.user_id,
        ))).all())
    check(len(snapshots) == 1, "normal material preparation freezes one video Snapshot", snapshots)
    snapshot = snapshots[0]
    check(snapshot.kind == "video" and snapshot.duration_ticks and snapshot.digest,
          "the frozen Snapshot has its real type, duration and immutable identity", snapshot)
    from app.providers import storage
    import av
    import hashlib
    import io

    encoded = await storage.read(snapshot.storage_key)
    check(hashlib.sha256(encoded).hexdigest() == snapshot.digest,
          "the stored bytes match the Snapshot's frozen digest", snapshot.storage_key)
    container = av.open(io.BytesIO(encoded), mode="r")
    try:
        stream = container.streams.video[0]
        actual_duration = float(stream.duration * stream.time_base)
    finally:
        container.close()
    check(abs(snapshot.duration_ticks / SOURCE_TIMEBASE - actual_duration) < 0.001,
          "Snapshot duration comes from the actual fixture timebase", actual_duration)
    check(clip.source is not None and clip.source.snapshot_id == snapshot.id
          and clip.source.snapshot_digest == snapshot.digest,
          "the Video Clip binds the mentioned asset's real Snapshot", clip)
    source_range = clip.source.source_range
    check(source_range is not None and 0 <= source_range.start < source_range.end <= snapshot.duration_ticks,
          "the selected source window is ordered and inside the frozen source", source_range)
    check(clip.range.duration == 4 * content.settings.timebase
          and source_range.duration == output_ticks_to_source_ticks(
              clip.range.duration, content.settings.timebase,
          ),
          "output and source timebases both prove the user's exact four-second window",
          {"output": clip.range, "source": source_range, "timebase": content.settings.timebase})
    await _p1_report_first_draft(ctx, turn, "real_video_four_seconds")
    print("P1_REAL_VIDEO", json.dumps({
        "project_id": pid,
        "asset_id": video_id,
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
        "snapshot_duration_ticks": snapshot.duration_ticks,
        "message_id": (turn.get("assistant_message") or {}).get("id"),
        "version_id": str(versions[0].id),
        "clip_id": clip.clip_id,
        "output_range": clip.range.model_dump(mode="json"),
        "source_range": source_range.model_dump(mode="json"),
    }, ensure_ascii=False))


async def promo_p1_continuation(ctx: Ctx) -> None:
    """SSE draft, non-streaming clarification, SSE save with restored receipts."""
    from app.editing.store import content_of

    skill_ref = await _p1_skill_ref(ctx)
    pid = await ctx.new_project("P1 exact-copy three-turn continuation")
    first_stream = await ctx.chat_stream(
        pid,
        "Start a message-led draft with exactly 2 scenes and 10 seconds, "
        "no narration and no music, but do not save it yet. Read references/pipeline.md, "
        "two installed shot cards, and one available reference preview once. Use this "
        "exact copy in order, with no other on-screen text and no repetition: "
        "A practical course for clearer product launches. Join the next workshop. "
        "Do not produce a video.",
        skill=skill_ref,
    )
    check(first_stream.completed is not None and first_stream.failed is None,
          "exact-copy SSE draft completes", first_stream.failed)
    first = first_stream.completed
    check(not await composition_versions_of(pid) and await count_runs(pid) == 0,
          "the first exact-copy turn retains a draft without saving or producing", pid)
    first_calls = _p1_report_tokens("exact_copy_initial_draft", first)
    _p1_assert_generic_design_wire(first_calls)
    if len(first_calls) > 1:
        second_usage = (first_calls[1]["outcome"].get("response") or {}).get("usage") or {}
        check((second_usage.get("prompt_tokens") or 0) <= 45_000,
              "fresh second provider call stays at or below 45k prompt tokens", second_usage)
    first_tools = [(name, args) for call in first_calls for name, args in _p1_tool_calls(call)]
    read_paths = [args.get("path") for name, args in first_tools if name == "read_skill_reference"]
    shot_reads = [path for path in read_paths if str(path).startswith("references/shots/")]
    previews = [args for name, args in first_tools if name == "get_skill_preview"]
    check("references/pipeline.md" in read_paths
          and len(set(shot_reads)) >= 2
          and len(previews) == 1,
          "the first turn reads its two selected cards and the required reference preview once",
          first_tools)
    await _p1_report_first_draft(ctx, first, "exact_copy_initial_draft", require_saved=False)
    initial_draft = await _p1_active_draft(ctx, first)
    initial_receipt = await _p1_skill_receipt(ctx, pid, skill_ref)
    check(initial_receipt.get("owner_id") == str(ctx.user_id)
          and initial_receipt.get("reads") and initial_receipt.get("preview_checks"),
          "the first receipt binds owner, package resources and the actual preview read", initial_receipt)

    clarify = await ctx.chat(
        pid,
        "Should the two supplied sentences stay verbatim and in that order? "
        "Only clarify the draft; do not save a version and do not produce.",
    )
    clarify_calls = _p1_report_tokens("exact_copy_non_streaming_clarification", clarify)
    check(not await composition_versions_of(pid) and clarify.get("run_id") is None,
          "the non-streaming clarification neither saves nor produces", pid)
    clarified_draft = await _p1_active_draft(ctx, clarify)
    clarified_receipt = await _p1_skill_receipt(ctx, pid, skill_ref)
    check(clarified_draft["draft_id"] == initial_draft["draft_id"]
          and clarified_draft["draft_digest"] == initial_draft["draft_digest"],
          "clarification preserves the same draft identity and digest", clarified_draft)
    check(clarified_receipt == initial_receipt,
          "ConversationContext restores identical reads without a non-streaming Activity receipt",
          clarified_receipt)
    clarify_wire = json.dumps(
        [call["request"].get("payload") for call in clarify_calls], ensure_ascii=False,
    )
    check(initial_receipt["package_identity"] in clarify_wire
          and all(read["digest"] in clarify_wire for read in initial_receipt["reads"]),
          "the clarification provider request contains the restored package/version/digests",
          initial_receipt)

    third_stream = await ctx.chat_stream(
        pid,
        "Save that existing draft unchanged as the first storyboard. "
        "Do not reread the Skill and do not produce.",
    )
    check(third_stream.completed is not None and third_stream.failed is None,
          "the third-turn SSE save completes", third_stream.failed)
    third = third_stream.completed
    third_calls = _p1_report_tokens("exact_copy_third_turn_save", third)
    third_tools = [(name, args) for call in third_calls for name, args in _p1_tool_calls(call)]
    third_designs = [args for name, args in third_tools if name == "design_video"]
    check(third_designs and all(
        args.get("draft_ref") == {
            "draft_id": initial_draft["draft_id"], "draft_digest": initial_draft["draft_digest"],
        } and args.get("save") is True and not {
            "shots", "tracks", "clips", "ops", "scene", "scene_plan",
        } & set(args)
        for args in third_designs
    ), "third turn saves the exact restored draft without rebinding or redesigning", third_designs)
    check(not any(name in {"read_skill_reference", "list_skill_shots", "get_skill_preview"}
                  for name, _ in third_tools),
          "third-turn save reuses receipts without another package read", third_tools)
    third_wire = json.dumps([call["request"].get("payload") for call in third_calls], ensure_ascii=False)
    check("arc_not_read" not in third_wire and "shot_not_read" not in third_wire,
          "third-turn save never regresses to arc/shot read repair", third_wire[-4000:])
    check("receipt_contains_media" in third_wire and initial_receipt["package_identity"] in third_wire
          and all(read["digest"] in third_wire for read in initial_receipt["reads"]),
          "third turn receives the same owner/package/version/digest receipt", initial_receipt)
    check(not _p1_media_parts(third_calls),
          "no current or historical preview media is reinjected for the save-only turn",
          _p1_media_parts(third_calls))
    check(await _p1_skill_receipt(ctx, pid, skill_ref) == initial_receipt,
          "saving does not alter the durable read receipt", None)
    read, _ = await ctx.acknowledge_video_presentation(third)
    _check_complete_video_storyboard(read, "third-turn exact-copy save")
    versions = await composition_versions_of(pid)
    check(len(versions) == 1 and not content_of(versions[0]).sources
          and await count_runs(pid) == 0 and not await outputs_of(pid, "video"),
          "third turn saves exactly one copy-only version with zero Runs/Outputs", pid)
    expected = "A practical course for clearer product launches. Join the next workshop."
    check(_native_copy_without_whitespace(content_of(versions[0])) == expected.replace(" ", ""),
          "exact copy survives continuation once, in order", _native_copy_without_whitespace(content_of(versions[0])))
    await _p1_report_first_draft(ctx, third, "exact_copy_third_turn")
    print("P1_CONTINUATION", json.dumps({
        "project_id": pid,
        "turn_ids": [_p1_turn_id(first), _p1_turn_id(clarify), _p1_turn_id(third)],
        "user_message_ids": [
            (first.get("user_message") or {}).get("id"),
            (clarify.get("user_message") or {}).get("id"),
            (third.get("user_message") or {}).get("id"),
        ],
        "draft": initial_draft,
        "receipt": initial_receipt,
        "message_id": (third.get("assistant_message") or {}).get("id"),
        "version_id": str(versions[0].id),
    }, ensure_ascii=False))


async def promo_p1_revision(ctx: Ctx) -> None:
    """Independent seeded baseline; ordinary Chat performs only bounded revisions."""
    from app.editing.service import compute_change_set
    from app.editing.store import content_of

    skill_ref = await _p1_skill_ref(ctx)
    pid = await ctx.new_project("P1 independent ordinary revisions")
    initial = await _seed_p1_promo_baseline(ctx, pid, skill_ref)
    _, duration_version = await _p1_revise(
        ctx, pid, "第二个镜头多停一秒，只保存修订，不制作。", "set_clip_duration", 2,
    )
    duration_change = compute_change_set(content_of(initial), content_of(duration_version))
    check(not duration_change["clips"]["added"] and not duration_change["clips"]["removed"]
          and all(change["changes"] == ["range"] for change in duration_change["clips"]["updated"]),
          "duration changes only ranges and no clip identities", duration_change)
    _, text_version = await _p1_revise(
        ctx, pid, "把开场标题换成「让每一份价值都有据可查」，只保存修订，不制作。", "set_text", 3,
    )
    text_change = compute_change_set(content_of(duration_version), content_of(text_version))
    check(len(text_change["clips"]["updated"]) == 1
          and text_change["clips"]["updated"][0]["changes"] == ["object"],
          "set_text changes only the intended native TextObject", text_change)
    _, preset_version = await _p1_revise(
        ctx, pid, "把开场标题改成逐词 reveal（text-reveal），只保存修订，不制作。", "apply_preset", 4,
    )
    preset_change = compute_change_set(content_of(text_version), content_of(preset_version))
    check(len(preset_change["clips"]["updated"]) == 1
          and preset_change["clips"]["updated"][0]["changes"] == ["animations"],
          "apply_preset changes only target animations", preset_change)

    ambiguous = await ctx.chat(
        pid,
        "当前有多个标题，我没有指定哪一个。把标题改成「每次判断都有证据」；"
        "先确认目标再保存，不要替我选，不制作。",
    )
    assistant = ambiguous.get("assistant_message") or {}
    question_id = str((assistant.get("question") or {}).get("id") or assistant.get("id") or "")
    check(bool(assistant.get("question")) and question_id,
          "ambiguous title target creates a real ask_user question row", ambiguous)
    check(len(await composition_versions_of(pid)) == 4 and await count_runs(pid) == 0,
          "ambiguous target creates no version or Run", None)
    _p1_report_tokens("ordinary_revision_title_ambiguity", ambiguous)
    print("P1_REVISION_PROJECT", json.dumps({"project_id": pid, "question_id": question_id}))


async def promo_p1_overlay(ctx: Ctx) -> None:
    """Legacy-provenance overlay ask/answer/save/delete through ordinary Chat."""
    from app.editing.service import compute_change_set
    from app.editing.store import content_of
    from app.editing.timing import output_ticks_to_source_ticks

    skill_ref = await _p1_skill_ref(ctx)
    pid = await ctx.new_project("P1 independent overlay pending")
    initial = await _seed_p1_promo_baseline(ctx, pid, skill_ref)
    initial_content = content_of(initial)
    check((initial.skill_provenance or {}).get("skill") == "promo-video"
          and len(initial_content.scenes) >= 2,
          "the saved fixture really carries legacy Promo provenance and two Scenes", initial.id)
    video_key = await copy_fixture(REMIX_SOURCE_KEY, f"scenario/p1/{uuid.uuid4().hex}")
    video_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "person-demo.mp4", processed=True,
        file_url=video_key, meta={"language": "zh", "origin": {"kind": "p1_person_overlay"}},
    )
    mention = [{"type": "asset", "id": video_id, "label": "本人视频"}]
    ask_turn = await ctx.chat(
        pid, "加一段我的本人视频显示在画面右下角，只保存修订，不制作。", mentions=mention,
    )
    ask_assistant = ask_turn.get("assistant_message") or {}
    question = ask_assistant.get("question") or {}
    question_id = str(ask_assistant.get("id") or "")
    check(bool(question) and question_id and question.get("options"),
          "overlay ambiguity lands a real ask_user with candidate choices", ask_turn)
    ask_wire = json.dumps([question, ask_assistant.get("content")], ensure_ascii=False)
    check("第二" in ask_wire or "second" in ask_wire.lower(),
          "the question points at actual Scene candidates rather than prose-only clarification", ask_wire)
    versions_after_ask = await composition_versions_of(pid)
    check(len(versions_after_ask) == 1 and versions_after_ask[0].content_digest == initial.content_digest,
          "overlay clarification leaves the original version byte-identical", None)
    ask_calls = _p1_report_tokens("overlay_ask", ask_turn)
    check(max(
        ((call["outcome"].get("response") or {}).get("usage") or {}).get("prompt_tokens") or 0
        for call in ask_calls
    ) <= 70_000, "overlay ask's each provider call stays at or below 70k prompt tokens", None)

    overlay_turn, overlay_version = await _p1_revise(
        ctx, pid, "整个第二镜，不需要我再给秒数。", "overlay_answer_save", 2,
    )
    check(str((overlay_turn.get("answered_question") or {}).get("id") or "") == question_id,
          "whole-second-Scene save settles the original question, not a proactive trigger", overlay_turn)
    async with AsyncSessionLocal() as db:
        stored_question = await db.get(Message, uuid.UUID(question_id))
        snapshot = await db.get(SourceSnapshot, next(
            clip.source.snapshot_id
            for track in content_of(overlay_version).timeline.tracks for clip in track.clips
            if clip.clip_id.startswith("clp_overlay_")
        ))
    check(stored_question is not None
          and (stored_question.answer or {}).get("kind") == "freeform"
          and (stored_question.answer or {}).get("text") == "整个第二镜，不需要我再给秒数。",
          "the original question row is genuinely answered only after the successful save", stored_question.answer)
    check(snapshot is not None and snapshot.owner_id == ctx.user_id and snapshot.kind == "video"
          and snapshot.asset_id == uuid.UUID(video_id) and snapshot.duration_ticks,
          "the overlay uses the mentioned real video Snapshot with owner and duration facts", snapshot)
    overlay_content = content_of(overlay_version)
    overlay_change = compute_change_set(initial_content, overlay_content)
    check(len(overlay_change["clips"]["added"]) == 1
          and not overlay_change["clips"]["updated"] and not overlay_change["clips"]["removed"],
          "the overlay revision adds exactly one Clip and changes no existing Clip", overlay_change)
    overlay = next(
        clip for track in overlay_content.timeline.tracks for clip in track.clips
        if clip.clip_id.startswith("clp_overlay_")
    )
    second_scene = sorted(overlay_content.scenes, key=lambda scene: scene.range.start)[1]
    right_margin = 1920 - overlay.object.layout.x - overlay.object.layout.width
    bottom_margin = 1080 - overlay.object.layout.y - overlay.object.layout.height
    check(overlay.range == second_scene.range
          and overlay.source.snapshot_id == snapshot.id
          and overlay.source.source_range.start >= 0
          and overlay.source.source_range.end <= snapshot.duration_ticks
          and overlay.source.source_range.duration == output_ticks_to_source_ticks(
              second_scene.range.duration, overlay_content.settings.timebase,
          )
          and 0 <= right_margin <= 512 and 0 <= bottom_margin <= 512
          and abs(right_margin - bottom_margin) < 1e-6,
          "whole-Scene overlay uses the current head range, legal source window and bottom-right layout",
          {"clip": overlay, "right_margin": right_margin, "bottom_margin": bottom_margin})

    delete_turn, removed_version = await _p1_revise(
        ctx, pid, "把这段本人视频删掉，只保存修订，不制作。", "overlay_delete", 3,
    )
    removed_content = content_of(removed_version)
    delete_change = compute_change_set(overlay_content, removed_content)
    check(delete_change["clips"]["removed"] == [overlay.clip_id]
          and not delete_change["clips"]["added"] and not delete_change["clips"]["updated"]
          and all(clip.clip_id != overlay.clip_id
                  for track in removed_content.timeline.tracks for clip in track.clips),
          "ordinary Chat deletes only the intended overlay Clip", delete_change)
    conversation = await ctx.conversation(pid)
    check(conversation.status_code == 200
          and conversation.json().get("pending_question") is None,
          "deletion does not resurrect the settled question", conversation.text)
    delete_wire = json.dumps([
        call["request"].get("payload") for call in _p1_provider_calls(delete_turn)
    ], ensure_ascii=False)
    check("Pending question awaiting the user's answer:" not in delete_wire
          and question_id not in delete_wire,
          "the deletion turn's actual model input has no old pending reminder", delete_wire[-4000:])
    print("P1_OVERLAY_PROJECT", json.dumps({
        "project_id": pid,
        "question_id": question_id,
        "snapshot_id": str(snapshot.id),
        "overlay_clip_id": overlay.clip_id,
        "overlay_version_id": str(overlay_version.id),
        "removed_version_id": str(removed_version.id),
    }))


async def _seed_sequential_oxvalue_draft(ctx: Ctx, pid: str):
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ToolExchange, ToolObservation
    from app.agents.working_drafts import working_draft_observation
    from app.chat.conversation_context import ConversationContext
    from app.editing.store import content_of
    from app.tools.video.design import CompositionDesignVideoArgs

    fixture_version_id = uuid.UUID("946f96f9-ef35-4c0c-87b2-d6115738ad77")
    async with AsyncSessionLocal() as db:
        version = await db.get(CompositionVersion, fixture_version_id)
        check(version is not None, "P2 frozen OxValue fixture version exists", fixture_version_id)
        composition = await db.get(Composition, version.composition_id)
        check(composition.owner_id == ctx.user_id,
              "P2 uses the frozen fixture's owner without copying or recapturing media", composition.owner_id)
        content = content_of(version)
        conversation = Conversation(user_id=ctx.user_id, project_id=uuid.UUID(pid))
        db.add(conversation)
        await db.flush()
        opening = Message(
            conversation_id=conversation.id,
            role="user",
            content="测试夹具：恢复同一未保存的 OxValue 两幕工作草稿。",
            turn_state="settled",
            seq=1,
        )
        db.add(opening)
        await db.flush()
        opening.turn_id = opening.id
        await db.commit()
        conversation_id, opening_id = conversation.id, opening.id
    arguments = {
        "content": content.model_dump(mode="json"),
        "design": {"name": "OxValue sequential draft review"},
    }
    record = CandidateRecord.create(
        tool_name="design_video",
        arguments=arguments,
        errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id=str(ctx.user_id), conversation_id=str(conversation_id)),
        base_keys=frozenset(),
        call_id="fixture-oxvalue-two-scenes",
        candidate_id="cnd_oxvalue_sequential",
    )
    observation = ToolObservation(json.dumps(working_draft_observation(record), ensure_ascii=False))
    exchange = ToolExchange(
        call_id="fixture-oxvalue-two-scenes",
        tool_name="design_video",
        arguments={"fixture": "frozen_oxvalue_two_scene_draft"},
        executed_arguments=arguments,
        observation=observation,
        target_tool="design_video",
        candidate={
            "candidate_id": record.candidate_id,
            "candidate_digest": record.candidate_digest,
            "target_tool": "design_video",
            "base_keys": [],
            "active": True,
        },
    )
    await ConversationContext(
        conversation_id=conversation_id,
        owner_id=ctx.user_id,
        turn_id=opening_id,
    ).record(exchange)
    return content


async def sequential_oxvalue_draft_review(ctx: Ctx) -> None:
    """P2 ordinary-Chat sequential draft review, local fix, recheck and save; no production."""
    from app.editing.store import content_of
    fixture_owner = uuid.UUID("1291c14d-fdae-406a-8be4-7585f2e213a0")
    local = Ctx(fixture_owner, keep=ctx.keep)
    try:
        pid = await local.new_project("P2 OxValue sequential draft review")
        before = await _seed_sequential_oxvalue_draft(local, pid)
        stream = await local.chat_stream(
            pid,
            "请按播放顺序审查当前工作草稿：先检查第 1 幕，再检查第 2 幕与上一幕的衔接。"
            "第 1 幕应让观众看清 Frame / Enrich，第 2 幕应转向 Value / Defend。"
            "请根据真实预览证据判断；若发现不符，只修改有问题的幕，复查受影响范围，"
            "核对第一幕、原生文字轨、来源和时间线没有意外改动后，保存并呈现可编辑分镜。"
            "不要制作或渲染正式视频。",
        )
        check(stream.failed is None and stream.completed is not None,
              "P2 ordinary Chat completes with an envelope", stream.failed)
        turn = stream.completed
        calls = _p1_report_tokens("P2 sequential OxValue", turn)
        tool_calls = [item for call in calls for item in _p1_tool_calls(call)]
        names = [name for name, _ in tool_calls]
        check(names.count("review_working_draft") >= 3,
              "P2 actually previews Scene 1, the 1→2 join and the affected recheck", names)
        first_review = names.index("review_working_draft")
        second_review = names.index("review_working_draft", first_review + 1)
        first_edit = next((index for index, (name, args) in enumerate(tool_calls)
                           if name == "design_video" and not args.get("save")), None)
        check(first_edit is not None and first_edit > second_review,
              "P2 model edits only after evidence from the second Scene", tool_calls)
        recheck_index = next((index for index in range(first_edit + 1, len(tool_calls))
                              if tool_calls[index][0] == "review_working_draft"), None)
        check(recheck_index is not None, "P2 rechecks after the local edit", names)
        save_index = next((index for index in range(recheck_index + 1, len(tool_calls))
                           if tool_calls[index][0] == "design_video"
                           and tool_calls[index][1].get("save") is True), None)
        check(save_index is not None and save_index > recheck_index,
              "P2 saves only after the affected continuous recheck", tool_calls)
        review_args = [args for name, args in tool_calls if name == "review_working_draft"]
        check(all("target" not in args and "requirements" not in args for args in review_args),
              "P2 server owns preview windows instead of model-supplied targets", review_args)
        check(sum(args.get("judgment") is not None for args in review_args) >= 3,
              "P2 records explicit judgments against returned evidence ids", review_args)
        edited_clip_ids = {
            entity.get("clip_id") or (entity.get("clip") or {}).get("clip_id")
            for name, args in tool_calls[:save_index]
            if name == "design_video" and not args.get("save")
            for entity in [
                *(args.get("clips") or []),
                *[
                    clip for track in args.get("tracks") or []
                    for clip in track.get("clips") or []
                ],
            ]
        }
        edited_clip_ids.update(
            args["focus_clip_id"]
            for name, args in tool_calls[:save_index]
            if name == "design_video" and not args.get("save") and args.get("focus_clip_id")
        )
        edited_clip_ids.discard(None)
        check(edited_clip_ids == {"clp_review_web"},
              "P2 edits only the second Scene web Clip", edited_clip_ids)
        print("P2_MODEL_DISCOVERY", json.dumps({
            "second_review_tool_index": second_review,
            "first_edit_tool_index": first_edit,
            "edited_clip_ids": sorted(edited_clip_ids),
            "recheck_tool_index": recheck_index,
            "save_tool_index": save_index,
        }))

        active = [item for item in stream.activities if item.get("status") == "active"]
        expected_activity = [
            "chat.activity.videoDraftScene",
            "chat.activity.videoDraftJoin",
            "chat.activity.videoDraftRecheck",
            "chat.activity.videoSave",
        ]
        positions = [next((i for i, item in enumerate(active) if item.get("key") == key), None)
                     for key in expected_activity]
        check(all(index is not None for index in positions) and positions == sorted(positions),
              "P2 Activity starts in actual review/recheck/save order", active)
        check(active[positions[0]].get("count") == 1
              and active[positions[1]].get("count") == 2
              and active[positions[2]].get("count") == 2,
              "P2 Activity names the actual Scene and cumulative range", active)
        evidence_receipts = list({
            (item.get("receipt") or {})["evidence_id"]: (item.get("receipt") or {})
            for item in stream.activities
            if item.get("status") == "completed"
            and (item.get("receipt") or {}).get("kind") == "video_draft_review"
        }.values())
        check(len(evidence_receipts) >= 3
              and len({item["media_digest"] for item in evidence_receipts}) >= 3,
              "P2 completed Activity follows distinct actual preview media", evidence_receipts)
        check(evidence_receipts[0]["scene_ids"] == ["input"]
              and evidence_receipts[0]["source_range_seconds"] == {"start": 0.0, "end": 4.0},
              "P2 first receipt proves Scene 1 alone", evidence_receipts[0])
        check({"input", "review"} <= set(evidence_receipts[1]["scene_ids"])
              and evidence_receipts[1]["source_range_seconds"]["end"] == 8.0,
              "P2 second receipt proves the 1→2 join and Scene 2", evidence_receipts[1])
        check("review" in evidence_receipts[2]["scene_ids"]
              and evidence_receipts[2]["source_range_seconds"]["end"] == 8.0,
              "P2 recheck receipt covers the affected second Scene", evidence_receipts[2])
        check(all(item.get("evidence_id") for item in evidence_receipts)
              and len({item["evidence_id"] for item in evidence_receipts}) == len(evidence_receipts),
              "P2 reports stable distinct evidence ids", evidence_receipts)
        print("P2_PREVIEW_WINDOWS", json.dumps([{
            "evidence_id": item["evidence_id"],
            "media_digest": item["media_digest"],
            "range": item["source_range_seconds"],
            "scene_ids": item["scene_ids"],
        } for item in evidence_receipts], ensure_ascii=False))

        interim_positions = [
            index for index, event in enumerate(stream.raw_events)
            if event["event"] == "assistant.interim_prose"
        ]
        first_preview_done = next(
            index for index, event in enumerate(stream.raw_events)
            if event["event"] == "assistant.activity"
            and event["data"].get("key") == "chat.activity.videoDraftSceneDone"
        )
        second_preview_done = next(
            index for index, event in enumerate(stream.raw_events)
            if event["event"] == "assistant.activity"
            and event["data"].get("key") == "chat.activity.videoDraftJoinDone"
        )
        edit_started = next(
            index for index, event in enumerate(stream.raw_events)
            if index > second_preview_done and event["event"] == "assistant.activity"
            and event["data"].get("key") == "chat.activity.videoDesign"
            and event["data"].get("status") == "active"
        )
        check(sum(position < first_preview_done for position in interim_positions) <= 1,
              "P2 opening plan occurs at most once before the first evidence", stream.interim_prose_rows)
        check(any(second_preview_done < position < edit_started for position in interim_positions),
              "P2 second-Scene finding follows its actual preview and precedes repair", stream.raw_events)
        check(len(interim_positions) <= 2,
              "P2 later repair and recheck do not repeat the opening plan", stream.interim_prose_rows)

        versions = await composition_versions_of(pid)
        check(len(versions) == 1, "P2 final working draft lands exactly one editable version", versions)
        final = content_of(versions[0])
        await local.acknowledge_video_presentation(turn)
        old_clips = {clip.clip_id: clip for track in before.timeline.tracks for clip in track.clips}
        new_clips = {clip.clip_id: clip for track in final.timeline.tracks for clip in track.clips}
        changed = [clip_id for clip_id in old_clips if old_clips[clip_id] != new_clips[clip_id]]
        check(changed == ["clp_review_web"],
              "P2 saved delta is exactly the second web Clip", changed)
        check(final.settings == before.settings and final.sources == before.sources
              and final.timeline.transitions == before.timeline.transitions,
              "P2 preserves settings, sources and transitions", None)
        check(final.scenes[0] == before.scenes[0]
              and new_clips["clp_input_web"] == old_clips["clp_input_web"]
              and new_clips["clp_input_headline"] == old_clips["clp_input_headline"]
              and new_clips["clp_review_headline"] == old_clips["clp_review_headline"],
              "P2 preserves Scene 1 and both native text Clips", None)
        check(new_clips["clp_review_web"].animations != old_clips["clp_review_web"].animations
              and new_clips["clp_review_web"].object == old_clips["clp_review_web"].object
              and new_clips["clp_review_web"].source == old_clips["clp_review_web"].source,
              "P2 changes only the target camera animation and preserves its frozen source", None)
        check(await count_runs(pid) == 0, "P2 creates no production Run", None)
        async with AsyncSessionLocal() as db:
            outputs = await db.scalar(select(func.count(Output.id)).where(Output.project_id == uuid.UUID(pid)))
        check(outputs == 0, "P2 creates no formal Output", outputs)
        print("P2_FINAL", json.dumps({
            "project_id": pid,
            "composition_id": str(versions[0].composition_id),
            "composition_version_id": str(versions[0].id),
            "content_digest": versions[0].content_digest,
            "provider_calls": len(calls),
            "prompt_tokens": sum(((call["outcome"].get("response") or {}).get("usage") or {}).get("prompt_tokens") or 0
                                 for call in calls),
            "evidence_ids": [item["evidence_id"] for item in evidence_receipts],
            "preview_windows": [item["source_range_seconds"] for item in evidence_receipts],
            "changed_clip_ids": changed,
        }, ensure_ascii=False))

        title_text = "Value / Defend — 已更新"
        title_stream = await local.chat_stream(
            pid,
            f"把刚才保存作品的第二幕标题改为“{title_text}”。只改这个标题，"
            "不要重新审片，不要制作或渲染正式视频。",
        )
        check(title_stream.failed is None and title_stream.completed is not None,
              "P2 saved-version title edit completes in the same Chat", title_stream.failed)
        title_turn = title_stream.completed
        title_calls = _p1_report_tokens("P2 saved-version title edit", title_turn)
        title_tool_calls = [item for call in title_calls for item in _p1_tool_calls(call)]
        check(any(name == "revise_video" for name, _ in title_tool_calls),
              "P2 title feedback writes through saved-version revision", title_tool_calls)
        check(not title_stream.interim_prose_rows,
              "P2 targeted saved-version edit calls tools without opening or progress prose",
              title_stream.interim_prose_rows)
        for call in title_calls:
            payload = call["request"].get("payload") or {}
            messages = payload.get("messages") or []
            text = "\n".join(
                content if isinstance((content := message.get("content")), str)
                else json.dumps(content, ensure_ascii=False)
                for message in messages
            )
            check('"video_stage": "version_edit"' in text,
                  "P2 every saved-version provider request uses version_edit", text[-2000:])
            check('"video_stage": "draft_review"' not in text,
                  "P2 saved-version edit never reenters first-draft review", None)
            declared = {
                (item.get("function") or {}).get("name")
                for item in payload.get("tools") or []
            }
            check("review_working_draft" not in declared and "design_video" not in declared,
                  "P2 saved-version request omits draft authoring and review tools", declared)
            media_parts = [
                part for message in messages for part in (message.get("content") or [])
                if isinstance(message.get("content"), list)
                and isinstance(part, dict) and part.get("type") != "text"
            ]
            check(not media_parts, "P2 saved-version request carries no current or historical video", media_parts)

        title_versions = await composition_versions_of(pid)
        check(len(title_versions) == 2 and title_versions[1].version == 2,
              "P2 title edit creates exactly one next immutable version", title_versions)
        title_final = content_of(title_versions[1])
        title_clips = {
            clip.clip_id: clip for track in title_final.timeline.tracks for clip in track.clips
        }
        title_changed = [
            clip_id for clip_id in new_clips
            if new_clips[clip_id] != title_clips[clip_id]
        ]
        check(title_changed == ["clp_review_headline"],
              "P2 title revision changes only the requested text Clip", title_changed)
        check(title_clips["clp_review_headline"].object.text == title_text
              and title_clips["clp_review_web"] == new_clips["clp_review_web"]
              and title_clips["clp_input_headline"] == new_clips["clp_input_headline"],
              "P2 title text is exact and prior repair/other text stay intact", None)
        check(await count_runs(pid) == 0, "P2 two turns create no production Run", None)
        async with AsyncSessionLocal() as db:
            outputs = await db.scalar(select(func.count(Output.id)).where(Output.project_id == uuid.UUID(pid)))
        check(outputs == 0, "P2 two turns create no formal Output", outputs)
        print("P2_TITLE_EDIT", json.dumps({
            "project_id": pid,
            "composition_id": str(title_versions[1].composition_id),
            "composition_version_id": str(title_versions[1].id),
            "content_digest": title_versions[1].content_digest,
            "provider_calls": len(title_calls),
            "prompt_tokens": sum(((call["outcome"].get("response") or {}).get("usage") or {}).get("prompt_tokens") or 0
                                 for call in title_calls),
            "changed_clip_ids": title_changed,
            "run_count": 0,
            "output_count": 0,
        }, ensure_ascii=False))
    finally:
        await local.cleanup()
        await local.close()


async def _external_generator_journey(
    ctx: Ctx, *, package: str, resource_id: str, component_path: str,
    component_export: str, output: dict, extra_files: dict[str, bytes],
    images: dict[str, bytes],
) -> None:
    from app.editing.store import content_of
    from app.skills.external import build_skill_draft
    from app.skills.store import import_external_skill
    from app.tools.video.components import ComponentError, assert_component_bake_available

    try:
        await assert_component_bake_available()
    except ComponentError as exc:
        raise ExternalServiceBlocked(str(exc)) from exc
    root = Path(os.environ.get("JOURNEY_SKILL_ROOT", str(Path.home() / "Downloads"))) / f"{package}-main"
    entry_path = "template/generators/entry.tsx"
    import_path = "../../" + component_path.rsplit(".", 1)[0]
    component_import = f"{{ {component_export} as Shot }}" if component_export else "Shot"
    entry = (
        'import React from "react";\n'
        'import { Composition, registerRoot } from "remotion";\n'
        f'import {component_import} from "{import_path}";\n'
        f'const Root = () => <Composition id="PackageShot" component={{Shot}} '
        f'durationInFrames={{{output["duration_frames"]}}} fps={{{output["fps"]}}} '
        f'width={{{output["width"]}}} height={{{output["height"]}}} />;\n'
        'registerRoot(Root);\n'
    ).encode()
    media_paths = {name: f"gallery/media/{name}" for name in images}
    declaration = {
        "entry": entry_path, "composition_id": "PackageShot",
        "files": [entry_path, component_path, *extra_files],
        "resources": media_paths, "output": output,
    }
    files = {
        "SKILL.md": (root / "SKILL.md").read_bytes(),
        component_path: (root / component_path).read_bytes(),
        entry_path: entry,
        f"template/generators/{resource_id}.json": json.dumps(declaration).encode(),
        **extra_files,
        **{media_paths[name]: data for name, data in images.items()},
    }
    draft = build_skill_draft(files, declared_capabilities={"runtime:remotion-source"})
    async with AsyncSessionLocal() as db:
        skill_version, _ = await import_external_skill(db, owner_id=ctx.user_id, draft=draft)
        skill_ref = {"kind": "external", "skill_version_id": str(skill_version.id)}
        await db.commit()

    pid = await ctx.new_project(f"Dynamic Skill {package}")
    ticks = output["duration_frames"] * 90000 // output["fps"]
    print(f"  Project {pid}, bound SkillVersion {skill_ref['skill_version_id']}", flush=True)
    turn = await ctx.chat(
        pid,
        f"Use the bound Skill to save a one-scene storyboard using its declared {resource_id} "
        f"Generator. Use list_skill_shots to discover it, then place it with the skill_resource "
        f"field. Create Scene scene_demo at ticks 0–{ticks}, timebase 90000. Create an "
        "empty visual Track track_main with role main in tracks. Place the packaged resource "
        "using scene_demo, track_main and clip_demo, and leave clips empty for this write. "
        "Use the packaged source and assets as-is. This is a silent visual example. "
        "Save and present the editable storyboard. No title, narration, music, preview or production.",
        skill=skill_ref,
    )
    read, ack = await ctx.acknowledge_video_presentation(turn)
    versions = await composition_versions_of(pid)
    check(len(versions) == 1, "one saved version", [str(version.id) for version in versions])
    version = versions[0]
    content = content_of(version)
    clips = [clip for track in content.timeline.tracks for clip in track.clips]
    check(len(clips) == 1 and clips[0].object.kind == "generator",
          "one editable Generator Clip", [clip.clip_id for clip in clips])
    clip = clips[0]
    project = clip.object.project
    check(project is not None and {f.path: f.content.encode() for f in project.files}
          == {path: files[path] for path in declaration["files"]},
          "exact package source bytes reached the saved Clip", None)
    check({r.path for r in project.resources} == set(images),
          "exact package image paths reached the saved Clip", None)
    provenance = version.skill_provenance or {}
    check(provenance.get("skill_reference") == skill_ref
          and provenance.get("skill_generator_resources", {}).get(clip.clip_id, {}).get("resource_id") == resource_id,
          "saved version pins package version and resource", provenance)
    check("video_preview" not in read and ack.get("accepted") is True,
          "default storyboard acknowledged without dynamic preview", ack)
    scrub_target = {"kind": "object", "object_id": clip.object.object_id}
    preview_turn = await ctx.chat(
        pid,
        f"Show the local motion preview of object {clip.object.object_id} from the saved "
        f"version {version.id}. Please re-present the storyboard with its isolated object "
        "Scrub. Leave the saved composition as it is.",
    )
    scrub, _ = await ctx.acknowledge_video_presentation(preview_turn)
    check(scrub.get("scrub") == scrub_target, "only the requested object was previewed", scrub.get("scrub"))
    preview = scrub.get("video_preview") or {}
    check(preview.get("status") == "ready", "explicit local Generator Scrub succeeds", preview)
    check(len(await composition_versions_of(pid)) == 1, "preview is read-only", None)
    async with AsyncSessionLocal() as db:
        outputs = await db.scalar(select(func.count()).select_from(Output).where(Output.project_id == uuid.UUID(pid)))
    check(await count_runs(pid) == outputs == 0, "zero Run and Output", outputs)
    print(f"  Version {version.id}, assistant message {turn['assistant_message'].get('id')}, local Scrub ready")


async def dynamic_skill_shotcraft(ctx: Ctx) -> None:
    """Load a real Shotcraft TSX + layout JSON and fixed image closure."""
    package = "video-shotcraft"
    root = Path(os.environ.get("JOURNEY_SKILL_ROOT", str(Path.home() / "Downloads"))) / f"{package}-main"
    layout_path = "demos/_legacy/_textures/live-layout.json"
    layout_data = (root / layout_path).read_bytes()
    cards = json.loads(layout_data)["projects"]["cards"]
    image_names = ["projects-full.png", "card4-hires.png", *[card["file"] for i, card in enumerate(cards) if i != 3][:8]]
    await _external_generator_journey(
        ctx, package=package, resource_id="dolly-zoom",
        component_path="demos/_legacy/camera/depth-layer-moves/DollyZoomReal.tsx",
        component_export="DollyZoomReal",
        output={"width": 1920, "height": 1080, "fps": 30, "duration_frames": 135, "background": "#efece6"},
        extra_files={layout_path: layout_data},
        images={f"legacy-textures/{name}": (root / layout_path).with_name(name).read_bytes() for name in image_names},
    )


async def dynamic_skill_talkcraft(ctx: Ctx) -> None:
    """Load a real Talkcraft data-animation card with no fixed media."""
    await _external_generator_journey(
        ctx, package="video-talkcraft", resource_id="chart-grow",
        component_path="template/cards/chart-grow.tsx", component_export="",
        output={"width": 960, "height": 540, "fps": 30, "duration_frames": 68, "background": "#ffffff"},
        extra_files={}, images={},
    )


async def _import_promo_method(ctx: Ctx) -> dict:
    from app.config import settings
    from app.skills.external import build_skill_draft
    from app.skills.package_reader import open_builtin_skill_package
    from app.skills.store import import_external_skill

    version = settings.managed_skill_versions.get("promo-video")
    root = open_builtin_skill_package("promo-video", version).root_manifest.parent
    package_files = {"SKILL.md": (root / "SKILL.md").read_bytes()}
    for path in (root / "references").rglob("*.md"):
        package_files[path.relative_to(root).as_posix()] = path.read_bytes()
    draft = build_skill_draft(package_files, declared_capabilities=set())
    async with AsyncSessionLocal() as db:
        skill, _ = await import_external_skill(db, owner_id=ctx.user_id, draft=draft)
        skill_ref = {"kind": "external", "skill_version_id": str(skill.id)}
        await db.commit()
    return skill_ref


async def promo_generic_cutover_probe(ctx: Ctx) -> None:
    """Exercise the Promo method through the generic writer with exact copy and two briefs."""
    from app.editing.store import content_of
    from app.providers import storage
    skill_ref = await _import_promo_method(ctx)
    api_root = Path(__file__).resolve().parents[2]
    screenshot = api_root / "test/fixtures/video_project/media/web-hero.png"
    key = f"scenario/promo-generic/{uuid.uuid4().hex}/web-hero.png"
    await storage.save(key, screenshot.read_bytes(), content_type="image/png")
    plans = (
        ("Evidence for a product team", "See evidence before deciding.", ("image", "text")),
        ("An invitation for reviewers", "Join the review workshop.", ("text", "image")),
    )
    for label, title, order in plans:
        pid = await ctx.new_project(f"Generic Promo · {label}")
        asset = await seed_asset(
            pid, ctx.user_id, AssetType.IMAGE, screenshot.name, processed=True, file_url=key,
        )
        print(f"  {label}: project {pid}", flush=True)
        directions = {
            "image": "show only the attached real website screenshot",
            "text": f'show only the native title "{title}"',
        }
        turn = await ctx.chat(
            pid,
            f"Use the bound promotional Skill to make a silent, editable storyboard. "
            f"Exactly two 4-second scenes: first {directions[order[0]]}, "
            f"then {directions[order[1]]}. The native title must appear exactly once "
            f"with no other authored on-screen text. Read the relevant Shotcraft method or card, "
            f"prepare the attached screenshot, build and save the storyboard. "
            f"No audio, preview or production.",
            skill=skill_ref,
            mentions=[{"type": "asset", "id": asset, "label": "Website screenshot"}],
        )
        read, _ = await ctx.acknowledge_video_presentation(turn)
        _check_complete_video_storyboard(read, label)
        versions = await composition_versions_of(pid)
        check(len(versions) == 1 and versions[0].skill_provenance.get("skill_reference") == skill_ref
              and "builder_version" not in versions[0].skill_provenance,
              "the generic writer saves one version with the bound Skill identity", versions)
        content = content_of(versions[0])
        check(_media_kinds_in_scene_order(content) == list(order), "brief determines scene order", order)
        native_titles = [
            clip for track in content.timeline.tracks for clip in track.clips
            if clip.object.kind == "text" and clip.object.caption is None
        ]
        check([clip.object.text for clip in native_titles] == [title],
              "the exact native copy appears once", title)
        edited_title = "Make the next review clearer."
        revised = await ctx.chat(pid, f'Change the title to "{edited_title}"')
        await ctx.acknowledge_video_presentation(revised)
        history = await composition_versions_of(pid)
        check(len(history) == 2, "the title edit creates exactly one new version", history)
        _check_only_text_revision(content, content_of(history[-1]), native_titles[0].clip_id, edited_title)
        async with AsyncSessionLocal() as db:
            outputs = await db.scalar(select(func.count()).select_from(Output).where(Output.project_id == uuid.UUID(pid)))
        check(await count_runs(pid) == outputs == 0, "the generic authoring and edit start no production", pid)
        print(f"  {label}: versions {history[0].id}, {history[-1].id}", flush=True)


async def promo_short_confirmation_delivery(ctx: Ctx) -> None:
    """Use a real URL, then only OK/Yes, to deliver the approved storyboard."""
    await topup_wallet(ctx.user_id)
    pid = await ctx.new_project("Promo URL to confirmed delivery")
    print(f"  Project {pid}", flush=True)
    first = await ctx.chat(
        pid, "/promo-video 帮我给这个网站制作一个宣传片：https://agent.oxvalue.ai/",
        skill=await _p1_skill_ref(ctx),
    )
    first_calls = _p1_report_tokens("promo_builtin_first_draft", first)
    for call in first_calls:
        for declaration in (call["request"].get("payload") or {}).get("tools") or []:
            function = declaration.get("function") or {}
            if function.get("name") != "design_video":
                continue
            properties = (function.get("parameters") or {}).get("properties") or {}
            check(not {"scene_count", "target_seconds", "aspect", "background"} & set(properties),
                  "the unfixed URL brief never exposes invented hard constraints", sorted(properties))
            check("verbatim_copy" not in properties,
                  "the plain URL brief does not invent an exact-copy restriction", sorted(properties))
        declared_names = {
            (declaration.get("function") or {}).get("name")
            for declaration in (call["request"].get("payload") or {}).get("tools") or []
        }
        check("show_music_candidates" not in declared_names,
              "an autonomous first draft does not turn background music into a user decision", declared_names)
    read, ack = await ctx.acknowledge_video_presentation(first)
    _check_complete_video_storyboard(read, "website Promo first storyboard")
    check(ack.get("accepted") and await count_runs(pid) == 0,
          "the storyboard is presented before a Run exists", ack)
    check("按这版开始制作吗？" in first["assistant_message"]["content"]
          or "Shall I produce this version?" in first["assistant_message"]["content"],
          "the storyboard asks for production approval", first["assistant_message"]["content"])
    versions = await composition_versions_of(pid)
    check(len(versions) == 1, "one saved storyboard", versions)
    from app.editing.store import content_of
    saved_content = content_of(versions[0])
    music_clips = [
        clip for track in saved_content.timeline.tracks if track.role == "music"
        for clip in track.clips
    ]
    presentation_request_text = json.dumps(
        first_calls[-1]["request"].get("payload") or {}, ensure_ascii=False,
    )
    expected_music_fact = (
        f"Music: {len(music_clips)} saved Clip(s) in this version."
        if music_clips else "Music: none in this saved version."
    )
    check(expected_music_fact in presentation_request_text,
          "the presentation request reads saved music facts, not an old selection plan",
          {"music_clips": len(music_clips), "model_call_id": first_calls[-1]["request"].get("model_call_id")})
    print(f"  Storyboard {versions[0].id}, message {first['assistant_message']['id']}, saved music Clips {len(music_clips)}", flush=True)

    approved = await ctx.chat(pid, "OK")
    _p1_report_tokens("promo_short_ok", approved)
    if approved.get("run_id") is None:
        question = (approved.get("assistant_message") or {}).get("question") or {}
        check(question.get("kind") == "task_book", "OK yields a real production quote", approved)
        approved = await ctx.chat(pid, "Yes")
        _p1_report_tokens("promo_short_yes", approved)
    run_id = approved.get("run_id")
    check(run_id is not None and await count_runs(pid) == 1, "one authorized production Run", approved)
    production_speech = (approved.get("assistant_message") or {}).get("content") or ""
    check(not any(marker in production_speech for marker in ("dock call", "Re-issuing", "empty payload", "extra title field")),
          "production confirmation does not expose tool-argument repair narration", production_speech)
    print(f"  Run {run_id}", flush=True)
    run = await run_row(run_id)
    check(run["context"].get("version_ref") == read["base_ref"],
          "the Run pins the approved version", run["context"])
    check(await wait_run_terminal(run_id, timeout=900.0) == "completed", "production completes", run_id)
    videos = await outputs_of(pid, "video")
    check(len(videos) == 1 and videos[0].render_status == RenderStatus.COMPLETED
          and bool((videos[0].files or {}).get("video"))
          and videos[0].composition_version_id == versions[0].id,
          "one delivered playable video pins the storyboard", videos)
    check((videos[0].render_spec or {}).get("provenance") == run["context"].get("version_ref"),
          "Run and Output render input pin the same version and digest", videos[0].render_spec)
    import av
    import hashlib
    import io
    from app.providers import storage
    from app.tools.video.output_checks import inspect_output_audio
    encoded = await storage.read(videos[0].files["video"])
    with av.open(io.BytesIO(encoded)) as container:
        check(bool(container.streams.video), "the delivered Output has a video stream", videos[0].id)
        stream = container.streams.video[0]
        decoded_frames = sum(1 for _ in container.decode(video=0))
        video_facts = {
            "decoded_frames": decoded_frames,
            "width": stream.width, "height": stream.height, "fps": float(stream.average_rate),
            "stream_seconds": float(stream.duration * stream.time_base) if stream.duration else None,
            "container_seconds": container.duration / 1e6,
        }
    check(decoded_frames == int((videos[0].render_spec or {}).get("duration_frames") or 0),
          "the complete delivered video decodes every executed frame", video_facts)
    audio, audio_issues = inspect_output_audio(encoded, videos[0].render_spec or {})
    check(not audio_issues, "the actual delivered audio satisfies the confirmed render input",
          [issue.model_dump(mode="json") for issue in audio_issues])
    print("  Media decode " + json.dumps({
        "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(),
        "video": video_facts, "audio": audio.model_dump(mode="json"),
    }, ensure_ascii=False), flush=True)
    delivered = await wait_trigger_review(ctx, first["conversation_id"], run_id, timeout=120.0)
    check(delivered and (delivered.get("intent") or {}).get("output_refs") == [str(videos[0].id)],
          "delivery returns the exact Output to the original Chat", delivered)
    _p1_report_tokens("promo_auto_delivery", run_id)
    check(len(await composition_versions_of(pid)) == 1, "production does not redesign", pid)
    print(f"  Delivered Output {videos[0].id}, message {delivered['id']}", flush=True)

    repeated = await ctx.chat(pid, "Yes")
    _p1_report_tokens("promo_repeated_yes", repeated)
    repeated_speech = ((repeated.get("assistant_message") or {}).get("content") or "").casefold()
    check(any(marker in repeated_speech for marker in ("completed", "ready", "完成", "已就绪"))
          and not any(marker in repeated_speech for marker in ("underway", "while it renders", "仍在渲染", "正在制作")),
          "repeating confirmation reports the actual completed delivery", repeated_speech)
    check(await count_runs(pid) == 1 and len(await outputs_of(pid, "video")) == 1
          and len(await composition_versions_of(pid)) == 1,
          "repeating Yes neither starts another Run nor changes the delivered version", repeated)
    history = await ctx.messages(first["conversation_id"])
    deliveries = [
        message for message in history
        if (message.get("intent") or {}).get("trigger") == "run_completed"
        and (message.get("intent") or {}).get("ref") == run_id
        and (message.get("intent") or {}).get("output_refs") == [str(videos[0].id)]
    ]
    check(len(deliveries) == 1 and deliveries[0]["id"] == delivered["id"],
          "repeating confirmation does not duplicate the automatic delivery", [item["id"] for item in deliveries])


JOURNEYS = {
    "lost_user": lost_user_full_journey,
    "material_to_clips": material_to_clips_full_chain,
    "guided_exploration": material_suggestion_exploration,
    "writing_without_material": no_material_writers,
    "research_to_writing": research_grounds_writer,
    "consultation": consult_never_deadends,
    "revision_and_undo": second_circle_revision,
    "interview_to_framing": interview_to_framing,
    "credits_boundary": credits_boundary,
    "remix": remix_flagship,
    "temporal_revision": temporal_revision_without_production,
    "speech_edit_refusal": speech_capability_refusal_closes_honestly,
    "builtin_promo_skill": promo_skill_storyboard_revision_and_delivery,
    "promo_p1_first_draft": promo_p1_first_draft,
    "promo_p1_continuation": promo_p1_continuation,
    "promo_p1_revision": promo_p1_revision,
    "promo_p1_overlay": promo_p1_overlay,
    "sequential_oxvalue_draft_review": sequential_oxvalue_draft_review,
    "external_skill": external_skill_fixed_image_and_adversarial_packages,
    "dynamic_skill_shotcraft": dynamic_skill_shotcraft,
    "dynamic_skill_talkcraft": dynamic_skill_talkcraft,
    "promo_generic_cutover_probe": promo_generic_cutover_probe,
    "promo_short_confirmation_delivery": promo_short_confirmation_delivery,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated journey names (e.g. lost_user,consultation)")
    parser.add_argument("--keep", action="store_true", help="keep journey projects")
    args = parser.parse_args()

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    selected = [(k, fn) for k, fn in JOURNEYS.items() if only is None or k in only]
    if not selected:
        print(f"No journeys matched --only {args.only!r} (have: {', '.join(JOURNEYS)})")
        return 2

    print(f"API: {BASE} — {len(selected)} journey(s)\n")
    user_id = await make_user()
    ctx = Ctx(user_id, keep=args.keep)

    failures: dict[str, str] = {}
    blocked: dict[str, str] = {}
    try:
        for name, fn in selected:
            print(f"▶ {name} {fn.__doc__.strip() if fn.__doc__ else ''}")
            try:
                await fn(ctx)
            except JourneyFailure as exc:
                failures[name] = str(exc)
                print(f"  ✘ FAIL {exc}\n")
            except (ExternalServiceBlocked, httpx.HTTPError) as exc:
                blocked[name] = f"{type(exc).__name__}: {exc}"
                print(f"  ⊘ BLOCKED {type(exc).__name__}: {exc}\n")
            except Exception as exc:
                if type(exc).__module__.startswith(("botocore", "boto3")):
                    blocked[name] = f"{type(exc).__name__}: {exc}"
                    print(f"  ⊘ BLOCKED {type(exc).__name__}: {exc}\n")
                else:
                    failures[name] = f"{type(exc).__name__}: {exc}"
                    print(f"  ✘ ERROR {type(exc).__name__}: {exc}\n")
            else:
                print("  ✓ PASS\n")
            await ctx.cleanup()
    finally:
        await ctx.close()

    print("=" * 60)
    if failures or blocked:
        print(f"{len(selected) - len(failures) - len(blocked)}/{len(selected)} passed.")
        for name, why in failures.items():
            print(f"  FAIL {name}: {why}")
        for name, why in blocked.items():
            print(f"  BLOCKED {name}: {why}")
        return 1
    print(f"All {len(selected)} journey(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

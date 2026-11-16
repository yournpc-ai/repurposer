"""Real Chat journeys for saved Composition authoring and delivery."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import av
import io
from app.models.schemas import AssetStatus

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


def is_plan_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


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
    Message,
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
        for pid in self.project_ids:
            await self.client.delete(f"/projects/{pid}")
        self.project_ids.clear()


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


REMIX_SOURCE_KEY = "demo/uploads/demo_talk.mp4"


REMIX_EXEMPLAR_KEY = "demo/outputs/highlight-clips-preview-ec8e575b.mp4"


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
    _, intro_version = await _p1_revise(
        ctx, pid, "把开场副标题改成「从真实证据开始」，只保存修订，不制作。", "set_intro_text", 2,
    )
    intro_change = compute_change_set(content_of(initial), content_of(intro_version))
    check(not intro_change["clips"]["added"] and not intro_change["clips"]["removed"]
          and all(change["changes"] == ["object"] for change in intro_change["clips"]["updated"]),
          "duration changes only ranges and no clip identities", intro_change)
    _, text_version = await _p1_revise(
        ctx, pid, "把开场标题换成「让每一份价值都有据可查」，只保存修订，不制作。", "set_text", 3,
    )
    text_change = compute_change_set(content_of(intro_version), content_of(text_version))
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



async def uploaded_video_editing(ctx: Ctx) -> None:
    """Real HTTP upload → ASR selection → fixed portrait captions/dub → one delivery."""
    from app.editing.schemas import AudioObject, SourceCaptionDerivation, VideoObject
    from app.editing.store import content_of
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.tables import NarrationAlignment, SourceSnapshot
    from app.providers import storage
    from app.tools.video.output_checks import inspect_output_audio

    await ctx.set_confirmation(execution="auto", credits="auto")
    await topup_wallet(ctx.user_id)
    pid = await ctx.new_project("P9 uploaded video editing")
    uploaded = Path("test/fixtures/video_project/media/pricing-talk-source.mp4").read_bytes()
    response = await ctx.client.post(
        f"/projects/{pid}/assets/upload",
        data={"type": "video"},
        files={"file": ("demo_talk.mp4", uploaded, "video/mp4")},
    )
    check(response.status_code == 201, "ordinary HTTP video upload", response.text)
    asset_id = response.json()["id"]
    analysis = await ctx.chat(
        pid,
        "Please transcribe and analyze this uploaded video so I can edit it.",
        mentions=[{"type": "asset", "id": asset_id, "label": "Uploaded talk"}],
    )
    check(analysis.get("run_id") is None, "material understanding starts no production Run", analysis)
    status = await wait_asset_status(asset_id, {AssetStatus.COMPLETED, AssetStatus.FAILED})
    check(status == AssetStatus.COMPLETED, "worker completes real ASR", status)
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, uuid.UUID(asset_id))
        words = (asset.meta or {}).get("words") or []
    check(bool(words), "the uploaded source exposes a real word axis", len(words))
    print(f"  Uploaded asset {asset_id}: {len(words)} ASR words", flush=True)

    first = await ctx.chat(
        pid,
        "Please select the middle passage about pricing from this uploaded long video, "
        "and keep the sentence before it. Make one 9:16 video with a fixed centered "
        "cover crop. Add native captions from the source ASR on an ordinary caption track. "
        "Lower the original sound but keep it audible. Save and present the editable "
        "storyboard only; do not produce yet.",
        mentions=[{"type": "asset", "id": asset_id, "label": "Uploaded talk"}],
    )
    read, _ = await ctx.acknowledge_video_presentation(first)
    versions = await composition_versions_of(pid)
    check(len(versions) == 1 and first.get("run_id") is None,
          "the semantic selection saves one draft without production", first)
    content = content_of(versions[0])
    source = next(
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(clip.object, VideoObject) and track.role == "main"
    )
    check(source.source is not None and source.source.source_range is not None
          and source.source.source_range.start > 0
          and source.source.source_range.end < 119 * SOURCE_TIMEBASE,
          "the selected source window is inside the long source, not its whole duration",
          source.source)
    check((content.settings.width, content.settings.height) == (1080, 1920)
          and source.object.fit == "cover" and source.object.gain_db < 0,
          "fixed portrait cover and reduced original sound are saved", source.object)
    source_captions = [
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(getattr(clip.object, "caption", None), SourceCaptionDerivation)
        and clip.object.caption.alignment == "faster-whisper-source-v1"
    ]
    check(bool(source_captions), "native ASR TextObjects are saved", len(source_captions))
    check("pricing" in " ".join(clip.object.text for clip in source_captions).lower(),
          "the semantic selection contains the actual pricing passage",
          [clip.object.text for clip in source_captions])
    print(f"  Initial source window {source.source.source_range}", flush=True)

    second = await ctx.chat(
        pid,
        "Prepare a new English narration with voice presenter_male: "
        "'Our annual plan includes hands-on support for your team.' "
        "Freeze the audio and obtain its real sentence/word alignment for review. "
        "Do not change the Composition or produce a video yet.",
    )
    narration_run_id = second.get("run_id")
    if narration_run_id is None and is_plan_dock(second.get("assistant_message") or {}):
        answer = await ctx.answer(second["assistant_message"]["id"], {"kind": "start"})
        check(answer.status_code == 200, "authorize narration preparation", answer.text)
        narration_run_id = answer.json()["answered_question"].get("workflow_run_id")
    check(narration_run_id is not None, "ordinary authorization starts narration preparation", second)
    check(await wait_run_terminal(narration_run_id) == WorkflowStatus.COMPLETED,
          "narration preparation Run completes", second)
    versions = await composition_versions_of(pid)
    check(len(versions) == 1, "narration preparation alone does not change the work", second)
    async with AsyncSessionLocal() as db:
        alignment = (await db.scalars(
            select(NarrationAlignment)
            .where(NarrationAlignment.owner_id == ctx.user_id)
            .order_by(NarrationAlignment.created_at.desc()).limit(1)
        )).first()
    check(alignment is not None, "the authorized narration has an alignment row", second)
    check(alignment.status in {"PENDING", "PROCESSING", "ALIGNED", "READY"},
          "the narration alignment settles without a failure", alignment.status)

    placement = await ctx.chat(
        pid,
        "Use that prepared narration in this same edit with its aligned native captions. "
        "Complete the semantic annotation to READY if needed. Preserve every source clip "
        "and the original sound, save the revised storyboard only, and do not synthesize "
        "another narration or produce a video.",
    )
    check(placement.get("run_id") is None,
          "placing the already-prepared narration starts no additional Run", placement)
    versions = await composition_versions_of(pid)
    check(len(versions) >= 2, "READY narration and aligned captions create a new saved version", placement)
    content = content_of(versions[-1])
    dialogue = next(
        (clip for track in content.timeline.tracks for clip in track.clips
         if isinstance(clip.object, AudioObject)),
        None,
    )
    check(dialogue is not None and dialogue.source is not None,
          "the prepared frozen narration is an ordinary AudioObject", dialogue)
    narration_captions = [
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(getattr(clip.object, "caption", None), SourceCaptionDerivation)
        and clip.object.caption.narration_alignment_id is not None
    ]
    check(bool(narration_captions), "READY narration alignment supplies native captions", placement)
    async with AsyncSessionLocal() as db:
        alignment = await db.get(NarrationAlignment, alignment.id)
    check(alignment.status == "READY" and alignment.content_digest,
          "semantic annotation completes the existing alignment to READY", alignment.id)
    print(f"  Dialogue snapshot {dialogue.source.snapshot_id}", flush=True)

    revised = await ctx.chat(
        pid,
        "Change only the first source-ASR caption to 'Pricing made simple.' "
        "Preserve the selected source passage, all other content and the original sound. "
        "Save this version; do not produce.",
    )
    await ctx.acknowledge_video_presentation(revised)
    versions = await composition_versions_of(pid)
    content = content_of(versions[-1])
    source = next(
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(clip.object, VideoObject) and track.role == "main"
    )
    check(source.source.source_range.start > 0
          and source.range.duration == source.source.source_range.duration,
          "the selected source and output windows stay synchronized at 1x", source)
    edited = next(
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(getattr(clip.object, "caption", None), SourceCaptionDerivation)
        and clip.object.caption.alignment == "faster-whisper-source-v1"
    )
    check(edited.object.text == "Pricing made simple."
          and edited.object.caption.state == "independent",
          "the hand-edited ASR caption is independent and preserved", edited.object)
    dialogue = next(
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(clip.object, AudioObject)
    )
    check(dialogue.range.duration > 0
          and dialogue.range.duration == dialogue.source.source_range.duration,
          "the ordinary narration Clip retains its real playable duration", dialogue)

    approved = await ctx.chat(pid, "OK, produce this exact saved version.")
    run_id = approved.get("run_id") or (approved.get("assistant_message") or {}).get("workflow_run_id")
    if run_id is None:
        async with AsyncSessionLocal() as db:
            existing = await db.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.project_id == uuid.UUID(pid),
                    WorkflowRun.context["version_ref"]["composition_version_id"].as_string() == str(versions[-1].id),
                )
                .order_by(WorkflowRun.created_at.desc()).limit(1)
            )
        run_id = str(existing.id) if existing is not None else None
    if run_id is None and is_plan_dock(approved.get("assistant_message") or {}):
        answer = await ctx.answer(approved["assistant_message"]["id"], {"kind": "start"})
        check(answer.status_code == 200, "start the pinned production", answer.text)
        run_id = answer.json()["answered_question"].get("workflow_run_id")
    check(run_id is not None, "ordinary confirmation starts one production Run", approved)
    check(await wait_run_terminal(run_id) == WorkflowStatus.COMPLETED,
          "the saved version produces successfully", run_id)
    videos = await outputs_of(pid, "video")
    check(len(videos) == 1 and videos[0].render_status == RenderStatus.COMPLETED,
          "one completed video Output", [str(item.id) for item in videos])
    output = videos[0]
    check(output.composition_version_id == versions[-1].id,
          "the Output pins the exact saved version", output.composition_version_id)
    run = await run_row(run_id)
    check(run["context"].get("version_ref", {}).get("composition_version_id") == str(versions[-1].id),
          "the Run pins the same version", run["context"].get("version_ref"))

    delivered = await wait_trigger_review(ctx, approved["conversation_id"], run_id, timeout=120.0)
    check(delivered is not None and (delivered.get("intent") or {}).get("output_refs") == [str(output.id)],
          "the completed Run returns its one video to the original Chat", delivered)

    repeated = await ctx.chat(pid, "OK")
    check(await count_runs(pid) >= 2 and len(await outputs_of(pid, "video")) == 1,
          "repeated confirmation adds no second video Output", repeated)
    deliveries = [
        message for message in await ctx.messages(repeated["conversation_id"])
        if (message.get("intent") or {}).get("output_refs")
    ]
    check(deliveries and all(
        (message.get("intent") or {}).get("output_refs") == [str(output.id)]
        for message in deliveries
    ), "every delivery message owns the exact video reference", deliveries)

    encoded = await storage.read(output.files["video"])
    with av.open(io.BytesIO(encoded), mode="r") as container:
        decoded_frames = sum(1 for _ in container.decode(video=0))
        width, height = container.streams.video[0].codec_context.width, container.streams.video[0].codec_context.height
    check(decoded_frames == int((output.render_spec or {}).get("duration_frames") or 0),
          "the complete delivered video decodes every frame", decoded_frames)
    check((width, height) == (1080, 1920), "the delivered pixels are 9:16", (width, height))
    audio, audio_issues = inspect_output_audio(encoded, output.render_spec or {})
    check(not audio_issues and audio.present and audio.decode_ok,
          "the delivered original/narration mix decodes successfully", audio_issues)
    print(f"  Delivered {output.id}: {decoded_frames} frames, {audio.rms_dbfs} dBFS RMS", flush=True)




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


JOURNEYS = {
    "dynamic_skill_shotcraft": dynamic_skill_shotcraft,
    "dynamic_skill_talkcraft": dynamic_skill_talkcraft,
    "external_skill_fixed_image_and_adversarial_packages": external_skill_fixed_image_and_adversarial_packages,
    "promo_generic_cutover_probe": promo_generic_cutover_probe,
    "promo_p1_continuation": promo_p1_continuation,
    "promo_p1_first_draft": promo_p1_first_draft,
    "promo_p1_overlay": promo_p1_overlay,
    "promo_p1_revision": promo_p1_revision,
    "promo_short_confirmation_delivery": promo_short_confirmation_delivery,
    "promo_skill_storyboard_revision_and_delivery": promo_skill_storyboard_revision_and_delivery,
    "sequential_oxvalue_draft_review": sequential_oxvalue_draft_review,
    "uploaded_video_editing": uploaded_video_editing,
}


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

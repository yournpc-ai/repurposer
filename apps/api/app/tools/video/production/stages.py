"""Replayable produce_video stages on the existing WorkflowStep JSONB face."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog

from app.models.schemas import ProductionStage
from app.models.tables import WorkflowStep
from app.pipeline import step_display

logger = structlog.get_logger()

StageFacts = dict[str, bool | int]


def render_stage_kind(*, upload_only: bool) -> str:
    """Upload-only recovery reuses rendered bytes; it is never a new render."""
    return "upload" if upload_only else "render"


def production_stage_record(
    *,
    kind: str,
    run_id: UUID,
    step_id: UUID,
    attempt: int,
    status: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    facts: StageFacts | None = None,
) -> dict[str, Any]:
    """Build only the safe stage facts; seq is assigned by the persistent fold."""
    values = facts or {}
    return ProductionStage(
        event_id=f"{step_id}:{attempt}:{kind}",
        kind=kind,
        run_id=run_id,
        step_id=step_id,
        attempt=attempt,
        seq=0,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        reused=values.get("reused") if isinstance(values.get("reused"), bool) else None,
        item_count=values.get("item_count") if isinstance(values.get("item_count"), int) else None,
        reused_count=(
            values.get("reused_count") if isinstance(values.get("reused_count"), int) else None
        ),
    ).model_dump(mode="json")


def apply_production_stage(
    spec: dict[str, Any],
    stage: dict[str, Any],
    *,
    current_attempt: int,
) -> dict[str, Any]:
    """Append or settle one stage without letting an old attempt write new state.

    Starting an existing stage is idempotent; its first terminal write wins.
    Records from other attempts stay persisted for replay, while the writer's
    attempt fence prevents a stale executor from modifying them after re-claim.
    """
    incoming = ProductionStage.model_validate(stage)
    if incoming.attempt != current_attempt:
        return spec
    if incoming.event_id != f"{incoming.step_id}:{incoming.attempt}:{incoming.kind}":
        return spec

    raw_records = spec.get("production_stages")
    records = list(raw_records) if isinstance(raw_records, list) else []
    next_seq = 0
    for raw in records:
        if isinstance(raw, dict) and isinstance(raw.get("seq"), int):
            next_seq = max(next_seq, raw["seq"] + 1)

    for index, raw in enumerate(records):
        if not isinstance(raw, dict) or raw.get("event_id") != incoming.event_id:
            continue
        try:
            existing = ProductionStage.model_validate(raw)
        except Exception:  # noqa: BLE001 — never replace an unreadable durable fact
            return spec
        if existing.attempt != incoming.attempt or existing.status != "running":
            return spec
        if incoming.status == "running":
            return spec
        settled = incoming.model_dump(mode="json")
        settled["seq"] = existing.seq
        settled["started_at"] = existing.started_at
        records[index] = ProductionStage.model_validate(settled).model_dump(mode="json")
        return {**spec, "production_stages": records}

    appended = incoming.model_dump(mode="json")
    appended["seq"] = next_seq
    records.append(appended)
    return {**spec, "production_stages": records}


class ProductionStages:
    """Short-transaction stage writer fenced to one claimed step execution."""

    def __init__(
        self,
        *,
        run_id: UUID,
        step_id: UUID,
        attempt: int,
        claim_token: UUID | None,
    ) -> None:
        self.run_id = run_id
        self.step_id = step_id
        self.attempt = attempt
        self.claim_token = claim_token

    async def _write(self, stage: dict[str, Any]) -> None:
        try:
            async with step_display.AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, self.step_id, with_for_update=True)
                if (
                    node is None
                    or node.run_id != self.run_id
                    or node.claim_token != self.claim_token
                ):
                    return
                next_spec = apply_production_stage(
                    node.spec or {}, stage, current_attempt=node.attempt
                )
                if next_spec == (node.spec or {}):
                    return
                node.spec = next_spec
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — display cannot change production semantics
            logger.warning(
                "production_stage_write_failed",
                run_id=str(self.run_id),
                step_id=str(self.step_id),
                attempt=self.attempt,
                kind=stage.get("kind"),
                error=str(exc),
            )

    async def start(self, kind: str) -> datetime:
        """Record a real claimed-work start; replayed starts are idempotent."""
        started_at = datetime.now(UTC)
        await self._write(production_stage_record(
            kind=kind,
            run_id=self.run_id,
            step_id=self.step_id,
            attempt=self.attempt,
            status="running",
            started_at=started_at,
        ))
        return started_at

    async def settle(
        self,
        kind: str,
        status: Literal["completed", "failed"],
        *,
        started_at: datetime | None = None,
        facts: StageFacts | None = None,
    ) -> None:
        """Settle only an observed result boundary, never a guessed run state."""
        await self._write(production_stage_record(
            kind=kind,
            run_id=self.run_id,
            step_id=self.step_id,
            attempt=self.attempt,
            status=status,
            started_at=started_at or datetime.now(UTC),
            finished_at=datetime.now(UTC),
            facts=facts,
        ))

    @asynccontextmanager
    async def stage(self, kind: str) -> AsyncGenerator[StageFacts, None]:
        facts: StageFacts = {}
        started_at = await self.start(kind)
        try:
            yield facts
        except Exception:
            await self.settle(kind, "failed", started_at=started_at, facts=facts)
            raise
        await self.settle(kind, "completed", started_at=started_at, facts=facts)

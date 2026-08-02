"""Operation application service — the single write path for render_spec (ADR-032 D7).

Every mutation of an output's render_spec goes through here: registry-validated
op application + baseline lazy-creation + drift self-healing + hash chain, in
one transaction per batch. undo/redo never delete rows — ``undone_at`` only.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import canonical_json_hash
from app.models.tables import Operation, Output
from app.operations.registry import OP_REGISTRY, SOURCE_REGISTRY, validate_op

logger = logging.getLogger(__name__)


class OpConflict(Exception):
    """base_hash mismatch — the caller's spec base is stale (409)."""


class OpRejected(Exception):
    """Unknown op / system-internal op from a client / bad params (400)."""


def spec_hash(spec: dict) -> str:
    """Chain-integrity hash (ADR-032) — shared canonical implementation."""
    return canonical_json_hash(spec)


async def _lock_output(db: AsyncSession, output_id: UUID) -> Output:
    row = (
        await db.execute(
            select(Output).where(Output.id == output_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    return row


async def _ops_for_output(db: AsyncSession, output_id: UUID) -> list[Operation]:
    return list(
        (
            await db.execute(
                select(Operation)
                .where(Operation.output_id == output_id)
                .order_by(Operation.seq.asc())
            )
        ).scalars()
    )


def _active_head(ops: list[Operation]) -> Operation | None:
    active = [o for o in ops if o.undone_at is None]
    return active[-1] if active else None


def _insert_row(
    db: AsyncSession,
    output: Output,
    seq: int,
    op: str,
    params: dict,
    spec_after: dict,
    source: str,
    user_id: UUID | None,
    message_id: UUID | None,
) -> Operation:
    row = Operation(
        output_id=output.id,
        project_id=output.project_id,
        seq=seq,
        op=op,
        params=params,
        spec_after=spec_after,
        spec_hash=spec_hash(spec_after),
        source=source,
        user_id=user_id,
        message_id=message_id,
    )
    db.add(row)
    return row


async def _ensure_chain(
    db: AsyncSession,
    output: Output,
    ops: list[Operation],
    source: str,
    user_id: UUID | None,
) -> int:
    """Guarantee the journal reflects the live spec: lazily create the
    baseline (seq=0), and self-heal drift (a writer bypassed the service) with
    a system ``set_spec`` row. Returns the next seq to use.

    The journal is append-only: new rows always go above the MAX seq of ALL
    rows (active or undone — undone rows keep their seqs, so the active head's
    seq is NOT the high-water mark).
    """
    if output.render_spec is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Output has no render_spec (nothing to operate on)",
        )
    if not ops:
        _insert_row(
            db, output, 0, "snapshot", {}, output.render_spec, "system", None, None
        )
        return 1

    high_water = ops[-1].seq  # ops are seq-ordered; includes undone rows
    head = _active_head(ops)
    live_hash = spec_hash(output.render_spec)
    if head is not None and head.spec_hash != live_hash:
        logger.warning(
            "operations drift on output %s: live spec != head op %s — journaling set_spec",
            output.id,
            head.id,
        )
        _insert_row(
            db,
            output,
            high_water + 1,
            "set_spec",
            {"render_spec": output.render_spec, "drift": True},
            output.render_spec,
            "system",
            None,
            None,
        )
        return high_water + 2
    return high_water + 1


async def apply_operations(
    db: AsyncSession,
    output_id: UUID,
    ops: list[dict],
    *,
    source: str,
    user_id: UUID | None = None,
    message_id: UUID | None = None,
    base_hash: str | None = None,
) -> tuple[Output, list[Operation]]:
    """Apply a batch of client ops atomically. Returns (output, new op rows)."""
    if source not in SOURCE_REGISTRY:
        raise OpRejected(f"unknown source '{source}'")
    if not ops:
        raise OpRejected("empty op batch")

    output = await _lock_output(db, output_id)
    if output.type != "clip":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Operations target clip outputs only (v1)"
        )

    # Validate everything before touching state (batch is atomic).
    normalized: list[tuple[str, dict]] = []
    for item in ops:
        op_name = item.get("op", "")
        try:
            params = validate_op(op_name, item.get("params") or {}, client=True)
        except (KeyError, ValueError) as e:
            raise OpRejected(str(e)) from e
        # Precomputed ops (translate_captions / set_dub / remove_filler) have
        # no pure apply — they must arrive via their journal-calling owners
        # (editor endpoints / run runners), never the generic batch path.
        if OP_REGISTRY[op_name].precomputed:
            raise OpRejected(f"op '{op_name}' is precomputed — use its dedicated endpoint")
        normalized.append((op_name, params))

    existing = await _ops_for_output(db, output_id)
    next_seq = await _ensure_chain(db, output, existing, source, user_id)

    if base_hash is not None and base_hash != spec_hash(output.render_spec):
        raise OpConflict(
            "clip was modified elsewhere — refetch before applying"
        )

    spec = output.render_spec
    rows: list[Operation] = []
    for op_name, params in normalized:
        opdef = OP_REGISTRY[op_name]
        if op_name == "restore_version":
            target = next(
                (o for o in existing + rows if str(o.id) == params["operation_id"]),
                None,
            )
            if target is None:
                raise OpRejected(
                    f"restore_version target {params['operation_id']} not found on this output"
                )
            spec = target.spec_after
        else:
            assert opdef.apply is not None  # precomputed ops don't come through here
            spec = opdef.apply(spec, params)
        rows.append(
            _insert_row(
                db, output, next_seq, op_name, params, spec, source, user_id, message_id
            )
        )
        next_seq += 1

    output.render_spec = spec
    output.updated_at = datetime.now(UTC)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    await db.refresh(output)
    return output, rows


async def apply_precomputed(
    db: AsyncSession,
    output: Output,
    op: str,
    params: dict,
    new_spec: dict,
    *,
    source: str,
    user_id: UUID | None = None,
) -> Operation:
    """Journal an LLM-backed op whose endpoint already computed the new spec
    (translate_captions / set_dub). The endpoint commits; this flushes."""
    try:
        normalized = validate_op(op, params, client=True)
    except (KeyError, ValueError) as e:
        raise OpRejected(str(e)) from e
    if not OP_REGISTRY[op].precomputed:
        raise OpRejected(f"op '{op}' is not precomputed")

    locked = await _lock_output(db, output.id)
    existing = await _ops_for_output(db, output.id)
    next_seq = await _ensure_chain(db, locked, existing, source, user_id)

    row = _insert_row(
        db, locked, next_seq, op, normalized, new_spec, source, user_id, None
    )
    locked.render_spec = new_spec
    locked.updated_at = datetime.now(UTC)
    await db.flush()
    return row


async def undo(db: AsyncSession, output_id: UUID) -> Output:
    """Undo the newest active op (baseline excluded); restore the previous
    active snapshot. Append-only: marks ``undone_at``, never deletes."""
    output = await _lock_output(db, output_id)
    ops = await _ops_for_output(db, output_id)
    active = [o for o in ops if o.undone_at is None and o.seq > 0]
    if not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to undo")

    head = active[-1]
    head.undone_at = datetime.now(UTC)
    prev = _active_head([o for o in ops if o.id != head.id])
    # prev is the baseline at worst — its spec_after is always valid.
    output.render_spec = prev.spec_after
    output.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(output)
    return output


async def redo(db: AsyncSession, output_id: UUID) -> Output:
    """Redo the undone op directly above the active head, if any."""
    output = await _lock_output(db, output_id)
    ops = await _ops_for_output(db, output_id)
    head = _active_head(ops)
    head_seq = head.seq if head is not None else -1
    candidates = [o for o in ops if o.undone_at is not None and o.seq > head_seq]
    if not candidates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to redo")

    target = candidates[0]
    target.undone_at = None
    output.render_spec = target.spec_after
    output.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(output)
    return output


async def list_operations(db: AsyncSession, output_id: UUID) -> list[Operation]:
    return await _ops_for_output(db, output_id)

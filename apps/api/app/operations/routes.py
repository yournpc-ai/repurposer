"""Operations API — the three frontends' shared edit surface (ADR-032).

Mounted under /api/v1/outputs alongside the outputs router: an output's
operations sub-resource. Batch apply is the editor Save model's natural form;
undo/redo are journal state transitions (append-only).
"""

from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DBDep, get_current_user_required
from app.models.tables import Output, Project, User
from app.operations import service
from app.operations.service import OpConflict, OpRejected

router = APIRouter()


class OperationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str
    params: dict = Field(default_factory=dict)


class OperationApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ops: list[OperationItem] = Field(min_length=1)
    base_hash: str | None = None


class OperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    output_id: UUID
    seq: int
    op: str
    params: dict
    spec_hash: str
    source: str
    message_id: UUID | None = None
    undone_at: datetime | None = None
    created_at: datetime


async def _get_output_for_user(
    db: AsyncSession,
    output_id: UUID,
    user_id: UUID,
) -> Output:
    output = await db.get(Output, output_id)
    if output is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    project = await db.get(Project, output.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.user_id == user_id:
        return output
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def _output_json(output: Output) -> dict:
    from app.models.schemas import OutputResponse

    return OutputResponse.model_validate(output).model_dump(mode="json")


def _op_json(row) -> dict:
    return OperationResponse.model_validate(row).model_dump(mode="json")


@router.get("/{output_id}/operations", response_model=list[OperationResponse])
async def list_output_operations(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    """Operation history for an output (editor timeline / future calibration)."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    rows = await service.list_operations(db, output.id)
    return rows


@router.post("/{output_id}/operations", status_code=status.HTTP_201_CREATED)
async def apply_output_operations(
    output_id: UUID,
    data: OperationApplyRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    """Apply a batch of ops atomically (editor Save / chat edit)."""
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    try:
        output, rows = await service.apply_operations(
            db,
            output.id,
            [item.model_dump(mode="json") for item in data.ops],
            source="editor",
            user_id=UUID(str(current_user.id)),
            base_hash=data.base_hash,
        )
    except OpConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except OpRejected as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return {
        "output": _output_json(output),
        "operations": [_op_json(r) for r in rows],
    }


@router.post("/{output_id}/operations/undo")
async def undo_output_operation(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    output = await service.undo(db, output.id)
    return {"output": _output_json(output)}


@router.post("/{output_id}/operations/redo")
async def redo_output_operation(
    output_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
):
    output = await _get_output_for_user(db, output_id, UUID(str(current_user.id)))
    output = await service.redo(db, output.id)
    return {"output": _output_json(output)}

"""Derivative router for direct editing and regeneration."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import (
    ChatRequest,
    DerivativeResponse,
    DerivativeUpdate,
    ToneSettings,
    validate_derivative_content,
)
from app.models.tables import Derivative, Project, User
from app.services.chat import chat

router = APIRouter()


async def _get_derivative_for_user(
    db: AsyncSession,
    derivative_id: UUID,
    user_id: UUID,
) -> Derivative:
    """Fetch a derivative and ensure it belongs to the given user."""
    derivative = await db.get(Derivative, derivative_id)
    if derivative is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Derivative not found",
        )
    project = await db.get(Project, derivative.project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return derivative


class DerivativeRegenerateRequest(BaseModel):
    """Request to regenerate a derivative with an optional instruction."""

    instruction: str | None = Field(
        default=None,
        description="Steering prompt for the regeneration.",
    )
    target_language: str = Field(
        default="en",
        description="Target language code, e.g. en/zh/fr/de/es/it",
    )
    tone_settings: ToneSettings | None = None


@router.put("/{derivative_id}", response_model=DerivativeResponse)
async def update_derivative(
    derivative_id: UUID,
    data: DerivativeUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Derivative:
    """Directly edit a derivative's content or status."""
    derivative = await _get_derivative_for_user(
        db, derivative_id, UUID(str(current_user.id))
    )

    update_data = data.model_dump(exclude_unset=True)
    if "content" in update_data:
        update_data["content"] = validate_derivative_content(
            derivative.type, update_data["content"]
        )

    for field, value in update_data.items():
        if value is not None:
            setattr(derivative, field, value)

    derivative.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(derivative)
    return derivative


@router.post("/{derivative_id}/regenerate", response_model=dict)
async def regenerate_derivative(
    derivative_id: UUID,
    data: DerivativeRegenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> dict:
    """Queue regeneration of a single derivative through the generic chat layer."""
    derivative = await _get_derivative_for_user(
        db, derivative_id, UUID(str(current_user.id))
    )

    project = await db.get(Project, derivative.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    result = await chat(
        db,
        UUID(str(current_user.id)),
        ChatRequest(
            project_id=UUID(str(project.id)),
            asset_id=derivative_id,
            asset_type="derivative",
            message=data.instruction or "Regenerate this derivative",
        ),
    )

    return {
        "job_id": str(result.job_id) if result.job_id else None,
        "message_id": str(result.assistant_message.id),
        "session_id": str(result.session_id),
    }

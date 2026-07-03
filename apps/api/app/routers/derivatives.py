"""Derivative router for direct editing and regeneration."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    DerivativeResponse,
    DerivativeUpdate,
    ToneSettings,
)
from app.models.tables import Derivative, Project, User
from app.services.derivative_generation import generate_derivative
from app.services.project_context import collect_materials, resolve_speaker_and_persona

router = APIRouter()


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
) -> Derivative:
    """Directly edit a derivative's content or status."""
    derivative = await db.get(Derivative, derivative_id)
    if not derivative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Derivative not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(derivative, field, value)

    derivative.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(derivative)
    return derivative


@router.post("/{derivative_id}/regenerate", response_model=DerivativeResponse)
async def regenerate_derivative(
    derivative_id: UUID,
    data: DerivativeRegenerateRequest,
    db: DBDep,
    current_user: User = Depends(get_current_user),
) -> Derivative:
    """Regenerate a single derivative with an optional instruction."""
    derivative = await db.get(Derivative, derivative_id)
    if not derivative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Derivative not found",
        )

    project = await db.get(Project, derivative.project_id)
    if project is None or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    materials = await collect_materials(db, project.id)
    speaker, persona = await resolve_speaker_and_persona(db, project)
    instruction = data.instruction
    target_language = data.target_language or derivative.language or "en"

    try:
        derivative.content = await generate_derivative(
            project=project,
            derivative_type=derivative.type,
            materials=materials,
            target_language=target_language,
            instruction=instruction,
            speaker=speaker,
            persona=persona,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    derivative.language = target_language
    derivative.status = "generated"
    derivative.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(derivative)
    return derivative

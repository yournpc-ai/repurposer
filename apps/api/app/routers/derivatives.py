"""Derivative router for direct editing and regeneration."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user
from app.models.schemas import (
    ContentPlan,
    DerivativePlan,
    DerivativeResponse,
    DerivativeUpdate,
    GenerationContext,
    ToneSettings,
)
from app.models.tables import BrandTemplate, Derivative, Project, User
from app.services.brand import content_strategy_from_template
from app.services.derivative_dispatch import generate_derivative
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
    tone_settings = data.tone_settings

    # Resolve the user's default brand template for brand strategy context.
    bt = (
        await db.execute(
            select(BrandTemplate)
            .where(BrandTemplate.user_id == project.user_id)
            .order_by(BrandTemplate.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    content_strategy = content_strategy_from_template(bt.config if bt else None)

    context = GenerationContext(
        speaker_name=speaker.name if speaker else None,
        speaker_title=speaker.title if speaker else None,
        event_name=project.event_name,
        persona=persona,
        tone_settings=tone_settings,
        brand_strategy=content_strategy,
        target_language=target_language,
        instruction=instruction,
    )

    # Build a minimal content plan focused on this single derivative.
    content_plan = ContentPlan(
        core_thesis="Regenerate this derivative faithfully to the source material",
        derivatives=[
            DerivativePlan(
                derivative_type=derivative.type,
                focus="Regenerate this derivative faithfully to the source material",
            )
        ],
    )

    try:
        derivative.content = await generate_derivative(
            derivative_type=derivative.type,
            materials=materials,
            context=context,
            content_plan=content_plan,
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

"""Memory module routes: personas."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents import roster
from app.clients.minimax import MiniMaxError
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.dependencies.auth import DEFAULT_USER_ID
from app.models.schemas import (
    EMOTIONAL_TONES,
    AssetType,
    PersonaContext,
    PersonaCreate,
    PersonaUpdate,
)
from app.models.tables import Asset, Persona, User
from app.tools.extraction import extract_text
from app.tools.storage import (
    delete_file,
    delete_persona_files,
)

personas_router = APIRouter()


@personas_router.post("", response_model=PersonaContext, status_code=status.HTTP_201_CREATED)
async def create_persona(
    data: PersonaCreate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Persona:
    """Create a new persona."""
    # Bare creation (the frontend sends {name, title, language}) must not
    # write explicit NULLs into the strict fields: PersonaContext requires
    # the style-six/list fields non-None (present-but-None fails validation —
    # defaults don't cover it), and one NULL row poisons every list/response
    # serialization plus any generation that resolves it as the default.
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    persona = Persona(
        **{
            "core_values": [],
            "favorite_metaphors": [],
            "sentence_style": "",
            "emotional_tone": "rational",
            "typical_hooks": [],
            "avoid_words": [],
            **payload,
        },
        user_id=current_user.id,
    )
    db.add(persona)
    try:
        await db.commit()
        await db.refresh(persona)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Persona creation failed",
        )
    return persona


@personas_router.get("", response_model=list[PersonaContext])
async def list_personas(
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> list[Persona]:
    """List the current user's own personas.

    Default-user (shared) personas are intentionally excluded: project creation
    rejects persona_ids the caller does not own, so listing them would offer
    options that always 404 when selected. Anonymous callers get an empty
    list (generation requires login anyway).
    """
    if current_user is None:
        return []
    result = await db.execute(
        select(Persona)
        .where(Persona.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _get_user_persona(
    persona_id: UUID, user_id: UUID | None, db: DBDep, *, write: bool = False
) -> Persona:
    """Fetch a persona and check access. Legacy default-user (shared)
    personas stay READABLE to any caller; writes are owner-only — a shared
    row must never be mutated, deleted, or regenerated through another
    user's session."""
    query = select(Persona).where(Persona.id == persona_id)
    if user_id is None:
        query = query.where(Persona.user_id == DEFAULT_USER_ID)
    elif write:
        query = query.where(Persona.user_id == user_id)
    else:
        query = query.where(Persona.user_id.in_([user_id, DEFAULT_USER_ID]))
    result = await db.execute(query)
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found",
        )
    return persona


@personas_router.get("/{persona_id}", response_model=PersonaContext)
async def get_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User | None = Depends(get_current_user),
) -> Persona:
    """Get persona by ID."""
    return await _get_user_persona(
        persona_id, current_user.id if current_user else None, db
    )


@personas_router.put("/{persona_id}", response_model=PersonaContext)
async def update_persona(
    persona_id: UUID,
    data: PersonaUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> Persona:
    """Update persona."""
    persona = await _get_user_persona(persona_id, current_user.id, db, write=True)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(persona, field, value)

    await db.commit()
    await db.refresh(persona)
    return persona


@personas_router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> None:
    """Delete persona and all associated source assets."""
    persona = await _get_user_persona(persona_id, current_user.id, db, write=True)

    # Delete associated assets (files + DB rows)
    result = await db.execute(select(Asset).where(Asset.persona_id == persona_id))
    assets = list(result.scalars().all())
    for asset in assets:
        delete_file(asset.file_url)
        await db.delete(asset)

    await db.delete(persona)
    try:
        await db.commit()
    except IntegrityError as e:
        # Mounted on a project (projects.persona_id FK) — say so, don't 500.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Persona is in use by a project — detach it first",
        ) from e

    # Remove persona upload directory after DB commit
    delete_persona_files(persona_id, current_user.id)


@personas_router.post("/{persona_id}/generate", response_model=PersonaContext)
async def generate_persona(
    persona_id: UUID,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> PersonaContext:
    """Generate persona style and content memory from uploaded source assets."""
    persona = await _get_user_persona(persona_id, current_user.id, db, write=True)

    # Find persona's past material assets
    result = await db.execute(
        select(Asset).where(
            Asset.persona_id == persona_id,
            Asset.type == AssetType.PAST_MATERIAL,
        )
    )
    assets = list(result.scalars().all())
    if not assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No past materials uploaded for this persona",
        )

    # Ensure all source assets have extracted text
    asset_texts: list[str] = []
    for asset in assets:
        if not asset.extracted_text and asset.file_url:
            asset.extracted_text = extract_text(asset.file_url)
            asset.processed_at = datetime.now(UTC)
            db.add(asset)
        if asset.extracted_text:
            asset_texts.append(asset.extracted_text)

    if not asset_texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract text from any uploaded source asset",
        )

    await db.commit()

    try:
        memory = await roster.persona.call(
            persona_name=persona.name,
            persona_title=persona.title,
            language=persona.language,
            asset_texts=asset_texts,
        )
    except MiniMaxError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    persona.core_values = memory.core_values or []
    persona.favorite_metaphors = memory.favorite_metaphors or []
    persona.sentence_style = memory.sentence_style or ""
    # LLM extraction is a bare str — out-of-enum values ("calm", "冷静")
    # would poison every PersonaContext serialization off this row.
    persona.emotional_tone = (
        memory.emotional_tone
        if memory.emotional_tone in EMOTIONAL_TONES
        else "rational"
    )
    persona.typical_hooks = memory.typical_hooks or []
    persona.avoid_words = memory.avoid_words or []
    persona.audience = memory.audience
    persona.guidelines = memory.guidelines
    persona.cta = memory.cta
    persona.calibrated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(persona)
    return persona


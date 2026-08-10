"""Writer skills' shared procedure (ADR-039 P1).

One body serves the four copy-writer node kinds (post/quotes/carousel/
article): resolve the node's slot + language, load the director artifacts,
call the package's writer declaration, persist the output row. The
DerivativeType → writer map dies with the outputs-registry derivation (P2);
the blind retry is retired by the harness's one-round repair (P3).
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
    validate_derivative_content,
    validate_output_payload,
)
from app.models.tables import Output, Project, WorkflowStep, WorkflowRun
from app.pipeline.images import _save_quote_card_image
from app.pipeline.step_context import (
    _count_words,
    _generation_context,
    _list_assets,
)
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _set_stage,
    slot_tag,
)
from app.pipeline.edges import _load_director_outputs
from app.platform.project_context import collect_asset_texts, resolve_persona
from app.skills.article.agents import article_writer
from app.skills.carousel.agents import carousel_writer
from app.skills.posts.agents import post_writer
from app.skills.quotes.agents import quotes_writer

logger = structlog.get_logger()

_DERIVATIVE_WRITERS = {
    DerivativeType.POST: post_writer,
    DerivativeType.QUOTES: quotes_writer,
    DerivativeType.CAROUSEL: carousel_writer,
    DerivativeType.ARTICLE: article_writer,
}

_OUTPUT_TO_DERIVATIVE_TYPE: dict[str, DerivativeType] = {
    "post": DerivativeType.POST,
    "quotes": DerivativeType.QUOTES,
    "article": DerivativeType.ARTICLE,
    "carousel": DerivativeType.CAROUSEL,
}

_DERIVATIVE_KIND_TO_TYPE: dict[str, DerivativeType] = {
    "post_gen": DerivativeType.POST,
    "quotes_gen": DerivativeType.QUOTES,
    "carousel_gen": DerivativeType.CAROUSEL,
    "article_gen": DerivativeType.ARTICLE,
}


async def generate_derivative(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
) -> dict:
    """Generate a single derivative by dispatching to the appropriate writer.

    Returns the agent's generated content as a plain dict. Callers are
    responsible for persisting it.
    """
    writer = _DERIVATIVE_WRITERS.get(derivative_type)
    if writer is None:
        raise ValueError(f"Unsupported derivative type: {derivative_type}")

    result = await writer.call(
        asset_texts=asset_texts,
        context=context,
        understanding=understanding,
        storyboard=storyboard,
    )
    return validate_derivative_content(derivative_type, result.model_dump())


async def _generate_derivative_with_retry(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    understanding: MaterialUnderstanding,
    storyboard: Storyboard,
) -> dict:
    """Generate a derivative, retrying once on failure (preserved behavior —
    the blind retry is retired by the harness's one-round repair, P3)."""
    try:
        return await generate_derivative(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "derivative_auto_retry",
            derivative_type=derivative_type.value,
            error=str(e),
        )
        return await generate_derivative(
            derivative_type=derivative_type,
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
        )


async def run_derivative_gen(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Generate one derivative output (post/quotes/carousel/article).

    With ``spec.target_id`` set this is a targeted regeneration: the existing
    row is updated in place (its storyboard now comes from a real upstream
    director_plan node — the fabricated-plan path is gone).
    """
    derivative_type = _DERIVATIVE_KIND_TO_TYPE[node.kind]
    ctx = run.context or {}
    slot = _node_slot(node, ctx, derivative_type.value)
    target_id = node.spec.get("target_id")
    # Language resolves per slot first, then the node's targeted language,
    # then the task-book language.
    target_language = (
        (slot.language if slot else None)
        or node.spec.get("target_language")
        or ctx.get("target_language", "en")
    )

    await _set_stage(node.id, "writing_copy")

    asset_texts = await collect_asset_texts(db, project.id)
    persona = await resolve_persona(db, project)
    generation_context = _generation_context(run, project, persona)
    generation_context.target_language = target_language
    understanding, storyboard = await _load_director_outputs(db, node)

    # Narrow the storyboard to THIS slot: same-type sibling slots (e.g. an
    # English and a German post) are addressed by the slot's ordinal, which
    # compile_graph and director_plan both derive from the canonical order.
    same_type = [s for s in storyboard.slots if s.slot == derivative_type.value]
    if same_type:
        slot_index = int((node.spec or {}).get("slot_index") or 0)
        my_slot = same_type[min(slot_index, len(same_type) - 1)]
        storyboard = storyboard.model_copy(update={"slots": [my_slot]})

    content = await _generate_derivative_with_retry(
        derivative_type=derivative_type,
        asset_texts=asset_texts,
        context=generation_context,
        understanding=understanding,
        storyboard=storyboard,
    )

    if target_id:
        output = await db.get(Output, UUID(str(target_id)))
        if output is None or output.project_id != project.id:
            raise ValueError("Target output not found")
        output.payload = validate_output_payload(output.type, content)
        output.language = target_language
        output.status = "generated"
        output.updated_at = datetime.now(UTC)
        output.workflow_step_id = node.id
        await db.flush()
        await _fill_summary(
            node.id, node.kind, tag=slot_tag(slot), word_count=_count_words(content)
        )
        return [output.id]

    # Idempotency, sibling-safe (per-slot fan-out): same-type outputs produced
    # by THIS run's same-kind nodes are their own slots' products — only prior
    # products (other runs' steps, or step-less rows) are cleared. Two sibling
    # post_gen nodes can therefore never delete each other's output.
    sibling_step_ids = (
        select(WorkflowStep.id)
        .where(WorkflowStep.run_id == run.id, WorkflowStep.kind == node.kind)
        .scalar_subquery()
    )
    await db.execute(
        delete(Output).where(
            Output.project_id == project.id,
            Output.type == derivative_type.value,
            or_(
                Output.workflow_step_id.is_(None),
                Output.workflow_step_id.notin_(sibling_step_ids),
            ),
        )
    )

    output = Output(
        project_id=project.id,
        workflow_step_id=node.id,
        type=derivative_type.value,
        language=target_language,
        provenance="generated",
        payload=validate_output_payload(derivative_type.value, content),
    )
    db.add(output)
    await db.flush()

    # Quote cards get a generated PNG for the first quote.
    if derivative_type == DerivativeType.QUOTES:
        quotes = content.get("quotes", []) if isinstance(content, dict) else []
        if quotes:
            await _set_stage(node.id, "generating_image")
            first_quote = quotes[0]
            image_url = await _save_quote_card_image(
                quote=first_quote.get("quote", ""),
                attribution=first_quote.get("attribution", ""),
                output_id=output.id,
                project=project,
            )
            if image_url:
                output.files = {**(output.files or {}), "image": image_url}
                await db.flush()

    await _fill_summary(
        node.id, node.kind, tag=slot_tag(slot), word_count=_count_words(content)
    )
    return [output.id]

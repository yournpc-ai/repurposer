"""Writer tools' shared node base (ADR-039 P2).

One body serves the four copy-writer nodes (post/quotes/carousel/article):
resolve the node's slot + language, load the director artifacts, call the
package's writer declaration, persist the output row. Each package's
``node.py`` declares a thin subclass (kind / output_type / slot_label /
``writer``) — the DerivativeType → writer map died with the outputs-registry
derivation. A schema rejection is answered by the harness's one bounded
repair round inside ``Agent.call`` (ADR-039 P3) — no blind retries here.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, MAX_CHARS_PER_TEXT
from app.agents.contexts import _generation_context
from app.models.schemas import (
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
    validate_derivative_content,
    validate_output_payload,
)
from app.models.tables import Output, Project, WorkflowStep, WorkflowRun
from app.pipeline.graph import NODE_KINDS, NodeBase, TRANSCRIPT, estimate_mechanical, token_bounds
from app.pipeline.images import _save_quote_card_image
from app.pipeline.step_context import _count_words
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _set_stage,
    slot_tag,
    ui_lang_of,
)
from app.pipeline.edges import _load_director_outputs
from app.platform.project_context import collect_asset_texts, resolve_persona

logger = structlog.get_logger()


def derivative_output_types() -> frozenset[str]:
    """Output types owned by the copy-writer nodes (node-derived — the retired
    ``_OUTPUT_TO_DERIVATIVE_TYPE`` map has no parallel home)."""
    return frozenset(
        n.output_type
        for n in NODE_KINDS.values()
        if isinstance(n, DerivativeWriterNode) and n.output_type
    )


class CopyWriterParams(BaseModel):
    """The four copy-writer tools' shared adjudication document (outputs-
    derive, ADR-043): the writers share one node body, so their params are
    one model — quotes/carousel subclass it to add ``count`` in their own
    packages. Field descriptions ARE the LLM's parameter documentation
    (injected into the intent prompt): write them as "when to use / what
    null means", not as type restatements. Multi-version requests are
    multi-task (an English and a German post = two write_post tasks, each
    with its own language)."""

    language: str = Field(
        description="ISO code this output is WRITTEN in (e.g. 'a German "
        "post' → 'de'). Infer from the request; default to the prompt's "
        "language when the user names none."
    )
    focus: str | None = Field(
        default=None,
        description="A short angle phrase when the user assigns this output "
        "a specific angle (e.g. 'the post should cover the pricing debate' "
        "→ 'pricing debate'). null = the director picks the angle.",
    )
    tone_override: str | None = Field(
        default=None,
        description="A short tone note when the user asks for a per-output "
        "tone (e.g. '帖子正式一点' → 'formal'). null = the persona's tone.",
    )


class DerivativeWriterNode(NodeBase):
    """Shared body for the four copy-writer nodes; each package declares a
    thin subclass with its own ``writer`` (the tool-private agent)."""

    writer: Agent
    needs_director = True
    requires = (TRANSCRIPT,)
    produces_outputs = True
    # Per-writer quotation declarations (P4): completion bounds grounded in
    # the output schema's size class; ``images_per_run`` = exact image
    # generations (the quote card's 1, skipped on targeted regeneration).
    completion_bounds: tuple[int, int] = (400, 1500)
    images_per_run: int = 0

    @property
    def derivative_type(self) -> DerivativeType:
        """The DerivativeType IS the output type (N-32 single source)."""
        return DerivativeType(self.output_type)

    def estimate(self, ctx: dict) -> dict | None:
        """One writer call: prompt = trimmed asset texts + understanding /
        storyboard / persona context overhead; completion per the writer's
        size class."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800
        prompt[1] += 3000
        units: dict[str, float] = {}
        if self.images_per_run and not (ctx["spec"] or {}).get("target_id"):
            units["images"] = float(self.images_per_run)
        return estimate_mechanical(
            units, prompt=prompt, completion=list(self.completion_bounds)
        )

    async def _generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
        feedback: str | None = None,
    ) -> dict:
        """Generate a single derivative via the package's writer declaration.

        Returns the agent's generated content as a plain dict. Callers are
        responsible for persisting it. ``feedback`` (期 3 质检打回) rides the
        funnel's repair echo — the writer sees the failed checks verbatim.
        """
        result = await self.writer.call(
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
            repair_feedback=feedback,
        )
        return validate_derivative_content(self.derivative_type, result.model_dump())

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Generate one derivative output (post/quotes/carousel/article).

        With ``spec.target_id`` set this is a targeted regeneration: the existing
        row is updated in place (its storyboard now comes from a real upstream
        director_plan node — the fabricated-plan path is gone).
        """
        derivative_type = self.derivative_type
        ctx = run.context or {}
        # 质检打回 (期 3): a bounced round's feedback rides the spec exactly
        # once — pop it (reassign = SQLAlchemy-tracked) so a later targeted
        # regen never eats stale feedback.
        spec = dict(node.spec or {})
        feedback = spec.pop("feedback", None)
        if feedback is not None:
            node.spec = spec
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

        content = await self._generate(
            asset_texts=asset_texts,
            context=generation_context,
            understanding=understanding,
            storyboard=storyboard,
            feedback=feedback,
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
                node.id, self.kind, tag=slot_tag(slot),
                ui_language=ui_lang_of(run, project), word_count=_count_words(content),
            )
            return [output.id]

        # Idempotency, sibling-safe (per-slot fan-out): same-type outputs produced
        # by THIS run's same-kind nodes are their own slots' products — only prior
        # products (other runs' steps, or step-less rows) are cleared. Two sibling
        # write_post nodes can therefore never delete each other's output.
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
            node.id, self.kind, tag=slot_tag(slot),
            ui_language=ui_lang_of(run, project), word_count=_count_words(content),
        )
        return [output.id]

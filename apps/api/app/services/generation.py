"""Background generation orchestration.

Runs the analyzer/script/linkedin/quote agents for a project according to the
requested ``outputs``, tracking progress on a :class:`WorkflowRun`. Designed to
run in a FastAPI ``BackgroundTask`` with its own database session.
"""

from uuid import UUID

import structlog
from sqlalchemy import delete, select

from app.agents.analyzer import analyzer_agent
from app.agents.blog import blog_agent
from app.agents.linkedin import linkedin_agent
from app.agents.quote_card import quote_card_agent
from app.agents.script import script_agent
from app.agents.summary import summary_agent
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    DerivativeType,
    ProjectStatus,
    SpeakerPersona,
    ToneSettings,
    WorkflowStatus,
)
from app.models.tables import Asset, Clip, Derivative, Project, Speaker, WorkflowRun

logger = structlog.get_logger()

KNOWN_OUTPUTS = ("clips", "linkedin", "quote_cards", "summary", "blog")


async def run_generation(run_id: UUID) -> None:
    """Execute a queued generation run. Never raises — failures land on the run."""
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            logger.warning("generation_run_missing", run_id=str(run_id))
            return

        try:
            ctx = run.context or {}
            outputs = [o for o in ctx.get("outputs", ["clips"]) if o in KNOWN_OUTPUTS]
            if not outputs:
                outputs = ["clips"]
            clip_count = int(ctx.get("clip_count", 3))
            target_language = ctx.get("target_language", "en")
            tone_raw = ctx.get("tone_settings")
            tone_settings = ToneSettings.model_validate(tone_raw) if tone_raw else None

            run.status = WorkflowStatus.RUNNING
            run.progress = 0
            run.current_step = "loading"
            await db.commit()

            project = await db.get(Project, run.project_id)
            if project is None:
                raise ValueError("Project not found")
            speaker = (
                await db.get(Speaker, project.speaker_id)
                if project.speaker_id
                else None
            )

            asset_rows = await db.execute(
                select(Asset).where(Asset.project_id == project.id)
            )
            materials = [
                text
                for a in asset_rows.scalars().all()
                if (text := (a.extracted_text or a.transcript))
            ]
            if not materials:
                raise ValueError("No source material to analyze")

            persona = (
                SpeakerPersona.model_validate(speaker.persona)
                if speaker is not None and speaker.persona
                else None
            )

            # Idempotency: clear prior outputs for the requested types so reruns
            # replace rather than accumulate.
            if "clips" in outputs:
                await db.execute(delete(Clip).where(Clip.project_id == project.id))
            if "linkedin" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.LINKEDIN_POST,
                    )
                )
            if "quote_cards" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.QUOTE_CARD,
                    )
                )
            if "summary" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.SUMMARY,
                    )
                )
            if "blog" in outputs:
                await db.execute(
                    delete(Derivative).where(
                        Derivative.project_id == project.id,
                        Derivative.type == DerivativeType.BLOG,
                    )
                )
            await db.commit()

            total = len(outputs)
            done = 0

            if "clips" in outputs:
                run.current_step = "clips"
                await db.commit()
                analysis = await analyzer_agent.analyze(
                    materials=materials,
                    clip_count=clip_count,
                    event_name=project.event_name,
                )
                for segment in analysis.segments[:clip_count]:
                    script = await script_agent.generate(
                        segment=segment,
                        persona=persona,
                        tone_settings=tone_settings,
                        target_audience=analysis.target_audience,
                    )
                    db.add(
                        Clip(
                            project_id=project.id,
                            hook=script.hook,
                            script=script.model_dump(),
                            title_options=script.title_options,
                            music_mood=script.music_mood,
                            duration=script.duration_seconds,
                            language=target_language,
                            source_segment=segment.model_dump(),
                        )
                    )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "linkedin" in outputs:
                run.current_step = "linkedin"
                await db.commit()
                post = await linkedin_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.LINKEDIN_POST,
                        content=post.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "quote_cards" in outputs:
                run.current_step = "quote_cards"
                await db.commit()
                result = await quote_card_agent.generate(
                    materials=materials,
                    speaker_name=speaker.name if speaker is not None else "",
                    speaker_title=speaker.title if speaker is not None else "",
                    event_name=project.event_name,
                    count=3,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.QUOTE_CARD,
                        content=result.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "summary" in outputs:
                run.current_step = "summary"
                await db.commit()
                summary = await summary_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.SUMMARY,
                        content=summary.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            if "blog" in outputs:
                run.current_step = "blog"
                await db.commit()
                blog = await blog_agent.generate(
                    materials=materials,
                    persona=persona,
                    event_name=project.event_name,
                    target_language=target_language,
                )
                db.add(
                    Derivative(
                        project_id=project.id,
                        type=DerivativeType.BLOG,
                        content=blog.model_dump(),
                        language=target_language,
                    )
                )
                await db.commit()
                done += 1
                run.progress = int(done / total * 100)
                await db.commit()

            run.status = WorkflowStatus.COMPLETED
            run.current_step = "done"
            run.progress = 100
            if project is not None:
                project.status = ProjectStatus.REVIEW
            await db.commit()
            logger.info("generation_completed", run_id=str(run_id), outputs=outputs)
        except Exception as e:  # noqa: BLE001 — record any failure on the run
            logger.error("generation_failed", run_id=str(run_id), error=str(e))
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            await db.commit()

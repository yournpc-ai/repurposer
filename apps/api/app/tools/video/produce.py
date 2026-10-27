"""Queue a CompositionVersion for render — the minimal produce seam.

Phase A batch 1: NO run node, no estimate, no billing (those are phase B's
``produce_video``). This function is the shared core they will wrap: pin the
exact version, compile the video-spec, birth the Output with the full
Composition lineage (§2.2 — composition_id + composition_version_id +
content digest in the payload) and pend it onto the existing render queue
(``outputs.render_status=PENDING`` — the worker's claim loop is untouched).

Run-less by design for now: no workflow_step_id, no render mirror step, no
barrier (``render_barrier NULL`` claims immediately — the same lane
undo/redo and manual renders already use).
"""

from __future__ import annotations
from math import gcd

from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.store import PermissionDenied, content_of, snapshot_facts
from app.editing.video_spec import compile_video_spec
from app.models.schemas import RenderStatus
from app.models.tables import Composition, CompositionVersion, Output, Project


async def queue_composition_render(
    db: AsyncSession,
    *,
    project: Project,
    composition: Composition,
    version: CompositionVersion,
) -> Output:
    """Birth the video Output for one pinned version and pend its render.

    Identity law: the version must belong to the composition, and the
    composition to the project's owner — a version the caller cannot name
    through ownership never reaches the queue.
    """
    if composition.owner_id != project.user_id:
        raise PermissionDenied("that composition belongs to another user")
    if version.composition_id != composition.id:
        raise PermissionDenied("that version does not belong to the composition")

    content = content_of(version)
    facts = await snapshot_facts(
        db, {b.snapshot_id for b in content.sources}
    )
    spec = compile_video_spec(
        content,
        facts,
        composition_id=composition.id,
        version_id=version.id,
        content_digest=version.content_digest,
    )
    duration_seconds = spec["duration_frames"] * spec["fps"]["den"] / spec["fps"]["num"]
    divisor = gcd(spec["width"], spec["height"])

    output = Output(
        project_id=project.id,
        workflow_step_id=None,
        type="video",
        language=project.language,
        provenance="generated",
        payload={
            "name": composition.name,
            "duration_seconds": duration_seconds,
            "duration": duration_seconds,
            "aspect": f"{spec['width'] // divisor}:{spec['height'] // divisor}",
            # §2.2: the Output pins all three identity facts; the digest is
            # the payload's job (the columns pin the rows).
            "composition_digest": version.content_digest,
        },
        render_spec=spec,
        render_status=RenderStatus.PENDING,
        work_id=composition.id,
        composition_id=composition.id,
        composition_version_id=version.id,
    )
    db.add(output)
    await db.flush()
    return output

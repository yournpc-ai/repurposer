"""Create, locally revise and run-less render the real two-shot C4 Composition."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.editing.service import revise_video
from app.editing.store import apply_composition_edits
from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus, ReviseVideoArgs
from app.models.tables import Composition, CompositionVersion, Output, Project
from app.skills.external import SkillCapabilityReport, SkillDraft, SkillSource
from app.skills.video_shotcraft import (
    VIDEO_SHOTCRAFT_REVISION,
    BlurSlidePalette,
    instantiate_blur_demote_sequence,
)
from app.tools.video.produce import queue_composition_render

ORIGIN_COMPOSITION_ID = UUID("f372ae17-b351-4abf-8a3f-ac46fcdfc27c")
CREATE_REQUEST = "c4-blur-demote-sequence-v1"
REVISE_REQUEST = "c4-blur-demote-sequence-v2"
OUT = Path("/Users/sylas/repurposer/scratch/c4-multishot-evidence.json")
TERMINAL = {RenderStatus.COMPLETED, RenderStatus.FAILED}


def draft(source_hash: str) -> SkillDraft:
    sources = [
        ("references/shots/typography/blur-slide.md", "reference", "feb73479174b0ff073a6d774c6ed3bd250591439fbd750e1167c2f39b27a05d4"),
        ("demos/typography/blur-slide/BlurSlide.tsx", "implementation", "4e7227b050b4f9fdd0c8762f308aaf2a152f8c476fa3e11efe84b3a23cc43a91"),
        ("references/shots/typography/title-demote-to-label.md", "reference", "4e01c04c76d9f6a3f1b18e9c75ac1502cb1aefe1ac08ef47426b8628ea9fa08f"),
        ("demos/typography/title-demote-to-label/TitleDemoteToLabel.tsx", "implementation", "5448cdf76c9eb57ebc4de46ae0f2e9bd399275e9600181afb26fe5dfbf0eeff5"),
    ]
    return SkillDraft(
        name="video-shotcraft",
        description="Pinned two-shot evidence",
        instructions="Use the two pinned native shot methods.",
        references=[
            SkillSource(path=path, role=role, digest=digest, text="Pinned imported evidence.")
            for path, role, digest in sources
        ],
        source_hash=source_hash,
        source_uri="https://github.com/Vincentwei1021/video-shotcraft",
        source_revision=VIDEO_SHOTCRAFT_REVISION,
        capability_report=SkillCapabilityReport(),
    )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        origin = await db.get(Composition, ORIGIN_COMPOSITION_ID)
        owner_id = origin.owner_id
        project_id = origin.origin_project_id
        base_version = await db.get(CompositionVersion, UUID("5a112f13-3458-4ae3-aa50-cfab8a67f9bf"))
        instantiation = instantiate_blur_demote_sequence(
            draft(base_version.skill_provenance["source_hash"]),
            title_lines=("Make every idea", "move clearly"),
            subtitle="Your existing material shaped into the content you name",
            section_title="Shape",
            section_lines=(
                "Upload the material you already have",
                "Name the content you want",
                "Review and refine every version",
            ),
            palette=BlurSlidePalette(
                background="#101418",
                title="#F5F3EE",
                subtitle="#C7D0D8",
            ),
        )
        composition, v1, _ = await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            name="Two-shot product title sequence",
            ops=instantiation.ops,
            request_id=CREATE_REQUEST,
            skill_provenance=instantiation.skill_provenance,
        )
        revised_read = await revise_video(
            db,
            owner_id=owner_id,
            request_id=REVISE_REQUEST,
            args=ReviseVideoArgs.model_validate({
                "base_ref": {
                    "composition_id": str(composition.id),
                    "composition_version_id": str(v1.id),
                    "content_digest": v1.content_digest,
                },
                "edits": [{
                    "op": "update_text",
                    "clip_id": "clp_demote_content_1",
                    "text": "Choose the exact content you need",
                }],
                "visual_descriptions": [{
                    "scene_id": "scn_title_demote",
                    "text": (
                        "The Shape title settles into a small section label while three "
                        "product steps enter below, including choosing the exact content needed."
                    ),
                }],
            }),
        )
        v2 = await db.scalar(
            select(CompositionVersion).where(CompositionVersion.request_id == REVISE_REQUEST)
        )
        assert v2.skill_provenance == v1.skill_provenance
        version_ids = [v1.id, v2.id]
        output_ids = []
        project = await db.get(Project, project_id)
        for version_id in version_ids:
            existing = await db.scalar(
                select(Output).where(Output.composition_version_id == version_id).limit(1)
            )
            if existing is not None:
                output_ids.append(existing.id)
                continue
            version = await db.get(CompositionVersion, version_id)
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=f"c4-multishot-{version_id}",
            )
            output_ids.append(output.id)
        await db.commit()
        identities = {
            "composition_id": str(composition.id),
            "v1": {"version_id": str(v1.id), "digest": v1.content_digest},
            "v2": {
                "version_id": str(v2.id),
                "digest": v2.content_digest,
                "change_set": revised_read["change_set"],
            },
            "output_ids": [str(item) for item in output_ids],
            "charge_scope": "run-less adapter renders; no Run or render mirror",
        }

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 600
    while True:
        rows = []
        async with AsyncSessionLocal() as db:
            for output_id in output_ids:
                output = await db.get(Output, output_id)
                rows.append({
                    "output_id": str(output.id),
                    "composition_version_id": str(output.composition_version_id),
                    "render_status": output.render_status.value,
                    "duration_seconds": (output.payload or {}).get("duration_seconds"),
                    "files": output.files,
                })
        if all(row["render_status"] in {item.value for item in TERMINAL} for row in rows):
            evidence = {**identities, "outputs": rows}
            OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            print(json.dumps({
                **identities,
                "outputs": rows,
                "v2_change_set": "saved in evidence file",
            }, ensure_ascii=False, indent=2))
            if any(row["render_status"] != RenderStatus.COMPLETED.value for row in rows):
                raise RuntimeError("multi-shot render failed")
            return
        if loop.time() >= deadline:
            raise TimeoutError(json.dumps(rows))
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())

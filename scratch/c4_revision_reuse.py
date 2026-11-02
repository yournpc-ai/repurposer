"""Persist one native C4 revision and one second-product instantiation; no rendering."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.editing.store import apply_composition_edits, content_of
from app.models.database import AsyncSessionLocal
from app.models.schemas import ReviseVideoArgs
from app.models.tables import Composition, CompositionVersion
from app.skills.external import SkillCapabilityReport, SkillDraft, SkillSource
from app.skills.video_shotcraft import (
    VIDEO_SHOTCRAFT_REVISION,
    BlurSlidePalette,
    instantiate_blur_slide,
)

COMPOSITION_ID = UUID("f372ae17-b351-4abf-8a3f-ac46fcdfc27c")
BASE_VERSION_ID = UUID("5a112f13-3458-4ae3-aa50-cfab8a67f9bf")
REVISION_REQUEST = "c4-blur-slide-native-revision-v1"
REUSE_REQUEST = "c4-blur-slide-second-product-v1"
OUT = Path("/Users/sylas/repurposer/scratch/c4-revision-reuse.json")


def pinned_draft(source_hash: str) -> SkillDraft:
    return SkillDraft(
        name="video-shotcraft",
        description="Pinned shot evidence",
        instructions="Use the pinned blur-slide method.",
        references=[
            SkillSource(
                path="references/shots/typography/blur-slide.md",
                role="reference",
                digest="feb73479174b0ff073a6d774c6ed3bd250591439fbd750e1167c2f39b27a05d4",
                text="Previously imported pinned shot-card evidence.",
            ),
            SkillSource(
                path="demos/typography/blur-slide/BlurSlide.tsx",
                role="implementation",
                digest="4e7227b050b4f9fdd0c8762f308aaf2a152f8c476fa3e11efe84b3a23cc43a91",
                text="Previously imported pinned implementation evidence.",
            ),
        ],
        source_hash=source_hash,
        source_uri="https://github.com/Vincentwei1021/video-shotcraft",
        source_revision=VIDEO_SHOTCRAFT_REVISION,
        capability_report=SkillCapabilityReport(),
    )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        composition = await db.get(Composition, COMPOSITION_ID)
        base = await db.get(CompositionVersion, BASE_VERSION_ID)
        if composition is None or base is None or base.composition_id != composition.id:
            raise RuntimeError("C4 base composition/version not found")
        owner_id = composition.owner_id
        origin_project_id = composition.origin_project_id
        provenance = base.skill_provenance
        if not provenance:
            raise RuntimeError("C4 base has no Skill provenance")

        revised_read = await revise(
            db,
            owner_id=owner_id,
            base=base,
        )
        revised = await db.scalar(
            select(CompositionVersion).where(CompositionVersion.request_id == REVISION_REQUEST)
        )
        if revised is None:
            raise RuntimeError("revision did not persist")
        if revised.skill_provenance != provenance:
            raise AssertionError("revision lost or changed Skill provenance")

        reused_instantiation = instantiate_blur_slide(
            pinned_draft(provenance["source_hash"]),
            title_lines=("Grow your audience", "share boldly"),
            subtitle="Turn your hard earned expertise into stories worth following",
            palette=BlurSlidePalette(
                background="#101418",
                title="#F5F3EE",
                subtitle="#C7D0D8",
            ),
        )
        reused_composition, reused_version, _ = await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=origin_project_id,
            name="Second product blur-slide",
            ops=reused_instantiation.ops,
            request_id=REUSE_REQUEST,
            skill_provenance=reused_instantiation.skill_provenance,
        )
        reused_content = content_of(reused_version)
        texts = {
            clip.clip_id: clip.object.text
            for track in reused_content.timeline.tracks
            for clip in track.clips
        }
        assert texts == {
            "clp_blur_title_a": "Grow your audience",
            "clp_blur_title_b": "share boldly",
            "clp_blur_subtitle": "Turn your hard earned expertise into stories worth following",
        }
        assert reused_content.settings.background == "#101418"
        evidence = {
            "base": {
                "composition_id": str(composition.id),
                "version_id": str(base.id),
                "content_digest": base.content_digest,
            },
            "revision": {
                "composition_id": str(composition.id),
                "version_id": str(revised.id),
                "version": revised.version,
                "base_version_id": str(revised.base_version_id),
                "content_digest": revised.content_digest,
                "skill_provenance": revised.skill_provenance,
                "change_set": revised_read["change_set"],
            },
            "second_product": {
                "composition_id": str(reused_composition.id),
                "version_id": str(reused_version.id),
                "version": reused_version.version,
                "content_digest": reused_version.content_digest,
                "skill_provenance": reused_version.skill_provenance,
                "texts": texts,
                "background": reused_content.settings.background,
            },
            "paid_rendering_started": False,
        }
        OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


async def revise(db, *, owner_id: UUID, base: CompositionVersion) -> dict:
    from app.editing.service import revise_video

    return await revise_video(
        db,
        owner_id=owner_id,
        request_id=REVISION_REQUEST,
        args=ReviseVideoArgs.model_validate({
            "base_ref": {
                "composition_id": str(base.composition_id),
                "composition_version_id": str(base.id),
                "content_digest": base.content_digest,
            },
            "edits": [
                {
                    "op": "update_text",
                    "clip_id": "clp_blur_title_a",
                    "text": "Turn every insight",
                    "color": "#F5F3EE",
                },
                {
                    "op": "update_text",
                    "clip_id": "clp_blur_title_b",
                    "color": "#F5F3EE",
                },
                {
                    "op": "update_text",
                    "clip_id": "clp_blur_subtitle",
                    "text": "Your research and expertise shaped into content people remember",
                    "color": "#C7D0D8",
                },
                {"op": "set_background", "color": "#101418"},
            ],
            "visual_descriptions": [{
                "scene_id": "scn_blur_slide",
                "text": (
                    "On a dark canvas, light title and subtitle words reveal in sequence "
                    "with upward movement and blur, then remain fully readable."
                ),
            }],
        }),
    )


if __name__ == "__main__":
    asyncio.run(main())

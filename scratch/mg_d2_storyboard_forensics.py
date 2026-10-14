"""D2 取证: run the storyboarder ONCE against the real github.com manifest,
print the validator's violations verbatim (what exactly did the model invent?).

Run: uv run python scratch/mg_d2_storyboard_forensics.py
"""

import asyncio
import sys

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, WebPageResearch
from app.models.tables import Asset
from app.tools.film.storyboard import (
    film_storyboarder,
    format_violations,
    page_prompt_dict,
    StoryboardPage,
    validate_storyboard,
)
from app.pipeline.step_context import media_input_for_image


async def main():
    async with AsyncSessionLocal() as db:
        asset = (
            await db.execute(
                select(Asset).where(
                    Asset.type == AssetType.WEB_PAGE,
                    Asset.processing_status == AssetStatus.COMPLETED,
                ).order_by(Asset.created_at.desc()).limit(1)
            )
        ).scalar_one()
        meta = asset.meta or {}
        from urllib.parse import urlparse

        research = WebPageResearch.model_validate(meta["research"])
        page = StoryboardPage(
            asset_id=str(asset.id),
            research=research,
            screenshot_key=meta.get("screenshot_key"),
            host=urlparse(research.url).netloc,
        )

    media = []
    if page.screenshot_key:
        item = await media_input_for_image(
            page.screenshot_key, caption=f"Screenshot of page 0 ({page.host})"
        )
        if item:
            media.append(item)

    candidate = await film_storyboarder.call(
        pages=[page_prompt_dict(page, 0)],
        instruction="Make a short launch film of this page.",
        focus=None,
        page_images=media,
    )
    violations = validate_storyboard(candidate, [page])
    print("=== candidate storyboard ===")
    for i, s in enumerate(candidate.scenes):
        print(f"scene[{i}] {s.type}: {s.model_dump(mode='json', exclude={'type', 'seconds'})}")
    print("\n=== violations ===")
    print(format_violations(violations) if violations else "(clean)")


if __name__ == "__main__":
    asyncio.run(main())

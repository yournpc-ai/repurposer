"""Stage a morph-path repro project (2026-09-13 centering walkthrough):
fresh project + the SAME xy_2_15s.mp4 object (S3 server-side copy, new
project-namespaced key) + Asset row via the canonical create-from-key
sequence (PENDING + stamp_asset_node). The resident worker picks up ASR
itself. Prints the new project id for the CDP step.
"""

import asyncio
from uuid import UUID, uuid4

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, Project
from app.providers.storage import _get_s3_client, get_project_upload_dir

USER_ID = UUID("52037604-9321-4b70-9212-445ccf5ade60")
SRC_KEY = (
    "52037604-9321-4b70-9212-445ccf5ade60/uploads/projects/"
    "ad28d7c6-855f-4a0e-8c41-220e9b19a0c7/xy_2_15s-1789273213-wuIRsg.mp4"
)


async def main() -> None:
    project_id = uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Project(id=project_id, user_id=USER_ID, title="centering repro"))
        await db.commit()

    dst_key = f"{get_project_upload_dir(project_id, USER_ID)}/xy_2_15s-repro.mp4"
    _get_s3_client().copy_object(
        Bucket=settings.s3_bucket_name,
        CopySource={"Bucket": settings.s3_bucket_name, "Key": SRC_KEY},
        Key=dst_key,
    )
    print("copied to", dst_key)

    async with AsyncSessionLocal() as db:
        asset = Asset(
            user_id=USER_ID,
            project_id=project_id,
            type=AssetType.VIDEO,
            file_url=dst_key,
            title="xy_2_15s.mp4",
            processing_status=AssetStatus.PENDING,
            meta={"width": 960, "height": 960},
        )
        db.add(asset)
        from app.pipeline.graph_fill import stamp_asset_node

        await stamp_asset_node(db, project_id, asset)
        await db.commit()
    print("project:", project_id)


asyncio.run(main())

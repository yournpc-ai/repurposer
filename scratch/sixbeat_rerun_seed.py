"""Six-beat rerun seed: project + real-bytes video for the browser's user.

Creates a project owned by the CDP browser's logged-in user
(/tmp/sixbeat_auth.json), copies the demo talk video to an owned bucket key
(delete_project unlinks asset keys — never seed shared demo/ keys), and
seeds the asset PENDING so the dev worker really ASRs it.

Run (from apps/api, dev API + worker live):
    uv run python ../../scratch/sixbeat_rerun_seed.py
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

import httpx  # noqa: E402

from app.models.schemas import AssetStatus, AssetType  # noqa: E402
from chat_scenarios import copy_fixture, seed_asset, wait_asset_status  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
SOURCE_KEY = "demo/uploads/demo_talk.mp4"


async def main() -> None:
    auth = json.loads(Path("/tmp/sixbeat_auth.json").read_text())
    user_id = uuid.UUID(auth["id"])
    client = httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {auth['token']}"},
        timeout=60.0,
    )
    res = await client.post(
        "/projects", json={"title": "Six-beat rerun (fix verification)", "event_name": ""}
    )
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    key = await copy_fixture(SOURCE_KEY, f"scenario/sixbeat-rerun-{uuid.uuid4().hex[:8]}")
    asset_id = await seed_asset(
        pid, user_id, AssetType.VIDEO, "acceptance_talk.mp4", file_url=key
    )
    print(f"project: {pid}")
    print(f"asset:   {asset_id} ({key})")
    status = await wait_asset_status(
        asset_id, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    print(f"asr:     {status}")
    assert status == AssetStatus.COMPLETED, "ASR failed on the seeded talk"


asyncio.run(main())

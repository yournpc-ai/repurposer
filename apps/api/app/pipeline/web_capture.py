"""WEB_PAGE asset processor: capture orchestration + meta/storage writeback.

Same family as ``extraction.py`` / ``prosody.py``: the tool
(``tools/research/capture.py``) owns the capability (fetch + extract +
screenshot + SSRF policy); this module owns the asset-shaped plumbing —
read the URL off ``meta.capture_url``, run the capture, put the screenshot
in object storage, return the ProcessResult delta.

Single-processor chain (asset_processing.PROCESSORS): the content hash
can't run at the chain head here — a web_page is born with no file and no
text, so this processor stamps ``meta.content_sha256`` from its own yield.
"""

import io
from typing import Any

import structlog
from PIL import Image

from app.models.schemas import WebPageMeta
from app.models.tables import Asset
from app.providers.storage import get_project_output_dir, save
from app.tools.research.capture import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    capture_page,
    css_pixel_box,
    manifest_content_hash,
)

logger = structlog.get_logger()


def _png_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG":
            raise ValueError("web capture did not produce a PNG")
        return image.size


async def web_capture_processor(asset: Asset, _prior: Any) -> "Any":
    """Capture the asset's URL and fold the yield into the asset row.

    A capture failure (blocked / unreachable / non-HTML) raises — the chain
    settles the asset FAILED with the honest line. A missing screenshot is
    NOT a failure: the research manifest is the substance, and the card
    shows an honest absence (screenshot_key simply absent).
    """
    from app.pipeline.asset_processing import ProcessResult  # avoid cycle at import time

    url = (asset.meta or {}).get("capture_url") if isinstance(asset.meta, dict) else None
    if not url:
        raise ValueError("web_page asset missing meta.capture_url")

    outcome = await capture_page(url)

    meta: dict = {
        "capture_url": url,
        "research": outcome.research.model_dump(),
        # The chain-head hash seat's mirror: content-addressing key stamped
        # from the capture's own text yield (期 1 前移 same law).
        "content_sha256": manifest_content_hash(outcome.text),
    }
    # B4 recursion gate: a discovered child's meta marker rides forward
    # (this writeback REPLACES asset.meta wholesale), and its own discovery
    # list never leaves the tool — 禁递归深挖.
    discovered_from = (asset.meta or {}).get("discovered_from")
    if discovered_from:
        meta["discovered_from"] = discovered_from

    if outcome.screenshot is not None:
        if asset.project_id is None:
            # web_page assets are born project-bound; refuse the odd row
            # honestly rather than writing an unprefixable key.
            raise ValueError("web_page asset without project_id")
        key = f"{get_project_output_dir(asset.project_id, asset.user_id)}/web-capture-{asset.id}.png"
        await save(key, outcome.screenshot, content_type="image/png")
        meta["screenshot_key"] = key
        # The viewport's real pixels — the card's aspect truth (same law as
        # the chain-head probe's meta.width/height).
        meta["width"], meta["height"] = _png_size(outcome.screenshot)

    if outcome.page is not None:
        if asset.project_id is None:
            raise ValueError("web_page asset without project_id")
        page = outcome.page
        page_key = (
            f"{get_project_output_dir(asset.project_id, asset.user_id)}"
            f"/web-capture-{asset.id}-page.png"
        )
        await save(page_key, page.png, content_type="image/png")
        width, height = _png_size(page.png)
        meta["page"] = {
            "key": page_key,
            "width": width,
            "height": height,
            "css_width": page.css_width,
            "css_height": page.css_height,
            "device_scale_factor": page.device_scale_factor,
        }

    # ADR-121 B1: the fold + section shots (shots[0] IS the fold — its key
    # doubles as screenshot_key above). Each section shot gets its own
    # storage key; the element inventory rides the shot's meta entry.
    if outcome.shots:
        if asset.project_id is None:
            raise ValueError("web_page asset without project_id")
        out_dir = get_project_output_dir(asset.project_id, asset.user_id)
        shots_meta: list[dict] = []
        for i, shot in enumerate(outcome.shots):
            if i == 0:
                shot_key = meta["screenshot_key"]
            else:
                shot_key = f"{out_dir}/web-capture-{asset.id}-s{i}.png"
                await save(shot_key, shot.png, content_type="image/png")
            elements: list[dict] = []
            for raw_element in shot.elements:
                element = dict(raw_element)
                css_box = element.get("css_box")
                if isinstance(css_box, dict):
                    element["device_scale_factor"] = shot.device_scale_factor
                    element["pixel_box"] = css_pixel_box(
                        css_box, shot.device_scale_factor
                    )
                image = outcome.element_images.get(str(element.get("id")))
                if image is not None:
                    image_key = (
                        f"{out_dir}/web-capture-{asset.id}-{element['id']}.png"
                    )
                    await save(image_key, image, content_type="image/png")
                    element["image_key"] = image_key
                    element["image_width"], element["image_height"] = _png_size(image)
                elements.append(element)
            shots_meta.append(
                {
                    "key": shot_key,
                    "y": shot.y,
                    "heading": shot.heading,
                    "elements": elements,
                    "css_width": WINDOW_WIDTH,
                    "css_height": WINDOW_HEIGHT,
                    "device_scale_factor": shot.device_scale_factor,
                }
            )
        meta["shots"] = shots_meta

    # Contract check on our own writeback (the meta schema's seat):
    WebPageMeta.model_validate(meta)

    logger.info(
        "web_capture_processed",
        asset_id=str(asset.id),
        url=url,
        chars=len(outcome.text),
        screenshot=bool(outcome.screenshot),
        discovered=len(outcome.discovered),
        warnings=outcome.warnings,
    )
    return ProcessResult(
        extracted_text=outcome.text,
        meta=meta,
        # The spawn seat (process_asset) reads this; a discovered child
        # never re-discovers (禁递归深挖 — the marker above is the gate).
        discovered_urls=[] if discovered_from else outcome.discovered,
    )

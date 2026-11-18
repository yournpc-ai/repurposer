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

from app.config import settings
from app.models.schemas import WebPageMeta
from app.models.tables import Asset
from app.providers.storage import get_project_output_dir, save
from app.tools.research.capture import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    CaptureError,
    CapturePlan,
    capture_page,
    capture_plan_digest,
    capture_shots,
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

    source_meta = asset.meta or {}
    url = source_meta.get("capture_url") if isinstance(source_meta, dict) else None
    if not url:
        raise ValueError("web_page asset missing meta.capture_url")

    raw_plan = source_meta.get("capture_plan")
    plan = CapturePlan.model_validate(raw_plan) if raw_plan is not None else None
    if plan is not None and plan.capture_url != url:
        raise ValueError("web_page capture_url does not match its CapturePlan route")
    outcome = await capture_shots(plan) if plan is not None else await capture_page(url)

    meta: dict = {
        "capture_url": url,
        "research": outcome.research.model_dump(),
        # The chain-head hash seat's mirror: content-addressing key stamped
        # from the capture's own text yield (期 1 前移 same law).
        "content_sha256": manifest_content_hash(outcome.text),
    }
    if plan is not None:
        meta["capture_plan"] = plan.model_dump(mode="json")
        meta["capture_plan_digest"] = capture_plan_digest(plan)
        meta["capture_warnings"] = outcome.warnings
        meta["capture_issues"] = outcome.capture_issues
        meta["capture_issue_count"] = outcome.capture_issue_count
        meta["capture_issues_truncated"] = outcome.capture_issues_truncated
    origin = source_meta.get("origin")
    if origin is not None:
        meta["origin"] = origin
    # B4 recursion gate: a discovered child's meta marker rides forward
    # (this writeback REPLACES asset.meta wholesale), and its own discovery
    # list never leaves the tool — 禁递归深挖.
    discovered_from = (asset.meta or {}).get("discovered_from")
    if discovered_from:
        meta["discovered_from"] = discovered_from
    turn_id = (asset.meta or {}).get("turn_id")
    if turn_id:
        meta["turn_id"] = turn_id

    if outcome.screenshot is not None and plan is None:
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

    if outcome.shots:
        if asset.project_id is None:
            raise ValueError("web_page asset without project_id")
        out_dir = get_project_output_dir(asset.project_id, asset.user_id)
        shots_meta: list[dict] = []
        stored_bytes = 0
        issue_count = outcome.capture_issue_count

        def record_issue(shot: Any, error: Any) -> None:
            nonlocal issue_count
            issue_count += 1
            if len(outcome.capture_issues) < 64:
                outcome.capture_issues.append({
                    key: value
                    for key, value in {
                        "state_id": shot.state_id,
                        "output_id": shot.output_id or shot.view_id,
                        "target_id": shot.target_id,
                        "member_id": shot.member_id,
                        "error": str(error)[:300],
                    }.items()
                    if value is not None
                })
            else:
                outcome.capture_issues_truncated = True

        for i, shot in enumerate(outcome.shots):
            if stored_bytes + len(shot.png) > settings.web_capture_max_bytes:
                record_issue(shot, "captured image storage budget exceeded")
                continue
            try:
                if i == 0:
                    shot_key = (
                        meta["screenshot_key"] if plan is None
                        else f"{out_dir}/web-capture-{asset.id}.png"
                    )
                else:
                    shot_key = f"{out_dir}/web-capture-{asset.id}-s{i}.png"
                if plan is not None or i > 0:
                    await save(shot_key, shot.png, content_type="image/png")
                stored_bytes += len(shot.png)
                elements: list[dict] = []
                for raw_element in shot.elements:
                    element = dict(raw_element)
                    css_box = element.get("css_box")
                    if isinstance(css_box, dict):
                        element["device_scale_factor"] = shot.device_scale_factor
                        element["pixel_box"] = css_pixel_box(css_box, shot.device_scale_factor)
                    image = outcome.element_images.get(str(element.get("id")))
                    if image is not None:
                        if stored_bytes + len(image) > settings.web_capture_max_bytes:
                            record_issue(shot, "element image storage budget exceeded")
                        else:
                            try:
                                image_key = f"{out_dir}/web-capture-{asset.id}-{element['id']}.png"
                                await save(image_key, image, content_type="image/png")
                                stored_bytes += len(image)
                                element["image_key"] = image_key
                                element["image_width"], element["image_height"] = _png_size(image)
                            except Exception as exc:
                                record_issue(shot, f"element image storage failed: {exc}")
                    elements.append(element)
                shot_meta = {
                    "key": shot_key,
                    "y": shot.y,
                    "heading": shot.heading,
                    "elements": elements,
                    "css_width": WINDOW_WIDTH if plan is None else plan.viewport.width,
                    "css_height": WINDOW_HEIGHT if plan is None else plan.viewport.height,
                    "device_scale_factor": shot.device_scale_factor,
                }
                for field_name in (
                    "view_id", "state_id", "output_id", "artifact_role", "paired_view_id",
                    "target_id", "target_ids", "target_element_id", "member_id", "transparent",
                    "route", "actions", "page_height", "region_text",
                    "region_text_truncated", "region_visually_truncated",
                ):
                    value = getattr(shot, field_name)
                    if value is not None:
                        shot_meta[field_name] = value
                shots_meta.append(shot_meta)
                if plan is not None and "screenshot_key" not in meta and shot.artifact_role in {"view", "hero"}:
                    meta["screenshot_key"] = shot_key
                    meta["width"], meta["height"] = _png_size(shot.png)
            except Exception as exc:
                record_issue(shot, f"captured view storage failed: {exc}")
        if plan is not None and not shots_meta:
            raise CaptureError("final webpage capture could not store any usable views")
        meta["shots"] = shots_meta
        if plan is not None:
            meta["capture_issue_count"] = issue_count
            meta["capture_issues_truncated"] = (
                outcome.capture_issues_truncated or issue_count > len(outcome.capture_issues)
            )

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

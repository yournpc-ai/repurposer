"""Terminal facts for authorized scene-image preparation Runs."""

from __future__ import annotations

from uuid import UUID

from app.models.tables import Project, SourceSnapshot

_ALLOWED_REVIEW_STATES = {"pass", "fail", "needs_human", "advisory", "unavailable"}


def has_visual_asset_preparation_scope(run) -> bool:
    return isinstance((run.context or {}).get("visual_asset_preparation"), dict)


async def visual_asset_preparation_fact(db, run, steps) -> dict:
    preparation = (run.context or {}).get("visual_asset_preparation") or {}
    request = preparation.get("request") or {}
    result = preparation.get("result") or {}
    assets = result.get("assets") or []
    failures = result.get("failures") or []
    if not request or not (assets or failures):
        raise ValueError("visual asset preparation has no settled scenes")
    if "failures" in result:
        from app.tools.video.visual_assets import SceneAssetSpec

        specs = preparation.get("scene_assets") or request.get("scene_assets") or []
        expected_scenes = {
            spec.scene_id: spec.request_digest() for spec in (
                SceneAssetSpec.model_validate(raw) for raw in specs
            )
        }
        settled = [*assets, *failures]
        if len(settled) != len(expected_scenes) or {
            item["scene_id"]: item["request_digest"] for item in settled
        } != expected_scenes:
            raise ValueError("visual asset settlement does not match the authorized batch")
    step = next((item for item in steps if item.kind == "prepare_visual_assets"), None)
    if step is None or step.status != "done" or step.output_refs:
        raise ValueError("visual asset preparation did not settle as an Output-free step")
    project = await db.get(Project, run.project_id)
    if project is None:
        raise ValueError("visual asset preparation project is missing")
    expected_usage = float((result.get("usage") or {}).get("images") or 0)
    actual_usage = float(((step.cost or {}).get("units") or {}).get("images") or 0)
    if actual_usage < expected_usage or (not failures and actual_usage != expected_usage):
        raise ValueError("visual asset image usage does not match its settled step")
    facts = []
    for item in assets:
        snapshot_ref = item.get("snapshot") or {}
        snapshot = await db.get(SourceSnapshot, UUID(str(snapshot_ref.get("snapshot_id"))))
        if (
            snapshot is None
            or snapshot.owner_id != project.user_id
            or snapshot.origin_project_id != project.id
            or snapshot.kind != "image"
            or snapshot.digest != snapshot_ref.get("digest")
            or snapshot.digest != (item.get("media") or {}).get("digest")
        ):
            raise ValueError("visual asset SourceSnapshot identity is inconsistent")
        origin = (snapshot.meta or {}).get("visual_asset") or {}
        analysis = item.get("analysis") or {}
        review = item.get("content_review") or {}
        review_ref = item.get("content_review_ref") or {}
        retry_of = item.get("review_retry_of")
        if retry_of:
            from app.tools.video.media_analysis import read_report

            persisted_review = await read_report(review_ref)
            original_review = await read_report(retry_of)
            if (
                persisted_review != review
                or original_review.get("status") != "unavailable"
                or any(original_review.get(field) != review.get(field) for field in (
                    "source_ref", "scene_id", "request_digest", "analysis_report_ref",
                    "reviewer_version",
                ))
            ):
                raise ValueError("replacement ContentReview does not match the original fixed PNG")
        if (
            origin.get("request_digest") != item.get("request_digest")
            or origin.get("scene_id") != item.get("scene_id")
            or origin.get("analysis_ref") != item.get("analysis_ref")
            or origin.get("content_review_ref") != (retry_of or review_ref)
            or analysis.get("report_digest") != (item.get("analysis_ref") or {}).get("digest")
            or review.get("review_digest") != (item.get("content_review_ref") or {}).get("digest")
            or review.get("status") not in _ALLOWED_REVIEW_STATES
        ):
            raise ValueError("visual asset analysis or ContentReview reference is inconsistent")
        facts.append(
            {
                "scene_id": item["scene_id"],
                "request_digest": item["request_digest"],
                "snapshot_id": str(snapshot.id),
                "snapshot_digest": snapshot.digest,
                "analysis_ref": item["analysis_ref"],
                "content_review_ref": item["content_review_ref"],
                "content_review_status": review["status"],
                "cache_hit": bool(item.get("cache_hit")),
            }
        )
    return {
        "draft_ref": result.get("draft_ref"),
        "assets": facts,
        "failures": failures,
        "usage_images": actual_usage,
    }

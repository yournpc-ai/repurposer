"""Media preparation and recovery — unit contracts."""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.models.tables import SourceSnapshot
from app.tools.video import visual_assets
from app.tools.video.media_analysis import analyze_image_bytes, review_image_content
from test.support.media_helpers import image_draft

pytestmark = pytest.mark.unit


async def test_default_web_projection_is_compact_and_selected_target_restores_exact_facts():
    from types import SimpleNamespace

    from app.tools.project_context import source_context
    from app.tools.video.preparation import canonical_resource

    view = {
        'view_id': 'hero', 'heading': 'Launch', 'width': 1440, 'height': 900,
        'digest': 'c' * 64, 'storage_key': 'sources/hero.png',
        'elements': [{
            'id': 'title', 'kind': 'heading', 'text': 'Launch', 'x': 0.5, 'y': 0.3,
            'w': 0.6, 'h': 0.15, 'css': {'font': 'serif'}, 'storage_key': 'sources/title.png',
        }],
    }
    snapshot = SourceSnapshot(
        id=uuid4(), owner_id=uuid4(), kind='web', digest='a' * 64,
        storage_key='sources/web.json', meta={'lines': [{'line_id': 'L1', 'text': 'Launch'}], 'views': [view]},
    )
    projected = source_context(snapshot)
    assert 'meta' not in projected and 'elements' not in projected['views'][0]
    assert projected['citable_lines'][0]['line_id'] == 'L1'
    assert projected['views'][0]['targets'][0]['id'] == 'title'
    assert 'css' not in projected['views'][0]['targets'][0]
    default = canonical_resource(snapshot)
    assert 'elements' not in default['views'][0] and 'selected_target' not in default
    selected = canonical_resource(
        snapshot, target=SimpleNamespace(view_id='hero', element_id='title'),
    )
    assert selected['selected_target']['view'] == view


def test_visual_review_legacy_findings_require_actual_evidence():
    from app.tools.video.media_analysis import ContentReviewAnswer

    finding = {
        "requirement": "The diagram shows the cited paper",
        "evidence": "The area at the center of the PNG is empty",
    }
    report = {"status": "fail", "summary": "Missing diagram", "observed_issue": [finding]}
    answer = ContentReviewAnswer.model_validate(report)
    assert answer.findings[0].kind == "observed_issue"
    assert answer.findings[0].evidence == finding["evidence"]
    with pytest.raises(ValueError, match="pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{"requirement": finding["requirement"]}],
        })
    with pytest.raises(ValueError, match="distinct pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{**finding, "evidence": finding["requirement"]}],
        })


@pytest.mark.asyncio
async def test_bad_svg_is_reported_before_quote():
    specs = [
        visual_assets.SceneAssetSpec(
            scene_id=f"scene-{i}", intent="Evidence",
            source={"kind": "controlled_svg", "program": (
                '<svg><rect rx rx="5"/></svg>' if i == 2 else '<svg><rect rx="5"/></svg>'
            )},
        )
        for i in range(6)
    ]
    with pytest.raises(ValueError, match=r"Scene scene-2: SVG is not well formed"):
        visual_assets.preflight_scene_svgs(specs)


@pytest.mark.asyncio
async def test_review_uses_scene_role_and_user_words_and_keeps_pixel_identity():

    _, specs = image_draft()
    spec = specs[1].model_copy(update={"intent": "Use a vertically mounted phone."})
    roles = {"s1": "Show the link to a source paper.", "s2": "Show a researcher communicating science."}
    words = ["Show the researcher in the second scene."]
    spec._review_basis = {"user_words": words, "scene_roles": roles}
    pixel_identity = spec.request_digest()
    first_version = spec.review_version()
    output = io.BytesIO()
    Image.new("RGB", (32, 18), "white").save(output, format="PNG")
    data = output.getvalue()
    facts = analyze_image_bytes(data, snapshot_id=str(uuid4()))

    reviewer = AsyncMock(return_value={"status": "pass", "summary": "Use case visible", "findings": []})
    async def review():
        return await review_image_content(data, scene_asset=spec, analysis=facts,
                                          analysis_ref={"digest": facts.report_digest}, reviewer=reviewer)
    first = await review()
    projection = json.loads(reviewer.await_args.kwargs["scene_asset_json"])
    assert "vertically" not in str(projection)
    assert projection["requirements"]["narrative"] == roles["s2"]
    assert projection["other_scene_roles"] == {"s1": "Show the link to a source paper."}
    assert first.status == "pass"

    spec._review_basis = {"scene_roles": roles, "user_words": [*words, "Use a vertically mounted phone."]}
    assert spec.request_digest() == pixel_identity and spec.review_version() != first_version
    reviewer.return_value = {"status": "fail", "summary": "Orientation mismatch", "findings": [{
        "kind": "observed_issue", "requirement": "user_1", "observed": "Horizontal phone",
        "evidence": "The grip holds the long edge parallel to the desk.",
    }]}
    second = await review()
    assert second.status == "fail"
    assert json.loads(reviewer.await_args.kwargs["scene_asset_json"])["requirements"]["user_1"] == (
        "Use a vertically mounted phone.")

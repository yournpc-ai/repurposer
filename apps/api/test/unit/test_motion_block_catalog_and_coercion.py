"""Unit tests for MotionBlock catalog_prompt_index optional_slots and LLM prop coercion."""

import pytest

pytestmark = pytest.mark.unit
from pydantic import ValidationError

from app.editing.catalog import MOTION_BLOCK_CATALOG, catalog_prompt_index
from app.editing.revisions import coerce_motion_block_props
from app.editing.schemas import MOTION_BLOCK_PROP_MODELS, MotionBlockObject

BOX = dict(x=0, y=0, width=1920, height=1080)


def test_catalog_prompt_index_exposes_optional_slots_for_all_motion_blocks():
    index = catalog_prompt_index()
    blocks = {b["id"]: b for b in index["motion_blocks"]}
    assert set(blocks) == set(MOTION_BLOCK_CATALOG) == set(MOTION_BLOCK_PROP_MODELS)
    for block_id, entry in blocks.items():
        assert "optional_slots" in entry
        assert isinstance(entry["optional_slots"], list)
        assert entry["optional_slots"] == MOTION_BLOCK_CATALOG[block_id]["optional_slots"]
    # Product showcase description must document valid camera_motion and normalized callout_steps
    ps_desc = blocks["product_showcase"]["desc"]
    assert "subtle_push" in ps_desc
    assert "callout_steps" in ps_desc
    assert "0..1" in ps_desc


def test_coerce_motion_block_props_handles_llm_string_numbers_and_int_step_labels():
    flow_props = coerce_motion_block_props(
        "flow_diagram",
        {
            "title": "Valuation Pipeline",
            "nodes": [
                {"step_label": 1, "title": "Frame", "detail": "Scope assets", "reveal_at_s": "0.5"},
                {"step_label": 2, "title": "Value", "detail": "Run models", "reveal_at_s": "2.0"},
                {"step_label": 3, "title": "Defend", "detail": "Audit trail", "reveal_at_s": "4.0"},
            ],
        },
    )
    obj = MotionBlockObject(
        kind="motion_block",
        object_id="obj_flow",
        block_id="flow_diagram",
        props=flow_props,
        layout=BOX,
    )
    assert obj.props["nodes"][0]["step_label"] == "1"
    assert obj.props["nodes"][0]["reveal_at_s"] == 0.5

    showcase_props = coerce_motion_block_props(
        "product_showcase",
        {
            "camera_motion": "subtle_push",
            "zoom_scale": "1.08",
            "callout_steps": [
                {
                    "start_s": "1.2",
                    "end_s": "4.5",
                    "label": "Indicated EV",
                    "x": "0.12",
                    "y": "0.24",
                    "width": "0.3",
                    "height": "0.18",
                }
            ],
        },
    )
    ps_obj = MotionBlockObject(
        kind="motion_block",
        object_id="obj_ps",
        block_id="product_showcase",
        props=showcase_props,
        resources=[
            {
                "path": "media/img_0.png",
                "snapshot_id": "00000000-0000-0000-0000-000000000001",
                "snapshot_digest": "a" * 64,
                "content_type": "image/png",
            }
        ],
        layout=BOX,
    )
    assert ps_obj.props["zoom_scale"] == 1.08
    assert ps_obj.props["callout_steps"][0]["start_s"] == 1.2


def test_coerce_motion_block_props_preserves_closed_schema_and_bounds():
    bad_extra = coerce_motion_block_props("statement_hook", {"headline": "Hi", "supporting_text": "Nope"})
    with pytest.raises(ValidationError):
        MotionBlockObject(
            kind="motion_block",
            object_id="obj_bad1",
            block_id="statement_hook",
            props=bad_extra,
            layout=BOX,
        )

    bad_coord = coerce_motion_block_props(
        "product_showcase",
        {
            "callout_steps": [
                {"start_s": "1.0", "end_s": "3.0", "label": "Too wide", "x": "1497", "y": "0.2", "width": "0.2", "height": "0.2"}
            ]
        },
    )
    with pytest.raises(ValidationError):
        MotionBlockObject(
            kind="motion_block",
            object_id="obj_bad2",
            block_id="product_showcase",
            props=bad_coord,
            layout=BOX,
        )

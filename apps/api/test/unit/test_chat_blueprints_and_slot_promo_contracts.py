"""Chat blueprints and slot promo — unit contracts."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.skills.blueprint import extract_skill_draft_from_composition
from test.support.blueprint_fixtures import _sample_master_composition

pytestmark = pytest.mark.unit


def test_extract_skill_draft_strips_private_snapshots_and_copy():
    content, origins, ids = _sample_master_composition()
    comp_id = uuid4()
    draft, bp = extract_skill_draft_from_composition(
        composition_id=comp_id,
        version_number=40,
        content=content,
        snapshot_origins=origins,
        name="OxValue Promo Blueprint!",
        description="4-act commercial studio promo structure.",
    )
    assert draft.name == "oxvalue-promo-blueprint"
    assert len(bp.acts) == 4
    assert [a.block_id for a in bp.acts] == [
        "statement_hook",
        "product_showcase",
        "metric_grid",
        "closing_cta",
    ]
    assert bp.acts[0].transition_after is not None
    assert bp.acts[0].transition_after.duration_s == pytest.approx(0.4, abs=0.01)
    assert len(bp.acts[1].overlays) == 1
    assert bp.acts[1].overlays[0].style_defaults["surface_style"] == "pill_caption"
    assert bp.audio_profile.has_bgm is True
    assert bp.audio_profile.bgm_fade_in_s == pytest.approx(1.2, abs=0.05)
    assert bp.audio_profile.bgm_fade_out_s == pytest.approx(2.0, abs=0.05)
    assert len(bp.sfx_cues) == 2
    assert bp.sfx_cues[0].recipe_id == "swoosh_cut"
    assert bp.sfx_cues[0].act_index == 0 and bp.sfx_cues[0].anchor == "cut_after"
    assert bp.sfx_cues[0].offset_s == pytest.approx(-0.15, abs=0.01)
    assert bp.sfx_cues[1].recipe_id == "stinger"
    assert (bp.sfx_cues[1].act_index, bp.sfx_cues[1].anchor) in {(2, "cut_after"), (3, "act_start")}
    assert bp.sfx_cues[1].offset_s == pytest.approx(0.1, abs=0.01)

    # Zero private snapshot UUIDs, master composition_id, or master copy/metrics leak into SKILL.md or blueprint.json
    bp_text = draft.references[0].text
    combined = draft.instructions + "\n" + bp_text
    assert draft.source_uri == f"composition://{comp_id}@v40"
    assert str(comp_id) not in combined
    assert "source_composition_uri" not in bp_text
    for sid in ids.values():
        assert str(sid) not in combined
    for secret in ("SECRET_MASTER_HEADLINE", "SECRET_BADGE", "SECRET_METRICS", "SECRET_BRAND", "SECRET_PILL_TEXT"):
        assert secret not in combined

    # Backward-compatible deserialization when legacy blueprint.json carries source_composition_uri
    from app.skills.blueprint import SkillBlueprintV1

    legacy = json.loads(bp_text)
    legacy["source_composition_uri"] = f"composition://{comp_id}@v40"
    parsed_legacy = SkillBlueprintV1.model_validate(legacy)
    assert parsed_legacy.source_composition_uri == f"composition://{comp_id}@v40"

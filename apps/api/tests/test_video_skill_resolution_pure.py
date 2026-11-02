"""C2/C5 structural guards for unified Skill references and first-design scope."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.chat.video_turn_seats import design_video_seat
from app.models.schemas import (
    BuiltInSkillReference,
    ChatMessageResponse,
    ChatRequest,
    DesignVideoArgs,
    ExternalSkillReference,
    ReviseVideoArgs,
    SkillOption,
)
from app.skills.resolution import resolve_named_skill
from app.tools.video.design import DesignError, _design_locked
from app.tools.video.params import ProduceVideoParams


def _builtin() -> SkillOption:
    return SkillOption(
        reference=BuiltInSkillReference(
            kind="builtin", skill_id="launch-film", version="1.3.0"
        ),
        skill_id="launch-film",
        name="launch-film",
        capabilities=["website_capture"],
    )


def _external(version_id=None, *, name="video-shotcraft", version_number=None) -> SkillOption:
    version_id = version_id or uuid4()
    return SkillOption(
        reference=ExternalSkillReference(
            kind="external", skill_version_id=version_id
        ),
        skill_id=str(uuid4()),
        name=name,
        capabilities=["animation:opacity"],
        version_number=version_number,
    )


def test_named_skill_binds_only_one_exact_accessible_reference() -> None:
    external = _external()
    resolved = resolve_named_skill(
        "Please use video-shotcraft for this new shot", [_builtin(), external]
    )
    assert resolved.reference == external.reference
    assert resolved.ambiguous == ()
    assert resolve_named_skill("launch film, please", [_builtin()]).reference == _builtin().reference
    assert resolve_named_skill("用launch-film做", [_builtin()]).reference == _builtin().reference
    chinese = _external(name="马克笔")
    assert resolve_named_skill("用马克笔做新镜头", [chinese]).reference == chinese.reference
    assert resolve_named_skill("make a product film", [_builtin(), external]).reference is None


def test_named_skill_version_or_name_collision_is_ambiguous_not_latest() -> None:
    v1 = _external(name="shotcraft", version_number=1)
    v2 = _external(name="shotcraft", version_number=2)
    collision = _external(name="launch-film")
    assert len(resolve_named_skill("use shotcraft", [v1, v2]).ambiguous) == 2
    assert len(resolve_named_skill("use launch-film", [_builtin(), collision]).ambiguous) == 2
    assert resolve_named_skill("use shotcraft v2", [v1, v2]).reference == v2.reference
    follow_up = resolve_named_skill("v2", [v1, v2], prior_options=(v1, v2))
    assert follow_up.reference == v2.reference
    assert len(resolve_named_skill("v3", [v1, v2], prior_options=(v1, v2)).ambiguous) == 2


def test_user_history_replays_raw_skill_without_reresolving_registry() -> None:
    reference = _external().reference.model_dump(mode="json")
    row = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": "user",
        "content": "use the pinned method",
        "intent": {"skill": reference},
        "created_at": datetime.now(UTC),
    }
    response = ChatMessageResponse.model_validate(row)
    assert response.skill is not None
    assert response.skill.model_dump(mode="json") == reference
    assistant = ChatMessageResponse.model_validate({**row, "role": "assistant"})
    assert assistant.skill is None
    ambiguous = ChatMessageResponse.model_validate({
        **row,
        "intent": {"skill_ambiguity": [reference]},
    })
    assert ambiguous.skill is None


def test_chat_request_has_skill_not_hidden_recipe_transport() -> None:
    reference = _builtin().reference
    request = ChatRequest(project_id=uuid4(), message="make it", skill=reference)
    assert request.skill == reference
    assert "recipe_id" not in request.model_dump(mode="json")
    with pytest.raises(ValueError):
        ChatRequest.model_validate({
            "project_id": str(uuid4()),
            "message": "make it",
            "skill": {"kind": "external", "skill_version_id": str(uuid4()), "scripts": ["x.py"]},
        })


def test_revision_and_production_have_no_skill_reload_transport() -> None:
    assert "skill" not in ReviseVideoArgs.model_fields
    assert "skill" not in ProduceVideoParams.model_fields
    assert "skill_reference" not in ProduceVideoParams.model_fields


@pytest.mark.asyncio
async def test_explicit_skill_never_redrafts_an_existing_version() -> None:
    args = DesignVideoArgs(
        composition_id=uuid4(), text="new direction", specific_instruction="new direction"
    )
    with pytest.raises(DesignError, match="new first version"):
        await _design_locked(
            None,
            owner_id=uuid4(),
            project_id=uuid4(),
            args=args,
            request_id="test",
            skill=SimpleNamespace(validate_design=lambda _args: None),
        )


@pytest.mark.asyncio
async def test_external_skill_never_falls_through_to_launch_film() -> None:
    skill = SimpleNamespace(
        validate_design=lambda _args: None,
        instruction=lambda value: value,
    )
    with pytest.raises(DesignError, match="built-in launch-film Skill was not executed"):
        await _design_locked(
            None,
            owner_id=uuid4(),
            project_id=uuid4(),
            args=DesignVideoArgs(material_urls=["https://example.test"]),
            request_id="test",
            skill=skill,
        )


@pytest.mark.asyncio
async def test_builtin_skill_rejects_non_website_design_before_agent() -> None:
    with pytest.raises(DesignError, match="website design"):
        await _design_locked(
            None,
            owner_id=uuid4(),
            project_id=uuid4(),
            args=DesignVideoArgs(text="not a website"),
            request_id="test",
            builtin_skill=_builtin().reference,
        )


@pytest.mark.asyncio
async def test_design_seat_relays_exact_reference_only_to_design(monkeypatch) -> None:
    reference = _external().reference
    seen = {}

    async def fake_design(**kwargs):
        seen.update(kwargs)
        return {
            "composition_id": str(uuid4()),
            "composition_name": "Test composition",
            "composition_version_id": str(uuid4()),
            "version": 1,
            "content_digest": "a" * 64,
            "storyboard": {
                "settings": {"width": 1920, "height": 1080, "fps": 30},
                "duration_seconds": 0,
                "scenes": [],
                "unassigned_clips": [],
                "sources": [],
            },
            "base_ref": {},
        }

    monkeypatch.setattr("app.tools.video.design.design_video", fake_design)
    monkeypatch.setattr("app.tools.video.programs.enrich_generator_previews", lambda read: _identity(read))
    monkeypatch.setattr("app.tools.video.programs.generator_preview_images", lambda read: _empty(read))
    monkeypatch.setattr("app.config.settings.video_project_enabled", True)
    project = SimpleNamespace(id=uuid4(), user_id=uuid4())
    read, _ = await design_video_seat(
        project=project,
        args=DesignVideoArgs(
            text="new copy", mode="program", specific_instruction="A moving diagram"
        ),
        request_id="test",
        skill=reference,
    )
    assert read is not None
    assert seen["skill_reference"] == reference


async def _identity(value):
    return value


async def _empty(_):
    return []

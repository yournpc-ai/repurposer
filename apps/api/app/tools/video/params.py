"""Authorized production and preparation inputs, never creative instructions."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.models.schemas import VideoDraftRef, VideoVersionRef
from app.tools.music.score import ScoreSpecDraft
from app.tools.video.visual_assets import (
    VISUAL_ASSET_MAX_PER_CALL,
    SceneAssetSpec,
    SceneId,
    VisualAssetSelection,
    select_scene_assets,
)

NARRATION_FIT_MARGIN = 1.08


class NarrationPolicy(BaseModel):
    """Server-pinned paid-fit bounds for one authorized production."""

    model_config = ConfigDict(extra="forbid")

    min_speed: float = Field(default=1.0, ge=1.0, le=2.0)
    max_speed: float = Field(default=1.35, ge=1.0, le=2.0)
    max_attempts: int = Field(default=2, ge=1, le=2)
    fit_margin: float = Field(default=NARRATION_FIT_MARGIN, ge=1.0, le=1.1)
    max_tts_characters: int = Field(ge=0)


def narration_policy(max_tts_characters: int) -> NarrationPolicy:
    return NarrationPolicy(max_tts_characters=max_tts_characters)


def narration_original_policy(max_tts_characters: int) -> NarrationPolicy:
    """One speed-1.0 original only; narration preparation never adapts it."""
    return NarrationPolicy(
        max_speed=1.0,
        max_attempts=1,
        max_tts_characters=max_tts_characters,
    )


class PrepareNarrationParams(BaseModel):
    """The exact final script and resolved voice for one original-only Run."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=9000)
    voice_id: str = Field(min_length=1, max_length=255)
    language: str = Field(min_length=2, max_length=16)
    draft_ref: VideoDraftRef | None = None
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)


class PrepareVisualAssetsParams(VisualAssetSelection):
    """One bounded batch from an authenticated working draft."""

    # Persisted plans and Runs may still contain the old full-spec request.
    scene_assets: SkipJsonSchema[list[SceneAssetSpec] | None] = Field(
        default=None, min_length=1, max_length=VISUAL_ASSET_MAX_PER_CALL
    )
    scene_ids: list[SceneId] | None = Field(
        default=None, min_length=1, max_length=VISUAL_ASSET_MAX_PER_CALL
    )

    @model_validator(mode="after")
    def _request_shape(self):
        if (self.scene_ids is None) == (self.scene_assets is None):
            raise ValueError("provide scene_ids to select scenes from the current draft")
        if self.review_existing and self.scene_ids is None:
            raise ValueError("review_existing requires scene_ids")
        return self

    def resolve(self, draft: dict) -> list[SceneAssetSpec]:
        if self.scene_ids is not None:
            return select_scene_assets(draft, self.scene_ids)

        # Keep historical authorization exact. Legacy plans cannot update a draft.
        legacy = self.scene_assets or []
        selected = select_scene_assets(draft, [spec.scene_id for spec in legacy])
        for current, supplied in zip(selected, legacy):
            if current != supplied:
                raise ValueError(f"Scene {current.scene_id} does not match its current SceneAssetSpec")
        return selected


class PrepareMusicParams(BaseModel):
    """One bounded creative score resolved against an authorized working draft."""

    model_config = ConfigDict(extra="forbid")

    draft_ref: VideoDraftRef
    name: str = Field(min_length=1, max_length=255)
    score: ScoreSpecDraft


class ProduceVideoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_ref: VideoVersionRef = Field(
        description="复制 get_video_version 返回的确切 base_ref，直接渲染该保存版本，不重新设计。"
    )
    regenerate_media: bool = Field(
        default=False,
        description=(
            "仅当用户明确要求重新生成模型图片时设为 true。新 Run 会生成新媒体，该 Run 重试仍复用其固定结果。常规制作、恢复和原生内容编辑均保持 false。"
        ),
    )

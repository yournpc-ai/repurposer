"""Bounds for authorized narration generation."""
from pydantic import BaseModel, ConfigDict, Field

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

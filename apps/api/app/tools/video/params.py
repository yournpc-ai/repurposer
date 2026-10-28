"""Production names an immutable saved version; never creative instructions."""
from pydantic import BaseModel, ConfigDict, Field
from app.models.schemas import VideoVersionRef


class NarrationPolicy(BaseModel):
    """Server-pinned paid-fit bounds for one authorized production."""

    model_config = ConfigDict(extra="forbid")

    min_speed: float = Field(default=1.0, ge=1.0, le=2.0)
    max_speed: float = Field(default=1.35, ge=1.0, le=2.0)
    max_attempts: int = Field(default=2, ge=1, le=2)
    fit_margin: float = Field(default=1.02, ge=1.0, le=1.1)
    max_tts_characters: int = Field(ge=0)


def narration_policy(max_tts_characters: int) -> NarrationPolicy:
    return NarrationPolicy(max_tts_characters=max_tts_characters)


class ProduceVideoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_ref: VideoVersionRef = Field(
        description="Exact base_ref from get_video_version; renders this saved version without redesign."
    )
    regenerate_media: bool = Field(
        default=False,
        description=(
            "True ONLY when the user explicitly asks to generate the model image again. "
            "A new Run generates fresh media; retries of that Run still reuse its fixed result. "
            "Ordinary production, recovery and native-content edits keep this false."
        ),
    )

"""Production names an immutable saved version; never creative instructions."""
from pydantic import BaseModel, ConfigDict, Field
from app.models.schemas import VideoVersionRef


class ProduceVideoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_ref: VideoVersionRef = Field(
        description="Exact base_ref from get_video_version; renders this saved version without redesign."
    )

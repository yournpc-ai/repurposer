"""ReframeClipParams — compile-time adjudication document (see registry)."""

from typing import Literal

from pydantic import BaseModel, Field


class ReframeClipParams(BaseModel):
    target_output_id: str | None = Field(
        default=None,
        description="Reframe only this one output (uuid); null = all clips in scope",
    )
    mode: Literal["auto", "interview_switch", "speaker_follow", "static_center"] = Field(
        default="auto",
        description="auto picks by the footage (interview → interview_switch, one "
        "moving speaker → speaker_follow, else static_center); an explicit mode "
        "forces it. static_center = plain center crop, undoing any reframe.",
    )

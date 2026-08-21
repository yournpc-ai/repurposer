"""ReviseScriptParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class ReviseScriptParams(BaseModel):
    scope: str = Field(default="clip", description="Scope of the revision (default 'clip')")
    target_output_id: str | None = Field(
        default=None, description="Revise only this one output (uuid); null = the turn's current target"
    )
    instruction: str | None = Field(
        default=None, description="How to revise (shorter / longer / tone / language); null = the user's message text"
    )

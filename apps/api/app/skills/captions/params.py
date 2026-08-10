"""TranslateClipParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class TranslateClipParams(BaseModel):
    target_output_id: str | None = Field(default=None, description="Translate only this one output (uuid); null = all clips in scope")
    target_language: str = Field(description="ISO code of the caption language (required — no meaningful default)")

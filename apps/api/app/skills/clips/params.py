"""Clip-level params schemas — compile-time adjudication documents.

Field descriptions are injected into the intent agent's proposal prompt —
they ARE the LLM's parameter documentation, so write them as "when to use /
what null means", not as type restatements.
"""

from pydantic import BaseModel, Field


class SelectClipsParams(BaseModel):
    count: int = Field(default=5, description="How many highlight clips to cut")

"""Clip-level params schemas — compile-time adjudication documents.

Field descriptions are injected into the intent agent's proposal prompt —
they ARE the LLM's parameter documentation, so write them as "when to use /
what null means", not as type restatements.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SelectClipsParams(BaseModel):
    count: int = Field(default=3, description="How many highlight clips to cut")
    language: str | None = Field(
        default=None,
        description="ISO code for the clips' on-screen copy (titles). null = "
        "the source material's language — captions themselves always follow "
        "the spoken words; set this only when the user asks for another "
        "language's on-screen text.",
    )
    focus: str | None = Field(
        default=None,
        description="A short angle phrase when the user assigns the clips a "
        "theme (e.g. '切片剪定价争议' → 'pricing debate'). null = the "
        "the planner picks the strongest moments.",
    )
    aspect: Literal["9:16", "1:1", "16:9"] | None = Field(
        default=None,
        description="Frame format — set ONLY when the user explicitly names "
        "one ('竖版/vertical', '方形/square', '横版/landscape/16:9') or asks "
        "to keep the source's original frame (then pick the value matching "
        "the source's shape). null = the brand default (9:16).",
    )

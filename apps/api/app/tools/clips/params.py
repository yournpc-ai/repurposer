"""Clip-level params schemas — compile-time adjudication documents.

Field descriptions are injected into the intent agent's proposal prompt —
they ARE the LLM's parameter documentation, so write them as "when to use /
what null means", not as type restatements. (cut_segments excepted:
``llm_visible=False`` — its params document the COMPILER's contract.)
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SelectClipsParams(BaseModel):
    count: int = Field(default=1, description="How many highlight clips to cut")
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


class CutSegmentSpan(BaseModel):
    """One span to materialize — compiler-resolved numbers. The exploration
    door already validated the range verbatim against the asset's word
    timeline; the compiler dereferences the Select's pointer, never judges."""

    start: float = Field(ge=0, description="Span start, source seconds.")
    end: float = Field(gt=0, description="Span end, source seconds — must exceed start.")

    @model_validator(mode="after")
    def _ordered(self) -> "CutSegmentSpan":
        if self.end <= self.start:
            raise ValueError(f"span end ({self.end}) must exceed start ({self.start})")
        return self


class CutSegmentsParams(BaseModel):
    """cut_segments — the compiler-facing deterministic clip producer
    (ADR-089 §2, iter-2 ①, N-56). NEVER LLM-proposed (``llm_visible=False``)
    — these descriptions document the compiler's contract, not a prompt.
    No discovery semantics by construction: no focus, no count, no ranking —
    the spans ARE the decision. Language versions / caption forms / dubbing
    are transform semantics with their own capabilities (translate_clip /
    dub_clip chained by the compiler), never birth params. ``extra=forbid``
    (research precedent): the compiler is the only caller — a smuggled key
    is a compiler bug and must fail loudly, not be silently dropped."""

    model_config = ConfigDict(extra="forbid")

    segments: list[CutSegmentSpan] = Field(
        min_length=1,
        max_length=5,
        description="The source spans to materialize, one clip each. "
        "Compiler granularity law (R20-clean): one task per Content Plan "
        "clip output — never merge several plans' spans into one call.",
    )
    asset_id: str | None = Field(
        default=None,
        description="The asset the spans belong to — the Select's unique "
        "source made explicit (the compiler resolves it from the Candidate "
        "Set and always sets it). null = the shared render-source pool "
        "rules pick (same semantics as the source pin).",
    )
    aspect: Literal["9:16", "1:1", "16:9"] | None = Field(
        default=None,
        description="Frame format at birth (a birth property — the clip-spec "
        "bakes the frame; no downstream capability can change it). Set from "
        "the plan's aspect field when the user named one; null = the brand "
        "default.",
    )

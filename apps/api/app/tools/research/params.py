"""research tool params (ADR-052 B4). Field descriptions ARE the LLM's
parameter documentation (they ride the registry's catalog projection into
the intent prompt) — write them as "when to use / what null means"."""

from pydantic import BaseModel, ConfigDict, Field


class ResearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        description="The research question to ground with fresh web facts — specific and "
        "self-contained (names the topic, not 'the above')."
    )
    angle: str | None = Field(
        default=None,
        description="Optional emphasis narrowing the search (e.g. 'EU-focused', '2026 "
        "developments'); null = broad coverage of the query.",
    )

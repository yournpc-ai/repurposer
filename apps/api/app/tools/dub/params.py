"""DubClipParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class DubClipParams(BaseModel):
    voice: str | None = Field(default=None, description="Reserved — currently unwired: the dub chain voices from the project's own material (persona.voice binding is a deferred item, PROGRESS 需求池). Do not rely on it in proposals")
    target_output_id: str | None = Field(default=None, description="Dub only this one output (uuid); null = all clips in scope")
    target_language: str = Field(default="en", description="ISO code of the language to dub into")
    # agent-loop-upgrade W5: mode② spec = params.model_dump() carries this
    # into spec.fork, which run_dub_clip already reads — "再来一版/加一版"
    # stops overwriting the source clip.
    fork: bool = Field(
        default=False,
        description="True = create a NEW derived version and keep the source clip untouched (user said "
        "'再来一版' / '加一版' / 'another version' or asked to keep the original); False = rewrite in place",
    )

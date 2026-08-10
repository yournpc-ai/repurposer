"""DubClipParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class DubClipParams(BaseModel):
    voice: str | None = Field(default=None, description="Voice-clone id; null = the persona's own cloned voice")
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
